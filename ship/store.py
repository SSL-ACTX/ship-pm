"""Package installation, archive extraction, and store lifecycle management."""

import bz2
import datetime
import gzip
import lzma
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path

from ship.config import (
    SHIP_BACKUP_DIR,
    SHIP_BIN_DIR,
    SHIP_CACHE_DIR,
    SHIP_ROOT,
    SHIP_STORE_DIR,
    load_state,
    save_state,
)
from ship.discovery import resolve_command_binaries, scan_executables
from ship.linker import clean_package_links, link_package
from ship.patches import (
    apply_package_patch,
    apply_reapply_handlers,
    should_discover_all_bins,
)
from ship.patches.api import PatchReport
from ship.platform import detect_target_keys
from ship.registry import fetch_cached_file, get_pkg_manifest
from ship.ui import Progress, die, status
from ship.version import classify_channel, select_default_version


def _tracked_archive_members(
    members: Iterable[tarfile.TarInfo | zipfile.ZipInfo],
    progress: Progress,
    total: int | None,
) -> Iterator[tarfile.TarInfo | zipfile.ZipInfo]:
    for count, member in enumerate(members, 1):
        yield member
        progress.update(count, total)


def _copy_with_progress(
    source,
    destination,
    progress: Progress,
    *,
    offset: int = 0,
) -> None:
    copied = 0
    while chunk := source.read(64 * 1024):
        destination.write(chunk)
        copied += len(chunk)
        progress.update(offset + copied)


