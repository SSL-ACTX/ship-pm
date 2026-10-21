"""Sandbox Lean 4's bundled LLVM toolchain from the global bin directory."""

from pathlib import Path

from ship.patches.api import InstallPatch, PackagePatch, PatchContext

_BUNDLED_TOOLCHAIN = frozenset(
    (
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
    )
)


def _promote_bins(context: PatchContext) -> None:
    """Symlink every non-toolchain binary into the top-level bin/ dir.

    Lean's linux archives extract into a versioned subdirectory
    (e.g. lean-4.35.0-linux_aarch64/bin/). The manifest points at
    bin/lean4 at the install root, which is empty. Promote the real
    binaries up so the linker finds them, skipping bundled toolchain
    tools that would shadow system equivalents.
    """
    top_bin = context.install_dir / "bin"
    top_bin.mkdir(exist_ok=True)

    # Find the nested bin/ — one level down from install root.
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
        if not src.is_file() or src.name in _BUNDLED_TOOLCHAIN:
            continue
        link = top_bin / src.name
        if not link.exists() and not link.is_symlink():
            link.symlink_to(src.resolve())
            context.record(
                link, "symlink", f"-> {src.relative_to(context.install_dir)}"
            )

    # Ensure bin/lean4 exists as an alias for bin/lean (manifest target).
    lean4_link = top_bin / "lean4"
    lean_bin = top_bin / "lean"
    if not lean4_link.exists() and not lean4_link.is_symlink() and lean_bin.exists():
        lean4_link.symlink_to(lean_bin.resolve())
        context.record(lean4_link, "symlink", "-> lean")


PATCH = PackagePatch(
    pre_link=(InstallPatch(_promote_bins),),
    excluded_link_names=tuple(_BUNDLED_TOOLCHAIN),
    discover_all_bins=True,
)
