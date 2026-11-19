"""Declarative, unified, and modern package patch recipes and builder API."""

from __future__ import annotations

import fnmatch
import shutil
import subprocess
import textwrap
from collections.abc import Callable, Sequence
from enum import Enum, auto
from pathlib import Path
from typing import Any

from ship.api.code import SourcePatcher
from ship.api.scripting import (
    WrapperBuilder,
    patch_external_toolchain,
    patch_subtree_binaries,
    promote_nested_directory,
    resolve_soname_symlinks,
)
from ship.api.toolkit import (
    ArgumentCondition,
    ArgumentEquals,
    ArgumentOneOf,
    ExportPolicy,
    InstallHandler,
    InstallPatch,
    PackagePatch,
    PatchContext,
    PatchRecipe,
    ReapplyHandler,
    RuntimeCommand,
    RuntimePatch,
    RuntimeValue,
    raise_tls_alignment,
    shell_exec,
    shell_export,
)
from ship.core.profile import Profile, get_active_profile


class Mixin(Enum):
    """Platform adaptation mixins."""

    PosixShellSanitizer = auto()
    DisableBwrapSandbox = auto()
    BionicCompat = auto()
    AndroidShmem = auto()


class BuildContext:
    """Execution context provided to post_install and lifecycle hooks."""

    def __init__(self, install_dir: Path | str, home: Path | str | None = None) -> None:
        self.install_dir = Path(install_dir)
        self.home = Path(home) if home else Path.home()

    def exec(self, cmd: list[str], cwd: Path | None = None) -> int:
        """Run command synchronously inside the install/build tree."""
        return subprocess.run(cmd, cwd=cwd or self.install_dir, check=False).returncode

    def register_interceptor(
        self,
        tool: str,
        env_trigger: str,
        packages: list[str],
        c_flags: list[str] | None = None,
        ld_flags: list[str] | None = None,
        polyfills: list[str] | None = None,
    ) -> None:
        """Register dynamic toolchain build interceptor."""
        from ship.runtime.intercept import BuildInterceptor

        BuildInterceptor.register_rule(
            tool=tool,
            env_trigger=env_trigger,
            packages=packages,
            c_flags=c_flags,
            ld_flags=ld_flags,
            polyfills=polyfills,
        )


def _matches_platform(
    profile: Profile,
    target_key: str,
    *,
    platform: str | None = None,
    arch: str | None = None,
    target_pattern: str | None = None,
) -> bool:
    """Evaluate whether the active profile and target match the condition."""
    if platform is not None:
        p = platform.lower()
        if p in ("termux", "android") and not profile.is_termux:
            return False
        if p == "linux" and (profile.is_termux or profile.os != "linux"):
            return False
        if p == "darwin" and profile.os != "darwin":
            return False

    if arch is not None:
        target_arch = target_key.split("-")[0] if target_key else ""
        if arch.lower() != target_arch.lower():
            return False

    if target_pattern is not None:
        return fnmatch.fnmatchcase(target_key, target_pattern)

    return True


class PlatformCondition:
    """Predicate condition based on OS, environment profile, target triple, and arch."""

    def __init__(
        self,
        platform: str | None = None,
        *,
        arch: str | None = None,
        target: str | None = None,
        custom: Callable[[Profile, str], bool] | None = None,
    ) -> None:
        self.platform = platform
        self.arch = arch
        self.target = target
        self.custom = custom

    def check(self, profile: Profile, target_key: str) -> bool:
        if not _matches_platform(
            profile,
            target_key,
            platform=self.platform,
            arch=self.arch,
            target_pattern=self.target,
        ):
            return False
        if self.custom is not None:
            return self.custom(profile, target_key)
        return True


def on_platform(
    platform: str | None = None,
    *,
    arch: str | None = None,
    target: str | None = None,
) -> PlatformCondition:
    """Factory helper to construct a declarative platform condition."""
    return PlatformCondition(platform=platform, arch=arch, target=target)


def on_termux(
    arch: str | None = None,
    *,
    target: str | None = None,
) -> PlatformCondition:
    """Shorthand for Termux-specific condition."""
    return PlatformCondition(platform="termux", arch=arch, target=target)


