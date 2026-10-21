"""Sandbox Lean 4's bundled LLVM toolchain and inject Termux glibc linker flags."""

from pathlib import Path

from ship.config import IS_TERMUX
from ship.patchers.api import (
    ExportPolicy,
    InstallPatch,
    PackagePatch,
    PatchContext,
)
from ship.patchers.termux import termux_glibc_loader_path, termux_glibc_prefix

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

    lean4_link = top_bin / "lean4"
    lean_bin = top_bin / "lean"
    if not lean4_link.exists() and not lean4_link.is_symlink() and lean_bin.exists():
        lean4_link.symlink_to(lean_bin.resolve())
        context.record(lean4_link, "symlink", "-> lean")


def _hijack_bundled_linker(context: PatchContext) -> None:
    """Wrap bundled ld.lld so leanc/lake emit executables with Termux glibc interpreter and RPATH."""
    if not IS_TERMUX:
        return

    target_arch = context.target_key.split("-")[0]
    glibc_pfx = termux_glibc_prefix()
    glibc_lib = glibc_pfx / "lib"
    glibc_loader = termux_glibc_loader_path(target_arch)

    if not glibc_loader or not glibc_loader.is_file():
        return

    for lld_path in context.install_dir.glob("**/bin/ld.lld"):
        if lld_path.is_symlink():
            continue

        real_lld = lld_path.with_name(f"{lld_path.name}-real")
        if not real_lld.is_file():
            lld_path.replace(real_lld)
            context.record(real_lld, "move aside", f"-> {real_lld.name}")

        wrapper_script = f"""#!/data/data/com.termux/files/usr/bin/bash
GLIBC_LIB="{glibc_lib}"
LOADER="{glibc_loader}"

ARGS=()
HAS_DYNAMIC=0
for arg in "$@"; do
    if [[ "$arg" == "-dynamic-linker" || "$arg" == "--dynamic-linker" ]]; then
        HAS_DYNAMIC=1
    fi
done

for arg in "$@"; do
    if [[ "$arg" == /lib/ld-linux-*.so.* || "$arg" == /lib64/ld-linux-*.so.* ]]; then
        ARGS+=("$LOADER")
    else
        ARGS+=("$arg")
    fi
done

if [[ $HAS_DYNAMIC -eq 1 ]]; then
    ARGS+=("-rpath" "$GLIBC_LIB")
fi

unset LD_PRELOAD
exec "{real_lld}" "${{ARGS[@]}}"
"""
        lld_path.write_text(wrapper_script, encoding="utf-8")
        lld_path.chmod(0o755)
        context.record(
            lld_path,
            "install linker interceptor",
            "inject Termux glibc interpreter and RPATH",
        )


PATCH = PackagePatch(
    export_policy=ExportPolicy(
        only=_PUBLIC_COMMANDS,
        internal_only=_INTERNAL_TOOLCHAIN,
        aliases={"lean4": "lean"},
    ),
    pre_link=(
        InstallPatch(_promote_bins),
        InstallPatch(_hijack_bundled_linker),
    ),
    discover_all_bins=True,
)
