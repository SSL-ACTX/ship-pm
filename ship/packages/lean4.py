"""Sandbox Lean 4's bundled LLVM toolchain and inject Termux glibc linker flags."""

from ship.api import (
    PackageRecipe,
    PatchContext,
    WrapperBuilder,
    on_termux,
    promote_nested_directory,
)
from ship.runtime.termux import termux_glibc_loader_path, termux_glibc_prefix

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
    promote_nested_directory(context, target_dir="bin")

    lean4_link = top_bin / "lean4"
    lean_bin = top_bin / "lean"
    if not lean4_link.exists() and not lean4_link.is_symlink() and lean_bin.exists():
        lean4_link.symlink_to(lean_bin.resolve())
        context.record(lean4_link, "symlink", "-> lean")


def _hijack_bundled_linker(context: PatchContext) -> None:
    """Wrap bundled ld.lld so leanc/lake emit executables with Termux glibc interpreter and RPATH."""
    target_arch = context.target_key.split("-")[0]
    glibc_pfx = termux_glibc_prefix()
    glibc_lib = glibc_pfx / "lib"
    glibc_loader = termux_glibc_loader_path(target_arch)

    if not glibc_loader or not glibc_loader.is_file():
        return

    for lld_path in context.install_dir.glob("**/bin/ld.lld"):
        if lld_path.is_symlink():
            continue

        wrapper = WrapperBuilder(
            target_binary=lld_path.relative_to(context.install_dir),
            unset=["LD_PRELOAD"],
            rewrite_args={
                r"/lib/ld-linux-*.so.*": glibc_loader,
                r"/lib64/ld-linux-*.so.*": glibc_loader,
            },
            append_args_if=[
                ("-dynamic-linker", ["-rpath", str(glibc_lib)]),
                ("--dynamic-linker", ["-rpath", str(glibc_lib)]),
            ],
        )
        wrapper.apply(context)


PATCH = (
    PackageRecipe("lean4")
    .export(
        only=_PUBLIC_COMMANDS,
        internal_only=_INTERNAL_TOOLCHAIN,
        aliases={"lean4": "lean"},
        discover_all_bins=True,
    )
    .hook(_promote_bins, stage="pre_link")
    .hook(_hijack_bundled_linker, stage="pre_link", condition=on_termux())
    .to_patch()
)
