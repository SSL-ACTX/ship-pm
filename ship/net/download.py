"""HTTP download helpers with optional SHA-256 verification and caching."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ship.net.engine import DownloadEngine, get_default_engine
from ship.ui import die, status, warn


def fetch_file(
    url: str,
    dest_path: Path,
    *,
    label: str | None = None,
    engine: DownloadEngine | None = None,
) -> Path:
    eng = engine or get_default_engine()
    return eng.download(url, dest_path, label=label)


def fetch_cached_file(
    url: str,
    dest_path: Path,
    *,
    expected_sha256: str = "",
    description: str = "archive",
    engine: DownloadEngine | None = None,
) -> Path:
    """Reuse a cached download, verifying it when a checksum is available."""
    if dest_path.is_file() and dest_path.stat().st_size > 0:
        if expected_sha256:
            actual_sha = calc_sha256(dest_path)
            if actual_sha.lower() != expected_sha256.lower():
                warn(
                    f"Cached {description} failed SHA-256 verification; downloading again."
                )
                dest_path.unlink(missing_ok=True)
            else:
                status("Cached", f"reusing verified {description}")
                return dest_path
        else:
            status("Cached", f"reusing {description} (no SHA-256 checksum available)")
            return dest_path
    elif dest_path.exists():
        dest_path.unlink(missing_ok=True)

    eng = engine or get_default_engine()
    # DownloadEngine handles inline SHA-256 verification and atomic replacement directly
    eng.download(
        url,
        dest_path,
        label=description,
        expected_sha256=expected_sha256,
    )

    if expected_sha256 and not dest_path.is_file():
        die(f"Download failed verification for {description}")

    return dest_path


def calc_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()
