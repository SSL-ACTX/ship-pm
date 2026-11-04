"""Archive extraction into the package store."""

from __future__ import annotations

import bz2
import gzip
import lzma
import re
import shutil
import subprocess
import tarfile
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path

from ship.ui import Progress


def _tracked_archive_members(
    members: Iterable[tarfile.TarInfo | zipfile.ZipInfo],
    progress: Progress,
    total: int | None,
) -> Iterator[tarfile.TarInfo | zipfile.ZipInfo]:
    for count, member in enumerate(members, 1):
        yield member
        progress.update(count, total)


def _copy_with_progress(
    source,
    destination,
    progress: Progress,
    *,
    offset: int = 0,
) -> None:
    copied = 0
    while chunk := source.read(64 * 1024):
        destination.write(chunk)
        copied += len(chunk)
        progress.update(offset + copied)


def extract_archive(archive_path: Path, extract_dir: Path, pkg_name: str) -> None:
    """Extract an archive safely into an isolated store directory."""
    extract_dir.mkdir(parents=True, exist_ok=True)
    bin_dir = extract_dir / "bin"
    bin_dir.mkdir(exist_ok=True)

    name = archive_path.name.lower()
    progress = Progress("Extracting", extract_dir.name, unit="files")
    try:
        if name.endswith((".tar.gz", ".tgz")):
            with tarfile.open(archive_path, "r:gz") as tar:
                members = tar.getmembers()
                progress.set_total(len(members))
                tar.extractall(
                    extract_dir,
                    members=_tracked_archive_members(members, progress, len(members)),
                )
        elif name.endswith((".tar.xz", ".txz")):
            with tarfile.open(archive_path, "r:xz") as tar:
                members = tar.getmembers()
                progress.set_total(len(members))
                tar.extractall(
                    extract_dir,
                    members=_tracked_archive_members(members, progress, len(members)),
                )
        elif name.endswith((".tar.bz2", ".tbz2")):
            with tarfile.open(archive_path, "r:bz2") as tar:
                members = tar.getmembers()
                progress.set_total(len(members))
                tar.extractall(
                    extract_dir,
                    members=_tracked_archive_members(members, progress, len(members)),
                )
        elif name.endswith(".tar.zst"):
            decoder = shutil.which("zstd") or shutil.which("unzstd")
            if not decoder:
                raise RuntimeError(
                    "Cannot extract .tar.zst archive: install 'zstd' first."
                )
            proc = subprocess.Popen(
                [decoder, "-dc", str(archive_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            count = 0
            try:
                with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:

                    def tracked_stream_members():
                        nonlocal count
                        for member in tar:
                            yield member
                            count += 1
                            progress.update(count)

                    tar.extractall(extract_dir, members=tracked_stream_members())
                _, error = proc.communicate()
            except Exception:
                proc.kill()
                proc.communicate()
                raise
            if proc.returncode:
                raise RuntimeError(
                    f"zstd extraction failed: {error.decode(errors='replace').strip()}"
                )
        elif name.endswith(".tar"):
            with tarfile.open(archive_path, "r:") as tar:
                members = tar.getmembers()
                progress.set_total(len(members))
                tar.extractall(
                    extract_dir,
                    members=_tracked_archive_members(members, progress, len(members)),
                )
        elif name.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as z:
                members = z.infolist()
                progress.set_total(len(members))
                z.extractall(
                    extract_dir,
                    members=_tracked_archive_members(members, progress, len(members)),
                )
        elif name.endswith(".7z"):
            extractor: tuple[str, str] | None = None
            for command in ("7zz", "7z", "7za", "bsdtar"):
                exe = shutil.which(command)
                if exe:
                    extractor = exe, command
                    break
            if not extractor:
                raise RuntimeError("Cannot extract .7z archive: install 7zz or bsdtar.")
            executable, command = extractor
            if command == "bsdtar":
                progress.unit = "archive"
                args = [executable, "-xf", str(archive_path), "-C", str(extract_dir)]
            else:
                progress.unit = "%"
                progress.set_total(100)
                args = [
                    executable,
                    "x",
                    "-y",
                    f"-o{extract_dir}",
                    str(archive_path),
                    "-bsp1",
                ]
            proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            output_tail = bytearray()
            pending = bytearray()
            assert proc.stdout is not None
            while chunk := proc.stdout.read(4096):
                output_tail.extend(chunk)
                if len(output_tail) > 4096:
                    del output_tail[:-4096]
                pending.extend(chunk)
                while b"\r" in pending or b"\n" in pending:
                    seps = [
                        i for i in (pending.find(b"\r"), pending.find(b"\n")) if i >= 0
                    ]
                    idx = min(seps)
                    line = bytes(pending[:idx])
                    del pending[: idx + 1]
                    match = re.search(rb"\b(\d{1,3})%", line)
                    if match:
                        progress.update(min(100, int(match.group(1))), 100)
            if proc.wait():
                raise RuntimeError(
                    f"7z extraction failed: {output_tail.decode(errors='replace').strip()}"
                )
            progress.update(100, 100)
        elif name.endswith((".gz", ".xz", ".bz2")):
            dest_file = bin_dir / (f"{pkg_name}.exe" if ".exe" in name else pkg_name)
            opener = (
                gzip.open
                if name.endswith(".gz")
                else lzma.open
                if name.endswith(".xz")
                else bz2.open
            )
            progress.unit = "bytes"
            with opener(archive_path, "rb") as f_in, open(dest_file, "wb") as f_out:
                _copy_with_progress(f_in, f_out, progress)
        else:
            dest = bin_dir / pkg_name
            progress.unit = "bytes"
            with open(archive_path, "rb") as f_in, open(dest, "wb") as f_out:
                _copy_with_progress(f_in, f_out, progress)
            dest.chmod(0o755)

        if progress.unit == "files" and progress.total is None:
            progress.set_total(progress.current)
        progress.finish()
    except Exception:
        progress.finish(success=False)
        raise
