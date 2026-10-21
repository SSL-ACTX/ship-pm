"""Shared helpers for CLI command handlers."""

from __future__ import annotations

import os
import re
from pathlib import Path


def clean_repo_slug(raw_input: str) -> str:
    cleaned = re.sub(r"^https?://github\.com/", "", raw_input).strip()
    cleaned = cleaned.rstrip("/")
    cleaned = cleaned.removesuffix(".git")
    return cleaned.rstrip("/")


def installed_size_bytes(install_dir: Path) -> int | None:
    if not install_dir.is_dir():
        return None
    total = 0
    for root, _, files in os.walk(install_dir, followlinks=False):
        for filename in files:
            path = Path(root) / filename
            try:
                if not path.is_symlink():
                    total += path.stat().st_size
            except OSError:
                continue
    return total
