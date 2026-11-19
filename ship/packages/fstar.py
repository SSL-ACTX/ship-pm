"""Platform compatibility patches for F* and its bundled solvers."""

from ship.api import PackageRecipe
from ship.runtime import apply_patchers

_PUBLIC_COMMANDS = ("fstar", "fstar.exe", "krml")

PATCH = (
    PackageRecipe("fstar")
    .export(only=_PUBLIC_COMMANDS)
    .patch_subtree(
        "**/z3*/**/z3*",
        patcher_fn=lambda bin_path, target_key, report: apply_patchers(
            bin_path, target_key, report
        ),
    )
    .to_patch()
)
