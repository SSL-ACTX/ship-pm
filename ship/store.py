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
from ship.lifecycle import run_post_install_hook
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


def install_package(
    pkg_name: str,
    version: str | None = None,
    target_override: str | None = None,
    interactive: bool = False,
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
    run_post_install_hook(target_data, install_dir)
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
    state.setdefault("installed", {})[pkg_name] = {
        "version": version,
        "channel": channel,
        "target_key": matched_key,
        "install_dir": str(install_dir),
        "download_size_bytes": local_archive.stat().st_size,
        "symlinks": linked,
        "installed_at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d"),
    }
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
    inst_dir = Path(pkg_data.get("install_dir", ""))
    if inst_dir.is_dir():
        shutil.rmtree(inst_dir, ignore_errors=True)

    clean_symlinks(pkg_name)
    save_state(state)
    status("Removed", pkg_name)


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
