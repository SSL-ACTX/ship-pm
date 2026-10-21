"""Termux runtime compatibility patch for CryptoMiniSat."""

import shutil
from pathlib import Path

from ship.api import (
    ExportPolicy,
    PackagePatch,
    RuntimeCommand,
    RuntimePatch,
)
from ship.core.profile import get_active_profile


def cryptominisat_command(
    binary_name: str, real_binary: Path, target_key: str
) -> RuntimeCommand | None:
    """Run cryptominisat via qemu-aarch64 on Termux to bypass Android seccomp restrictions."""
    profile = get_active_profile()
    if not profile.is_termux:
        return None

    qemu = shutil.which("qemu-aarch64")
    if not qemu:
        return None

    return RuntimeCommand(
        argv=(qemu, "-L", profile.paths.prefix, real_binary),
    )


PATCH = PackagePatch(
    export_policy=ExportPolicy(
        only=("cryptominisat5", "cryptominisat"),
        aliases={"cryptominisat": "cryptominisat5"},
    ),
    runtime=(
        RuntimePatch(
            binaries=("cryptominisat", "cryptominisat5"),
            targets=("aarch64-*",),
            command=cryptominisat_command,
        ),
    ),
)
