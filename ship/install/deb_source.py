"""Rootless Debian (.deb) package transmuter and relocator."""

from __future__ import annotations

import io
import shutil
import tarfile
from pathlib import Path
from typing import Any

from ship.ui import die


class DebArchive:
    """Pure-Python Unix ar and .deb archive extractor."""

    def __init__(self, deb_path: Path | str) -> None:
        self.path = Path(deb_path)
        if not self.path.is_file():
            die(f"Debian archive not found: {self.path}")

    def extract_payload(self, destination: Path) -> dict[str, Any]:
        """Extract data.tar.* and control.tar.* from .deb, flattening filesystem hierarchy."""
        destination.mkdir(parents=True, exist_ok=True)
        control_info: dict[str, str] = {}

        with open(self.path, "rb") as f:
            magic = f.read(8)
            if magic != b"!<arch>\n":
                die(f"Invalid Debian ar archive format: {self.path.name}")

            while True:
                header = f.read(60)
                if len(header) < 60:
                    break
                name = header[:16].decode("ascii", errors="ignore").strip().rstrip("/")
                size_str = header[48:58].decode("ascii", errors="ignore").strip()
                try:
                    size = int(size_str)
                except ValueError:
                    break

                raw_data = f.read(size)
                if size % 2 == 1:
                    f.read(1)  # Pad byte

                if name.startswith("control.tar"):
                    control_info = self._parse_control(raw_data)
                elif name.startswith("data.tar"):
                    self._extract_and_flatten_data(raw_data, destination)

        return control_info

    def _parse_control(self, raw_tar: bytes) -> dict[str, str]:
        info: dict[str, str] = {}
        try:
            with tarfile.open(fileobj=io.BytesIO(raw_tar)) as tf:
                for member in tf.getmembers():
                    if member.name.endswith("control") or member.name == "./control":
                        cf = tf.extractfile(member)
                        if cf:
                            for line in (
                                cf.read().decode("utf-8", errors="ignore").splitlines()
                            ):
                                if ":" in line:
                                    k, v = line.split(":", 1)
                                    info[k.strip().lower()] = v.strip()
        except (tarfile.TarError, OSError):
            return info
        return info

    def _extract_and_flatten_data(self, raw_tar: bytes, destination: Path) -> None:
        """Extract tar contents and flatten /usr/bin -> bin, /usr/lib -> lib, /usr/share -> share."""
        temp_extract = destination / ".deb_raw_extract"
        temp_extract.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(fileobj=io.BytesIO(raw_tar)) as tf:
                tf.extractall(temp_extract)

            # Relocate from usr/ or standard root
            candidates = [
                temp_extract / "usr",
                temp_extract,
            ]
            for candidate in candidates:
                if not candidate.is_dir():
                    continue

                bin_dir = candidate / "bin"
                if bin_dir.is_dir():
                    dst_bin = destination / "bin"
                    dst_bin.mkdir(parents=True, exist_ok=True)
                    for item in bin_dir.iterdir():
                        shutil.move(str(item), str(dst_bin / item.name))

                lib_dir = candidate / "lib"
                if lib_dir.is_dir():
                    dst_lib = destination / "lib"
                    dst_lib.mkdir(parents=True, exist_ok=True)
                    for item in lib_dir.iterdir():
                        if item.is_dir():
                            for sub in item.iterdir():
                                shutil.move(str(sub), str(dst_lib / sub.name))
                        else:
                            shutil.move(str(item), str(dst_lib / item.name))

                share_dir = candidate / "share"
                if share_dir.is_dir():
                    dst_share = destination / "share"
                    dst_share.mkdir(parents=True, exist_ok=True)
                    for item in share_dir.iterdir():
                        shutil.move(str(item), str(dst_share / item.name))
        finally:
            shutil.rmtree(temp_extract, ignore_errors=True)
