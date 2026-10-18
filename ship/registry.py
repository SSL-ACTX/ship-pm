"""Package registry synchronization, manifest loading, and network downloads."""

import hashlib
import json
import os
import shutil
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
    try:
        with (
            urllib.request.urlopen(req) as resp,
            open(dest_path, "wb") as out,
        ):
            shutil.copyfileobj(resp, out)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        die(f"Download failed from {url}: {e}")


def calc_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()
