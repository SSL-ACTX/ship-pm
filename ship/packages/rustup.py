"""Termux runtime integration for rustup."""

import shutil
from pathlib import Path

from ship.api import PackagePatch, RuntimeCommand, RuntimePatch
from ship.core.profile import get_active_profile


def rustup_command(
    binary_name: str, real_binary: Path, target_key: str
) -> RuntimeCommand | None:
    """Use QEMU's Termux sysroot for rustup DNS/network access under musl.

    Rustup is statically compiled against musl and requires /etc/resolv.conf,
    which does not exist natively on Android. Wrapping rustup with QEMU using
    Termux's sysroot (-L $PREFIX) enables standard glibc/Termux DNS resolution.
    """
    qemu = shutil.which("qemu-aarch64")
    if not qemu:
        return None
    return RuntimeCommand(
        argv=(
            qemu,
            "-0",
            binary_name,
            "-L",
            get_active_profile().paths.prefix,
            real_binary,
        )
    )


PATCH = PackagePatch(
    runtime=(
        RuntimePatch(
            binaries=("rustup",),
            targets=("aarch64-*",),
            command=rustup_command,
        ),
    ),
)
