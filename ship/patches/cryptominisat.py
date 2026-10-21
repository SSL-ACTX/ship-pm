"""Termux runtime compatibility patch for CryptoMiniSat."""

import shutil
from pathlib import Path

from ship.config import IS_TERMUX, PREFIX
from ship.patches.api import (
    ExportPolicy,
    PackagePatch,
    RuntimeCommand,
    RuntimePatch,
)


def cryptominisat_command(
    binary_name: str, real_binary: Path, target_key: str
) -> RuntimeCommand | None:
    """Run cryptominisat via qemu-aarch64 on Termux to bypass Android seccomp restrictions."""
    if not IS_TERMUX:
        return None

    qemu = shutil.which("qemu-aarch64")
    if not qemu:
        return None

    return RuntimeCommand(
        argv=(qemu, "-L", PREFIX, real_binary),
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
