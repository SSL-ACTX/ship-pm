"""Installed-package history tracking for rollbacks."""

from __future__ import annotations


def history_key(entry: dict) -> tuple[str, str, str]:
    return (
        str(entry.get("source") or "registry"),
        str(entry.get("version") or ""),
        str(entry.get("target_key") or ""),
    )


def record_package_history(
    state: dict, pkg_name: str, previous: dict | None, installed: dict
) -> None:
    if not previous or not previous.get("version") or not previous.get("target_key"):
        return
    snapshot = {
        k: previous[k] for k in ("source", "version", "target_key") if k in previous
    }
    if history_key(snapshot) == history_key(installed):
        return

    histories = state.setdefault("history", {})
    if not isinstance(histories, dict):
        histories = state["history"] = {}
    entries = histories.get(pkg_name, [])
    if not isinstance(entries, list):
        entries = []
    identity = history_key(snapshot)
    histories[pkg_name] = [
        snapshot,
        *[
            item
            for item in entries
            if isinstance(item, dict) and history_key(item) != identity
        ],
    ][:10]
