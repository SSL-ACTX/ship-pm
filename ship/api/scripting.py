"""Template, inline script rendering, wrapper generation, and declarative patch recipes."""

from __future__ import annotations

import re
import shlex
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ship.api.toolkit import PatchContext, PatchReport, RuntimeCommand
    from ship.core.profile import Profile


class InlineScript:
    """A clean, dedented inline shell script with typed template substitution.

    Eliminates raw multi-line string indents, hardcoded paths, and manual escaping.
    Placeholders like ``@profile.bash@``, ``@target@``, or custom kwargs are substituted.
    """

    def __init__(
        self,
        template: str,
        shebang: str | Path | None = None,
        **defaults: Any,
    ) -> None:
        self.raw_template = textwrap.dedent(template).strip()
        self.shebang = shebang
        self.defaults = defaults

    def render(
        self,
        profile: Profile | None = None,
        context: PatchContext | None = None,
        **kwargs: Any,
    ) -> str:
        values: dict[str, Any] = dict(self.defaults)
        values.update(kwargs)

        if profile is not None:
            values.setdefault("profile.bash", str(profile.paths.bash))
            values.setdefault("profile.sh", str(profile.paths.sh))
            values.setdefault("profile.prefix", str(profile.paths.prefix))
            if hasattr(profile.paths, "glibc_lib"):
                values.setdefault("profile.glibc_lib", str(profile.paths.glibc_lib))
            if hasattr(profile.paths, "glibc_prefix"):
                values.setdefault(
                    "profile.glibc_prefix", str(profile.paths.glibc_prefix)
                )
            values.setdefault("profile.is_termux", profile.is_termux)
            values.setdefault(
                "profile.tls_cert", "/data/data/com.termux/files/usr/etc/tls/cert.pem"
            )
            values.setdefault(
                "profile.tls_cert_dir", "/data/data/com.termux/files/usr/etc/tls"
            )

        if context is not None:
            values.setdefault("context.install_dir", str(context.install_dir))
            values.setdefault("context.package_name", context.package_name)
            values.setdefault("context.target_key", context.target_key)

        content = self.raw_template
        for key, val in values.items():
            content = content.replace(f"@{key}@", str(val))

        # Check for any unrendered @...@ tokens
        unrendered = re.findall(r"@([a-zA-Z0-9_.]+)@", content)
        if unrendered:
            raise ValueError(
                f"Unrendered template placeholders in InlineScript: {unrendered}"
            )

        shebang_path = self.shebang
        if shebang_path is None and profile is not None:
            shebang_path = profile.paths.bash

        if shebang_path:
            return f"#!{shebang_path}\n{content}\n"
        return f"{content}\n"