def extract_archive(archive_path: Path, extract_dir: Path, pkg_name: str) -> None:
    """Extract an archive safely into an isolated store directory."""
    extract_dir.mkdir(parents=True, exist_ok=True)
    bin_dir = extract_dir / "bin"
    bin_dir.mkdir(exist_ok=True)

    name = archive_path.name.lower()
    progress = Progress("Extracting", extract_dir.name, unit="files")
    try:
        if name.endswith((".tar.gz", ".tgz")):
            with tarfile.open(archive_path, "r:gz") as tar:
                members = tar.getmembers()
                progress.set_total(len(members))
                tar.extractall(
                    extract_dir,
                    members=_tracked_archive_members(members, progress, len(members)),
                )
        elif name.endswith((".tar.xz", ".txz")):
            with tarfile.open(archive_path, "r:xz") as tar:
                members = tar.getmembers()
                progress.set_total(len(members))
                tar.extractall(
                    extract_dir,
                    members=_tracked_archive_members(members, progress, len(members)),
                )
        elif name.endswith((".tar.bz2", ".tbz2")):
            with tarfile.open(archive_path, "r:bz2") as tar:
                members = tar.getmembers()
                progress.set_total(len(members))
                tar.extractall(
                    extract_dir,
                    members=_tracked_archive_members(members, progress, len(members)),
                )
        elif name.endswith(".tar.zst"):
            decoder = shutil.which("zstd") or shutil.which("unzstd")
            if not decoder:
                raise RuntimeError(
                    "Cannot extract .tar.zst archive: install 'zstd' first."
                )
            proc = subprocess.Popen(
                [decoder, "-dc", str(archive_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            count = 0
            try:
                with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:

                    def tracked_stream_members():
                        nonlocal count
                        for member in tar:
                            yield member
                            count += 1
                            progress.update(count)

                    tar.extractall(extract_dir, members=tracked_stream_members())
                _, error = proc.communicate()
            except Exception:
                proc.kill()
                proc.communicate()
                raise
            if proc.returncode:
                raise RuntimeError(
                    f"zstd extraction failed: {error.decode(errors='replace').strip()}"
                )
        elif name.endswith(".tar"):
            with tarfile.open(archive_path, "r:") as tar:
                members = tar.getmembers()
                progress.set_total(len(members))
                tar.extractall(
                    extract_dir,
                    members=_tracked_archive_members(members, progress, len(members)),
                )
        elif name.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as z:
                members = z.infolist()
                progress.set_total(len(members))
                z.extractall(
                    extract_dir,
                    members=_tracked_archive_members(members, progress, len(members)),
                )
        elif name.endswith(".7z"):
            extractor: tuple[str, str] | None = None
            for command in ("7zz", "7z", "7za", "bsdtar"):
                exe = shutil.which(command)
                if exe:
                    extractor = exe, command
                    break
            if not extractor:
                raise RuntimeError("Cannot extract .7z archive: install 7zz or bsdtar.")
            executable, command = extractor
            if command == "bsdtar":
                progress.unit = "archive"
                args = [executable, "-xf", str(archive_path), "-C", str(extract_dir)]
            else:
                progress.unit = "%"
                progress.set_total(100)
                args = [
                    executable,
                    "x",
                    "-y",
                    f"-o{extract_dir}",
                    str(archive_path),
                    "-bsp1",
                ]
            proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            output_tail = bytearray()
            pending = bytearray()
            assert proc.stdout is not None
            while chunk := proc.stdout.read(4096):
                output_tail.extend(chunk)
                if len(output_tail) > 4096:
                    del output_tail[:-4096]
                pending.extend(chunk)
                while b"\r" in pending or b"\n" in pending:
                    seps = [
                        i for i in (pending.find(b"\r"), pending.find(b"\n")) if i >= 0
                    ]
                    idx = min(seps)
                    line = bytes(pending[:idx])
                    del pending[: idx + 1]
                    match = re.search(rb"\b(\d{1,3})%", line)
                    if match:
                        progress.update(min(100, int(match.group(1))), 100)
            if proc.wait():
                raise RuntimeError(
                    f"7z extraction failed: {output_tail.decode(errors='replace').strip()}"
                )
            progress.update(100, 100)
        elif name.endswith((".gz", ".xz", ".bz2")):
            dest_file = bin_dir / (f"{pkg_name}.exe" if ".exe" in name else pkg_name)
            opener = (
                gzip.open
                if name.endswith(".gz")
                else lzma.open
                if name.endswith(".xz")
                else bz2.open
            )
            progress.unit = "bytes"
            with opener(archive_path, "rb") as f_in, open(dest_file, "wb") as f_out:
                _copy_with_progress(f_in, f_out, progress)
        else:
            dest = bin_dir / pkg_name
            progress.unit = "bytes"
            with open(archive_path, "rb") as f_in, open(dest, "wb") as f_out:
                _copy_with_progress(f_in, f_out, progress)
            dest.chmod(0o755)

        if progress.unit == "files" and progress.total is None:
            progress.set_total(progress.current)
        progress.finish()
    except Exception:
        progress.finish(success=False)
        raise


def _show_patch_report(report: PatchReport, *, show_empty: bool = False) -> None:
    if not report.changed and show_empty:
        status("Patching", "no patch files changed")
    for change in report.changes:
        status("Patching", report.describe(change))


def _history_key(entry: dict) -> tuple[str, str, str]:
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
    if _history_key(snapshot) == _history_key(installed):
        return

    histories = state.setdefault("history", {})
    if not isinstance(histories, dict):
        histories = state["history"] = {}
    entries = histories.get(pkg_name, [])
    if not isinstance(entries, list):
        entries = []
    identity = _history_key(snapshot)
    histories[pkg_name] = [
        snapshot,
        *[
            item
            for item in entries
            if isinstance(item, dict) and _history_key(item) != identity
        ],
    ][:10]


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

    channel = classify_channel(version)
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
        for k in candidate_keys:
            if k in targets:
                matched_key = k
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

    local_archive = SHIP_CACHE_DIR / f"{pkg_name}-{version}-{Path(url).name}"
    fetch_cached_file(
        url,
        local_archive,
        expected_sha256=expected_sha,
        description=f"{pkg_name}@{version} archive",
    )

    install_dir = SHIP_STORE_DIR / f"{pkg_name}@{version}"
    shutil.rmtree(install_dir, ignore_errors=True)
    extract_archive(local_archive, install_dir, pkg_name)

    patch_report = PatchReport(pkg_name)
    apply_package_patch(
        pkg_name, "post_extract", install_dir, matched_key, patch_report
    )
    apply_package_patch(pkg_name, "pre_link", install_dir, matched_key, patch_report)

    # Resolve commands and execute isolated linking
    status("Linking", "discovering and linking binaries...")
    clean_package_links(pkg_name)

    effective_map = None if should_discover_all_bins(pkg_name) else binary_map
    commands = resolve_command_binaries(
        install_dir,
        pkg_name,
        declared_binaries=effective_map,
        target_key=matched_key,
    )
    linked = link_package(pkg_name, commands, matched_key, patch_report)

    _show_patch_report(patch_report)

    state = load_state()
    installed_entry = {
        "version": version,
        "channel": channel,
        "target_key": matched_key,
        "install_dir": str(install_dir),
        "download_size_bytes": local_archive.stat().st_size,
        "symlinks": linked,
        "installed_at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d"),
    }
    previous_entry = state.setdefault("installed", {}).get(pkg_name)
    if record_history:
        record_package_history(state, pkg_name, previous_entry, installed_entry)
    state["installed"][pkg_name] = installed_entry
    save_state(state)
    status("Installed", f"{pkg_name}@{version}{channel_badge} ({matched_key})")


def remove_package(pkg_name: str) -> None:
    state = load_state()
    if pkg_name not in state.get("installed", {}):
        die(f"Package '{pkg_name}' is not installed.")

    pkg_data = state["installed"].pop(pkg_name)
    state.get("history", {}).pop(pkg_name, None)
    inst_dir = Path(pkg_data.get("install_dir", ""))
    if inst_dir.is_dir():
        shutil.rmtree(inst_dir, ignore_errors=True)

    clean_package_links(pkg_name)
    save_state(state)
    status("Removed", pkg_name)


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
        from ship.github import install_from_github

        install_from_github(
            repo,
            version,
            target_override=target_key,
            record_history=False,
        )
    else:
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
        if isinstance(item, dict) and _history_key(item) != _history_key(current)
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
        for path in SHIP_BACKUP_DIR.iterdir()
        if path.name.startswith(f"{binary_name}.backup.")
        and (path.is_file() or path.is_symlink())
    ]
    if not backups:
        die(f"No saved binary backup found for '{binary_name}'.")
    backup = max(backups, key=lambda path: path.name.rsplit(".", 1)[-1])
    public_link = SHIP_BIN_DIR / binary_name
    if public_link.exists() or public_link.is_symlink():
        if not public_link.is_symlink():
            die(f"Refusing to replace unmanaged file at {public_link}.")
        try:
            public_link.resolve(strict=False).relative_to(SHIP_ROOT.resolve())
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
