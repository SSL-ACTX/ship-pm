"""Package installation, extraction, symlinking, and removal."""

import bz2
import datetime
import gzip
import lzma
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

from ship.config import (
    SHIP_BACKUP_DIR,
    SHIP_BIN_DIR,
    SHIP_CACHE_DIR,
    SHIP_INTERNAL_BIN,
    SHIP_ROOT,
    SHIP_STORE_DIR,
    load_state,
    save_state,
)
from ship.patchers import apply_patchers
from ship.patches import apply_package_patch, apply_reapply_handlers
from ship.patches.api import PatchReport
from ship.platform import detect_target_keys
from ship.registry import fetch_cached_file, get_pkg_manifest
from ship.ui import c, die, status, warn
from ship.version import classify_channel, select_default_version

NON_EXEC_EXTENSIONS = (
    ".so",
    ".dylib",
    ".dll",
    ".a",
    ".lib",
    ".rlib",
    ".o",
    ".obj",
    ".export",
    ".h",
    ".hpp",
    ".c",
    ".cpp",
    ".rs",
    ".py",
    ".pyc",
    ".pyo",
    ".lean",
    ".olean",
    ".ilean",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".txt",
    ".md",
    ".lock",
    ".log",
)


def is_cli_executable(file_path: Path) -> bool:
    name = file_path.name.lower()

    if any(name.endswith(ext) or f"{ext}." in name for ext in NON_EXEC_EXTENSIONS):
        return False

    if name.startswith("lib") and (".so" in name or ".dylib" in name):
        return False

    try:
        with open(file_path, "rb") as f:
            magic = f.read(18)
            if not magic:
                return False

            if magic.startswith(b"#!"):
                return True

            if magic.startswith(b"MZ"):
                return True

            if magic[:4] in (
                b"\xfe\xed\xfa\xce",
                b"\xfe\xed\xfa\xcf",
                b"\xce\xfa\xed\xfe",
                b"\xcf\xfa\xed\xfe",
                b"\xca\xfe\xba\xbe",
            ):
                return True

            if magic.startswith(b"\x7fELF"):
                if len(magic) >= 18:
                    e_type = magic[16] | (magic[17] << 8)
                    if e_type == 1:
                        return False
                return True

    except OSError:
        return False

    return False


def is_compiled_executable(file_path: Path) -> bool:
    """Return whether a CLI candidate is a native executable, not a script."""
    try:
        with open(file_path, "rb") as f:
            magic = f.read(4)
    except OSError:
        return False

    return magic.startswith((b"\x7fELF", b"MZ")) or magic in (
        b"\xfe\xed\xfa\xce",
        b"\xfe\xed\xfa\xcf",
        b"\xce\xfa\xed\xfe",
        b"\xcf\xfa\xed\xfe",
        b"\xca\xfe\xba\xbe",
    )


