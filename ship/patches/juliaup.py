"""Termux runtime integration for Juliaup and the Julia launcher."""

import json
import shutil
import subprocess
from pathlib import Path

from ship.config import HOME, IS_TERMUX, PREFIX, SHIP_BIN_DIR, SHIP_INTERNAL_BIN
from ship.patchers import apply_patchers
from ship.patchers.termux import termux_glibc_loader_path, termux_glibc_prefix
from ship.patches.api import (
    ArgumentOneOf,
    BinaryQuery,
    PackagePatch,
    PatchReport,
    RuntimeCommand,
    RuntimePatch,
    find_binaries,
    inspect_elf,
    set_elf_interpreter,
    set_elf_rpath,
)
from ship.ui import status

# Julia's compiled caches pair .ji metadata with checksum-sensitive .so files.
# Rewriting those shared objects makes the cache invalid, so don't traverse them.
PATCH_SKIP_DIRS = (
    "artifacts",
    "clones",
    "compiled",
    "downloads",
    "logs",
    "packages",
    "registries",
    "scratchspaces",
)

_JULIAUP_STATE = HOME / ".julia" / "juliaup" / "juliaup.json"


def _read_juliaup_state() -> dict:
    try:
        return json.loads(_JULIAUP_STATE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _link_julia_bin(report: PatchReport) -> None:
    """Ensure the active julia binary is linked into ship's bin directory."""
    state = _read_juliaup_state()
    default_channel = state.get("Default")
    channels = state.get("InstalledChannels", {})
    versions = state.get("InstalledVersions", {})
    root = HOME / ".julia" / "juliaup"

    version_key = channels.get(default_channel, {}).get("Version") if default_channel else None
    if not version_key:
        version_key = next(iter(versions), None)
    if not version_key:
        return

    rel = versions[version_key].get("BinaryPath", "")
    julia_bin = (root / rel).resolve()
    if not julia_bin.is_file():
        return

    # version_key e.g. "1.13.2+0.aarch64.linux.gnu"
    # platform is everything after the build tag: "aarch64.linux.gnu" -> "aarch64-linux-gnu"
    try:
        after_plus = version_key.split("+", 1)[1]       # "0.aarch64.linux.gnu"
        platform = after_plus.split(".", 1)[1]           # "aarch64.linux.gnu"
        target_key = platform.replace(".", "-")          # "aarch64-linux-gnu"
    except IndexError:
        target_key = "aarch64-linux-gnu"

    julia_bin.chmod(0o755)
    patched = apply_patchers(julia_bin, target_key, report)

    internal = SHIP_INTERNAL_BIN / "julia"
    public = SHIP_BIN_DIR / "julia"

    internal.unlink(missing_ok=True)
    internal.symlink_to(patched)

    if public.is_symlink():
        public.unlink()
    elif public.exists():
        return

    public.symlink_to(patched)
    report.add(public, "link julia", str(patched))


def patch_toolchain_dir(report: PatchReport | None = None) -> PatchReport:
    """Patch Juliaup-managed glibc executables after Julia installs them."""
    owns_report = report is None
    report = report or PatchReport("juliaup")
    root = HOME / ".julia" / "juliaup"
    loader = termux_glibc_loader_path()
    patchelf = shutil.which("patchelf")
    if (
        not IS_TERMUX
        or loader is None
        or not loader.is_file()
        or not patchelf
        or not root.is_dir()
    ):
        return report

    glibc_lib = termux_glibc_prefix() / "lib"
    query = BinaryQuery(
        executable_only=False,
        excluded_directory_names=PATCH_SKIP_DIRS,
    )
    for path in find_binaries(root, query):
        try:
            info = inspect_elf(path)
            if info is None:
                continue
            if info.abi == "glibc":
                rpath = (
                    f"{glibc_lib}:{path.parent}:{path.parent.parent / 'lib'}:"
                    f"{path.parent.parent / 'lib' / 'julia'}"
                )
                if set_elf_interpreter(path, loader, patchelf=patchelf):
                    report.add(path, "set ELF interpreter", str(loader))
                if set_elf_rpath(path, rpath, patchelf=patchelf):
                    report.add(path, "set ELF RPATH", rpath)
            elif path.name.endswith(".so") or ".so." in path.name:
                rpath = f"{glibc_lib}:{path.parent}:{path.parent.parent / 'lib'}"
                if set_elf_rpath(path, rpath, patchelf=patchelf):
                    report.add(path, "set ELF RPATH", rpath)
        except (OSError, subprocess.SubprocessError):
            continue

    _link_julia_bin(report)

    if owns_report:
        for change in report.changes:
            status("Patching", report.describe(change))
    return report


JULIAUP_AFTER = RuntimeCommand(
    argv=(
        "python3",
        "-c",
        "from ship.patches.juliaup import patch_toolchain_dir; patch_toolchain_dir()",
    ),
    forward_args=False,
    ignore_failure=True,
    condition=ArgumentOneOf(1, ("add", "update", "install", "default")),
)


def juliaup_command(
    binary_name: str, real_binary: Path, target_key: str
) -> RuntimeCommand | None:
    """Use QEMU's Termux sysroot for Juliaup network access only.

    The native Julia launcher stays outside QEMU to avoid emulating the Julia
    runtime. Juliaup's musl resolver needs the Termux sysroot's resolv.conf.
    """
    qemu = shutil.which("qemu-aarch64")
    if not qemu:
        return None
    return RuntimeCommand(argv=(qemu, "-L", PREFIX, real_binary))


PATCH = PackagePatch(
    reapply=(patch_toolchain_dir,),
    runtime=(
        RuntimePatch(
            binaries=("juliaup",),
            targets=("aarch64-*",),
            after=JULIAUP_AFTER,
            command=juliaup_command,
        ),
    ),
)
