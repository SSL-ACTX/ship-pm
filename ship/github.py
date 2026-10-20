"""Direct installation of pre-built releases from GitHub repositories."""

import datetime
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

from ship import __version__
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
from ship.platform import detect_target_keys
from ship.registry import calc_sha256, fetch_file
from ship.store import clean_symlinks, extract_archive, is_cli_executable
from ship.ui import c, die, status, warn

SIG_EXTENSIONS = (
    ".sig",
    ".asc",
    ".minisig",
    ".pem",
    ".cert",
    ".crt",
    ".sbom",
)
SKIP_EXTENSIONS = (
    ".whl",
    ".nupkg",
    ".snupkg",
    ".gem",
    ".jar",
    ".egg",
    ".deb",
    ".rpm",
    ".apk",
    ".msi",
    ".dmg",
    ".pkg",
    ".zst",
    ".appimage",
)
BUILD_ARTIFACT_PATTERNS = (
    "lean-build-",
    "-debug.",
    "-dbg.",
    "-symbols.",
    "-sdk.",
    "-source.",
    "-src.",
    "-sources.",
)


def parse_repo_slug(raw_input: str) -> tuple[str, str]:
    slug = re.sub(r"^https?://github\.com/", "", raw_input).strip()
    slug = slug.rstrip("/")
    slug = slug.removesuffix(".git")
    slug = slug.rstrip("/")
    if "/" not in slug:
        die(f"Invalid repository format: '{raw_input}'. Expected 'owner/repo'.")
    parts = slug.split("/", 1)
    return parts[0], parts[1]


