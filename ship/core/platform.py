"""Host OS / architecture detection and target-candidate expansion."""

from __future__ import annotations

import shutil

from ship.core.profile import _normalize_arch, get_active_profile
import platform as py_platform


def detect_target_keys(override: str | None = None) -> list[str]:
    if override:
        return [override]

    profile = get_active_profile()
    targets = list(profile.target_priority)
    arch = _normalize_arch(py_platform.machine())

    # QEMU user-emulation expansion for foreign architectures.
    if arch != "x86_64" and shutil.which("qemu-x86_64"):
        targets.extend(["x86_64-linux-musl", "x86_64-linux-gnu"])
    if arch != "armv7" and shutil.which("qemu-arm"):
        targets.extend(["armv7-linux-musl", "armv7-linux-gnu"])
    if arch != "riscv64" and shutil.which("qemu-riscv64"):
        targets.extend(["riscv64-linux-musl", "riscv64-linux-gnu"])
    if arch != "i686" and shutil.which("qemu-i386"):
        targets.extend(["i686-linux-musl", "i686-linux-gnu"])

    return targets
