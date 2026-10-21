"""Patcher and runner registry."""

from pathlib import Path

from ship.patchers.api import (
    BinaryQuery,
    ElfClass,
    ElfInfo,
    ExportPolicy,
    InstallPatch,
    PackagePatch,
    PatchContext,
    PatchReport,
    ReapplyHandler,
    RuntimeCommand,
    RuntimePatch,
    inspect_elf,
)
from ship.patchers.base import BinaryPatcher, LauncherTemplate, install_launcher
from ship.patchers.qemu import QemuRunnerPatcher
from ship.patchers.termux import TermuxPatcher

# Execution order: emulation wrappers first (so foreign ELF binaries get QEMU launchers),
# or native platform patches (glibc/patchelf/SSL) for native binaries.
PATCHERS: list[BinaryPatcher] = [
    QemuRunnerPatcher(),
    TermuxPatcher(),
]


def apply_patchers(
    binary_path: Path,
    target_key: str,
    report: PatchReport | None = None,
) -> Path:
    current = binary_path
    for patcher in PATCHERS:
        if patcher.should_patch(current, target_key):
            current = patcher.patch(current, target_key, report)
    return current
