"""Host OS, architecture, libc detection, and target candidate matching."""

import platform
import re
import shutil
from pathlib import Path

from ship.config import IS_TERMUX


def detect_target_keys(override: str | None = None) -> list[str]:
    if override:
        return [override]

    raw_os = platform.system().lower()
    raw_arch = platform.machine().lower()

    if raw_arch in ("x86_64", "amd64", "x64"):
        arch = "x86_64"
    elif raw_arch in ("aarch64", "arm64"):
        arch = "aarch64"
    elif raw_arch.startswith("armv7") or raw_arch in ("armhf", "arm"):
        arch = "armv7"
    elif raw_arch.startswith("armv6") or raw_arch == "armel":
        arch = "armv6"
    elif raw_arch == "riscv64":
        arch = "riscv64"
    elif raw_arch in ("ppc64le", "powerpc64le"):
        arch = "powerpc64le"
    elif raw_arch == "s390x":
        arch = "s390x"
    elif re.match(r"^i\d86$", raw_arch) or raw_arch == "x86":
        arch = "i686"
    else:
        arch = raw_arch

    targets: list[str] = []

    if raw_os == "darwin":
        targets = (
            ["aarch64-apple-darwin", "x86_64-apple-darwin"]
            if arch == "aarch64"
            else ["x86_64-apple-darwin"]
        )
    elif raw_os == "freebsd":
        targets = [f"{arch}-freebsd"]
    elif raw_os == "openbsd":
        targets = [f"{arch}-openbsd"]
    elif raw_os == "netbsd":
        targets = [f"{arch}-netbsd"]
    elif raw_os == "windows":
        targets = [f"{arch}-pc-windows-msvc", f"{arch}-pc-windows-gnu"]
    elif IS_TERMUX:
        targets = [
            f"{arch}-linux-musl",
            f"{arch}-termux",
            f"{arch}-android",
            f"{arch}-linux-android",
            f"{arch}-linux-gnu",
        ]
    else:
        is_musl = False
        try:
            for p in (
                "/lib/ld-musl-x86_64.so.1",
                "/lib/ld-musl-aarch64.so.1",
                "/usr/lib/ld-musl-x86_64.so.1",
            ):
                if Path(p).exists():
                    is_musl = True
                    break
        except OSError:
            pass

        targets = (
            [f"{arch}-linux-musl", f"{arch}-linux-gnu"]
            if is_musl
            else [f"{arch}-linux-gnu", f"{arch}-linux-musl"]
        )

    # QEMU User Emulation Target Expansion
    # Automatically append foreign targets if corresponding qemu-user emulator is in PATH
    if arch != "x86_64" and shutil.which("qemu-x86_64"):
        targets.extend(["x86_64-linux-musl", "x86_64-linux-gnu"])

    if arch != "armv7" and shutil.which("qemu-arm"):
        targets.extend(["armv7-linux-musl", "armv7-linux-gnu"])

    if arch != "riscv64" and shutil.which("qemu-riscv64"):
        targets.extend(["riscv64-linux-musl", "riscv64-linux-gnu"])

    if arch != "i686" and shutil.which("qemu-i386"):
        targets.extend(["i686-linux-musl", "i686-linux-gnu"])

    return targets
