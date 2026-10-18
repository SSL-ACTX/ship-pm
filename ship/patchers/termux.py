"""Termux-specific Glibc binary patcher and LD_PRELOAD wrapper."""

import os
import platform
import re
import shutil
import struct
import subprocess
from pathlib import Path

from ship.config import IS_TERMUX, PREFIX
from ship.patchers.base import BinaryPatcher
from ship.ui import status


class TermuxGlibcPatcher(BinaryPatcher):
    """Patches dynamic glibc ELF binaries and wraps them for native execution under Termux."""

    name = "termux-glibc"

    @staticmethod
    def has_dynamic_interpreter(file_path: Path) -> bool:
        """Parses the ELF Program Header Table to check for PT_INTERP (segment type 0x03)."""
        try:
            with open(file_path, "rb") as f:
                header = f.read(64)
                if not header.startswith(b"\x7fELF"):
                    return False

                ei_class = header[4]
                # 64-bit ELF
                if ei_class == 2:
                    e_phoff = struct.unpack_from("<Q", header, 32)[0]
                    e_phentsize = struct.unpack_from("<H", header, 54)[0]
                    e_phnum = struct.unpack_from("<H", header, 56)[0]
                    f.seek(e_phoff)
                    ph_data = f.read(e_phentsize * e_phnum)
                    for i in range(e_phnum):
                        p_type = struct.unpack_from(
                            "<I", ph_data, i * e_phentsize
                        )[0]
                        if p_type == 3:  # PT_INTERP
                            return True
                # 32-bit ELF
                elif ei_class == 1:
                    e_phoff = struct.unpack_from("<I", header, 28)[0]
                    e_phentsize = struct.unpack_from("<H", header, 42)[0]
                    e_phnum = struct.unpack_from("<H", header, 44)[0]
                    f.seek(e_phoff)
                    ph_data = f.read(e_phentsize * e_phnum)
                    for i in range(e_phnum):
                        p_type = struct.unpack_from(
                            "<I", ph_data, i * e_phentsize
                        )[0]
                        if p_type == 3:  # PT_INTERP
                            return True
        except (OSError, struct.error):
            return False

        return False

    def should_patch(self, binary_path: Path, target_key: str) -> bool:
        if not IS_TERMUX:
            return False

        if "linux-gnu" in target_key or binary_path.name == "odin":
            return True

        return self.has_dynamic_interpreter(binary_path)

    def patch(self, binary_path: Path, target_key: str) -> Path:
        glibc_pfx = Path(os.environ.get("GLIBC_PREFIX", f"{PREFIX}/glibc"))
        arch = platform.machine().lower()

        if arch in ("aarch64", "arm64"):
            loader_name = "ld-linux-aarch64.so.1"
        elif arch in ("x86_64", "amd64"):
            loader_name = "ld-linux-x86-64.so.2"
        elif arch.startswith("arm"):
            loader_name = "ld-linux-armhf.so.3"
        elif re.match(r"^i\d86$", arch):
            loader_name = "ld-linux.so.2"
        elif arch == "riscv64":
            loader_name = "ld-linux-riscv64-lp64d.so.1"
        else:
            loader_name = ""

        loader_path = glibc_pfx / "lib" / loader_name
        rpath = str(glibc_pfx / "lib")

        if loader_path.is_file():
            patchelf_bin = shutil.which("patchelf")
            if patchelf_bin:
                status("Patching", f"glibc interpreter for {binary_path.name}")
                subprocess.run(
                    [
                        patchelf_bin,
                        "--set-interpreter",
                        str(loader_path),
                        "--set-rpath",
                        rpath,
                        str(binary_path),
                    ],
                    check=False,
                    capture_output=True,
                )

        real_binary = binary_path.parent / f"{binary_path.name}-real"
        if not real_binary.exists():
            shutil.move(binary_path, real_binary)

        extra_env = ""
        if binary_path.name == "odin":
            extra_env = f'export ODIN_ROOT="{binary_path.parent}"'

        wrapper_content = f"""#!/data/data/com.termux/files/usr/bin/bash
# ship runtime wrapper - isolates environment and sets loader paths
unset LD_PRELOAD
export SSL_CERT_FILE="{glibc_pfx}/etc/ssl/certs/ca-certificates.crt"
{extra_env}
exec "{real_binary}" "$@"
"""
        binary_path.write_text(wrapper_content, encoding="utf-8")
        binary_path.chmod(0o755)
        real_binary.chmod(0o755)
        return binary_path
