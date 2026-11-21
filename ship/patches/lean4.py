"""Sandbox Lean 4's bundled LLVM toolchain and inject Termux glibc linker flags."""

from ship.api import (
    PackageRecipe,
    PatchContext,
    WrapperBuilder,
    on_termux,
    promote_nested_directory,
)
from ship.runtime.termux import (
    termux_glibc_loader_path,
    termux_glibc_prefix,
    termux_trampoline_loader_path,
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
    top_bin = context.install_dir / "bin"
    promote_nested_directory(context, target_dir="bin")

    lean4_link = top_bin / "lean4"
    lean_bin = top_bin / "lean"
    if not lean4_link.exists() and not lean4_link.is_symlink() and lean_bin.exists():
        lean4_link.symlink_to(lean_bin.resolve())
        context.record(lean4_link, "symlink", "-> lean")


def _hijack_bundled_linker(context: PatchContext) -> None:
    """Wrap bundled ld.lld so leanc/lake emit executables with Termux glibc interpreter and RPATH."""
    from ship.runtime import apply_patchers

    target_arch = context.target_key.split("-")[0]
    glibc_pfx = termux_glibc_prefix()
    glibc_lib = glibc_pfx / "lib"
    glibc_loader = termux_glibc_loader_path(target_arch)
    trampoline_loader = termux_trampoline_loader_path(target_arch)

    effective_loader = trampoline_loader if trampoline_loader else glibc_loader

    if not effective_loader or not effective_loader.is_file():
        return

    for lld_path in context.install_dir.glob("**/bin/ld.lld"):
        if lld_path.is_symlink():
            continue

        real_binary = lld_path.with_name(f"{lld_path.name}-real")
        if not real_binary.is_file():
            # First time: wrap ld.lld
            apply_patchers(lld_path, context.target_key, context.report)
            wrapper = WrapperBuilder(
                target_binary=lld_path.relative_to(context.install_dir),
                unset=["LD_PRELOAD"],
                rewrite_args={
                    r"/lib/ld-linux-*.so.*": effective_loader,
                    r"/lib64/ld-linux-*.so.*": effective_loader,
                    r"--dynamic-linker=/lib/ld-linux-*.so.*": f"--dynamic-linker={effective_loader}",
                    r"--dynamic-linker=/lib64/ld-linux-*.so.*": f"--dynamic-linker={effective_loader}",
                },
                append_args_if=[
                    ("-dynamic-linker", ["-rpath", str(glibc_lib)]),
                    ("--dynamic-linker", ["-rpath", str(glibc_lib)]),
                ],
            )
            wrapper.apply(context)

        # Ensure the real ld.lld binary has correct loader, RPATH, and executable permissions
        if real_binary.is_file():
            try:
                real_binary.chmod(real_binary.stat().st_mode | 0o755)
            except OSError:
                pass
            apply_patchers(real_binary, context.target_key, context.report)


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
