"""Patcher and runner registry."""

from pathlib import Path

from ship.patchers.base import BinaryPatcher
from ship.patchers.qemu import QemuRunnerPatcher
from ship.patchers.termux import TermuxPatcher
from ship.patches.api import PatchReport

# Execution order: native platform patches (glibc/patchelf/SSL) first, then emulation wrappers
PATCHERS: list[BinaryPatcher] = [
    TermuxPatcher(),
    QemuRunnerPatcher(),
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
