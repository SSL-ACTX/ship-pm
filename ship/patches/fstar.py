"""Platform compatibility patches for F* and its bundled solvers."""

from ship.patchers import apply_patchers
from ship.patchers.api import (
    ExportPolicy,
    InstallPatch,
    PackagePatch,
    PatchContext,
    inspect_elf,
)

_PUBLIC_COMMANDS = ("fstar", "fstar.exe", "krml")


def _patch_bundled_solvers(context: PatchContext) -> None:
    """Find and patch all bundled internal solver binaries (e.g. z3).

    F* bundles several versions of Z3 under lib/fstar/z3-*/bin/z3.
    Without platform patching (glibc/patchelf or QEMU), F* fails when launching
    the SMT solver subprocess.
    """
    for z3_binary in context.install_dir.glob("**/z3*/**/z3*"):
        if (
            not z3_binary.is_file()
            or z3_binary.is_symlink()
            or z3_binary.name.endswith("-real")
        ):
            continue

        elf_info = inspect_elf(z3_binary)
        if elf_info is None:
            continue

        arch = elf_info.architecture
        abi = elf_info.abi
        binary_target_key = f"{arch}-linux-{abi}" if arch else context.target_key

        z3_binary.chmod(0o755)
        apply_patchers(z3_binary, binary_target_key, context.report)


PATCH = PackagePatch(
    export_policy=ExportPolicy(
        only=_PUBLIC_COMMANDS,
    ),
    pre_link=(InstallPatch(_patch_bundled_solvers),),
)
