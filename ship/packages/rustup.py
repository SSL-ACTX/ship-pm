"""Termux runtime integration for rustup and Rust toolchains."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from ship.api import (
    ArgumentOneOf,
    InlineScript,
    InstallPatch,
    PackagePatch,
    PatchReport,
    RuntimeCommand,
    RuntimePatch,
    patch_external_toolchain,
)
from ship.core.profile import get_active_profile
from ship.core.settings import settings
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

    profile = get_active_profile()
    proxy_script = InlineScript("""
        unset LD_PRELOAD
        export SSL_CERT_FILE=@profile.tls_cert@
        export SSL_CERT_DIR=@profile.tls_cert_dir@
        exec -a "$0" @wrapper@ "$@"
    """)

    for name in proxies:
        wrapper = wrappers_dir / name
        if not wrapper.exists() or wrapper.resolve() != real_rustup.resolve():
            wrapper.unlink(missing_ok=True)
            wrapper.symlink_to(real_rustup.resolve())

        launcher_content = proxy_script.render(
            profile=profile,
            wrapper=shlex.quote(str(wrapper)),
        )

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

    patch_external_toolchain(
        root_dir=toolchains_dir,
        subdirs=("bin", "lib", "libexec"),
        report=report,
    )

    if owns_report:
        for change in report.changes:
            status("Patching", report.describe(change))
    return report


RUSTUP_AFTER = RuntimeCommand(
    argv=(
        "ship",
        "call",
        "ship.packages.rustup:patch_rust_toolchain_dir",
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
