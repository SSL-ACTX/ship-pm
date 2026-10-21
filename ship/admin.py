"""Maintainer operations for automated registry submission pull requests."""

from __future__ import annotations

import json
import re
from typing import Any

from ship.github_auth import (
    GitHubCLIError,
    ensure_registry_admin,
    github_api_json,
    run_gh,
)

TRUSTED_PERMISSIONS = {"admin", "maintain", "write"}
PUBLISHER_MARKER = re.compile(
    r"<!-- ship-publisher-v1 login=([A-Za-z0-9-]{1,39}) "
    r"id=(\d+) permission=(admin|maintain|write|read|none|unknown) -->"
)
PACKAGE_PATH = re.compile(r"^pkgs/[A-Za-z0-9._-]+\.json$")


def _publisher_from_body(body: str) -> tuple[str, str, str] | None:
    match = PUBLISHER_MARKER.search(body)
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3)


def list_package_submissions(registry_repo: str) -> None:
    """List pending registration PRs for a registry administrator."""
    ensure_registry_admin(registry_repo)
    raw = run_gh(
        [
            "pr",
            "list",
            "--repo",
            registry_repo,
            "--state",
            "open",
            "--label",
            "package-submission",
            "--json",
            "number,title,url,author,labels,headRefName,body",
            "--limit",
            "100",
        ]
    )
    try:
        submissions: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GitHubCLIError("GitHub returned invalid pull-request data.") from exc
    if not isinstance(submissions, list):
        raise GitHubCLIError("GitHub returned an unexpected pull-request response.")
    if not submissions:
        print("No open package-submission pull requests.")
        return

    for pr in submissions:
        labels = {
            label.get("name")
            for label in pr.get("labels", [])
            if isinstance(label, dict)
        }
        publisher_identity = _publisher_from_body(pr.get("body") or "")
        if publisher_identity:
            publisher_login, _, permission = publisher_identity
            publisher = f"@{publisher_login} ({permission} upstream)"
        else:
            publisher = "identity unavailable"
        trust = "trusted" if "trusted-contributor" in labels else "review required"
        author = pr.get("author", {}).get("login", "unknown")
        print(
            f"#{pr.get('number')} [{trust}; publisher {publisher}] {pr.get('title')} "
            f"(automation: @{author}, branch: {pr.get('headRefName')})"
        )
        print(f"  {pr.get('url')}")


def review_package_submission(registry_repo: str, pull_request_number: int) -> None:
    """Show the submission metadata and manifest diff for an administrator."""
    ensure_registry_admin(registry_repo)
    pr: Any = github_api_json(f"repos/{registry_repo}/pulls/{pull_request_number}")
    if pr.get("state") != "open":
        raise GitHubCLIError(f"Pull request #{pull_request_number} is not open.")
    labels = sorted(
        label.get("name", "")
        for label in pr.get("labels", [])
        if isinstance(label, dict) and label.get("name")
    )
    publisher = _publisher_from_body(pr.get("body") or "")
    print(f"#{pull_request_number} {pr.get('title', '')}")
    print(f"Author: @{pr.get('user', {}).get('login', 'unknown')} (automation)")
    print(f"URL: {pr.get('html_url', '')}")
    print(f"Labels: {', '.join(labels) if labels else '(none)'}")
    if publisher:
        print(
            f"Publisher: @{publisher[0]} (GitHub ID {publisher[1]}, "
            f"upstream permission: {publisher[2]})"
        )
        if publisher[2] not in TRUSTED_PERMISSIONS:
            print(
                "Publisher is not an upstream collaborator; review the diff before accepting."
            )
    else:
        print("Publisher: identity unavailable")
        print("Review the diff and publisher details before accepting.")

    files: Any = github_api_json(
        f"repos/{registry_repo}/pulls/{pull_request_number}/files?per_page=100"
    )
    if not isinstance(files, list):
        raise GitHubCLIError("GitHub returned an unexpected pull-request file list.")
    if not files:
        print("\nNo changed files reported.")
        return
    for changed_file in files:
        filename = changed_file.get("filename", "(unknown file)")
        print(f"\n--- {filename} ({changed_file.get('status', 'changed')}) ---")
        diff = changed_file.get("patch")
        if isinstance(diff, str) and diff:
            print(diff)
        else:
            print(
                "GitHub did not include an inline diff; open the PR URL to inspect it."
            )


