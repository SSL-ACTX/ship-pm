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

    # Check if this is a secondary / deb registry package
    if "_deb_url" in manifest or manifest.get("_source", "").startswith("ubuntu"):
        _install_deb_manifest(
            pkg_name,
            manifest,
            target_override=target_override,
            record_history=record_history,
        )
        return

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


def _install_deb_manifest(
    pkg_name: str,
    manifest: dict,
    target_override: str | None = None,
    record_history: bool = True,
    _visited: set[str] | None = None,
    _dep_of: str | None = None,
) -> None:
    """Install a package directly from an Ubuntu/deb manifest, resolving dependencies recursively."""
    from ship.core.package_name import normalize_package_name
    from ship.core.state import load_state

    if _visited is None:
        _visited = set()

    clean_name = normalize_package_name(pkg_name)
    if clean_name in _visited:
        return
    _visited.add(clean_name)

    # Check if already installed
    state = load_state()
    installed = state.get("installed", {})
    already_installed = any(
        k == pkg_name or normalize_package_name(k) == clean_name for k in installed
    )

    # Resolve and satisfy dependencies first
    deps = manifest.get("_depends", [])
    if deps:
        for dep in deps:
            dep_key = f"ubuntu:{dep}"
            dep_clean = normalize_package_name(dep)
            # Check if dependency is already satisfied in state
            if any(
                k == dep_key or normalize_package_name(k) == dep_clean
                for k in installed
            ):
                status("Satisfied", f"dependency '{dep}' is already installed")
                continue
            dep_manifest = get_pkg_manifest(dep_key)
            if dep_manifest and dep_clean not in _visited:
                status("Dependency", f"{pkg_name} requires {dep}")
                _install_deb_manifest(
                    dep_key,
                    dep_manifest,
                    target_override=target_override,
                    record_history=record_history,
                    _visited=_visited,
                    _dep_of=pkg_name,
                )
                # Reload state after dependency install
                installed = load_state().get("installed", {})

    if already_installed:
        status("Satisfied", f"package '{pkg_name}' is already installed")
        return

    url = manifest.get("_deb_url")
    if not url:
        die(f"No package download URL found in manifest for '{pkg_name}'")

    version = manifest.get("version", "deb")
    deb_name = Path(url).name
    cache_dest = settings.ship_cache_dir / deb_name

    candidate_keys = detect_target_keys(target_override)
    target_key = candidate_keys[0] if candidate_keys else "aarch64-linux-gnu"

    status("Resolving", f"{pkg_name}@{version} from {manifest.get('_source', 'deb')}")
    fetch_cached_file(url, cache_dest, description=deb_name)

    finalize_install(
        InstallArtifact(
            package_name=pkg_name,
            version=version,
            target_key=target_key,
            archive_path=cache_dest,
            source=f"deb:{manifest.get('_source', 'ubuntu')}",
            declared_binaries=None,
            discover_all_bins=True,
            validate_elf_architecture=False,
            success_label=f"{pkg_name}@{version} (ubuntu deb)",
            state_extra={"dep_of": _dep_of} if _dep_of else {},
        ),
        record_history=record_history,
    )
