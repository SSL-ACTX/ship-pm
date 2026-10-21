"""Package install / remove / list / search / info / clean / rollback / repatch."""

from __future__ import annotations

import json
from pathlib import Path

from ship.cli.commands._util import installed_size_bytes
from ship.cli.engine import Namespace
from ship.core.platform import detect_target_keys
from ship.core.settings import get_pkgs_dir, settings
from ship.core.state import init_dirs, load_state, save_state
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

    if ns.get("clean"):
        clean_spec = pkg_spec.split("/")[-1]
        for cfile in settings.ship_cache_dir.glob(f"*{clean_spec}*"):
            if cfile.is_file():
                cfile.unlink(missing_ok=True)
                ui.status("Cleaned", f"cached download {cfile.name}")

    if pkg_spec.endswith(".deb") or (
        Path(pkg_spec).is_file() and pkg_spec.endswith(".deb")
    ):
        deb_path = Path(pkg_spec)
        from ship.install.deb_source import DebArchive

        deb = DebArchive(deb_path)
        pkg_name = deb_path.stem.split("_")[0]
        inst_dir = settings.ship_store_dir / f"{pkg_name}@deb"
        deb.extract_payload(inst_dir)
        from ship.api import PatchReport

        report = PatchReport(pkg_name)
        from ship.link.discovery import resolve_command_binaries
        from ship.link.linker import link_package

        commands = resolve_command_binaries(inst_dir, pkg_name)
        linked = link_package(pkg_name, commands, "", report)
        state = load_state()
        state.setdefault("installed", {})[pkg_name] = {
            "version": "deb",
            "install_dir": str(inst_dir),
            "symlinks": linked,
            "source": f"deb:{deb_path.name}",
        }
        save_state(state)
        ui.status("Installed", f"{pkg_name}@deb ({len(linked)} binaries linked)")
        return

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
    pkg_name = ns.package
    remove_package(pkg_name)
    if ns.get("purge"):
        clean_spec = pkg_name.split("/")[-1]
        for cfile in settings.ship_cache_dir.glob(f"*{clean_spec}*"):
            if cfile.is_file():
                cfile.unlink(missing_ok=True)
                ui.status("Purged", f"cached archive {cfile.name}")


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


def run_clean(ns: Namespace) -> None:
    import shutil

    init_dirs()
    cache = settings.ship_cache_dir
    backups = settings.ship_backup_dir
    clean_all = bool(ns.get("all"))
    clean_store = bool(ns.get("store")) or clean_all

    cleaned_cache_count = 0
    cleaned_cache_bytes = 0
    cleaned_backup_count = 0
    cleaned_backup_bytes = 0

    if not clean_store or clean_all:
        if cache.is_dir():
            for item in cache.glob("*"):
                if item.is_file():
                    try:
                        sz = item.stat().st_size
                    except OSError:
                        sz = 0
                    item.unlink(missing_ok=True)
                    cleaned_cache_count += 1
                    cleaned_cache_bytes += sz

        if backups.is_dir():
            for item in backups.glob("*"):
                try:
                    if item.is_file():
                        cleaned_backup_bytes += item.stat().st_size
                        item.unlink(missing_ok=True)
                        cleaned_backup_count += 1
                    elif item.is_dir():
                        cleaned_backup_bytes += sum(
                            f.stat().st_size for f in item.rglob("*") if f.is_file()
                        )
                        shutil.rmtree(item, ignore_errors=True)
                        cleaned_backup_count += 1
                except OSError:
                    continue
            backups.mkdir(exist_ok=True)

        if cleaned_cache_count > 0:
            ui.status(
                "Cleaned",
                f"{cleaned_cache_count} cached archive(s) ({format_size(cleaned_cache_bytes)}) in {cache}",
            )
        else:
            ui.status("Skipped", f"cache directory {cache} is already empty")

        if cleaned_backup_count > 0:
            ui.status(
                "Cleaned",
                f"{cleaned_backup_count} backup snapshot(s) ({format_size(cleaned_backup_bytes)}) in {backups}",
            )
        else:
            ui.status("Skipped", f"backup directory {backups} is already empty")

    if clean_store:
        state = load_state()
        installed = state.get("installed", {})
        active_dirs = {
            Path(data.get("install_dir", "")).resolve()
            for data in installed.values()
            if data.get("install_dir")
        }
        orphans_cleaned = 0
        orphans_bytes = 0
        if settings.ship_store_dir.is_dir():
            for store_entry in settings.ship_store_dir.iterdir():
                if store_entry.is_dir() and store_entry.resolve() not in active_dirs:
                    try:
                        entry_sz = sum(
                            f.stat().st_size
                            for f in store_entry.rglob("*")
                            if f.is_file()
                        )
                    except OSError:
                        entry_sz = 0
                    shutil.rmtree(store_entry, ignore_errors=True)
                    ui.status(
                        "Cleaned",
                        f"orphaned store {store_entry.name} ({format_size(entry_sz)})",
                    )
                    orphans_cleaned += 1
                    orphans_bytes += entry_sz

        if orphans_cleaned == 0 and not clean_all:
            ui.status("Skipped", "no orphaned package versions found in store")
        elif orphans_cleaned > 0:
            ui.status(
                "Cleaned",
                f"{orphans_cleaned} orphaned store folder(s) ({format_size(orphans_bytes)})",
            )

    total_freed = (
        cleaned_cache_bytes
        + cleaned_backup_bytes
        + (orphans_bytes if clean_store else 0)
    )
    ui.status("Finished", f"cleanup complete (freed {format_size(total_freed)})")


def run_doctor(ns: Namespace) -> None:
    import sys

    from ship.core.doctor import DoctorEngine

    code = DoctorEngine.diagnose(heal=bool(ns.get("heal")))
    if code != 0 and not ns.get("heal"):
        sys.exit(code)


def run_export(ns: Namespace) -> None:
    from ship.core.export import ArtifactBundle

    ArtifactBundle.export(ns.package, ns.get("output"))


def run_import(ns: Namespace) -> None:
    from ship.core.export import ArtifactBundle

    ArtifactBundle.import_bundle(ns.bundle)


def run_sandbox(ns: Namespace) -> None:
    import sys

    from ship.core.sandbox import SandboxArea

    action = ns.get("action") or "list"
    target = ns.get("target")

    if action == "create":
        SandboxArea.create(target)
    elif action == "enter":
        SandboxArea.enter(target or "default")
    elif action == "test":
        if not target:
            ui.die("Usage: ship sandbox test <package> [--keep]")
        success = SandboxArea.test_install(target, keep=bool(ns.get("keep")))
        if not success:
            sys.exit(1)
    elif action in ("clean", "destroy", "rm"):
        SandboxArea.clean(target)
    elif action == "list":
        boxes = SandboxArea.list_sandboxes()
        if not boxes:
            ui.blank()
            ui.info("No active sandbox areas.")
            ui.blank()
            return
        ui.blank()
        ui.heading("Active Sandbox Areas:")
        ui.blank()
        for b in boxes:
            pkgs = ", ".join(b["packages"]) if b["packages"] else "empty"
            ui.bullet(f"{b['name']} - [{pkgs}]")
        ui.blank()
    elif action == "run":
        if not target:
            ui.die("Usage: ship sandbox run <name> <command...>")
        cmd = ns.get("cmd") or []
        code = SandboxArea.run_command(target, cmd)
        sys.exit(code)
    else:
        ui.die(
            f"Unknown sandbox action '{action}'. Valid: test, create, enter, run, list, clean"
        )
