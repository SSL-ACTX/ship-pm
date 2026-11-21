"""Keep Verus's bundled solver and verifier helpers private to Ship."""

from ship.api import PackageRecipe

_PUBLIC_COMMANDS = ("verus", "cargo-verus")

PATCH = (
    PackageRecipe("verus")
    .export(only=_PUBLIC_COMMANDS, discover_all_bins=True)
    .to_patch()
)
