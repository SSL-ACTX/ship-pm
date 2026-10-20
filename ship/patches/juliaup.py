"""Termux runtime integration for Juliaup and the Julia launcher."""

import shlex
import shutil
from pathlib import Path

from ship.config import HOME, PREFIX
from ship.patchers.termux import patch_termux_glibc_dir


def patch_toolchain_dir() -> None:
    """Patch Juliaup-managed glibc executables after Julia installs them."""
    patch_termux_glibc_dir(HOME / ".julia" / "juliaup")


def runtime_wrapper_hooks(binary_name: str) -> tuple[str, str]:
    """Return (before-exec, after-exec) shell snippets for Termux wrappers."""
    if binary_name == "juliaup":
        after = """
case "$*" in
    *add*|*update*|*install*|*default*)
        python3 -c "from ship.patches.juliaup import patch_toolchain_dir; patch_toolchain_dir()" 2>/dev/null || true
        ;;
esac
"""
        return "", after
    return "", ""


def runtime_exec_command(
    binary_name: str, real_binary: Path, target_key: str
) -> str | None:
    """Use QEMU's Termux sysroot for Juliaup network access only.

    The native Julia launcher stays outside QEMU to avoid emulating the Julia
    runtime. Juliaup's musl resolver needs the Termux sysroot's resolv.conf.
    """
    if binary_name != "juliaup" or not target_key.startswith("aarch64-"):
        return None
    qemu = shutil.which("qemu-aarch64")
    if not qemu:
        return None
    return (
        f"{shlex.quote(qemu)} -L {shlex.quote(str(PREFIX))} "
        f'{shlex.quote(str(real_binary))} "$@"'
    )