class RecipeAction:
    """An executable action performed during a specific lifecycle stage."""

    def __init__(
        self,
        func: Callable[[PatchContext], None],
        stage: str = "pre_link",
        condition: PlatformCondition | None = None,
        description: str = "",
    ) -> None:
        self.func = func
        self.stage = stage
        self.condition = condition
        self.description = description

    def execute(self, context: PatchContext) -> None:
        profile = context.profile or get_active_profile()
        if self.condition is not None and not self.condition.check(
            profile, context.target_key
        ):
            return
        self.func(context)


class PackageRecipe:
    """Unified, fluent declarative package recipe builder.

    Supports layout manipulation, file templating, ELF and toolchain patching,
    runtime command interception, and full compilation to PackagePatch.
    """

    def __init__(
        self,
        name: str = "",
        version: str = "",
        mixins: Sequence[Mixin] | None = None,
        prebuilts: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.mixins: list[Mixin] = list(mixins) if mixins is not None else []
        self.prebuilts: dict[str, str] = (
            dict(prebuilts) if prebuilts is not None else {}
        )

        # Export policy config
        self._export_only: tuple[str, ...] = ()
        self._export_exclude: tuple[str, ...] = ()
        self._export_internal_only: tuple[str, ...] = ()
        self._export_aliases: dict[str, str] = {}
        self._discover_all_bins: bool = False
        self._allow_foreign_binaries: bool = False

        # Lifecycle actions
        self._actions: list[RecipeAction] = []
        self._runtime_patches: list[RuntimePatch] = []
        self._reapply_handlers: list[ReapplyHandler] = []

    # -------------------------------------------------------------------------
    # Export Policy
    # -------------------------------------------------------------------------

    def export(
        self,
        only: Sequence[str] | None = None,
        exclude: Sequence[str] | None = None,
        internal_only: Sequence[str] | None = None,
        aliases: dict[str, str] | None = None,
        *,
        discover_all_bins: bool | None = None,
        allow_foreign_binaries: bool | None = None,
    ) -> PackageRecipe:
        """Configure which package binaries are exposed or kept private."""
        if only is not None:
            self._export_only = tuple(only)
        if exclude is not None:
            self._export_exclude = tuple(exclude)
        if internal_only is not None:
            self._export_internal_only = tuple(internal_only)
        if aliases is not None:
            self._export_aliases.update(aliases)
        if discover_all_bins is not None:
            self._discover_all_bins = discover_all_bins
        if allow_foreign_binaries is not None:
            self._allow_foreign_binaries = allow_foreign_binaries
        return self

    # -------------------------------------------------------------------------
    # Layout and Filesystem Primitives
    # -------------------------------------------------------------------------

    def flatten_nested_root(
        self, pattern: str = "*", *, stage: str = "post_extract"
    ) -> PackageRecipe:
        """If package extracted with a single nested top-level folder, promote its contents."""

        def _flatten(context: PatchContext) -> None:
            target_prefix = context.install_dir
            nested = [
                d
                for d in context.install_dir.glob(pattern)
                if d.is_dir() and d.name != "ship-state"
            ]
            if len(nested) == 1 and nested[0].is_dir():
                target_prefix = nested[0]
                for item in target_prefix.iterdir():
                    dest = context.install_dir / item.name
                    if not dest.exists():
                        shutil.move(str(item), str(dest))
                        context.record(dest, "promoted", f"from {nested[0].name}")
                shutil.rmtree(target_prefix, ignore_errors=True)

        self._actions.append(
            RecipeAction(_flatten, stage=stage, description=f"flatten {pattern}")
        )
        return self

    def promote_nested_directory(
        self,
        target_dir: str = "bin",
        *,
        stage: str = "pre_link",
        condition: PlatformCondition | None = None,
    ) -> PackageRecipe:
        """Flatten and promote a nested subfolder (e.g. nested bin/ or lib/) up to root."""

        def _promote(context: PatchContext) -> None:
            promote_nested_directory(context, target_dir=target_dir)

        self._actions.append(
            RecipeAction(
                _promote,
                stage=stage,
                condition=condition,
                description=f"promote nested {target_dir}",
            )
        )
        return self

    def symlink(
        self,
        source: str | Path,
        to: str | Path,
        *,
        stage: str = "pre_link",
        condition: PlatformCondition | None = None,
    ) -> PackageRecipe:
        """Create a symlink inside the install tree."""

        def _symlink(context: PatchContext) -> None:
            src_path = context.resolve(source)
            dst_path = context.resolve(to)
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            if not dst_path.exists() and not dst_path.is_symlink():
                dst_path.symlink_to(src_path)
                context.record(dst_path, "symlink", f"-> {src_path.name}")

        self._actions.append(
            RecipeAction(
                _symlink,
                stage=stage,
                condition=condition,
                description=f"symlink {to} -> {source}",
            )
        )
        return self

    def write_template(
        self,
        path: str | Path,
        content: str,
        *,
        mode: int = 0o644,
        stage: str = "pre_link",
        condition: PlatformCondition | None = None,
        **kwargs: Any,
    ) -> PackageRecipe:
        """Write a formatted text/configuration template inside the package root."""

        def _write(context: PatchContext) -> None:
            dest = context.resolve(path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            profile = context.profile or get_active_profile()

            # Substitution mappings
            bindings: dict[str, Any] = {
                "install_dir": str(context.install_dir),
                "bin_dir": str(context.install_dir / "bin"),
                "lib_dir": str(context.install_dir / "lib"),
                "target_key": context.target_key,
                "profile.bash": str(profile.paths.bash),
                "profile.prefix": str(profile.paths.prefix),
            }
            if hasattr(profile.paths, "sh"):
                bindings["profile.sh"] = str(profile.paths.sh)
            if hasattr(profile.paths, "glibc_lib"):
                bindings["profile.glibc_lib"] = str(profile.paths.glibc_lib)
            if hasattr(profile.paths, "glibc_prefix"):
                bindings["profile.glibc_prefix"] = str(profile.paths.glibc_prefix)
            bindings.update(kwargs)

            rendered = textwrap.dedent(content).strip()
            for k, v in bindings.items():
                rendered = rendered.replace(f"{{{k}}}", str(v))
                rendered = rendered.replace(f"@{k}@", str(v))

            dest.write_text(rendered + "\n", encoding="utf-8")
            dest.chmod(mode)
            context.record(dest, "write", f"template: {dest.name}")

        self._actions.append(
            RecipeAction(
                _write,
                stage=stage,
                condition=condition,
                description=f"template {path}",
            )
        )
        return self

    def ensure_dirs(
        self,
        *dirs: str | Path,
        stage: str = "pre_link",
        condition: PlatformCondition | None = None,
    ) -> PackageRecipe:
        """Ensure specific subdirectories exist inside the install tree."""

        def _mkdir(context: PatchContext) -> None:
            for d in dirs:
                p = context.resolve(d)
                p.mkdir(parents=True, exist_ok=True)

        self._actions.append(
            RecipeAction(
                _mkdir, stage=stage, condition=condition, description="ensure dirs"
            )
        )
        return self

    # -------------------------------------------------------------------------
    # ELF & Toolchain Adjustments
    # -------------------------------------------------------------------------

    def raise_tls_alignment(
        self,
        binaries: Sequence[str | Path],
        *,
        alignment: int = 64,
        stage: str = "pre_link",
        condition: PlatformCondition | None = None,
    ) -> PackageRecipe:
        """Raise ELF PT_TLS segment alignment (commonly needed on Android/Termux for static binaries)."""

        def _tls(context: PatchContext) -> None:
            for b in binaries:
                p = context.resolve(b)
                if (
                    p.is_file()
                    and not p.is_symlink()
                    and raise_tls_alignment(p, alignment=alignment)
                ):
                    context.record(p, "adjusted PT_TLS alignment", f"{alignment} bytes")

        self._actions.append(
            RecipeAction(
                _tls,
                stage=stage,
                condition=condition,
                description=f"tls alignment {alignment}",
            )
        )
        return self

    def resolve_sonames(
        self,
        soname_map: dict[str, str],
        *,
        stage: str = "post_extract",
        condition: PlatformCondition | None = None,
    ) -> PackageRecipe:
        """Symlink missing sonames into package lib/ from host glibc-compat providers."""

        def _sonames(context: PatchContext) -> None:
            resolve_soname_symlinks(context, soname_map)

        self._actions.append(
            RecipeAction(
                _sonames,
                stage=stage,
                condition=condition,
                description="resolve sonames",
            )
        )
        return self

    def patch_subtree(
        self,
        pattern: str,
        *,
        patcher_fn: Callable[[Path], Any] | None = None,
        stage: str = "pre_link",
        condition: PlatformCondition | None = None,
    ) -> PackageRecipe:
        """Traverse and patch sub-binaries (e.g. bundled z3, internal toolchains)."""

        def _sub(context: PatchContext) -> None:
            patch_subtree_binaries(context, pattern, patcher_fn=patcher_fn)

        self._actions.append(
            RecipeAction(
                _sub, stage=stage, condition=condition, description="patch subtree"
            )
        )
        return self

    def patch_external_toolchain(
        self,
        root_dir: Path | str,
        *,
        subdirs: Sequence[str] = (),
        skip_dirs: Sequence[str] = (),
        stage: str = "pre_link",
        condition: PlatformCondition | None = None,
    ) -> PackageRecipe:
        """Patch dynamic linkers and RPATHs across externally managed toolchains (e.g. Julia/Rust toolchains)."""

        def _ext(context: PatchContext) -> None:
            patch_external_toolchain(
                root_dir,
                report=context.report,
                subdirs=subdirs,
                skip_dirs=skip_dirs,
            )

        self._actions.append(
            RecipeAction(
                _ext, stage=stage, condition=condition, description="external toolchain"
            )
        )
        return self

    # -------------------------------------------------------------------------
    # Binary Wrappers & Runtime Patches
    # -------------------------------------------------------------------------

    def wrap_binary(
        self,
        target_binary: str | Path,
        *,
        shebang: str | Path | None = None,
        unset: Sequence[str] = (),
        environment: dict[str, Any] | None = None,
        rewrite_args: dict[str, str | Path] | None = None,
        append_args_if: Sequence[tuple[str, Sequence[str]]] | None = None,
        exec_name: str | None = None,
        before: str | None = None,
        stage: str = "pre_link",
        condition: PlatformCondition | None = None,
    ) -> PackageRecipe:
        """Generate an in-tree wrapper replacing the target binary with a real binary redirect."""

        def _wrap(context: PatchContext) -> None:
            wb = WrapperBuilder(
                target_binary=target_binary,
                shebang=shebang,
                unset=unset,
                environment=environment or {},
                rewrite_args=rewrite_args or {},
                append_args_if=append_args_if or [],
                exec_name=exec_name,
                before=before,
            )
            wb.apply(context)

        self._actions.append(
            RecipeAction(
                _wrap,
                stage=stage,
                condition=condition,
                description=f"wrap {target_binary}",
            )
        )
        return self

    def multiplex_proxies(
        self,
        target_binary: str,
        proxies: Sequence[str],
        *,
        extra_dirs: Sequence[Path | str] = (),
        environment: dict[str, Any] | None = None,
        unset: Sequence[str] = ("LD_PRELOAD",),
        stage: str = "pre_link",
        condition: PlatformCondition | None = None,
    ) -> PackageRecipe:
        """Multiplex a group of toolchain commands (e.g. rustc, cargo, rustfmt) to a central binary.

        Generates wrappers pointing each proxy name to target_binary across Ship's bin directory
        and optional external directories (like ~/.cargo/bin).
        """
        from ship.api.scripting import InlineScript
        from ship.core.settings import settings

        def _sync_proxies(context: PatchContext) -> None:
            profile = context.profile or get_active_profile()
            wrappers_dir = settings.ship_root / "lib" / "wrappers"
            wrappers_dir.mkdir(parents=True, exist_ok=True)
            real_target = wrappers_dir / target_binary

            env_exports = []
            if environment:
                for k, v in environment.items():
                    env_exports.append(f'export {k}="{v}"')
            env_block = "\n".join(env_exports)
            unset_block = "\n".join(f"unset {var}" for var in unset)

            template = f"""
                {unset_block}
                {env_block}
                exec -a "$0" @wrapper@ "$@"
            """
            proxy_script = InlineScript(template)

            # Target bin directories
            all_target_dirs = [settings.ship_bin_dir]
            for ed in extra_dirs:
                p = Path(ed)
                p.mkdir(parents=True, exist_ok=True)
                all_target_dirs.append(p)

            for name in proxies:
                wrapper = wrappers_dir / name
                if not wrapper.exists() or wrapper.resolve() != real_target.resolve():
                    wrapper.unlink(missing_ok=True)
                    wrapper.symlink_to(real_target.resolve())

                launcher_content = proxy_script.render(
                    profile=profile,
                    wrapper=str(wrapper),
                )

                for tdir in all_target_dirs:
                    dest = tdir / name
                    if (
                        not dest.is_file()
                        or dest.is_symlink()
                        or dest.read_text(encoding="utf-8") != launcher_content
                    ):
                        dest.unlink(missing_ok=True)
                        dest.write_text(launcher_content, encoding="utf-8")
                        dest.chmod(0o755)
                        context.record(dest, "proxy", f"-> {target_binary}")

        self._actions.append(
            RecipeAction(
                _sync_proxies,
                stage=stage,
                condition=condition,
                description=f"multiplex proxies to {target_binary}",
            )
        )
        return self

    def on_subcommand(
        self,
        binaries: Sequence[str],
        triggers: Sequence[str],
        *,
        post_exec_call: str | None = None,
        targets: Sequence[str] = (),
    ) -> PackageRecipe:
        """Trigger a background maintenance/patching action whenever specific subcommands run."""
        if post_exec_call is not None:
            cmd = RuntimeCommand(
                argv=("ship", "call", post_exec_call),
                forward_args=False,
                ignore_failure=True,
                condition=ArgumentOneOf(1, tuple(triggers)),
            )
            self._runtime_patches.append(
                RuntimePatch(
                    binaries=tuple(binaries),
                    targets=tuple(targets),
                    after=cmd,
                )
            )
        return self

    def intercept_compiler_run(
        self,
        binary: str,
        *,
        subcommand: str = "run",
        build_subcommand: str = "build",
        output_flag: str = "-out:{output}",
        unsupported_flags: frozenset[str] = frozenset(),
        fixup: Callable[[Path], Any] | None = None,
        targets: Sequence[str] = (),
        condition: PlatformCondition | None = None,
    ) -> PackageRecipe:
        """Intercept compiler run/test subcommands so emitted binaries are patched before execution.

        Handles:
          - Flag parsing and separator ('--') splitting between compiler and program args
          - Compiling into an isolated tempdir using build_subcommand and output_flag
          - Applying fixup (e.g. raise_tls_alignment, set_elf_interpreter)
          - Forwarding exit codes and POSIX signals cleanly
        """
        import os
        import signal
        import sys
        import tempfile

        def _execute_intercepted(real_binary: str, args: list[str]) -> int:
            if not args or args[0] != subcommand:
                return subprocess.run([real_binary, *args], check=False).returncode

            compiler_args = args[1:]
            try:
                separator = compiler_args.index("--")
                program_args = compiler_args[separator + 1 :]
                compiler_args = compiler_args[:separator]
            except ValueError:
                program_args = []

            # Check if help or unsupported flags are present -> native path
            if (
                not compiler_args
                or all(arg.startswith("-") for arg in compiler_args)
                or any(arg in ("-help", "--help", "-h") for arg in compiler_args)
                or any(
                    arg.split(":", 1)[0].lstrip("-") in unsupported_flags
                    for arg in compiler_args
                )
            ):
                return subprocess.run([real_binary, *args], check=False).returncode

            # Reorder source and flags if flags appear first
            if (
                len(compiler_args) > 1
                and compiler_args[0].startswith("-")
                and not compiler_args[-1].startswith("-")
            ):
                compiler_args = [compiler_args[-1], *compiler_args[:-1]]

            requested_output = None
            out_prefix = output_flag.split("{")[0]
            for arg in compiler_args:
                if arg.startswith(out_prefix):
                    requested_output = Path(arg.partition(out_prefix)[2])

            keep_executable = any(
                arg in ("-keep-executable", "--keep-executable")
                for arg in compiler_args
            )

            def build_and_run(out_path: Path) -> int:
                flag_str = output_flag.replace("{output}", str(out_path))
                build_args = [real_binary, build_subcommand, *compiler_args]
                if requested_output is None:
                    build_args.append(flag_str)
                build = subprocess.run(build_args, check=False)
                if build.returncode:
                    if build.returncode < 0:
                        signum = -build.returncode
                        signal.signal(signum, signal.SIG_DFL)
                        os.kill(os.getpid(), signum)
                    return build.returncode

                if not out_path.is_file():
                    return 1

                if fixup is not None:
                    fixup(out_path)

                result = subprocess.run([str(out_path), *program_args], check=False)
                if result.returncode < 0:
                    signum = -result.returncode
                    signal.signal(signum, signal.SIG_DFL)
                    os.kill(os.getpid(), signum)

                if result.returncode == 0 and not keep_executable:
                    out_path.unlink(missing_ok=True)
                return result.returncode

            if requested_output is not None:
                if not requested_output.is_absolute():
                    requested_output = Path.cwd() / requested_output
                return build_and_run(requested_output)

            temp_dir = Path(tempfile.mkdtemp(prefix=f"ship-{binary}-run-"))
            output = temp_dir / "main"
            try:
                result = build_and_run(output)
            finally:
                if keep_executable or output.is_file():
                    if output.is_file():
                        print(f"Keeping executable at {output}", file=sys.stderr)
                else:
                    shutil.rmtree(temp_dir, ignore_errors=True)
            return result

        def _command_provider(
            binary_name: str, real_binary: Path, target_key: str
        ) -> RuntimeCommand | None:
            if binary_name != binary:
                return None
            profile = get_active_profile()
            if condition is not None and not condition.check(profile, target_key):
                return None

            ship_bin = shutil.which("ship")
            if not ship_bin:
                python = shutil.which("python3")
                if not python:
                    return None
                ship_lib = Path(__file__).resolve().parents[2]
                code = (
                    f"import sys; sys.path.insert(0, {str(ship_lib)!r}); "
                    f"from ship.packages.{binary} import run_{binary}; "
                    f"raise SystemExit(run_{binary}(sys.argv[1], sys.argv[2:]))"
                )
                return RuntimeCommand(
                    argv=(python, "-c", code, real_binary),
                    condition=ArgumentEquals(1, subcommand),
                    otherwise=RuntimeCommand(argv=(real_binary,)),
                )

            return RuntimeCommand(
                argv=(
                    ship_bin,
                    "call",
                    f"ship.packages.{binary}:run_{binary}",
                    real_binary,
                ),
                condition=ArgumentEquals(1, subcommand),
                otherwise=RuntimeCommand(argv=(real_binary,)),
            )

        self.intercept_func = _execute_intercepted
        self._runtime_patches.append(
            RuntimePatch(
                binaries=(binary,),
                targets=tuple(targets),
                command=_command_provider,
            )
        )
        return self

    def runtime(
        self,
        binaries: Sequence[str],
        *,
        targets: Sequence[str] = (),
        prepend_path: Sequence[str | Path] = (),
        prepend_ld_library_path: Sequence[str | Path] = (),
        env: dict[str, str | Path] | None = None,
        before: RuntimeValue = "",
        after: RuntimeValue = "",
        command: RuntimeValue = "",
    ) -> PackageRecipe:
        """Register public launcher wrapper behavior executed when users run the command."""
        self._runtime_patches.append(
            RuntimePatch(
                binaries=tuple(binaries),
                targets=tuple(targets),
                prepend_path=tuple(prepend_path),
                prepend_ld_library_path=tuple(prepend_ld_library_path),
                env=dict(env or {}),
                before=before,
                after=after,
                command=command,
            )
        )
        return self

    # -------------------------------------------------------------------------
    # Custom Lifecycle Hooks & Condition Blocks
    # -------------------------------------------------------------------------

    def hook(
        self,
        func: Callable[[PatchContext], None],
        *,
        stage: str = "pre_link",
        condition: PlatformCondition | None = None,
        description: str = "",
    ) -> PackageRecipe:
        """Attach an arbitrary imperative hook into the lifecycle."""
        self._actions.append(
            RecipeAction(
                func, stage=stage, condition=condition, description=description
            )
        )
        return self

    def on_reapply(self, handler: ReapplyHandler) -> PackageRecipe:
        """Register a handler called during `ship repatch`."""
        self._reapply_handlers.append(handler)
        return self

    # -------------------------------------------------------------------------
    # Compilation to PackagePatch
    # -------------------------------------------------------------------------

    def to_patch(self) -> PackagePatch:
        """Compile the recipe into an immutable PackagePatch for the install pipeline."""
        post_extract_list: list[InstallPatch] = []
        pre_link_list: list[InstallPatch] = []

        for action in self._actions:

            def _make_handler(act: RecipeAction) -> InstallHandler:
                def _handler(context: PatchContext) -> None:
                    act.execute(context)

                return _handler

            patch_entry = InstallPatch(_make_handler(action))
            if action.stage == "post_extract":
                post_extract_list.append(patch_entry)
            else:
                pre_link_list.append(patch_entry)

        export_pol = ExportPolicy(
            only=self._export_only,
            exclude=self._export_exclude,
            internal_only=self._export_internal_only,
            aliases=self._export_aliases,
        )

        return PackagePatch(
            export_policy=export_pol,
            post_extract=tuple(post_extract_list),
            pre_link=tuple(pre_link_list),
            runtime=tuple(self._runtime_patches),
            reapply=tuple(self._reapply_handlers),
            discover_all_bins=self._discover_all_bins,
            allow_foreign_binaries=self._allow_foreign_binaries,
        )

    # Make PackageRecipe directly usable wherever PackagePatch is expected
    def __getattr__(self, name: str) -> Any:
        return getattr(self.to_patch(), name)

    # -------------------------------------------------------------------------
    # Legacy mixin support for v1 specs
    # -------------------------------------------------------------------------

    def apply_mixins(self, root_dir: Path) -> None:
        """Apply active mixin shims across the extracted root."""
        from ship.runtime.polyfills import PolyfillEngine

        patcher = SourcePatcher(root_dir)
        for m in self.mixins:
            if m == Mixin.PosixShellSanitizer:
                PolyfillEngine.apply_posix_shell(root_dir, patcher)
            elif m == Mixin.DisableBwrapSandbox:
                PolyfillEngine.ensure_bwrap_shim()
            elif m == Mixin.BionicCompat:
                PolyfillEngine.apply_bionic_compat(root_dir, patcher)
            elif m == Mixin.AndroidShmem:
                PolyfillEngine.apply_android_shmem(root_dir, patcher)

    def post_extract(self, patcher: SourcePatcher, target_key: str) -> None:
        """Runs after initial extraction."""

    def post_install(self, ctx: BuildContext) -> None:
        """Lifecycle hook executed after linking."""


__all__ = [
    "ArgumentCondition",
    "ArgumentEquals",
    "ArgumentOneOf",
    "BuildContext",
    "ExportPolicy",
    "InstallHandler",
    "InstallPatch",
    "Mixin",
    "PackagePatch",
    "PackageRecipe",
    "PatchRecipe",
    "PlatformCondition",
    "ReapplyHandler",
    "RecipeAction",
    "RuntimeCommand",
    "RuntimePatch",
    "RuntimeValue",
    "SourcePatcher",
    "on_platform",
    "on_termux",
    "shell_exec",
    "shell_export",
]
