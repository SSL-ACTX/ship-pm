"""Install packages resolved from the Ship registry index."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from ship.core.platform import detect_target_keys
from ship.core.settings import settings
from ship.core.version import (
    classify_channel_for_version,
    select_default_version,
)
from ship.install.pipeline import InstallArtifact, finalize_install
from ship.net.download import fetch_cached_file
from ship.registry.manifests import get_pkg_manifest
from ship.ui import die, status


def install_package(
    pkg_name: str,
    version: str | None = None,
    target_override: str | None = None,
    interactive: bool = False,
    *,
    record_history: bool = True,
) -> None:
    """Download, extract, patch, and link a package from the registry."""
    manifest = get_pkg_manifest(pkg_name)
    if not manifest:
        die(
            f"Package '{pkg_name}' not found in registry. Submit it using: ship publish <owner/repo>"
        )

    versions = manifest.get("versions", {})
    if not versions:
        die(f"No versions found for '{pkg_name}'")

    if not version:
        version = select_default_version(versions)
        if not version:
            die(f"No available versions found for '{pkg_name}'")

    if version not in versions:
        die(
            f"Version '{version}' not found for '{pkg_name}'. Available: {', '.join(versions.keys())}"
        )

    channel = classify_channel_for_version(version, versions)
    ver_data = versions[version]
    targets = ver_data.get("targets", {})
    if not targets:
        die(f"No targets available for {pkg_name}@{version}")

    candidate_keys = detect_target_keys(target_override)
    matched_key = None

    if interactive and sys.stdin.isatty():
        all_keys = list(targets.keys())
        for idx, k in enumerate(all_keys, 1):
            print(f"  [{idx}] {k}")
        while True:
            try:
                choice = input(f"Select target [1-{len(all_keys)}]: ").strip()
                if not choice:
                    continue
                idx_choice = int(choice) - 1
                if 0 <= idx_choice < len(all_keys):
                    matched_key = all_keys[idx_choice]
                    break
            except (ValueError, KeyboardInterrupt, EOFError):
                die("\nTarget selection cancelled.")
    else:
        for key in candidate_keys:
            if key in targets:
                matched_key = key
                break

    if not matched_key:
        die(
            f"No compatible target found for system ({platform.system()} {platform.machine()})."
        )

    target_data = targets[matched_key]
    url = target_data.get("url")
    expected_sha = target_data.get("sha256", "")
    binary_map = target_data.get("binaries") or ver_data.get("binaries")

    channel_badge = f" [{channel}]" if channel in ("nightly", "prerelease") else ""
    status("Resolving", f"{pkg_name}@{version}{channel_badge} for {matched_key}")

    local_archive = settings.ship_cache_dir / f"{pkg_name}-{version}-{Path(url).name}"
    fetch_cached_file(
        url,
        local_archive,
        expected_sha256=expected_sha,
        description=f"{pkg_name}@{version} archive",
    )

    finalize_install(
        InstallArtifact(
            package_name=pkg_name,
            version=version,
            target_key=matched_key,
            archive_path=local_archive,
            source="registry",
            channel=channel,
            declared_binaries=binary_map,
            success_label=f"{pkg_name}@{version}{channel_badge} ({matched_key})",
        ),
        record_history=record_history,
    )