def fetch_github_json(url: str) -> dict | list | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"ship/{__version__}",
    }
    gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def install_from_github(
    repo_input: str,
    tag: str | None = None,
    target_override: str | None = None,
    interactive: bool = False,
) -> None:
    owner, repo_name = parse_repo_slug(repo_input)
    target_tag = tag if (tag and tag != "latest") else None

    status("Querying", f"GitHub releases for {owner}/{repo_name}...")
    release: dict | None = None

    if target_tag:
        tag_url = f"https://api.github.com/repos/{owner}/{repo_name}/releases/tags/{target_tag}"
        res = fetch_github_json(tag_url)
        if isinstance(res, dict):
            release = res

    if not release:
        list_url = f"https://api.github.com/repos/{owner}/{repo_name}/releases"
        releases = fetch_github_json(list_url)
        if isinstance(releases, list) and releases:
            if target_tag:
                clean_target = target_tag.lstrip("v")
                for r in releases:
                    r_tag = str(r.get("tag_name", "")).lstrip("v")
                    if r_tag == clean_target:
                        release = r
                        break
            if not release:
                release = releases[0]

    if not release:
        die(f"Could not find any releases for {owner}/{repo_name}.")

    raw_version = str(release.get("tag_name", "latest"))
    version = raw_version.lstrip("v")
    assets = release.get("assets", [])

    if not assets:
        die(
            f"No downloadable assets found in release {raw_version} of {owner}/{repo_name}."
        )

    target_keys = detect_target_keys(target_override)
    candidate_assets: list[tuple[dict, str, int]] = []
    checksum_assets: list[dict] = []

    for a in assets:
        name = a.get("name", "").lower()
        if any(name.endswith(ext) for ext in SIG_EXTENSIONS) or any(
            name.endswith(ext) for ext in SKIP_EXTENSIONS
        ):
            continue
        if any(k in name for k in BUILD_ARTIFACT_PATTERNS):
            continue
        if any(k in name for k in ("sha256", "checksum", "hashes", "sha256sum")):
            checksum_assets.append(a)
            continue
        if any(k in name for k in ("doc.zip", "docs.zip", "-doc.", "-docs.")):
            continue

        for idx, target in enumerate(target_keys):
            t_arch, t_os, *t_abi = target.split("-")
            matches_arch = (
                (
                    t_arch in ("aarch64", "arm64")
                    and any(x in name for x in ("aarch64", "arm64"))
                )
                or (
                    t_arch in ("x86_64", "amd64")
                    and any(x in name for x in ("x86_64", "amd64", "x64"))
                )
                or (
                    t_arch in ("armv7", "armhf")
                    and any(x in name for x in ("armv7", "armhf", "arm32"))
                )
                or (t_arch == "riscv64" and "riscv64" in name)
                or (
                    t_arch in ("i686", "i386")
                    and any(x in name for x in ("i686", "i386", "386", "x86"))
                )
            )
            matches_os = (
                (
                    t_os in ("darwin", "apple")
                    and any(x in name for x in ("darwin", "apple", "macos", "osx"))
                )
                or (
                    t_os in ("linux", "android", "termux")
                    and any(
                        x in name
                        for x in (
                            "linux",
                            "glibc",
                            "manylinux",
                            "musl",
                            "android",
                            "termux",
                        )
                    )
                )
                or (t_os in ("freebsd", "openbsd", "netbsd") and t_os in name)
                or (
                    t_os == "windows"
                    and any(
                        x in name
                        for x in (
                            "windows",
                            "-win-",
                            "-win.",
                            "_win_",
                            "_win.",
                            "win64",
                            "win32",
                            ".exe",
                        )
                    )
                )
            )

            if matches_arch and matches_os:
                score = 100 - idx * 10
                if t_abi and t_abi[0] in name:
                    score += 15
                if any(
                    name.endswith(ext) for ext in (".tar.gz", ".tgz", ".tar.xz", ".zip")
                ):
                    score += 5
                candidate_assets.append((a, target, score))

    if not candidate_assets:
        die(
            f"No compatible binary assets found for system in {owner}/{repo_name}@{raw_version}."
        )

    if interactive and sys.stdin.isatty():
        print(f"\n{c('Available release assets:', '1')}")
        unique_choices = []
        for a, tgt, _ in candidate_assets:
            if (a["name"], tgt) not in unique_choices:
                unique_choices.append((a, tgt))
        for idx, (a, tgt) in enumerate(unique_choices, 1):
            print(f"  [{idx}] {a['name']} ({tgt})")
        while True:
            try:
                choice = input(f"Select asset [1-{len(unique_choices)}]: ").strip()
                if not choice:
                    continue
                chosen_idx = int(choice) - 1
                if 0 <= chosen_idx < len(unique_choices):
                    best_asset, best_target = unique_choices[chosen_idx]
                    break
            except (ValueError, KeyboardInterrupt, EOFError):
                die("\nAsset selection cancelled.")
    else:
        candidate_assets.sort(key=lambda x: x[2], reverse=True)
        best_asset, best_target, _ = candidate_assets[0]

    asset_name = best_asset["name"]
    download_url = best_asset["browser_download_url"]

    status("Matched", f"asset {asset_name} ({best_target})")
    status("Downloading", download_url)

    dest_archive = SHIP_CACHE_DIR / f"{owner}_{repo_name}_{asset_name}"
    fetch_file(download_url, dest_archive)

    expected_sha = ""
    for ca in checksum_assets:
        ca_url = ca.get("browser_download_url")
        if not ca_url:
            continue
        try:
            req = urllib.request.Request(
                ca_url, headers={"User-Agent": f"ship/{__version__}"}
            )
            with urllib.request.urlopen(req) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
                for line in content.splitlines():
                    if asset_name in line:
                        match = re.search(r"[0-9a-fA-F]{64}", line)
                        if match:
                            expected_sha = match.group(0).lower()
                            break
            if expected_sha:
                break
        except (urllib.error.URLError, TimeoutError, OSError):
            pass

    if expected_sha:
        status("Verifying", f"SHA-256 checksum ({expected_sha[:12]}...)...")
        actual_sha = calc_sha256(dest_archive)
        if actual_sha.lower() != expected_sha:
            dest_archive.unlink(missing_ok=True)
            die(
                f"Checksum mismatch for {asset_name}!\n  Expected: {expected_sha}\n  Got:      {actual_sha}"
            )

    install_dir = SHIP_STORE_DIR / f"{repo_name}@{version}"
    shutil.rmtree(install_dir, ignore_errors=True)
    status("Extracting", str(install_dir))
    extract_archive(dest_archive, install_dir, repo_name)

    clean_symlinks(repo_name)
    status("Linking", "discovering and linking binaries...")

    # Strict discovery: search bin/ first; if not present, filter root strictly
    execs: list[Path] = []
    for root, _, files in os.walk(install_dir):
        if os.path.basename(root) in ("bin", "usr/bin"):
            for f in files:
                p = Path(root) / f
                if is_cli_executable(p):
                    execs.append(p)

    if not execs:
        # Search shallow directory structure, strictly rejecting libraries and build artifacts
        for root, dirs, files in os.walk(install_dir):
            # Do not traverse into lib directories or internal build caches
            dirs[:] = [
                d
                for d in dirs
                if d not in ("lib", "lib64", "share", "include", "build")
            ]
            for f in files:
                p = Path(root) / f
                if is_cli_executable(p):
                    execs.append(p)

    if not execs:
        die(f"Could not find any executable CLI binaries in {asset_name}.")

    linked = []
    for exe in execs:
        exe.chmod(0o755)
        patched_exe = apply_patchers(exe, best_target)
        symlink_name = exe.name

        internal_link = SHIP_INTERNAL_BIN / symlink_name
        internal_link.unlink(missing_ok=True)
        internal_link.symlink_to(patched_exe)

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

        pub_link.symlink_to(patched_exe)
        linked.append(str(pub_link))
        print(f"  {c('Linked', '1;32')} {symlink_name} -> {pub_link}")

    state = load_state()
    state.setdefault("installed", {})[repo_name] = {
        "source": f"github:{owner}/{repo_name}",
        "version": version,
        "target_key": best_target,
        "install_dir": str(install_dir),
        "symlinks": linked,
        "installed_at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d"),
    }
    save_state(state)
    status("Installed", f"{owner}/{repo_name}@{version} (GitHub release)")
