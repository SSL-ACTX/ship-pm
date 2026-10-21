# ship/install/github_source.py
"""Install packages resolved from GitHub release assets."""

from __future__ import annotations

import hashlib
import re
import sys
import urllib.error
import urllib.request

from ship import __version__
from ship.core.platform import detect_target_keys
from ship.core.settings import settings
from ship.core.version import classify_channel, semver_sort_key
from ship.install.pipeline import InstallArtifact, finalize_install
from ship.net.download import fetch_cached_file
from ship.net.github import fetch_github_json, parse_repo_slug
from ship.ui import c, die, status

_CHANNEL_NAMES = frozenset({"stable", "prerelease", "nightly", "pre", "rc", "dev"})

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
    "installer",
    "setup",
)


def _reconcile_target_label(matched_target: str, asset_name: str) -> str:
    """Return an accurate target label for *asset_name*.

    When the asset matched via a target key (e.g. ``aarch64-linux-musl`` or
    ``aarch64-termux``) but the asset itself is a glibc build (e.g.
    ``…glibc-2.38.zip``), the raw matched key would be misleading.  Detect ABI
    from the asset filename and substitute the correct suffix.
    """
    name = asset_name.lower()
    parts = matched_target.split("-")
    arch = parts[0]

    # Determine the OS family from the target key.
    os_part = parts[1] if len(parts) >= 2 else ""
    if os_part not in ("linux", "android", "termux"):
        return matched_target  # only fixup Linux-family targets

    if "musl" in name or "alpine" in name:
        return f"{arch}-linux-musl"
    if "glibc" in name or "manylinux" in name:
        return f"{arch}-linux-gnu"
    # No ABI token in name — keep the matched key as-is.
    return matched_target


def _pick_release_by_channel(releases: list[dict], channel: str) -> dict | None:
    """Find the best GitHub release matching *channel* (stable/prerelease/nightly)."""
    best: dict | None = None
    best_key: tuple = ()
    for rel in releases:
        if rel.get("draft"):
            continue
        tag = str(rel.get("tag_name") or "").strip()
        if not tag:
            continue
        rel_channel = classify_channel(tag)
        # Honour GitHub's prerelease flag when the tag looks stable.
        if rel.get("prerelease") and rel_channel == "stable":
            rel_channel = "prerelease"
        if rel_channel != channel:
            continue
        key = semver_sort_key(tag)
        if best is None or key > best_key:
            best = rel
            best_key = key
    return best


