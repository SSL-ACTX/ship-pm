"""Archive extraction into the package store with nested archive support."""

from __future__ import annotations

import bz2
import gzip
import hashlib
import lzma
import os
import re
import shutil
import subprocess
import tarfile
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path

from ship.link.discovery import scan_executables
from ship.ui import Progress, status

ARCHIVE_EXTENSIONS = (
    ".tar.gz",
    ".tgz",
    ".tar.xz",
    ".txz",
    ".tar.bz2",
    ".tbz2",
    ".tar.zst",
    ".tar",
    ".zip",
    ".7z",
)

SINGLE_COMPRESSED_EXTENSIONS = (".gz", ".xz", ".bz2")

SKIP_SCAN_DIRS = {
    "doc",
    "docs",
    "example",
    "examples",
    "test",
    "tests",
    "fixture",
    "fixtures",
    ".git",
}


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


def _is_archive_file(path: Path) -> bool:
    if not path.is_file():
        return False
    name = path.name.lower()
    if any(name.endswith(ext) for ext in ARCHIVE_EXTENSIONS):
        return True
    return any(name.endswith(ext) for ext in SINGLE_COMPRESSED_EXTENSIONS) and not any(
        name.endswith(f".tar{ext}") for ext in SINGLE_COMPRESSED_EXTENSIONS
    )


def _score_archive_for_target(path: Path, target_key: str) -> int:
    name = path.name.lower()
    score = 0
    if target_key.lower() in name:
        score += 100

    parts = target_key.lower().split("-")
    t_arch = parts[0]
    t_os = parts[1] if len(parts) > 1 else ""

    arch_matches = (
        (
            t_arch in ("aarch64", "arm64")
            and any(x in name for x in ("aarch64", "arm64"))
        )
        or (
            t_arch in ("x86_64", "amd64")
            and any(x in name for x in ("x86_64", "amd64", "x64"))
        )
        or (
            t_arch in ("armv7", "armhf", "arm")
            and any(x in name for x in ("armv7", "armhf", "arm32", "arm"))
        )
        or (t_arch == "riscv64" and "riscv64" in name)
        or (
            t_arch in ("i686", "i386")
            and any(x in name for x in ("i686", "i386", "386", "x86"))
        )
    )
    if arch_matches:
        score += 40

    if t_os and any(x in name for x in (t_os, "musl", "gnu", "glibc")):
        score += 30

    if len(parts) > 2 and parts[2] in name:
        score += 20

    return score


def _find_nested_archives(extract_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    for root, dirs, files in os.walk(extract_dir):
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_SCAN_DIRS]
        for f in files:
            p = Path(root) / f
            if _is_archive_file(p):
                candidates.append(p)
    candidates.sort(key=lambda p: len(p.relative_to(extract_dir).parts))
    return candidates


def _verify_nested_checksum(archive_path: Path) -> None:
    candidates = [
        archive_path.parent / f"{archive_path.name}.sha256",
        archive_path.parent / f"{archive_path.name}.sha256sum",
        archive_path.with_suffix(".sha256"),
    ]
    for c_file in candidates:
        if c_file.is_file():
            content = c_file.read_text(encoding="utf-8", errors="ignore")
            match = re.search(r"\b[0-9a-fA-F]{64}\b", content)
            if match:
                expected = match.group(0).lower()
                h = hashlib.sha256()
                with open(archive_path, "rb") as f:
                    while chunk := f.read(64 * 1024):
                        h.update(chunk)
                actual = h.hexdigest().lower()
                if actual != expected:
                    raise RuntimeError(
                        f"Checksum verification failed for nested archive {archive_path.name}:\n"
                        f"  Expected: {expected}\n"
                        f"  Actual:   {actual}"
                    )
                status(
                    "Verified",
                    f"nested archive {archive_path.name} against {c_file.name}",
                )
            break


def _extract_single(
    archive_path: Path,
    extract_dir: Path,
    pkg_name: str,
    label: str | None = None,
) -> None:
    """Extract a single archive or compressed binary into the destination directory."""
    extract_dir.mkdir(parents=True, exist_ok=True)
    bin_dir = extract_dir / "bin"
    bin_dir.mkdir(exist_ok=True)

    name = archive_path.name.lower()
    progress = Progress("Extracting", label or extract_dir.name, unit="files")
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
        elif name.endswith(SINGLE_COMPRESSED_EXTENSIONS):
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


def extract_archive(
    archive_path: Path,
    extract_dir: Path,
    pkg_name: str,
    target_key: str | None = None,
) -> None:
    """Extract an archive and resolve any nested archive layers safely."""
    _extract_single(archive_path, extract_dir, pkg_name)

    # Automatically unpack nested archives if no executables exist yet
    max_nesting_levels = 3
    for _ in range(max_nesting_levels):
        if scan_executables(extract_dir):
            break

        nested = _find_nested_archives(extract_dir)
        if not nested:
            break

        if target_key:
            nested.sort(
                key=lambda p: _score_archive_for_target(p, target_key),
                reverse=True,
            )

        target_archive = nested[0]
        _verify_nested_checksum(target_archive)

        _extract_single(
            target_archive,
            extract_dir,
            pkg_name,
            label=f"{extract_dir.name} ({target_archive.name})",
        )

        # Remove the extracted archive and companion files to keep the store clean
        target_archive.unlink(missing_ok=True)
        for ext in (".sha256", ".sha256sum", ".sig", ".asc", ".md5"):
            (target_archive.parent / f"{target_archive.name}{ext}").unlink(
                missing_ok=True
            )
            alt = target_archive.with_suffix(ext)
            if alt != target_archive:
                alt.unlink(missing_ok=True)

        # Remove remaining unselected nested archives
        for other in nested[1:]:
            other.unlink(missing_ok=True)
