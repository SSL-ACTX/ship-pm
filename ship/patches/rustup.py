"""Termux runtime integration for rustup and Rust toolchains."""

from __future__ import annotations

import os
from pathlib import Path

from ship.api import (
    PackageRecipe,
    PatchReport,
    RuntimeCommand,
    on_termux,
    patch_external_toolchain,
)
from ship.core.settings import settings
from ship.ui import status

PROXIES = (
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


def _cargo_home() -> Path:
    env = os.environ.get("CARGO_HOME")
    return Path(env) if env else (settings.home / ".cargo")


def patch_rust_toolchain_dir(report: PatchReport | None = None) -> PatchReport:
    """Patch rustup-managed glibc executables (rustc, cargo, LLVM libs) in RUSTUP_HOME."""
    owns_report = report is None
    report = report or PatchReport("rustup")

    rustup_home_env = os.environ.get("RUSTUP_HOME")
    rustup_home = (
        Path(rustup_home_env) if rustup_home_env else (settings.home / ".rustup")
    )
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


PATCH = (
    PackageRecipe("rustup")
    .multiplex_proxies(
        target_binary="rustup",
        proxies=PROXIES,
        extra_dirs=[_cargo_home() / "bin"],
        environment={
            "SSL_CERT_FILE": "/data/data/com.termux/files/usr/etc/tls/cert.pem",
            "SSL_CERT_DIR": "/data/data/com.termux/files/usr/etc/tls",
        },
        condition=on_termux(),
    )
    .on_subcommand(
        binaries=("rustup",),
        triggers=("add", "update", "install", "default", "toolchain"),
        post_exec_call="ship.patches.rustup:patch_rust_toolchain_dir",
        targets=("aarch64-*",),
    )
    .runtime(
        binaries=PROXIES,
        targets=("aarch64-*",),
        command=rustup_command,
    )
    .on_reapply(patch_rust_toolchain_dir)
    .to_patch()
)
