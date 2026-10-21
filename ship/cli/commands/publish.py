"""Publish and auth command handlers."""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request

from ship import __version__
from ship.admin.github_auth import GitHubCLIError, get_github_identity, get_github_token
from ship.cli.commands._util import clean_repo_slug
from ship.cli.engine import Namespace
from ship.core.settings import settings
from ship.ui import ui

PUBLISH_TIMEOUT_SECONDS = 30


def run_publish(ns: Namespace) -> None:
    repo = clean_repo_slug(ns.repo)
    tag = ns.get("tag") or "latest"
    if "/" not in repo:
        ui.die("Invalid repository format. Expected 'owner/repo'.")

    try:
        identity = get_github_identity()
        token = get_github_token()
    except GitHubCLIError as exc:
        ui.die(str(exc))

    ui.status(
        "Publishing",
        f"{repo} (tag: {tag}) as @{identity.login} to central registry bridge...",
    )
    payload = json.dumps({"repo": repo, "tag": tag}).encode("utf-8")
    req = urllib.request.Request(
        settings.ship_bridge_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"ship/{__version__}",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=PUBLISH_TIMEOUT_SECONDS) as resp:
            ui.status(
                "Finished",
                f"publish request accepted for @{identity.login} (HTTP {resp.status})",
            )
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8", errors="replace")).get(
                "error", ""
            )
        except (json.JSONDecodeError, AttributeError):
            detail = ""
        suffix = f": {detail}" if detail else ""
        ui.die(f"Registry bridge rejected the publish request (HTTP {exc.code}){suffix}")
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            ui.die(
                f"Publish request timed out after {PUBLISH_TIMEOUT_SECONDS} seconds. "
                "The request may already be queued; check before retrying."
            )
        ui.die(f"Publish request failed: {exc}")
    except TimeoutError:
        ui.die(
            f"Publish request timed out after {PUBLISH_TIMEOUT_SECONDS} seconds. "
            "The request may already be queued; check before retrying."
        )
    except OSError as exc:
        ui.die(f"Publish request failed: {exc}")


def run_auth(ns: Namespace) -> None:
    action = ns.get("action") or "status"
    if action == "login":
        if not shutil.which("gh"):
            ui.die(
                "GitHub CLI (`gh`) is required. Install it before running `ship auth login`."
            )
        try:
            result = subprocess.run(["gh", "auth", "login"], check=False)
        except OSError as exc:
            ui.die(f"Could not start GitHub CLI: {exc}")
        if result.returncode:
            ui.die("GitHub login did not complete.")
        action = "status"
    if action != "status":
        ui.die("Usage: ship auth [status|login]")
    try:
        identity = get_github_identity()
    except GitHubCLIError as exc:
        ui.die(str(exc))
    ui.status(
        "GitHub",
        f"authenticated as @{identity.login} (user ID {identity.user_id})",
    )
