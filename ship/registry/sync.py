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
        # Get local commit hash before update
        pre_rev = subprocess.run(
            ["git", "-C", str(registry_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()

        # Attempt pull / fetch & reset
        res = subprocess.run(
            ["git", "-C", str(registry_dir), "pull", "--ff-only"],
            capture_output=True,
            check=False,
        )
        if res.returncode != 0:
            subprocess.run(
                ["git", "-C", str(registry_dir), "fetch", "--depth", "1", "origin"],
                capture_output=True,
                check=False,
            )
            subprocess.run(
                ["git", "-C", str(registry_dir), "reset", "--hard", "origin/main"],
                capture_output=True,
                check=False,
            )

        # Get commit hash after update
        post_rev = subprocess.run(
            ["git", "-C", str(registry_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()

        if pre_rev and post_rev and pre_rev != post_rev:
            status("Updated", f"registry updated ({pre_rev[:7]} -> {post_rev[:7]})")
        else:
            status("Up to date", "registry is already at latest upstream")
    else:
        if _clone_registry(registry_git, str(registry_dir)):
            rev = subprocess.run(
                ["git", "-C", str(registry_dir), "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            status("Finished", f"registry index cloned ({rev})")
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
