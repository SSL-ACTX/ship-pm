"""Low-level GitHub HTTP helpers."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from ship import __version__
from ship.ui import die


def parse_repo_slug(raw_input: str) -> tuple[str, str]:
    slug = re.sub(r"^https?://github\.com/", "", raw_input).strip()
    slug = slug.rstrip("/")
    slug = slug.removesuffix(".git")
    slug = slug.rstrip("/")
    if "/" not in slug:
        die(f"Invalid repository format: '{raw_input}'. Expected 'owner/repo'.")
    parts = slug.split("/", 1)
    return parts[0], parts[1]


def fetch_github_json(url: str) -> dict | list | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"ship/{__version__}",
    }
    gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
