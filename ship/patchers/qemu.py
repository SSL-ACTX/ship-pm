"""Foreign architecture emulation runner via QEMU user mode."""

import platform
import shutil
from pathlib import Path
from typing import ClassVar

from ship.config import PREFIX
from ship.patchers.base import BinaryPatcher
from ship.ui import status, warn


class QemuRunnerPatcher(BinaryPatcher):
    """Wraps foreign-architecture binaries to execute transparently via QEMU user emulator."""

    name = "qemu-runner"

    EMULATOR_MAP: ClassVar[dict[str, str]] = {
        "x86_64": "qemu-x86_64",
        "i686": "qemu-i386",
        "armv7": "qemu-arm",
        "armv6": "qemu-arm",
        "aarch64": "qemu-aarch64",
        "riscv64": "qemu-riscv64",
        "powerpc64le": "qemu-ppc64le",
        "s390x": "qemu-s390x",
    }

    @staticmethod
    def get_target_arch(target_key: str) -> str:
        return target_key.split("-")[0] if "-" in target_key else ""

    def is_foreign_target(self, target_key: str) -> bool:
        host_arch = platform.machine().lower()
        if host_arch in ("arm64", "aarch64"):
            host_arch = "aarch64"
        elif host_arch in ("amd64", "x64"):
            host_arch = "x86_64"

        target_arch = self.get_target_arch(target_key)
        if not target_arch:
            return False

        # If target architecture differs from host architecture, it requires emulation
        return target_arch != host_arch

    def should_patch(self, binary_path: Path, target_key: str) -> bool:
        # Another platform patcher may already have replaced the ELF with a
        # shell launcher. Never wrap that launcher in a second QEMU process.
        try:
            with open(binary_path, "rb") as binary:
                if binary.read(4) != b"\x7fELF":
                    return False
        except OSError:
            return False

        if not self.is_foreign_target(target_key):
            return False

        target_arch = self.get_target_arch(target_key)
        emulator_bin = self.EMULATOR_MAP.get(target_arch)
        return bool(emulator_bin and shutil.which(emulator_bin))

    def patch(self, binary_path: Path, target_key: str) -> Path:
        target_arch = self.get_target_arch(target_key)
        emulator_bin = self.EMULATOR_MAP.get(target_arch, "qemu")

        status(
            "Emulating",
            f"wrapping {binary_path.name} with {emulator_bin} ({target_arch})",
        )

        real_binary = binary_path.parent / f"{binary_path.name}-real"
        if not real_binary.exists():
            shutil.move(binary_path, real_binary)

        bash_path = (
            f"{PREFIX}/bin/bash" if (PREFIX / "bin/bash").exists() else "/bin/sh"
        )
        wrapper_content = f"""#!{bash_path}
# ship foreign architecture runner - {target_arch} via {emulator_bin}
unset LD_PRELOAD
exec {emulator_bin} "{real_binary}" "$@"
"""
        try:
            binary_path.write_text(wrapper_content, encoding="utf-8")
            binary_path.chmod(0o755)
            real_binary.chmod(0o755)
        except OSError as e:
            warn(f"Failed to generate QEMU wrapper for {binary_path.name}: {e}")
            return real_binary

        return binary_path
