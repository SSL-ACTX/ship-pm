"""Registry administrator commands."""

from __future__ import annotations

from ship.admin import (
    accept_package_submission,
    list_package_submissions,
    reject_package_submission,
    review_package_submission,
)
from ship.admin.github_auth import GitHubCLIError
from ship.cli.engine import Namespace
from ship.core.settings import settings
from ship.ui import ui


def run_admin(ns: Namespace) -> None:
    action = ns.action
    repo = settings.ship_registry_repo
    assume_yes = bool(ns.get("yes"))

    try:
        if action == "prs":
            list_package_submissions(repo)
            return
        if action == "review":
            if ns.get("pr") is None:
                ui.die("Usage: ship admin review <PR>")
            review_package_submission(repo, _pr_number(ns.pr))
            return
        if action == "accept":
            if ns.get("pr") is None:
                ui.die("Usage: ship admin accept <PR> [--yes]")
            accept_package_submission(repo, _pr_number(ns.pr), assume_yes=assume_yes)
            return
        if action == "reject":
            if ns.get("pr") is None:
                ui.die("Usage: ship admin reject <PR> [--reason TEXT] [--yes]")
            reason = (ns.get("reason") or "").strip() or "Rejected by registry maintainer."
            reject_package_submission(
                repo,
                _pr_number(ns.pr),
                reason=reason,
                assume_yes=assume_yes,
            )
            return
    except GitHubCLIError as exc:
        ui.die(str(exc))

    ui.die(
        "Usage: ship admin prs | ship admin review <PR> | "
        "ship admin accept <PR> [--yes] | "
        "ship admin reject <PR> [--reason TEXT] [--yes]"
    )


def _pr_number(raw: object) -> int:
    try:
        number = int(str(raw))
    except (TypeError, ValueError):
        ui.die("Pull request number must be a positive integer.")
    if number <= 0:
        ui.die("Pull request number must be a positive integer.")
    return number
