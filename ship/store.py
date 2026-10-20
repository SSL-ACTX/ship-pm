"""Package installation, extraction, symlinking, and removal."""

import datetime
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
    HOME,
    IS_TERMUX,
    PREFIX,
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
from ship.platform import detect_target_keys
from ship.registry import calc_sha256, fetch_file, get_pkg_manifest
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
    elif name.endswith(".tar"):
        with tarfile.open(archive_path, "r:") as tar:
            tar.extractall(extract_dir)
    elif name.endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as z:
            z.extractall(extract_dir)
    else:
        dest1 = extract_dir / archive_path.name
        dest2 = extract_dir / pkg_name
        dest3 = bin_dir / pkg_name
        shutil.copy2(archive_path, dest1)
        shutil.copy2(archive_path, dest2)
        shutil.copy2(archive_path, dest3)
        for d in (dest1, dest2, dest3):
            d.chmod(0o755)


def run_post_install_hook(target_data: dict, install_dir: Path) -> None:
    post_hook = target_data.get("hooks", {}).get("post_install")
    if not post_hook:
        return

    status("Hook", "Executing post_install hook...")
    env = os.environ.copy()
    env["INSTALL_DIR"] = str(install_dir)
    env["HOME"] = str(HOME)

    if IS_TERMUX:
        glibc_pfx = Path(os.environ.get("GLIBC_PREFIX", f"{PREFIX}/glibc"))
        env["PREFIX"] = str(PREFIX)
        env["GLIBC_PREFIX"] = str(glibc_pfx)

        for cert in (
            glibc_pfx / "etc/ssl/certs/ca-certificates.crt",
            PREFIX / "etc/tls/cert.pem",
            PREFIX / "etc/ssl/certs/ca-certificates.crt",
        ):
            if cert.is_file():
                env["SSL_CERT_FILE"] = str(cert)
                break

    try:
        subprocess.run(post_hook, shell=True, cwd=install_dir, env=env, check=True)
    except subprocess.SubprocessError as e:
        die(f"post_install hook failed: {e}")


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
    declared_binaries = (
        target_data.get("binaries")
        or ver_data.get("binaries")
        or {pkg_name: f"bin/{pkg_name}"}
    )

    channel_badge = f" [{channel}]" if channel in ("nightly", "prerelease") else ""
    status(
        "Resolving",
        f"{pkg_name}@{version}{channel_badge} for {matched_key}",
    )

    archive_name = f"{pkg_name}-{version}-{Path(url).name}"
    local_archive = SHIP_CACHE_DIR / archive_name
    status("Downloading", url)
    fetch_file(url, local_archive)

    if expected_sha:
        status("Verifying", "SHA-256 checksum...")
        actual_sha = calc_sha256(local_archive)
        if actual_sha.lower() != expected_sha.lower():
            local_archive.unlink(missing_ok=True)
            die(
                f"Checksum mismatch for {pkg_name}@{version}!\n  Expected: {expected_sha}\n  Got:      {actual_sha}"
            )

    install_dir = SHIP_STORE_DIR / f"{pkg_name}@{version}"
    shutil.rmtree(install_dir, ignore_errors=True)
    status("Extracting", str(install_dir))
    extract_archive(local_archive, install_dir, pkg_name)

    run_post_install_hook(target_data, install_dir)

    status("Linking", "creating binary symlinks...")
    clean_symlinks(pkg_name)
    linked = []

    # 1. Discover all candidate CLI binaries in package
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

    for root, dirs, files in os.walk(install_dir):
        dirs[:] = [
            d for d in dirs if d not in ("lib", "lib64", "share", "include", "build")
        ]
        for f in files:
            p = Path(root) / f
            if is_cli_executable(p) and not p.name.endswith("-real"):
                if p.name not in found_binaries:
                    found_binaries[p.name] = p

    for symlink_name, target in found_binaries.items():
        target.chmod(0o755)
        patched_target = apply_patchers(target, matched_key)

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

    state = load_state()
    state.setdefault("installed", {})[pkg_name] = {
        "version": version,
        "channel": channel,
        "target_key": matched_key,
        "install_dir": str(install_dir),
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
