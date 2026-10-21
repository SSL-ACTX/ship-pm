"""Git-backed registry index synchronization."""

from __future__ import annotations

import os
import shutil

from ship.core.settings import get_pkgs_dir, settings
from ship.core.state import init_dirs
from ship.ui import status, warn


def sync_registry() -> None:
    init_dirs()
    registry_git = settings.ship_registry_git
    registry_dir = settings.ship_registry_dir
    status("Updating", f"registry index from {registry_git}...")
    git_dir = registry_dir / ".git"
    if git_dir.is_dir():
        res = os.system(f"git -C '{registry_dir}' pull --ff-only >/dev/null 2>&1")
        if res == 0:
            status("Finished", "registry index updated")
            return

    shutil.rmtree(registry_dir, ignore_errors=True)
    res = os.system(
        f"git clone --depth 1 '{registry_git}' '{registry_dir}' >/dev/null 2>&1"
    )
    if res == 0:
        status("Finished", "registry index cloned")
    else:
        warn("Git clone failed. Checking local package manifests...")


def ensure_registry() -> None:
    pkgs = get_pkgs_dir()
    if not pkgs.is_dir() or not any(pkgs.glob("*.json")):
        sync_registry()