def install_from_github(
    repo_input: str,
    tag: str | None = None,
    target_override: str | None = None,
    interactive: bool = False,
    asset_filter: str | None = None,
    *,
    record_history: bool = True,
) -> None:
    owner, raw_repo_name = parse_repo_slug(repo_input)
    GENERIC_NAMES = {
        "compiler",
        "cli",
        "v1",
        "v2",
        "v3",
        "core",
        "tooling",
        "app",
        "bin",
        "binary",
        "binaries",
        "releases",
        "cmd",
    }
    pkg_name = (
        owner.lower()
        if raw_repo_name.lower() in GENERIC_NAMES
        else raw_repo_name.lower()
    )

    target_tag = tag if (tag and tag != "latest") else None
    # Check if the user requested a channel name instead of a specific tag.
    requested_channel: str | None = None
    if target_tag and target_tag.lower() in _CHANNEL_NAMES:
        requested_channel = target_tag.lower()
        if requested_channel in ("pre", "rc", "dev"):
            requested_channel = "prerelease"
        target_tag = None  # resolve from release list below

    status("Querying", f"GitHub releases for {owner}/{raw_repo_name}...")
    release: dict | None = None

    if target_tag:
        tag_url = f"https://api.github.com/repos/{owner}/{raw_repo_name}/releases/tags/{target_tag}"
        res = fetch_github_json(tag_url)
        if isinstance(res, dict):
            release = res

    if not release:
        list_url = f"https://api.github.com/repos/{owner}/{raw_repo_name}/releases"
        releases = fetch_github_json(list_url)
        if isinstance(releases, list) and releases:
            if target_tag:
                clean_target = target_tag.lstrip("v")
                for r in releases:
                    r_tag = str(r.get("tag_name", "")).lstrip("v")
                    if r_tag == clean_target:
                        release = r
                        break
            if not release and requested_channel:
                # Pick the best release matching the requested channel.
                release = _pick_release_by_channel(releases, requested_channel)
                if not release:
                    die(
                        f"No {requested_channel} release found for "
                        f"{owner}/{raw_repo_name}."
                    )
            if not release:
                release = releases[0]

    if not release:
        die(f"Could not find any releases for {owner}/{raw_repo_name}.")

    raw_version = str(release.get("tag_name", "latest"))
    version = raw_version.lstrip("v")
    assets = release.get("assets", [])

    if not assets:
        die(
            f"No downloadable assets found in release {raw_version} of {owner}/{raw_repo_name}."
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
            is_universal = "universal" in name or "all" in name
            matches_arch = (
                is_universal
                or (
                    t_arch in ("aarch64", "arm64")
                    and any(
                        x in name for x in ("aarch64", "arm64", "mac-arm", "-mac-arm")
                    )
                )
                or (
                    t_arch in ("x86_64", "amd64")
                    and any(x in name for x in ("x86_64", "amd64", "x64"))
                )
                or (
                    t_arch in ("armv7", "armhf")
                    and any(
                        x in name
                        for x in (
                            "armv7",
                            "armhf",
                            "arm32",
                            "arm-unknown",
                            "linux-arm",
                            "-linux-arm",
                            "-arm-linux",
                            "_arm_linux",
                            "-arm.",
                        )
                    )
                    or name.endswith(("-arm", "_arm"))
                )
                or (t_arch == "riscv64" and "riscv64" in name)
                or (
                    t_arch in ("i686", "i386")
                    and any(
                        x in name
                        for x in ("i686", "i386", "386", "-x86-", "-x86.", "-x86")
                    )
                )
            )
            if (
                not matches_arch
                and t_arch == "x86_64"
                and not is_universal
                and not any(
                    token in name
                    for token in (
                        "aarch64",
                        "arm64",
                        "arm",
                        "x86_64",
                        "amd64",
                        "x64",
                        "riscv",
                        "ppc",
                        "s390",
                        "source",
                        "src",
                        "-all",
                        "_all",
                    )
                )
            ):
                matches_arch = True
            matches_os = (
                is_universal
                or (
                    t_os in ("darwin", "apple")
                    and any(
                        x in name
                        for x in ("darwin", "apple", "macos", "osx", "mac-", "-mac")
                    )
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
                            "alpine",
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
                    or name.endswith(("-win", "_win"))
                )
            )

            if matches_arch and matches_os:
                score = 100 - idx * 10
                if is_universal:
                    score += 20

                # Detect ABI signals in the asset filename.
                asset_is_glibc = "glibc" in name or "gnu" in name
                asset_is_musl = "musl" in name or "alpine" in name

                if t_abi:
                    abi = t_abi[0]
                    # Check if the asset's ABI matches this target's ABI.
                    # "gnu" and "glibc" are synonyms for glibc-linked binaries.
                    abi_match = (
                        abi in name
                        or (abi == "gnu" and asset_is_glibc)
                        or (abi == "musl" and asset_is_musl)
                    )
                    if abi_match:
                        score += 15
                    # Penalise ABI cross-matches: musl target vs glibc asset
                    # (or vice-versa).
                    want_musl = abi == "musl"
                    want_gnu = abi in ("gnu", "glibc")
                    if (
                        want_musl
                        and asset_is_glibc
                        and not asset_is_musl
                        or want_gnu
                        and asset_is_musl
                        and not asset_is_glibc
                    ):
                        score -= 25
                else:
                    # Target has no ABI part (e.g. aarch64-termux).  If the
                    # asset has a clear ABI marker, deprioritise this target so
                    # a properly-labelled target key wins.
                    if asset_is_glibc or asset_is_musl:
                        score -= 15

                if any(
                    name.endswith(ext)
                    for ext in (".tar.gz", ".tgz", ".tar.xz", ".tar.zst", ".zip")
                ):
                    score += 5
                candidate_assets.append((a, target, score))

    if not candidate_assets:
        die(
            f"No compatible binary assets found for system in {owner}/{raw_repo_name}@{raw_version}."
        )

    if asset_filter:
        filtered = [
            (a, t, s) for a, t, s in candidate_assets if asset_filter in a["name"]
        ]
        if filtered:
            candidate_assets = filtered

    if interactive:
        print(f"\n{c('Available release assets:', '1')}")
        # Deduplicate by asset filename — one entry per file, best-scored target wins.
        candidate_assets.sort(key=lambda x: x[2], reverse=True)
        seen_asset_names: set[str] = set()
        unique_choices: list[tuple[dict, str]] = []
        for a, tgt, _ in candidate_assets:
            if a["name"] not in seen_asset_names:
                seen_asset_names.add(a["name"])
                unique_choices.append((a, tgt))
        for idx, (a, tgt) in enumerate(unique_choices, 1):
            print(f"  [{idx}] {a['name']} ({tgt})")
        try:
            tty = open("/dev/tty")  # noqa: SIM115
        except OSError:
            tty = sys.stdin
        while True:
            try:
                sys.stdout.write(f"Select asset [1-{len(unique_choices)}]: ")
                sys.stdout.flush()
                choice = tty.readline().strip()
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

    # Correct the target label if the asset ABI doesn't match the matched key
    # (e.g. glibc asset matched via a musl target key on Termux).
    best_target = _reconcile_target_label(best_target, asset_name)

    status("Matched", f"asset {asset_name} ({best_target})")
    url_key = hashlib.sha256(download_url.encode("utf-8")).hexdigest()[:16]
    dest_archive = (
        settings.ship_cache_dir / f"{owner}_{raw_repo_name}_{url_key}_{asset_name}"
    )

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

    fetch_cached_file(
        download_url,
        dest_archive,
        expected_sha256=expected_sha,
        description=f"{owner}/{raw_repo_name}@{raw_version} ({asset_name})",
    )

    finalize_install(
        InstallArtifact(
            package_name=pkg_name,
            version=version,
            target_key=best_target,
            archive_path=dest_archive,
            source=f"github:{owner}/{raw_repo_name}",
            declared_binaries=None,
            discover_all_bins=True,
            validate_elf_architecture=True,
            asset_label=asset_name,
            success_label=f"{owner}/{raw_repo_name}@{version} (GitHub release)",
        ),
        record_history=record_history,
    )
