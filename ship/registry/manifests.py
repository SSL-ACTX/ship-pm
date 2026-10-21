"""Package manifest loading from the local registry index."""

from __future__ import annotations

import json
from pathlib import Path

from ship.core.settings import get_pkgs_dir
from ship.registry.sync import ensure_registry

_UBUNTU_CACHE: dict | None = None


def _bundled_registry_path() -> Path | None:
    """Fallback: bundled ubuntu-noble.json shipped with the repo."""
    repo_root = get_pkgs_dir().parent
    for p in (
        repo_root / "registries" / "ubuntu-noble.json",
        Path("registries/ubuntu-noble.json"),
    ):
        if p.is_file():
            return p
    return None


def load_secondary_registries() -> dict[str, dict]:
    global _UBUNTU_CACHE
    if _UBUNTU_CACHE is not None:
        return _UBUNTU_CACHE

    from ship.registry.ubuntu import load_ubuntu_registry

    data = load_ubuntu_registry()

    # If cache is empty fall back to bundled file
    if not data:
        p = _bundled_registry_path()
        if p:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}

    _UBUNTU_CACHE = data
    return _UBUNTU_CACHE


def invalidate_secondary_cache() -> None:
    global _UBUNTU_CACHE
    _UBUNTU_CACHE = None


def get_pkg_manifest(pkg_name: str) -> dict | None:
    ensure_registry()
    name = pkg_name.lower().strip()

    # Direct Ubuntu prefix syntax: ubuntu:package or u:package
    if name.startswith(("ubuntu:", "u:")):
        clean_name = name.split(":", 1)[1]
        return load_secondary_registries().get(clean_name)

    # Standard registry package lookup
    path = get_pkgs_dir() / f"{name}.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    # Transparent fallback to secondary registries
    return load_secondary_registries().get(name)