def _validated_submission(
    registry_repo: str, pull_request_number: int
) -> tuple[dict[str, Any], str, tuple[str, str, str] | None]:
    pr: Any = github_api_json(f"repos/{registry_repo}/pulls/{pull_request_number}")
    if pr.get("state") != "open":
        raise GitHubCLIError(f"Pull request #{pull_request_number} is not open.")
    base_repo = pr.get("base", {}).get("repo", {}).get("full_name", "")
    if base_repo.casefold() != registry_repo.casefold():
        raise GitHubCLIError(
            "Pull request base repository does not match the configured registry."
        )
    if not pr.get("head", {}).get("ref", "").startswith("publish/"):
        raise GitHubCLIError("Pull request is not on a generated publish branch.")

    labels = {
        label.get("name") for label in pr.get("labels", []) if isinstance(label, dict)
    }
    required_labels = {"package-submission", "needs-review"}
    if not required_labels.issubset(labels):
        missing = ", ".join(sorted(required_labels - labels))
        raise GitHubCLIError(
            f"Pull request is missing required review label(s): {missing}."
        )

    publisher = _publisher_from_body(pr.get("body") or "")

    files: Any = github_api_json(
        f"repos/{registry_repo}/pulls/{pull_request_number}/files?per_page=100"
    )
    if (
        not isinstance(files, list)
        or pr.get("changed_files") != 1
        or len(files) != 1
        or not PACKAGE_PATH.fullmatch(files[0].get("filename", ""))
        or files[0].get("status") not in ("added", "modified")
    ):
        raise GitHubCLIError(
            "Submission must add or update exactly one package manifest under pkgs/."
        )

    return pr, files[0]["filename"], publisher


def accept_package_submission(
    registry_repo: str, pull_request_number: int, *, assume_yes: bool = False
) -> None:
    """Merge one verified package submission after checking its scope and origin."""
    ensure_registry_admin(registry_repo)
    pr, manifest_path, publisher = _validated_submission(
        registry_repo, pull_request_number
    )
    if pr.get("draft") is True:
        raise GitHubCLIError("Draft pull requests cannot be accepted.")
    assert publisher is not None
    publisher_login, publisher_id, permission = publisher
    print(
        f"Accepting #{pull_request_number}: {manifest_path}; "
        f"publisher @{publisher_login} (GitHub ID {publisher_id}, upstream {permission})."
    )
    if not assume_yes:
        try:
            answer = input("Merge this package submission? [y/N] ").strip().casefold()
        except EOFError:
            answer = ""
        if answer not in {"y", "yes"}:
            print("Merge cancelled.")
            return

    run_gh(
        [
            "pr",
            "merge",
            str(pull_request_number),
            "--repo",
            registry_repo,
            "--squash",
            "--delete-branch",
        ]
    )
    print(f"Merged package submission #{pull_request_number}.")


def reject_package_submission(
    registry_repo: str,
    pull_request_number: int,
    *,
    reason: str = "Rejected by registry maintainer.",
    assume_yes: bool = False,
) -> None:
    """Close a package submission with a visible maintainer explanation."""
    ensure_registry_admin(registry_repo)
    _, manifest_path, publisher = _validated_submission(
        registry_repo, pull_request_number
    )
    publisher_text = (
        f"; publisher @{publisher[0]} ({publisher[2]} upstream)" if publisher else ""
    )
    print(f"Rejecting #{pull_request_number}: {manifest_path}{publisher_text}.")
    print(f"Reason: {reason}")
    if not assume_yes:
        try:
            answer = input("Close this package submission? [y/N] ").strip().casefold()
        except EOFError:
            answer = ""
        if answer not in {"y", "yes"}:
            print("Rejection cancelled.")
            return

    run_gh(
        [
            "pr",
            "close",
            str(pull_request_number),
            "--repo",
            registry_repo,
            "--comment",
            reason,
        ]
    )
    print(f"Rejected and closed package submission #{pull_request_number}.")
