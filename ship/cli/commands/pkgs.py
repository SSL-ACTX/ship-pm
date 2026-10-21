"""Package install / remove / list / search / info / clean / rollback / repatch."""

from __future__ import annotations

import json
from pathlib import Path

from ship.cli.commands._util import installed_size_bytes
from ship.cli.engine import Namespace
from ship.core.platform import detect_target_keys
from ship.core.settings import get_pkgs_dir, settings
from ship.core.state import init_dirs, load_state
from ship.core.version import (
    classify_channel,
    format_version,
    select_default_version,
    semver_sort_key,
)
from ship.install import (
    install_from_github,
    install_package,
    remove_package,
    repatch_package,
    rollback_binary,
    rollback_package,
)
from ship.registry import ensure_registry, get_pkg_manifest
from ship.ui import Column, format_license, format_size, ui


def run_install(ns: Namespace) -> None:
    pkg_spec = ns.package
    ver = ns.version
    if "@" in pkg_spec and not pkg_spec.startswith("git@"):
        pkg_spec, ver = pkg_spec.split("@", 1)

    target = ns.get("target")
    interactive = bool(ns.get("select_target"))
    asset = ns.get("asset")

    if "/" in pkg_spec:
        install_from_github(
            pkg_spec,
            ver,
            target_override=target,
            interactive=interactive,
            asset_filter=asset,
        )
    else:
        install_package(
            pkg_spec,
            ver,
            target_override=target,
            interactive=interactive,
        )


def run_remove(ns: Namespace) -> None:
    remove_package(ns.package)


def run_repatch(ns: Namespace) -> None:
    repatch_package(ns.package)


def run_rollback(ns: Namespace) -> None:
    assume_yes = bool(ns.get("yes"))
    if ns.get("binary"):
        rollback_binary(ns.binary, assume_yes=assume_yes)
        return
    if not ns.get("package"):
        ui.die(
            "Usage: ship rollback <package> [--yes] | "
            "ship rollback --binary <command> [--yes]"
        )
    rollback_package(ns.package, assume_yes=assume_yes)


def run_list(_ns: Namespace) -> None:
    installed = load_state().get("installed", {})
    if not installed:
        ui.blank()
        ui.info("No packages installed.")
        ui.blank()
        return

    ui.blank()
    ui.heading("Installed Packages:")
    ui.blank()

    rows = []
    for name, data in sorted(installed.items()):
        ver = format_version(data.get("version"))
        channel = data.get("channel") or classify_channel(data.get("version", ""))
        style = {
            "stable": "channel_stable",
            "prerelease": "channel_prerelease",
            "nightly": "channel_nightly",
        }.get(channel, "muted")
        rows.append(
            (
                ui.style(name, "package"),
                ui.style(ver, style),
                ui.style(data.get("target_key", "universal"), "muted"),
                str(data.get("installed_at", ""))[:10],
            )
        )

    ui.table(
        (
            Column("PACKAGE", 16),
            Column("VERSION", 16),
            Column("TARGET", 24),
            Column("INSTALLED", 12),
        ),
        rows,
    )
    ui.blank()
    ui.status("Finished", f"{len(installed)} package(s) tracked in store.")
    ui.blank()


