"""Termux compatibility patch for cvc5's missing glibc runtime dependencies.

The ``shared-gpl`` release variant links against system libraries that are not
present in Termux's glibc compat layer under the expected sonames.  This patch
creates symlinks for those libraries inside cvc5's own ``lib/`` directory so
that the dynamic linker finds them via the existing ``${ORIGIN}/../lib`` RUNPATH
without requiring any wrapper changes.

Missing libraries and resolutions:
  libedit.so.2  ->  libedit-glibc provides libedit.so.0 (same lib, soname diff)
"""

from __future__ import annotations

from pathlib import Path

from ship.config import IS_TERMUX
from ship.patches.api import InstallPatch, PackagePatch, PatchContext

_GLIBC_LIB = Path("/data/data/com.termux/files/usr/glibc/lib")

# Maps the soname cvc5 expects -> the real file available in glibc/lib.
_SONAME_MAP: dict[str, str] = {
    "libedit.so.2": "libedit.so.0.0.78",
}


def _symlink_missing_libs(context: PatchContext) -> None:
    """Symlink missing sonames into cvc5's ``lib/`` using glibc-compat providers."""
    if not IS_TERMUX:
        return

    # cvc5 extracts into a versioned subdirectory; find the first lib/ below root.
    lib_dir = context.install_dir / "lib"
    if not lib_dir.is_dir():
        for child in sorted(context.install_dir.iterdir()):
            if child.is_dir():
                candidate = child / "lib"
                if candidate.is_dir():
                    lib_dir = candidate
                    break
        else:
            return

    for soname, real_name in _SONAME_MAP.items():
        link = lib_dir / soname
        if link.exists() or link.is_symlink():
            continue
        source = _GLIBC_LIB / real_name
        if source.is_file():
            link.symlink_to(source)
            context.record(link, "symlink", f"-> {source}")


PATCH = PackagePatch(
    post_extract=(InstallPatch(_symlink_missing_libs, targets=("*-linux-*",)),),
)
