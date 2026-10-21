"""Package remove, rollback, and repatch operations."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ship.api import PatchReport
from ship.core.settings import settings
from ship.core.state import load_state, save_state
from ship.install.history import history_key
from ship.install.pipeline import _show_patch_report
from ship.link.discovery import resolve_command_binaries, scan_executables
from ship.link.linker import clean_package_links, link_package
from ship.packages import apply_package_patch, apply_reapply_handlers
from ship.ui import die, status


def remove_package(pkg_name: str) -> None:
    state = load_state()
    if pkg_name not in state.get("installed", {}):
        die(f"Package '{pkg_name}' is not installed.")

    pkg_data = state["installed"].pop(pkg_name)
    state.get("history", {}).pop(pkg_name, None)
    version = pkg_data.get("version", "unknown")
    inst_dir = Path(pkg_data.get("install_dir", ""))

    unlinked = clean_package_links(pkg_name, verbose=True)

    removed_files_count = 0
    if inst_dir.is_dir():
        for _ in inst_dir.rglob("*"):
            removed_files_count += 1
        shutil.rmtree(inst_dir, ignore_errors=True)
        status("Cleaned", f"store directory {inst_dir} ({removed_files_count} files)")

    save_state(state)
    status("Removed", f"{pkg_name}@{version} ({len(unlinked)} binaries unlinked)")


def rollback_package(pkg_name: str, *, assume_yes: bool = False) -> None:
    """Reinstall the previous recorded version of a package."""
    state = load_state()
    current = state.get("installed", {}).get(pkg_name)
    if not current:
        die(f"Package '{pkg_name}' is not installed.")
    histories = state.get("history", {})
    entries = histories.get(pkg_name, []) if isinstance(histories, dict) else []
    if not isinstance(entries, list) or not entries:
        die(f"No previous installed version is recorded for '{pkg_name}'.")

    previous = entries[0]
    version = str(previous.get("version", ""))
    target_key = str(previous.get("target_key", ""))
    if not version or not target_key:
        die(f"Rollback history for '{pkg_name}' is incomplete.")
    status(
        "Rolling back",
        f"{pkg_name}@{current.get('version', 'unknown')} -> {pkg_name}@{version} ({target_key})",
    )
    if not assume_yes:
        try:
            answer = input("Install the previous version? [y/N] ").strip().casefold()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer not in {"y", "yes"}:
            print("Rollback cancelled.")
            return

    source = str(previous.get("source", ""))
    if source.startswith("github:"):
        repo = source.removeprefix("github:")
        from ship.install.github_source import install_from_github

        install_from_github(
            repo,
            version,
            target_override=target_key,
            record_history=False,
        )
    else:
        from ship.install.registry_source import install_package

        install_package(
            pkg_name,
            version,
            target_override=target_key,
            record_history=False,
        )

    updated_state = load_state()
    history_state = updated_state.setdefault("history", {})
    if not isinstance(history_state, dict):
        history_state = updated_state["history"] = {}
    remaining = [
        item
        for item in entries[1:]
        if isinstance(item, dict) and history_key(item) != history_key(current)
    ]
    previous_current = {
        key: current[key]
        for key in ("source", "version", "target_key")
        if key in current
    }
    history_state[pkg_name] = [previous_current, *remaining][:10]
    save_state(updated_state)
    status("Finished", f"rolled back {pkg_name} to {version}")


def rollback_binary(binary_name: str, *, assume_yes: bool = False) -> None:
    """Restore the most recent pre-Ship executable saved for a command name."""
    if (
        not binary_name
        or Path(binary_name).name != binary_name
        or binary_name in {".", ".."}
    ):
        die("Binary name must be a single command name.")
    state = load_state()
    backups = [
        path
        for path in settings.ship_backup_dir.iterdir()
        if path.name.startswith(f"{binary_name}.backup.")
        and (path.is_file() or path.is_symlink())
    ]
    if not backups:
        die(f"No saved binary backup found for '{binary_name}'.")
    backup = max(backups, key=lambda path: path.name.rsplit(".", 1)[-1])
    public_link = settings.ship_bin_dir / binary_name
    if public_link.exists() or public_link.is_symlink():
        if not public_link.is_symlink():
            die(f"Refusing to replace unmanaged file at {public_link}.")
        try:
            public_link.resolve(strict=False).relative_to(settings.ship_root.resolve())
        except ValueError:
            die(f"Refusing to replace unmanaged symlink at {public_link}.")

    status("Rolling back", f"restoring {binary_name} from {backup.name}")
    if not assume_yes:
        try:
            answer = input("Restore the saved binary? [y/N] ").strip().casefold()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer not in {"y", "yes"}:
            print("Rollback cancelled.")
            return

    public_link.unlink(missing_ok=True)
    os.replace(backup, public_link)
    for pkg_data in state.get("installed", {}).values():
        pkg_data["symlinks"] = [
            link for link in pkg_data.get("symlinks", []) if Path(link) != public_link
        ]
    save_state(state)
    status("Finished", f"restored {binary_name}")


def repatch_package(pkg_name: str) -> None:
    """Reapply patches and clean up symlinks using fresh ExportPolicy evaluation."""
    state = load_state()
    pkg_data = state.get("installed", {}).get(pkg_name)
    if not pkg_data:
        die(f"Package '{pkg_name}' is not installed.")

    install_dir = Path(pkg_data.get("install_dir", ""))
    if not install_dir.is_dir():
        die(f"Installed files for '{pkg_name}' are missing: {install_dir}")
    target_key = pkg_data.get("target_key", "")

    status(
        "Patching", f"reapplying patches to {pkg_name}@{pkg_data.get('version', '')}"
    )

    for binary in scan_executables(install_dir):
        real_binary = binary.with_name(f"{binary.name}-real")
        if real_binary.is_file():
            os.replace(real_binary, binary)

    patch_report = PatchReport(pkg_name)
    apply_package_patch(pkg_name, "post_extract", install_dir, target_key, patch_report)
    apply_package_patch(pkg_name, "pre_link", install_dir, target_key, patch_report)
    apply_reapply_handlers(pkg_name, patch_report)

    clean_package_links(pkg_name)
    commands = resolve_command_binaries(install_dir, pkg_name, target_key=target_key)
    new_links = link_package(pkg_name, commands, target_key, patch_report)

    pkg_data["symlinks"] = new_links
    save_state(state)
    _show_patch_report(patch_report, show_empty=True)
    status("Finished", f"reapplied patches to {pkg_name}")