def run_search(ns: Namespace) -> None:
    ensure_registry()
    pkgs_dir = get_pkgs_dir()
    installed = load_state().get("installed", {})
    query = (ns.get("query") or "").lower().strip()
    matched = 0

    ui.blank()
    for path in sorted(pkgs_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        name = path.stem
        desc = data.get("description", "")
        if query and query not in name.lower() and query not in desc.lower():
            continue

        versions = list(data.get("versions", {}).keys())
        latest = select_default_version(versions) or "unknown"
        channel = classify_channel(latest)
        matched += 1

        line = f"  {ui.style(name, 'package')} {ui.style(format_version(latest), 'version')}"
        if channel != "stable":
            line += f" {ui.style('[' + channel + ']', 'muted')}"
        if name in installed:
            line += f" {ui.style('[installed]', 'info')}"
        print(line)
        if desc:
            print(f"    {desc}")
        print()

    if matched == 0:
        if query:
            print(f"  No packages matching '{ns.query}'.\n")
        else:
            print("  No packages available in registry.\n")


def run_info(ns: Namespace) -> None:
    pkg_name = ns.package
    manifest = get_pkg_manifest(pkg_name)
    if not manifest:
        ui.die(f"Package '{pkg_name}' not found in registry.")

    inst = load_state().get("installed", {}).get(pkg_name)
    host_targets = detect_target_keys()

    ui.blank()
    ui.title(pkg_name)
    if "description" in manifest:
        ui.kv("Description:", manifest["description"])
    if "author" in manifest:
        ui.kv("Author:", manifest["author"])
    if "repository" in manifest:
        ui.kv("Repository:", manifest["repository"])
    if "license" in manifest:
        ui.kv("License:", format_license(str(manifest["license"])))

    all_versions = sorted(manifest.get("versions", {}).keys(), key=semver_sort_key)
    groups = (
        ("Stable:", "stable", "channel_stable"),
        ("Pre-release:", "prerelease", "channel_prerelease"),
        ("Nightly:", "nightly", "channel_nightly"),
    )
    for label, channel, style in groups:
        versions = [v for v in all_versions if classify_channel(v) == channel]
        if versions:
            shown = ", ".join(format_version(v) for v in versions)
            ui.kv(label, ui.style(shown, style))

    if inst:
        inst_ch = inst.get("channel", classify_channel(inst.get("version", "")))
        ui.kv(
            "Status:",
            f"{ui.style('Installed', 'success')} "
            f"({format_version(inst.get('version'))} [{inst_ch}] via {inst.get('target_key')})",
        )
    else:
        ui.kv("Status:", ui.style("Not installed", "muted"))

    default_ver = select_default_version(all_versions)
    info_version = str(inst.get("version")) if inst else (default_ver or "")
    info_version_data = manifest.get("versions", {}).get(info_version, {})
    info_targets = info_version_data.get("targets", {})
    info_target = inst.get("target_key") if inst else None
    if not info_target or info_target not in info_targets:
        info_target = next(
            (target for target in host_targets if target in info_targets), None
        )

    download_size = inst.get("download_size_bytes") if inst else None
    target_data = info_targets.get(info_target, {}) if info_target else {}
    if download_size is None:
        download_size = target_data.get("download_size_bytes")
    if download_size is None and target_data.get("url"):
        archive = (
            settings.ship_cache_dir
            / f"{pkg_name}-{info_version}-{Path(target_data['url']).name}"
        )
        if archive.is_file():
            download_size = archive.stat().st_size
    size_suffix = f" ({info_target})" if info_target else ""
    ui.kv("Download size:", f"{format_size(download_size)}{size_suffix}")

    if inst:
        install_path = inst.get("install_dir")
        installed_bytes = (
            installed_size_bytes(Path(install_path)) if install_path else None
        )
        ui.kv("Installed size:", format_size(installed_bytes))

    if default_ver:
        targets = manifest.get("versions", {}).get(default_ver, {}).get("targets", {})
        if targets:
            ui.blank()
            print(
                f"  {ui.style(f'Targets for default ({format_version(default_ver)}):', 'bold')}"
            )
            for target in targets:
                marker = (
                    ui.style(" [host match]", "success")
                    if target in host_targets
                    else ""
                )
                ui.bullet(f"{target}{marker}")
    ui.blank()


def run_clean(_ns: Namespace) -> None:
    init_dirs()
    cache = settings.ship_cache_dir
    backups = settings.ship_backup_dir
    ui.status("Cleaning", f"cache files in {cache}...")
    for item in cache.glob("*"):
        if item.is_file():
            item.unlink(missing_ok=True)
    ui.status("Cleaning", f"backups in {backups}...")
    import shutil

    shutil.rmtree(backups, ignore_errors=True)
    backups.mkdir(exist_ok=True)
    ui.status("Finished", "cache and backups cleaned")
