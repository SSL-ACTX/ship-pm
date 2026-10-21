"""GitHub CLI authentication helpers used by publishing and admin commands."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Sequence


class GitHubCLIError(RuntimeError):
    """Raised when GitHub CLI is missing, unauthenticated, or returns an error."""


@dataclass(frozen=True, slots=True)
class GitHubIdentity:
    login: str
    user_id: int


def run_gh(args: Sequence[str]) -> str:
    """Run a non-interactive gh command without exposing its credentials."""
    if not shutil.which("gh"):
        raise GitHubCLIError(
            "GitHub CLI (`gh`) is required. Install it, then run `ship auth login`."
        )
    try:
        result = subprocess.run(
            ["gh", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitHubCLIError(f"Could not run GitHub CLI: {exc}") from exc
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise GitHubCLIError(detail or "GitHub CLI request failed.")
    return result.stdout


def get_github_identity() -> GitHubIdentity:
    """Return the identity GitHub reports for the current gh credential."""
    try:
        user: Any = json.loads(run_gh(["api", "user"]))
        login = user.get("login")
        user_id = user.get("id")
    except (json.JSONDecodeError, AttributeError) as exc:
        raise GitHubCLIError("GitHub returned an invalid authenticated-user response.") from exc
    if not isinstance(login, str) or not login or not isinstance(user_id, int):
        raise GitHubCLIError("GitHub did not return a valid authenticated user.")
    return GitHubIdentity(login=login, user_id=user_id)


def get_github_token() -> str:
    """Read the current token from gh's credential store; callers must not persist it."""
    token = run_gh(["auth", "token"]).strip()
    if not token:
        raise GitHubCLIError("GitHub CLI has no active token. Run `ship auth login`.")
    return token


def github_api_json(endpoint: str) -> Any:
    """Read one GitHub REST API endpoint through the authenticated gh session."""
    try:
        return json.loads(run_gh(["api", endpoint]))
    except json.JSONDecodeError as exc:
        raise GitHubCLIError("GitHub returned invalid JSON.") from exc


def ensure_registry_admin(repo: str) -> GitHubIdentity:
    """Require the authenticated user to be an administrator of the registry."""
    identity = get_github_identity()
    repository = github_api_json(f"repos/{repo}")
    permissions = repository.get("permissions", {})
    if not isinstance(permissions, dict) or permissions.get("admin") is not True:
        raise GitHubCLIError(
            f"@{identity.login} is not an administrator of {repo}; GitHub denied admin access."
        )
    return identity
