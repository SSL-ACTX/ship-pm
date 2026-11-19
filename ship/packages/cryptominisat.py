"""Termux runtime compatibility patch for CryptoMiniSat."""

from ship.api import (
    PackageRecipe,
    qemu_command,
)

PATCH = (
    PackageRecipe("cryptominisat")
    .export(
        only=("cryptominisat5", "cryptominisat"),
        aliases={"cryptominisat": "cryptominisat5"},
    )
    .runtime(
        binaries=("cryptominisat", "cryptominisat5"),
        targets=("aarch64-*",),
        command=lambda name, real_bin, target: qemu_command(real_bin, arch="aarch64"),
    )
    .to_patch()
)