def extract_archive(archive_path: Path, extract_dir: Path, pkg_name: str) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    bin_dir = extract_dir / "bin"
    bin_dir.mkdir(exist_ok=True)

    name = archive_path.name.lower()
    if name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(extract_dir)
    elif name.endswith((".tar.xz", ".txz")):
        with tarfile.open(archive_path, "r:xz") as tar:
            tar.extractall(extract_dir)
    elif name.endswith((".tar.bz2", ".tbz2")):
        with tarfile.open(archive_path, "r:bz2") as tar:
            tar.extractall(extract_dir)
    elif name.endswith(".tar.zst"):
        decoder = shutil.which("zstd") or shutil.which("unzstd")
        if not decoder:
            raise RuntimeError(
                "Cannot extract .tar.zst archive: install the 'zstd' command first."
            )
        proc = subprocess.Popen(
            [decoder, "-dc", str(archive_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
                tar.extractall(extract_dir)
            _, error = proc.communicate()
        except Exception:
            proc.kill()
            proc.communicate()
            raise
        if proc.returncode:
            raise RuntimeError(
                f"zstd could not extract {archive_path.name}: "
                f"{error.decode(errors='replace').strip()}"
            )
    elif name.endswith(".tar"):
        with tarfile.open(archive_path, "r:") as tar:
            tar.extractall(extract_dir)
    elif name.endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as z:
            z.extractall(extract_dir)
    elif name.endswith(".gz") and not name.endswith(".tar.gz"):
        dest_file = bin_dir / (f"{pkg_name}.exe" if ".exe" in name else pkg_name)
        with gzip.open(archive_path, "rb") as f_in, open(dest_file, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    elif name.endswith(".xz") and not name.endswith(".tar.xz"):
        dest_file = bin_dir / (f"{pkg_name}.exe" if ".exe" in name else pkg_name)
        with lzma.open(archive_path, "rb") as f_in, open(dest_file, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    elif name.endswith(".bz2") and not name.endswith(".tar.bz2"):
        dest_file = bin_dir / (f"{pkg_name}.exe" if ".exe" in name else pkg_name)
        with bz2.open(archive_path, "rb") as f_in, open(dest_file, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    else:
        dest1 = extract_dir / archive_path.name
        dest2 = extract_dir / pkg_name
        dest3 = bin_dir / pkg_name
        shutil.copy2(archive_path, dest1)
        shutil.copy2(archive_path, dest2)
        shutil.copy2(archive_path, dest3)
        for d in (dest1, dest2, dest3):
            d.chmod(0o755)


def clean_symlinks(pkg_name: str) -> None:
    state = load_state()
    pkg = state.get("installed", {}).get(pkg_name)
    if pkg:
        for sym in pkg.get("symlinks", []):
            p = Path(sym)
            if p.is_symlink() or p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass

    pkg_pattern = f"{pkg_name}@"
    for bin_dir in (SHIP_BIN_DIR, SHIP_INTERNAL_BIN):
        if not bin_dir.is_dir():
            continue
        for item in bin_dir.iterdir():
            if item.is_symlink():
                try:
                    dest = str(item.resolve())
                    if pkg_pattern in dest:
                        item.unlink(missing_ok=True)
                except OSError:
                    pass


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
    """Record the prior package version when a different version is installed."""
    if not previous or not previous.get("version") or not previous.get("target_key"):
        return
    snapshot = {
        key: previous[key]
        for key in ("source", "version", "target_key")
        if key in previous
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
        print(
            f"\n{c('⚠️  Manual target selection override requested (not recommended).', '1;33')}"
        )
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
                print("Invalid index, try again.")
            except (ValueError, KeyboardInterrupt, EOFError):
                die("\nTarget selection cancelled.")
    else:
        for k in candidate_keys:
            if k in targets:
                matched_key = k
                break

    if not matched_key:
        print(
            f"{c('warning:', '1;33')} Available targets for {pkg_name}@{version}:",
            file=sys.stderr,
        )
        for t in targets:
            print(f"  - {t}", file=sys.stderr)
        die(
            f"No compatible target found for system ({platform.system()} {platform.machine()}). Force one using '--target <triple>'."
        )

    target_data = targets[matched_key]
    url = target_data.get("url")
    expected_sha = target_data.get("sha256", "")
    binary_map = target_data.get("binaries") or ver_data.get("binaries")
    declared_binaries = binary_map or {pkg_name: f"bin/{pkg_name}"}

    channel_badge = f" [{channel}]" if channel in ("nightly", "prerelease") else ""
    status(
        "Resolving",
        f"{pkg_name}@{version}{channel_badge} for {matched_key}",
    )

    archive_name = f"{pkg_name}-{version}-{Path(url).name}"
    local_archive = SHIP_CACHE_DIR / archive_name
    fetch_cached_file(
        url,
        local_archive,
        expected_sha256=expected_sha,
        description=f"{pkg_name}@{version} archive",
    )

    install_dir = SHIP_STORE_DIR / f"{pkg_name}@{version}"
    shutil.rmtree(install_dir, ignore_errors=True)
    status("Extracting", str(install_dir))
    extract_archive(local_archive, install_dir, pkg_name)

    patch_report = PatchReport(pkg_name)
    apply_package_patch(
        pkg_name, "post_extract", install_dir, matched_key, patch_report
    )
    apply_package_patch(pkg_name, "pre_link", install_dir, matched_key, patch_report)

    status("Linking", "creating binary symlinks...")
    clean_symlinks(pkg_name)
    linked = []

    found_binaries: dict[str, Path] = {}

    for symlink_name, rel_path in declared_binaries.items():
        cand = install_dir / rel_path
        if not cand.is_file():
            cand = install_dir / "bin" / symlink_name
        if not cand.is_file():
            for root, _, files in os.walk(install_dir):
                if symlink_name in files:
                    p = Path(root) / symlink_name
                    if is_cli_executable(p):
                        cand = p
                        break
        if cand.is_file() and is_cli_executable(cand):
            found_binaries[symlink_name] = cand

    # Generated manifests can contain a guessed path that differs from the
    # executable's name inside an archive (for example, a project named
    # "valerie-core" shipping `bin/valerie-compiler`). Preserve the declared
    # command name when the package has exactly one declared command and one
    # discoverable CLI executable; do not guess when either side is ambiguous.
    if binary_map and len(declared_binaries) == 1 and not found_binaries:
        symlink_name = next(iter(declared_binaries))
        candidates = []
        for root, dirs, files in os.walk(install_dir):
            dirs[:] = [
                d
                for d in dirs
                if d not in ("lib", "lib64", "share", "include", "build")
            ]
            for filename in files:
                candidate = Path(root) / filename
                if is_cli_executable(candidate) and not candidate.name.endswith(
                    "-real"
                ):
                    candidates.append(candidate)
        if len(candidates) == 1:
            found_binaries[symlink_name] = candidates[0]
            warn(
                f"Manifest binary path {next(iter(declared_binaries.values()))!r} "
                f"was missing; using the package's only CLI executable "
                f"{candidates[0].relative_to(install_dir)} as {symlink_name}."
            )

    # An explicit manifest map is authoritative. Only use archive discovery
    # for older or local manifests that do not declare their commands.
    if not binary_map:
        for root, dirs, files in os.walk(install_dir):
            dirs[:] = [
                d
                for d in dirs
                if d not in ("lib", "lib64", "share", "include", "build")
            ]
            for filename in files:
                candidate = Path(root) / filename
                if (
                    is_cli_executable(candidate)
                    and not candidate.name.endswith("-real")
                    and candidate.name not in found_binaries
                ):
                    found_binaries[candidate.name] = candidate

    for symlink_name, target in found_binaries.items():
        target.chmod(0o755)
        patched_target = apply_patchers(target, matched_key, patch_report)

        internal_link = SHIP_INTERNAL_BIN / symlink_name
        internal_link.unlink(missing_ok=True)
        internal_link.symlink_to(patched_target)

        pub_link = SHIP_BIN_DIR / symlink_name
        if pub_link.is_symlink() or pub_link.exists():
            if not (
                pub_link.is_symlink() and str(SHIP_ROOT) in str(pub_link.resolve())
            ):
                backup_file = (
                    SHIP_BACKUP_DIR / f"{symlink_name}.backup.{int(time.time())}"
                )
                pub_link.rename(backup_file)
                warn(f"Backed up external binary to {backup_file}")
            else:
                pub_link.unlink()

        pub_link.symlink_to(patched_target)
        linked.append(str(pub_link))
        print(f"  {c('Linked', '1;32')} {symlink_name} -> {pub_link}")

    if not linked:
        die("No functional binaries could be linked.")

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
    status(
        "Installed",
        f"{pkg_name}@{version}{channel_badge} ({matched_key})",
    )


def remove_package(pkg_name: str) -> None:
    state = load_state()
    if pkg_name not in state.get("installed", {}):
        die(f"Package '{pkg_name}' is not installed.")

    pkg_data = state["installed"].pop(pkg_name)
    state.get("history", {}).pop(pkg_name, None)
    inst_dir = Path(pkg_data.get("install_dir", ""))
    if inst_dir.is_dir():
        shutil.rmtree(inst_dir, ignore_errors=True)

    clean_symlinks(pkg_name)
    save_state(state)
    status("Removed", pkg_name)


def _discover_previous_install(pkg_name: str, current: dict) -> dict | None:
    """Find an older extracted version left by installs before history tracking."""
    current_version = str(current.get("version", ""))
    target_key = str(current.get("target_key", ""))
    source = current.get("source")
    manifest = get_pkg_manifest(pkg_name) if not source else None
    candidates: list[tuple[int, dict]] = []
    try:
        directories = list(SHIP_STORE_DIR.iterdir())
    except OSError:
        return None
    prefix = f"{pkg_name}@"
    for directory in directories:
        if not directory.is_dir() or not directory.name.startswith(prefix):
            continue
        version = directory.name[len(prefix) :]
        if not version or version == current_version:
            continue
        if manifest:
            version_data = manifest.get("versions", {}).get(version, {})
            if target_key not in version_data.get("targets", {}):
                continue
        try:
            modified = directory.stat().st_mtime_ns
        except OSError:
            continue
        snapshot = {"version": version, "target_key": target_key}
        if source:
            snapshot["source"] = source
        candidates.append((modified, snapshot))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def rollback_package(pkg_name: str, *, assume_yes: bool = False) -> None:
    """Reinstall the previous recorded version of a package."""
    state = load_state()
    current = state.get("installed", {}).get(pkg_name)
    if not current:
        die(f"Package '{pkg_name}' is not installed.")
    histories = state.get("history", {})
    entries = histories.get(pkg_name, []) if isinstance(histories, dict) else []
    if not isinstance(entries, list):
        entries = []
    if not entries:
        discovered = _discover_previous_install(pkg_name, current)
        if discovered:
            entries = [discovered]
    if not entries or not isinstance(entries[0], dict):
        die(
            f"No previous installed version is recorded for '{pkg_name}'. "
            "Ship can roll back versions installed before history tracking only "
            "when their extracted files are still present."
        )

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
    """Reapply package and platform patches to an installed package in place."""
    state = load_state()
    pkg_data = state.get("installed", {}).get(pkg_name)
    if not pkg_data:
        die(f"Package '{pkg_name}' is not installed.")

    install_dir = Path(pkg_data.get("install_dir", ""))
    if not install_dir.is_dir():
        die(f"Installed files for '{pkg_name}' are missing: {install_dir}")
    target_key = pkg_data.get("target_key", "")
    if not target_key:
        die(f"No target is recorded for installed package '{pkg_name}'.")

    binaries: dict[str, Path] = {}
    for symlink in pkg_data.get("symlinks", []):
        link = Path(symlink)
        try:
            target = link.resolve(strict=True)
            target.relative_to(install_dir.resolve())
        except (OSError, ValueError):
            continue
        binaries[link.name] = target

    if not binaries:
        die(f"No installed command links found for '{pkg_name}'.")

    status(
        "Patching",
        f"reapplying patches to {pkg_name}@{pkg_data.get('version', '')}",
    )
    # Platform patchers keep the original executable beside their launcher.
    # Restore it first so patching is applied to the ELF, not the shell wrapper.
    for binary in set(binaries.values()):
        real_binary = binary.with_name(f"{binary.name}-real")
        if real_binary.is_file():
            os.replace(real_binary, binary)

    patch_report = PatchReport(pkg_name)
    apply_package_patch(pkg_name, "post_extract", install_dir, target_key, patch_report)
    apply_package_patch(pkg_name, "pre_link", install_dir, target_key, patch_report)
    apply_reapply_handlers(pkg_name, patch_report)

    patched_by_source: dict[Path, Path] = {}
    for target in set(binaries.values()):
        target.chmod(0o755)
        patched_by_source[target] = apply_patchers(target, target_key, patch_report)
    patched_binaries = {
        name: patched_by_source[target] for name, target in binaries.items()
    }
    clean_symlinks(pkg_name)

    new_links: list[str] = []
    for symlink_name, patched_target in patched_binaries.items():
        internal_link = SHIP_INTERNAL_BIN / symlink_name
        internal_link.unlink(missing_ok=True)
        internal_link.symlink_to(patched_target)

        public_link = SHIP_BIN_DIR / symlink_name
        if public_link.is_symlink() or public_link.exists():
            if not (
                public_link.is_symlink()
                and str(SHIP_ROOT) in str(public_link.resolve())
            ):
                backup_file = (
                    SHIP_BACKUP_DIR / f"{symlink_name}.backup.{int(time.time())}"
                )
                public_link.rename(backup_file)
                warn(f"Backed up external binary to {backup_file}")
            else:
                public_link.unlink()

        public_link.symlink_to(patched_target)
        new_links.append(str(public_link))
        print(f"  {c('Linked', '1;32')} {symlink_name} -> {public_link}")

    pkg_data["symlinks"] = new_links
    save_state(state)
    _show_patch_report(patch_report, show_empty=True)
    status("Finished", f"reapplied patches to {pkg_name}")
