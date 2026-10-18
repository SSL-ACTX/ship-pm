"""Termux-specific Glibc binary patcher and LD_PRELOAD wrapper."""

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from ship.config import IS_TERMUX, PREFIX
from ship.patchers.base import BinaryPatcher
from ship.ui import status, warn


class TermuxGlibcPatcher(BinaryPatcher):
    """Patches dynamic glibc ELF binaries to execute cleanly under Termux Glibc."""

    name = "termux-glibc"

    @staticmethod
    def is_dynamic_glibc_elf(file_path: Path) -> bool:
        try:
            with open(file_path, "rb") as f:
                content = f.read(4096)
                if not content.startswith(b"\x7fELF"):
                    return False
                return (
                    b"ld-linux" in content
                    or b"/lib64/ld" in content
                    or b"/lib/ld" in content
                )
        except OSError:
            return False

    def should_patch(self, binary_path: Path, target_key: str) -> bool:
        return IS_TERMUX and self.is_dynamic_glibc_elf(binary_path)

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
        rpath = str(glibc_pfx / "lib")  # STRICTLY glibc/lib only

        if loader_path.is_file():
            patchelf_bin = shutil.which("patchelf")
            if patchelf_bin:
                status("Patching", f"glibc interpreter for {binary_path.name}")
                try:
                    subprocess.run(
                        [
                            patchelf_bin,
                            "--set-interpreter",
                            str(loader_path),
                            "--set-rpath",
                            rpath,
                            str(binary_path),
                        ],
                        check=True,
                        capture_output=True,
                    )
                except subprocess.SubprocessError as e:
                    warn(f"patchelf failed: {e}")
                    return binary_path

                # Create an LD_PRELOAD-safe launcher wrapper in place
                real_binary = binary_path.parent / f"{binary_path.name}-real"
                if not real_binary.exists():
                    shutil.move(binary_path, real_binary)
                    wrapper_content = f"""#!/data/data/com.termux/files/usr/bin/bash
# ship glibc wrapper - prevents libtermux-exec.so collisions
unset LD_PRELOAD
export SSL_CERT_FILE="{glibc_pfx}/etc/ssl/certs/ca-certificates.crt"
exec "{real_binary}" "$@"
"""
                    binary_path.write_text(wrapper_content)
                    binary_path.chmod(0o755)
                return binary_path
            else:
                warn(
                    f"{binary_path.name} is a glibc ELF. Run 'pkg install patchelf-glibc' for full glibc support."
                )
        else:
            warn(
                f"{binary_path.name} was built for glibc. Run 'pkg install glibc' or use 'musl' targets on Termux."
            )

        return binary_path
