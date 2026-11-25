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

    def extract_payload(
        self, destination: Path, progress: Any = None
    ) -> dict[str, Any]:
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
                    self._extract_and_flatten_data(
                        raw_data, destination, progress=progress
                    )

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

    def _extract_and_flatten_data(
        self, raw_tar: bytes, destination: Path, progress: Any = None
    ) -> None:
        """Extract tar contents and flatten /usr/bin -> bin, /usr/lib -> lib, /usr/share -> share."""
        temp_extract = destination / ".deb_raw_extract"
        temp_extract.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(fileobj=io.BytesIO(raw_tar)) as tf:
                members = tf.getmembers()
                if progress is not None:
                    progress.set_total(len(members))
                for idx, member in enumerate(members, 1):
                    tf.extract(member, temp_extract, filter="fully_trusted")
                    if progress is not None:
                        progress.update(idx, len(members))

            # Relocate from deep prefix (e.g. Termux's data/data/com.termux/files/usr), usr/, or root
            candidates = [
                temp_extract / "data" / "data" / "com.termux" / "files" / "usr",
                temp_extract / "usr",
                temp_extract,
            ]
            relocated = False
            for candidate in candidates:
                if not candidate.is_dir():
                    continue

                bin_dir = candidate / "bin"
                if bin_dir.is_dir():
                    dst_bin = destination / "bin"
                    dst_bin.mkdir(parents=True, exist_ok=True)
                    for item in bin_dir.iterdir():
                        shutil.move(str(item), str(dst_bin / item.name))
                    relocated = True

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
                    relocated = True

                share_dir = candidate / "share"
                if share_dir.is_dir():
                    dst_share = destination / "share"
                    dst_share.mkdir(parents=True, exist_ok=True)
                    for item in share_dir.iterdir():
                        shutil.move(str(item), str(dst_share / item.name))
                    relocated = True

                if relocated:
                    break
        finally:
            shutil.rmtree(temp_extract, ignore_errors=True)