@dataclass
class WrapperBuilder:
    """Builder for binary wrappers, dynamic link interceptors, and subcommand forwarders.

    Handles renaming originals to ``<name>-real``, writing robust launchers,
    setting file modes, and change recording automatically.
    """

    target_binary: str | Path
    real_binary_suffix: str = "-real"
    shebang: str | Path | None = None
    unset: list[str] = field(default_factory=lambda: ["LD_PRELOAD"])
    environment: dict[str, str | Path] = field(default_factory=dict)
    before: str = ""
    after: str = ""
    rewrite_args: dict[str, str | Path] = field(default_factory=dict)
    append_args_if: list[tuple[str, list[str]]] = field(default_factory=list)
    exec_name: str | None = None  # for exec -a "$0"

    def apply(self, context: PatchContext) -> Path:
        binary_path = context.resolve(self.target_binary)
        if not binary_path.exists():
            raise FileNotFoundError(f"target binary does not exist: {binary_path}")

        real_binary = binary_path.with_name(
            f"{binary_path.name}{self.real_binary_suffix}"
        )
        if not real_binary.exists():
            binary_path.replace(real_binary)
            try:
                real_binary.chmod(real_binary.stat().st_mode | 0o755)
            except OSError:
                pass
            context.record(real_binary, "move aside", f"-> {real_binary.name}")

        shebang = self.shebang
        if shebang is None:
            if context.profile is not None:
                shebang = context.profile.paths.bash
            else:
                shebang = "/bin/bash"

        lines = [f"#!{shebang}"]
        for var in self.unset:
            lines.append(f"unset {var}")

        for k, v in self.environment.items():
            # Double-quote so shell expansions in values (e.g. ${PATH:-}) are preserved.
            safe = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'export {k}="{safe}"')

        if self.before:
            lines.append(textwrap.dedent(self.before).strip())

        needs_arg_loop = bool(self.rewrite_args or self.append_args_if)
        if needs_arg_loop:
            lines.append("ARGS=()")
            flag_vars: dict[str, str] = {}
            for idx, (trigger, _) in enumerate(self.append_args_if):
                vname = f"__FLAG_HAS_{idx}"
                flag_vars[trigger] = vname
                lines.append(f"{vname}=0")

            lines.append('for arg in "$@"; do')
            for trigger, vname in flag_vars.items():
                lines.append(
                    f'  if [[ "$arg" == {shlex.quote(trigger)} ]]; then {vname}=1; fi'
                )

            if self.rewrite_args:
                for idx, (pattern, repl) in enumerate(self.rewrite_args.items()):
                    if idx == 0:
                        lines.append(f'  if [[ "$arg" == {pattern} ]]; then')
                    else:
                        lines.append(f'  elif [[ "$arg" == {pattern} ]]; then')
                    lines.append(f"    ARGS+=({shlex.quote(str(repl))})")
                lines.append("  else")
                lines.append('    ARGS+=("$arg")')
                lines.append("  fi")
            else:
                lines.append('  ARGS+=("$arg")')
            lines.append("done")

            for trigger, to_append in self.append_args_if:
                vname = flag_vars[trigger]
                appended_str = " ".join(shlex.quote(a) for a in to_append)
                lines.append(f"if [[ ${vname} -eq 1 ]]; then")
                lines.append(f"  ARGS+=({appended_str})")
                lines.append("fi")

            target_call = f'"{real_binary.resolve()}" "${{ARGS[@]}}"'
        else:
            target_call = f'"{real_binary.resolve()}" "$@"'

        if self.exec_name:
            if self.exec_name == "$0":
                exec_part = f'exec -a "$0" {target_call}'
            else:
                exec_part = f"exec -a {shlex.quote(self.exec_name)} {target_call}"
        else:
            exec_part = f"exec {target_call}"

        if not self.after:
            lines.append(exec_part)
        else:
            lines.append(target_call)
            lines.append("EXIT_CODE=$?")
            lines.append(textwrap.dedent(self.after).strip())
            lines.append("exit $EXIT_CODE")

        content = "\n".join(lines) + "\n"
        binary_path.write_text(content, encoding="utf-8")
        binary_path.chmod(0o755)
        context.record(binary_path, "install wrapper", f"wrapping {real_binary.name}")
        return binary_path


def promote_nested_directory(
    context: PatchContext,
    subfolder_pattern: str = "*",
    target_dir: str = "bin",
) -> int:
    """Promotes files from nested archive directories (e.g. ``pkg-1.0/bin/*`` to root ``bin/``).

    Solves the repetitive archive flattening logic across multiple packages.
    """
    top_target = context.install_dir / target_dir
    top_target.mkdir(parents=True, exist_ok=True)

    count = 0
    for child in sorted(context.install_dir.iterdir()):
        if not child.is_dir() or child.name == target_dir:
            continue
        if not child.match(subfolder_pattern):
            continue

        candidate = child / target_dir
        if candidate.is_dir():
            for src in sorted(candidate.iterdir()):
                if not src.is_file():
                    continue
                dest = top_target / src.name
                if not dest.exists() and not dest.is_symlink():
                    dest.symlink_to(src.resolve())
                    context.record(
                        dest, "promote", f"-> {src.relative_to(context.install_dir)}"
                    )
                    count += 1
            break
    return count


def resolve_soname_symlinks(
    context: PatchContext,
    soname_map: dict[str, str],
    target_subpath: str = "lib",
) -> int:
    """Symlinks missing dynamic library sonames from host/profile glibc lib paths into package lib/."""
    profile = context.profile
    if profile is None or not profile.is_termux:
        return 0

    lib_dir = context.install_dir / target_subpath
    if not lib_dir.is_dir():
        for child in sorted(context.install_dir.iterdir()):
            if child.is_dir() and child.name not in ("glibc", "sysroot"):
                candidate = child / target_subpath
                if candidate.is_dir():
                    lib_dir = candidate
                    break
        else:
            return 0

    glibc_lib = getattr(profile.paths, "glibc_lib", None)
    if not glibc_lib or not glibc_lib.is_dir():
        return 0

    count = 0
    for soname, real_name in soname_map.items():
        link = lib_dir / soname
        if link.exists() or link.is_symlink():
            continue
        source = glibc_lib / real_name
        if source.is_file():
            link.symlink_to(source)
            context.record(link, "soname compat", f"-> {source}")
            count += 1
    return count


