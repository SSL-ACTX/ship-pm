"""Package manifest loading from the local registry index."""

from __future__ import annotations

import json

from ship.core.settings import get_pkgs_dir
from ship.registry.sync import ensure_registry


def get_pkg_manifest(pkg_name: str) -> dict | None:
    ensure_registry()
    path = get_pkgs_dir() / f"{pkg_name.lower()}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
