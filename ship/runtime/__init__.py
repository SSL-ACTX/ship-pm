"""Platform runtime adapters applied to linked binaries."""

from pathlib import Path

from ship.api import (
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
from ship.runtime.base import BinaryPatcher, LauncherTemplate, install_launcher
from ship.runtime.qemu import QemuRunnerPatcher
from ship.runtime.termux import TermuxPatcher

# Emulation wrappers first so foreign ELFs are QEMU-wrapped before host adapters.
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


__all__ = [
    "BinaryPatcher",
    "BinaryQuery",
    "ElfClass",
    "ElfInfo",
    "ExportPolicy",
    "InstallPatch",
    "LauncherTemplate",
    "PATCHERS",
    "PackagePatch",
    "PatchContext",
    "PatchReport",
    "QemuRunnerPatcher",
    "ReapplyHandler",
    "RuntimeCommand",
    "RuntimePatch",
    "TermuxPatcher",
    "apply_patchers",
    "inspect_elf",
    "install_launcher",
]
