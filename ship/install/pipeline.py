"""Shared post-download install pipeline used by every package source."""

from __future__ import annotations

import datetime
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ship.api import PatchReport, inspect_elf
from ship.core.settings import settings
from ship.core.state import load_state, save_state
from ship.install.extract import extract_archive
from ship.install.history import record_package_history
from ship.link.discovery import resolve_command_binaries, scan_executables
from ship.link.linker import clean_package_links, link_package
from ship.packages import (
    allows_foreign_binaries,
    apply_package_patch,
    should_discover_all_bins,
)
from ship.ui import die, status

TARGET_ELF_ARCHITECTURES: dict[str, str] = {
    "x86_64": "x86_64",
    "i686": "i386",
    "i386": "i386",
    "aarch64": "aarch64",
    "arm64": "aarch64",
    "armv7": "arm",
    "armv6": "arm",
    "arm": "arm",
    "riscv64": "riscv64",
    "powerpc64le": "powerpc64",
    "s390x": "s390x",
}


@dataclass(frozen=True)
class InstallArtifact:
    """Resolved download ready for the shared extract/patch/link path."""

    package_name: str
    version: str
    target_key: str
    archive_path: Path
    source: str = "registry"
    channel: str | None = None
    declared_binaries: dict | None = None
    discover_all_bins: bool | None = None
    validate_elf_architecture: bool = False
    asset_label: str | None = None
    state_extra: dict = field(default_factory=dict)
    success_label: str | None = None


def _matches_target_elf_architecture(binary: Path, target_key: str) -> bool:
    target_parts = target_key.split("-")
    if len(target_parts) < 2 or target_parts[1] != "linux":
        return True
    expected_arch = TARGET_ELF_ARCHITECTURES.get(target_parts[0])
    if expected_arch is None:
        return True
    info = inspect_elf(binary)
    return info is None or info.architecture == expected_arch


def _show_patch_report(report: PatchReport, *, show_empty: bool = False) -> None:
    if not report.changed and show_empty:
        status("Patching", "no patch files changed")
    for change in report.changes:
        status("Patching", report.describe(change))


def finalize_install(artifact: InstallArtifact, *, record_history: bool = True) -> None:
    """Extract, patch, discover, link, and persist state for one artifact."""
    pkg_name = artifact.package_name
    version = artifact.version
    target_key = artifact.target_key
    archive = artifact.archive_path

    install_dir = settings.ship_store_dir / f"{pkg_name}@{version}"
    shutil.rmtree(install_dir, ignore_errors=True)
    extract_archive(archive, install_dir, pkg_name)

    patch_report = PatchReport(pkg_name)
    apply_package_patch(pkg_name, "post_extract", install_dir, target_key, patch_report)
    apply_package_patch(pkg_name, "pre_link", install_dir, target_key, patch_report)

    if artifact.validate_elf_architecture:
        exes = scan_executables(install_dir)
        wrong_arch_execs = [
            path for path in exes if not _matches_target_elf_architecture(path, target_key)
        ]
        matching_execs = [
            path for path in exes if _matches_target_elf_architecture(path, target_key)
        ]
        if (
            wrong_arch_execs
            and not matching_execs
            and not allows_foreign_binaries(pkg_name)
        ):
            detected = sorted(
                {
                    info.architecture
                    for binary in wrong_arch_execs
                    if (info := inspect_elf(binary)) is not None
                }
            )
            target_arch = target_key.split("-", 1)[0]
            details = (
                f"; archive contains {', '.join(detected)} binaries" if detected else ""
            )
            label = artifact.asset_label or archive.name
            die(
                f"Release asset {label} has no compiled binaries for target "
                f"{target_arch}{details}."
            )

    status("Linking", "discovering and linking binaries...")
    clean_package_links(pkg_name)

    if artifact.discover_all_bins is None:
        use_declared = not should_discover_all_bins(pkg_name)
    else:
        use_declared = not artifact.discover_all_bins
    effective_map = artifact.declared_binaries if use_declared else None
    commands = resolve_command_binaries(
        install_dir,
        pkg_name,
        declared_binaries=effective_map,
        target_key=target_key,
    )
    linked = link_package(pkg_name, commands, target_key, patch_report)
    _show_patch_report(patch_report)

    state = load_state()
    installed_entry = {
        "version": version,
        "target_key": target_key,
        "install_dir": str(install_dir),
        "download_size_bytes": archive.stat().st_size,
        "symlinks": linked,
        "installed_at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d"),
        **artifact.state_extra,
    }
    if artifact.source != "registry":
        installed_entry["source"] = artifact.source
    if artifact.channel is not None:
        installed_entry["channel"] = artifact.channel

    previous_entry = state.setdefault("installed", {}).get(pkg_name)
    if record_history:
        record_package_history(state, pkg_name, previous_entry, installed_entry)
    state["installed"][pkg_name] = installed_entry
    save_state(state)

    if artifact.success_label:
        status("Installed", artifact.success_label)
    else:
        channel_badge = (
            f" [{artifact.channel}]"
            if artifact.channel in ("nightly", "prerelease")
            else ""
        )
        status("Installed", f"{pkg_name}@{version}{channel_badge} ({target_key})")
