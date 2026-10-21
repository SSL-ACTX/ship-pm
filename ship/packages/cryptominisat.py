"""Termux runtime compatibility patch for CryptoMiniSat."""

from pathlib import Path

from ship.api import (
    ExportPolicy,
    PackagePatch,
    RuntimeCommand,
    RuntimePatch,
    qemu_command,
)


def cryptominisat_command(
    binary_name: str, real_binary: Path, target_key: str
) -> RuntimeCommand | None:
    """Run cryptominisat via qemu-aarch64 on Termux to bypass Android seccomp restrictions."""
    return qemu_command(real_binary, arch="aarch64")


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
