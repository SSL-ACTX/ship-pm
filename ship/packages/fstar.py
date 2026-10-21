"""Platform compatibility patches for F* and its bundled solvers."""

from ship.api import (
    ExportPolicy,
    InstallPatch,
    PackagePatch,
    PatchContext,
    patch_subtree_binaries,
)
from ship.runtime import apply_patchers

_PUBLIC_COMMANDS = ("fstar", "fstar.exe", "krml")


def _patch_bundled_solvers(context: PatchContext) -> None:
    """Find and patch all bundled internal solver binaries (e.g. z3)."""
    patch_subtree_binaries(context, "**/z3*/**/z3*", patcher_fn=apply_patchers)


PATCH = PackagePatch(
    export_policy=ExportPolicy(
        only=_PUBLIC_COMMANDS,
    ),
    pre_link=(InstallPatch(_patch_bundled_solvers),),
)
