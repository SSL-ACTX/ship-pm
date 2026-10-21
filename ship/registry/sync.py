"""Git-backed registry index synchronization."""

from __future__ import annotations

import shutil
import subprocess

from ship.core.settings import get_pkgs_dir, settings
from ship.core.state import init_dirs
from ship.ui import status, warn


def _clone_registry(registry_git: str, registry_dir: str) -> bool:
    shutil.rmtree(registry_dir, ignore_errors=True)
    res = subprocess.run(
        ["git", "clone", "--depth", "1", registry_git, registry_dir],
        capture_output=True,
        check=False,
    )
    return res.returncode == 0


def sync_registry(refresh_ubuntu: bool = False) -> None:
    init_dirs()
    registry_git = settings.ship_registry_git
    registry_dir = settings.ship_registry_dir
    status("Updating", f"registry index from {registry_git}...")
    git_dir = registry_dir / ".git"

    if git_dir.is_dir():
        # First attempt a fast-forward pull
        res = subprocess.run(
            ["git", "-C", str(registry_dir), "pull", "--ff-only"],
            capture_output=True,
            check=False,
        )
        if res.returncode == 0:
            status("Finished", "registry index updated")
        else:
            # If the index cache diverged, has local commits, or ff-only failed,
            # reset to remote tracking branch so user never gets stuck.
            fetch_res = subprocess.run(
                ["git", "-C", str(registry_dir), "fetch", "--depth", "1", "origin"],
                capture_output=True,
                check=False,
            )
            reset_res = subprocess.run(
                ["git", "-C", str(registry_dir), "reset", "--hard", "origin/main"],
                capture_output=True,
                check=False,
            )
            if fetch_res.returncode == 0 and reset_res.returncode == 0:
                status("Finished", "registry index updated (reset to upstream)")
            elif _clone_registry(registry_git, str(registry_dir)):
                status("Finished", "registry index re-cloned")
            else:
                err_msg = res.stderr.decode("utf-8", errors="replace").strip()
                warn(f"Git pull failed: {err_msg}" if err_msg else "Git pull failed.")
    else:
        if _clone_registry(registry_git, str(registry_dir)):
            status("Finished", "registry index cloned")
        else:
            warn("Git clone failed. Checking local package manifests...")

    if refresh_ubuntu:
        from ship.registry.manifests import invalidate_secondary_cache
        from ship.registry.ubuntu import fetch_ubuntu_registry

        fetch_ubuntu_registry(force=True)
        invalidate_secondary_cache()


def refresh_ubuntu_registry() -> None:
    """Force-refresh the Ubuntu deb registry from ports.ubuntu.com."""
    from ship.registry.manifests import invalidate_secondary_cache
    from ship.registry.ubuntu import fetch_ubuntu_registry

    fetch_ubuntu_registry(force=True)
    invalidate_secondary_cache()


def ensure_registry() -> None:
    pkgs = get_pkgs_dir()
    if not pkgs.is_dir() or not any(pkgs.glob("*.json")):
        sync_registry()
