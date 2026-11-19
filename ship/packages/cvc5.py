"""Termux compatibility patch for cvc5's missing glibc runtime dependencies."""

from __future__ import annotations

from ship.api import PackageRecipe, on_platform

_SONAME_MAP: dict[str, str] = {
    "libedit.so.2": "libedit.so.0.0.78",
}

PATCH = (
    PackageRecipe("cvc5")
    .resolve_sonames(
        _SONAME_MAP,
        stage="post_extract",
        condition=on_platform(target="*-linux-*"),
    )
    .to_patch()
)
