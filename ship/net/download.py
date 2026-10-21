"""HTTP download helpers with optional SHA-256 verification and caching."""

from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ship import __version__
from ship.ui import Progress, die, status, warn


def fetch_file(url: str, dest_path: Path, *, label: str | None = None) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": f"ship/{__version__}"})
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{dest_path.name}.", dir=dest_path.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    display_name = label or Path(urllib.parse.urlsplit(url).path).name or url
    progress = Progress("Downloading", display_name)
    try:
        with (
            urllib.request.urlopen(req) as resp,
            open(temp_path, "wb") as out,
        ):
            try:
                total = int(resp.headers.get("Content-Length", ""))
            except ValueError:
                total = 0
            progress.set_total(total)
            downloaded = 0
            while chunk := resp.read(64 * 1024):
                out.write(chunk)
                downloaded += len(chunk)
                progress.update(downloaded)
        os.replace(temp_path, dest_path)
        progress.update(downloaded, total or None)
        progress.finish()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        progress.finish(success=False)
        temp_path.unlink(missing_ok=True)
        die(f"Download failed from {url}: {e}")


def fetch_cached_file(
    url: str,
    dest_path: Path,
    *,
    expected_sha256: str = "",
    description: str = "archive",
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

    fetch_file(url, dest_path, label=description)
    if expected_sha256:
        status("Verifying", f"SHA-256 checksum ({expected_sha256[:12]}...)...")
        actual_sha = calc_sha256(dest_path)
        if actual_sha.lower() != expected_sha256.lower():
            dest_path.unlink(missing_ok=True)
            die(
                f"Checksum mismatch for {description}!\n"
                f"  Expected: {expected_sha256}\n  Got:      {actual_sha}"
            )
    return dest_path


def calc_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()
