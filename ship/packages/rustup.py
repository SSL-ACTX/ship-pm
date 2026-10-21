"""Termux runtime integration for rustup and Rust toolchains."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

from ship.api import (
    ArgumentOneOf,
    InstallPatch,
    PackagePatch,
    PatchReport,
    RuntimeCommand,
    RuntimePatch,
    inspect_elf,
    set_elf_interpreter,
    set_elf_rpath,
)
from ship.core.profile import get_active_profile
from ship.core.settings import settings
from ship.runtime.termux import termux_glibc_loader_path, termux_glibc_prefix
from ship.ui import status


def sync_cargo_proxies(report: PatchReport | None = None) -> None:
    """Ensure ~/.cargo/bin proxies (rustc, cargo, rustdoc, etc.) are installed and linked."""
    cargo_home_env = os.environ.get("CARGO_HOME")
    cargo_home = Path(cargo_home_env) if cargo_home_env else (settings.home / ".cargo")
    cargo_bin = cargo_home / "bin"
    cargo_bin.mkdir(parents=True, exist_ok=True)

    rustup_bin = settings.ship_bin_dir / "rustup"
    if not rustup_bin.exists():
        rustup_bin = settings.ship_internal_bin / "rustup"

    wrappers_dir = settings.ship_root / "lib" / "wrappers"
    wrappers_dir.mkdir(parents=True, exist_ok=True)
    real_rustup = wrappers_dir / "rustup"

    # All proxies managed by rustup plus rustup itself
    proxies = (
        "rustup",
        "rustc",
        "cargo",
        "rustdoc",
        "rust-lldb",
        "rust-gdb",
        "rust-gdbgui",
        "rls",
        "cargo-clippy",
        "clippy-driver",
        "cargo-miri",
        "rust-analyzer",
        "rustfmt",
        "cargo-fmt",
    )

    glibc_bash = str(get_active_profile().paths.bash)

    for name in proxies:
        wrapper = wrappers_dir / name
        if not wrapper.exists() or wrapper.resolve() != real_rustup.resolve():
            wrapper.unlink(missing_ok=True)
            wrapper.symlink_to(real_rustup.resolve())

        # Clean native launcher using exec -a "$0" directly without wrapper shell argument corruption
        launcher_content = f"""#!{glibc_bash}
