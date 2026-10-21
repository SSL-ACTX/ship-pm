"""Sandbox Lean 4's bundled LLVM toolchain from the global bin directory."""

from pathlib import Path

from ship.patches.api import (
    ExportPolicy,
    InstallPatch,
    PackagePatch,
    PatchContext,
)

_PUBLIC_COMMANDS = ("lean", "lake", "leanc", "lean4")

_INTERNAL_TOOLCHAIN = (
    "clang",
    "clang++",
    "ld.lld",
    "lld",
    "llvm-ar",
    "llvm-nm",
    "llvm-objcopy",
    "llvm-objdump",
    "llvm-ranlib",
    "llvm-strip",
    "cadical",
    "con-leche",
    "con-ron",
    "lean4lean",
    "leanchecker",
    "leanchecker-paranoid",
    "leanexport",
    "leanir",
    "leanmake",
    "leantar",
    "nanoda_bin",
)


def _promote_bins(context: PatchContext) -> None:
    """Symlink real binaries to the root bin/ dir while preserving isolation.

    Lean's release archives extract into a versioned subdirectory
    (e.g. lean-4.36.0-rc1-linux_aarch64/bin/). Populate the root bin/
    so internal components resolve one another.
    """
    top_bin = context.install_dir / "bin"
    top_bin.mkdir(exist_ok=True)

    nested_bin: Path | None = None
    for child in sorted(context.install_dir.iterdir()):
        if child.is_dir() and child.name != "bin":
            candidate = child / "bin"
            if candidate.is_dir():
                nested_bin = candidate
                break

    if nested_bin is None:
        return

    for src in sorted(nested_bin.iterdir()):
        if not src.is_file():
            continue
        link = top_bin / src.name
        if not link.exists() and not link.is_symlink():
            link.symlink_to(src.resolve())
            context.record(
                link, "symlink", f"-> {src.relative_to(context.install_dir)}"
            )

    # Ensure bin/lean4 exists as an alias for bin/lean
    lean4_link = top_bin / "lean4"
    lean_bin = top_bin / "lean"
    if not lean4_link.exists() and not lean4_link.is_symlink() and lean_bin.exists():
        lean4_link.symlink_to(lean_bin.resolve())
        context.record(lean4_link, "symlink", "-> lean")


PATCH = PackagePatch(
    export_policy=ExportPolicy(
        only=_PUBLIC_COMMANDS,
        internal_only=_INTERNAL_TOOLCHAIN,
        aliases={"lean4": "lean"},
    ),
    pre_link=(InstallPatch(_promote_bins),),
    discover_all_bins=True,
)
