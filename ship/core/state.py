"""Persistent install-state I/O under the active profile's data root."""

from __future__ import annotations

import json

from ship.core.settings import settings


def init_dirs() -> None:
    profile = settings.profile
    for path in (
        profile.data_root,
        profile.cache_dir,
        profile.store_dir,
        profile.internal_bin,
        profile.bin_dir,
        profile.backup_dir,
        profile.registry_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
    if not profile.state_file.exists():
        profile.state_file.write_text('{"installed":{},"backups":{}}\n')


def load_state() -> dict:
    init_dirs()
    try:
        return json.loads(settings.ship_state_file.read_text())
    except (json.JSONDecodeError, OSError):
        return {"installed": {}, "backups": {}}


def save_state(state: dict) -> None:
    settings.ship_state_file.write_text(json.dumps(state, indent=2) + "\n")