unset LD_PRELOAD
export SSL_CERT_FILE=/data/data/com.termux/files/usr/etc/tls/cert.pem
export SSL_CERT_DIR=/data/data/com.termux/files/usr/etc/tls
exec -a "$0" {shlex.quote(str(wrapper))} "$@"
"""

        # Install into cargo_bin
        cargo_target = cargo_bin / name
        if (
            not cargo_target.is_file()
            or cargo_target.is_symlink()
            or cargo_target.read_text(encoding="utf-8") != launcher_content
        ):
            cargo_target.unlink(missing_ok=True)
            cargo_target.write_text(launcher_content, encoding="utf-8")
            cargo_target.chmod(0o755)

        # Install into ship_bin_dir
        pub_link = settings.ship_bin_dir / name
        if (
            not pub_link.is_file()
            or pub_link.is_symlink()
            or pub_link.read_text(encoding="utf-8") != launcher_content
        ):
            pub_link.unlink(missing_ok=True)
            pub_link.write_text(launcher_content, encoding="utf-8")
            pub_link.chmod(0o755)


def patch_rust_toolchain_dir(report: PatchReport | None = None) -> PatchReport:
    """Patch rustup-managed glibc executables (rustc, cargo, LLVM libs) in RUSTUP_HOME."""
    owns_report = report is None
    report = report or PatchReport("rustup")

    sync_cargo_proxies(report)

    rustup_home_env = os.environ.get("RUSTUP_HOME")
    if rustup_home_env:
        rustup_home = Path(rustup_home_env)
    else:
        rustup_home = settings.home / ".rustup"

    toolchains_dir = rustup_home / "toolchains"
    loader = termux_glibc_loader_path()
    patchelf = shutil.which("patchelf")

    if (
        not get_active_profile().is_termux
        or loader is None
        or not loader.is_file()
        or not patchelf
        or not toolchains_dir.is_dir()
    ):
        return report

    glibc_lib = termux_glibc_prefix() / "lib"

    # Only scan bin, lib, and libexec folders of each toolchain root
    target_dirs: list[Path] = []
    for tc in toolchains_dir.iterdir():
        if not tc.is_dir():
            continue
        for sub in ("bin", "lib", "libexec"):
            p = tc / sub
            if p.is_dir():
                target_dirs.append(p)

    for base_dir in target_dirs:
        for root, _, files in os.walk(base_dir):
            for file_name in files:
                path = Path(root) / file_name
                try:
                    if path.is_symlink() or not (
                        os.access(path, os.X_OK)
                        or path.name.endswith(".so")
                        or ".so." in path.name
                    ):
                        continue
                    info = inspect_elf(path)
                    if info is None:
                        continue

                    toolchain_root = path.parent
                    while (
                        toolchain_root.parent != toolchains_dir
                        and toolchain_root != toolchains_dir
                    ):
                        toolchain_root = toolchain_root.parent
                    toolchain_lib = toolchain_root / "lib"

                    if info.abi == "glibc":
                        rpath = f"{glibc_lib}:{toolchain_lib}:{path.parent}"
                        if set_elf_interpreter(path, loader, patchelf=patchelf):
                            report.add(path, "set ELF interpreter", str(loader))
                        if set_elf_rpath(path, rpath, patchelf=patchelf):
                            report.add(path, "set ELF RPATH", rpath)
                    elif path.name.endswith(".so") or ".so." in path.name:
                        rpath = f"{glibc_lib}:{toolchain_lib}:{path.parent}"
                        if set_elf_rpath(path, rpath, patchelf=patchelf):
                            report.add(path, "set ELF RPATH", rpath)
                except (OSError, subprocess.SubprocessError):
                    continue

    if owns_report:
        for change in report.changes:
            status("Patching", report.describe(change))
    return report


RUSTUP_AFTER = RuntimeCommand(
    argv=(
        "python3",
        "-c",
        (
            "import os, sys, glob; "
            "from pathlib import Path; "
            "prefix = Path(os.environ.get('PREFIX', '/data/data/com.termux/files/usr')); "
            "ship_roots = [prefix / 'share' / 'ship', Path.home() / '.local' / 'share' / 'ship']; "
            "repo_candidates = glob.glob(str(Path.home() / '*-pm')) + glob.glob(str(Path.home() / 'ship*')); "
            "search = repo_candidates + [str(r / 'lib') for r in ship_roots] + [str(r / 'registry') for r in ship_roots]; "
            "[sys.path.insert(0, p) for p in search if (Path(p) / 'ship' / '__init__.py').is_file()]; "
            "from ship.packages.rustup import patch_rust_toolchain_dir; "
            "patch_rust_toolchain_dir()"
        ),
    ),
    forward_args=False,
    ignore_failure=True,
    condition=ArgumentOneOf(1, ("add", "update", "install", "default", "toolchain")),
)


def rustup_command(
    binary_name: str, real_binary: Path, target_key: str
) -> RuntimeCommand | None:
    """Run rustup/cargo/rustc multiplexers preserving clean argv without foreign runner corruption."""
    wrappers_dir = settings.ship_root / "lib" / "wrappers"
    wrappers_dir.mkdir(parents=True, exist_ok=True)
    proxy = wrappers_dir / binary_name
    if not proxy.exists() or proxy.resolve() != real_binary.resolve():
        proxy.unlink(missing_ok=True)
        proxy.symlink_to(real_binary.resolve())

    return RuntimeCommand(argv=(proxy,))


PATCH = PackagePatch(
    reapply=(patch_rust_toolchain_dir,),
    pre_link=(InstallPatch(lambda ctx: sync_cargo_proxies()),),
    runtime=(
        RuntimePatch(
            binaries=(
                "rustup",
                "rustc",
                "cargo",
                "rustdoc",
                "cargo-clippy",
                "clippy-driver",
                "cargo-miri",
                "rust-analyzer",
                "rustfmt",
                "cargo-fmt",
            ),
            targets=("aarch64-*",),
            after=RUSTUP_AFTER,
            command=rustup_command,
        ),
    ),
)
