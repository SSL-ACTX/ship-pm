"""Runtime environment configuration for Why3."""

from __future__ import annotations

from ship.api import PackageRecipe
from ship.runtime import apply_patchers

_PUBLIC_COMMANDS = ("why3", "gnatwhy3")

PATCH = (
    PackageRecipe("why3")
    .export(only=_PUBLIC_COMMANDS)
    .patch_subtree(
        "**/*",
        patcher_fn=lambda bin_path, target_key, report: apply_patchers(
            bin_path, target_key, report
        ),
    )
    .runtime(
        binaries=_PUBLIC_COMMANDS,
        targets=("*",),
        env={
            "WHY3LOADPATH": "{install_dir}/share/why3/theories",
            "WHY3DATA": "{install_dir}/share/why3",
        },
    )
    .to_patch()
)
