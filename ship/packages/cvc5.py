"""Termux compatibility patch for cvc5's missing glibc runtime dependencies."""

from __future__ import annotations

from ship.api import InstallPatch, PackagePatch, PatchContext, resolve_soname_symlinks

_SONAME_MAP: dict[str, str] = {
    "libedit.so.2": "libedit.so.0.0.78",
}


def _symlink_missing_libs(context: PatchContext) -> None:
    """Symlink missing sonames into cvc5's ``lib/`` using glibc-compat providers."""
    resolve_soname_symlinks(context, _SONAME_MAP)


PATCH = PackagePatch(
    post_extract=(InstallPatch(_symlink_missing_libs, targets=("*-linux-*",)),),
)
