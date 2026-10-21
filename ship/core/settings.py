"""Centralized Ship settings derived from the active Profile and environment."""

from __future__ import annotations

import os
from pathlib import Path

from ship.core.profile import Profile, get_active_profile


def _registry_repo_from_git(git_url: str) -> str:
    value = git_url.strip()
    if value.startswith("git@github.com:"):
        value = value.removeprefix("git@github.com:")
    else:
        value = value.removeprefix("https://github.com/")
    return value.removesuffix(".git").strip("/") or "SSL-ACTX/ship-pm"


class Settings:
    """Lazy facade over the active profile plus registry/network defaults."""

    @property
    def profile(self) -> Profile:
        return get_active_profile()

    @property
    def is_termux(self) -> bool:
        return self.profile.is_termux

    @property
    def home(self) -> Path:
        return self.profile.home

    @property
    def prefix(self) -> Path:
        return self.profile.paths.prefix

    @property
    def ship_root(self) -> Path:
        return self.profile.data_root

    @property
    def ship_bin_dir(self) -> Path:
        return self.profile.bin_dir

    @property
    def ship_cache_dir(self) -> Path:
        return self.profile.cache_dir

    @property
    def ship_store_dir(self) -> Path:
        return self.profile.store_dir

    @property
    def ship_internal_bin(self) -> Path:
        return self.profile.internal_bin

    @property
    def ship_backup_dir(self) -> Path:
        return self.profile.backup_dir

    @property
    def ship_state_file(self) -> Path:
        return self.profile.state_file

    @property
    def ship_registry_dir(self) -> Path:
        return self.profile.registry_dir

    @property
    def system_bin_dirs(self) -> tuple[Path, ...]:
        return self.profile.forbid_bin_dirs

    @property
    def ship_registry_git(self) -> str:
        return os.environ.get(
            "SHIP_REGISTRY_GIT", "https://github.com/SSL-ACTX/ship-pm.git"
        )

    @property
    def ship_registry_repo(self) -> str:
        return os.environ.get(
            "SHIP_REGISTRY_REPO", _registry_repo_from_git(self.ship_registry_git)
        )

    @property
    def ship_update_url(self) -> str:
        return os.environ.get(
            "SHIP_UPDATE_URL",
            "https://github.com/SSL-ACTX/ship-pm/raw/refs/heads/main/bin/ship",
        )

    @property
    def ship_bridge_url(self) -> str:
        return os.environ.get(
            "SHIP_REGISTRY_BRIDGE",
            "https://corrupted-lily-1011.callixjeira.workers.dev/",
        )


settings = Settings()


def get_pkgs_dir() -> Path:
    if Path("./pkgs").is_dir():
        return Path("./pkgs").resolve()
    script_dir = Path(__file__).resolve().parent.parent
    if (script_dir.parent / "pkgs").is_dir():
        return (script_dir.parent / "pkgs").resolve()
    return settings.ship_registry_dir / "pkgs"
