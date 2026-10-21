"""Package registry synchronization, manifest loading, and network downloads."""

import hashlib
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from ship import __version__
from ship.config import (
    SHIP_REGISTRY_DIR,
    SHIP_REGISTRY_GIT,
    get_pkgs_dir,
    init_dirs,
)
from ship.ui import die, status, warn


def sync_registry() -> None:
    init_dirs()
    status("Updating", f"registry index from {SHIP_REGISTRY_GIT}...")
    git_dir = SHIP_REGISTRY_DIR / ".git"
    if git_dir.is_dir():
        res = os.system(f"git -C '{SHIP_REGISTRY_DIR}' pull --ff-only >/dev/null 2>&1")
        if res == 0:
            status("Finished", "registry index updated")
            return

    shutil.rmtree(SHIP_REGISTRY_DIR, ignore_errors=True)
    res = os.system(
        f"git clone --depth 1 '{SHIP_REGISTRY_GIT}' '{SHIP_REGISTRY_DIR}' >/dev/null 2>&1"
    )
    if res == 0:
        status("Finished", "registry index cloned")
    else:
        warn("Git clone failed. Checking local package manifests...")


def ensure_registry() -> None:
    pkgs = get_pkgs_dir()
    if not pkgs.is_dir() or not any(pkgs.glob("*.json")):
        sync_registry()


def get_pkg_manifest(pkg_name: str) -> dict | None:
    ensure_registry()
    path = get_pkgs_dir() / f"{pkg_name.lower()}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def fetch_file(url: str, dest_path: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": f"ship/{__version__}"})
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{dest_path.name}.", dir=dest_path.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        with (
            urllib.request.urlopen(req) as resp,
            open(temp_path, "wb") as out,
        ):
            shutil.copyfileobj(resp, out)
        os.replace(temp_path, dest_path)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
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

    status("Downloading", url)
    fetch_file(url, dest_path)
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
