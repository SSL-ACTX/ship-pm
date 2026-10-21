"""Symlink management, toolchain sandboxing, and binary collision safety."""

import time
from pathlib import Path

from ship.api import PatchReport
from ship.core.settings import settings
from ship.core.state import load_state
from ship.packages import get_export_policy
from ship.runtime import apply_patchers
from ship.ui import c, die, status, warn


def clean_package_links(pkg_name: str, *, verbose: bool = False) -> list[Path]:
    """Remove any existing symlinks created for a package and return unlinked paths."""
    unlinked: list[Path] = []
    state = load_state()
    pkg = state.get("installed", {}).get(pkg_name)
    if pkg:
        for sym in pkg.get("symlinks", []):
            p = Path(sym)
            if p.is_symlink() or p.exists():
                try:
                    p.unlink()
                    unlinked.append(p)
                    if verbose:
                        status("Unlinked", str(p))
                except OSError:
                    pass

    pkg_pattern = f"{pkg_name}@"
    for bin_dir in (settings.ship_bin_dir, settings.ship_internal_bin):
        if not bin_dir.is_dir():
            continue
        for item in bin_dir.iterdir():
            if item.is_symlink():
                try:
                    dest = str(item.resolve())
                    if pkg_pattern in dest and item not in unlinked:
                        item.unlink(missing_ok=True)
                        unlinked.append(item)
                        if verbose:
                            status("Unlinked", str(item))
                except OSError:
                    pass
    return unlinked


def link_package(
    pkg_name: str,
    commands: dict[str, Path],
    target_key: str,
    patch_report: PatchReport,
) -> list[str]:
    """
    Enforce ExportPolicy, separate internal vs public binaries, and create symlinks.
    Returns the list of public symlinks created.
    """
    policy = get_export_policy(pkg_name)
    sandboxed_internal: dict[str, Path] = {}
    active_commands = dict(commands)

    # Apply explicit aliases from ExportPolicy
    for alias_name, orig_name in policy.aliases.items():
        if orig_name in active_commands and alias_name not in active_commands:
            active_commands[alias_name] = active_commands[orig_name]

    # Enforce ExportPolicy rules (whitelist / blacklist / internal_only)
    for name in list(active_commands.keys()):
        is_whitelisted = not policy.only or name in policy.only
        is_blacklisted = name in policy.exclude or name in policy.internal_only
        if not is_whitelisted or is_blacklisted:
            sandboxed_internal[name] = active_commands.pop(name)
            status("Sandboxed", f"{name} (kept private to {pkg_name})")

    # Link private tools to settings.ship_internal_bin only
    for name, target in sandboxed_internal.items():
        target.chmod(0o755)
        patched = apply_patchers(target, target_key, patch_report)
        internal_link = settings.ship_internal_bin / name
        internal_link.unlink(missing_ok=True)
        internal_link.symlink_to(patched)

    # Link public tools to BOTH settings.ship_internal_bin and settings.ship_bin_dir
    public_links: list[str] = []
    ship_root_resolved = settings.ship_root.resolve()

    for symlink_name, target in active_commands.items():
        target.chmod(0o755)
        patched = apply_patchers(target, target_key, patch_report)

        # 1. Internal link
        internal_link = settings.ship_internal_bin / symlink_name
        internal_link.unlink(missing_ok=True)
        internal_link.symlink_to(patched)

        # 2. Public link
        pub_link = settings.ship_bin_dir / symlink_name

        if pub_link.parent in settings.system_bin_dirs:
            die(
                f"Configuration safety error: Refusing to create symlinks inside system directory '{pub_link.parent}'."
            )

        if pub_link.is_symlink() or pub_link.exists():
            is_ship_owned = False
            if pub_link.is_symlink():
                try:
                    dest = pub_link.resolve()
                    if str(ship_root_resolved) in str(dest):
                        is_ship_owned = True
                except (OSError, ValueError):
                    is_ship_owned = False

            if not is_ship_owned:
                backup = (
                    settings.ship_backup_dir
                    / f"{symlink_name}.backup.{int(time.time())}"
                )
                pub_link.rename(backup)
                warn(f"Backed up external binary to {backup}")
            else:
                pub_link.unlink()

        pub_link.symlink_to(patched)
        public_links.append(str(pub_link))
        print(f"  {c('Linked', '1;32')} {symlink_name} -> {pub_link}")

    if not public_links and not sandboxed_internal:
        die("No functional binaries could be linked.")

    return public_links