def patch_subtree_binaries(
    context: PatchContext,
    glob_pattern: str = "**/*",
    patcher_fn: Any = None,
) -> int:
    """Discovers internal ELF binaries matching a glob pattern and applies runtime patchers.

    Solves the repetitive bundled toolchain and solver patching (e.g. F* bundling Z3,
    or toolchains embedding precompiled internal tools).
    """
    from ship.api.toolkit import inspect_elf
    from ship.runtime import apply_patchers

    effective_patcher = patcher_fn if patcher_fn is not None else apply_patchers
    count = 0
    for binary_path in context.install_dir.glob(glob_pattern):
        if (
            not binary_path.is_file()
            or binary_path.is_symlink()
            or binary_path.name.endswith("-real")
        ):
            continue

        elf_info = inspect_elf(binary_path)
        if elf_info is None:
            continue

        arch = elf_info.architecture
        abi = elf_info.abi
        target_key = f"{arch}-linux-{abi}" if arch else context.target_key

        binary_path.chmod(0o755)
        effective_patcher(binary_path, target_key, context.report)
        count += 1
    return count


def qemu_command(
    real_binary: Path | str,
    arch: str = "aarch64",
    profile: Profile | None = None,
) -> RuntimeCommand | None:
    """Convenience helper to wrap a binary with qemu and sysroot prefix for Termux bypass."""
    import shutil

    from ship.api.toolkit import RuntimeCommand
    from ship.core.profile import get_active_profile

    prof = profile or get_active_profile()
    if not prof.is_termux:
        return None

    qemu_bin = shutil.which(f"qemu-{arch}")
    if not qemu_bin:
        return None

    return RuntimeCommand(
        argv=(qemu_bin, "-L", prof.paths.prefix, str(real_binary)),
    )


def patch_external_toolchain(
    root_dir: Path | str,
    subdirs: tuple[str, ...] = ("bin", "lib", "libexec"),
    skip_dirs: tuple[str, ...] = (),
    report: PatchReport | None = None,
) -> int:
    """Patches dynamically downloaded or updated external toolchain ELFs (rustup, juliaup, etc.)."""
    import shutil
    import subprocess

    from ship.api.toolkit import (
        BinaryQuery,
        find_binaries,
        inspect_elf,
        set_elf_interpreter,
        set_elf_rpath,
    )
    from ship.core.profile import get_active_profile
    from ship.runtime.termux import termux_glibc_loader_path, termux_glibc_prefix

    profile = get_active_profile()
    if not profile.is_termux:
        return 0

    root = Path(root_dir)
    if not root.is_dir():
        return 0

    loader = termux_glibc_loader_path()
    patchelf = shutil.which("patchelf")
    if not loader or not loader.is_file() or not patchelf:
        return 0

    glibc_lib = termux_glibc_prefix() / "lib"

    # Collect target subdirectories
    target_roots: list[Path] = []
    if subdirs:
        for child in root.iterdir():
            if not child.is_dir():
                continue
            for sub in subdirs:
                p = child / sub
                if p.is_dir():
                    target_roots.append(p)
    else:
        target_roots = [root]

    count = 0
    for base_dir in target_roots:
        query = BinaryQuery(
            executable_only=False,
            excluded_directory_names=skip_dirs,
        )
        for path in find_binaries(base_dir, query):
            try:
                info = inspect_elf(path)
                if info is None:
                    continue
                if info.abi == "glibc":
                    rpath = f"{glibc_lib}:{path.parent}:{path.parent.parent / 'lib'}:{path.parent.parent / 'lib' / 'julia'}"
                    if set_elf_interpreter(path, loader, patchelf=patchelf):
                        if report is not None:
                            report.add(path, "set ELF interpreter", str(loader))
                        count += 1
                    if set_elf_rpath(path, rpath, patchelf=patchelf):
                        if report is not None:
                            report.add(path, "set ELF RPATH", rpath)
                        count += 1
                elif path.name.endswith(".so") or ".so." in path.name:
                    rpath = f"{glibc_lib}:{path.parent}:{path.parent.parent / 'lib'}"
                    if set_elf_rpath(path, rpath, patchelf=patchelf):
                        if report is not None:
                            report.add(path, "set ELF RPATH", rpath)
                        count += 1
            except (OSError, subprocess.SubprocessError):
                continue

    return count
