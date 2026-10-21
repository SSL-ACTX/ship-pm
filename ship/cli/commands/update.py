"""Update, check-upstream, and self-update commands."""

from __future__ import annotations

import concurrent.futures
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from ship import __version__
from ship.cli.commands._util import clean_repo_slug
from ship.cli.commands.publish import run_publish
from ship.cli.engine import Namespace
from ship.core.settings import settings
from ship.core.state import load_state
from ship.core.version import (
    classify_channel,
    classify_channel_for_version,
    format_version,
    select_default_version,
    select_latest_in_channel,
    semver_sort_key,
    versions_equal,
)
from ship.install import install_from_github, install_package
from ship.net.github import fetch_github_json
from ship.registry import fetch_file, get_pkg_manifest, sync_registry
from ship.ui import ui
from ship.ui.sync import PkgState, SyncUI, UpdateUI


def run_update(ns: Namespace) -> None:
    target = ns.get("target") or ""
    if target in ("self", "ship"):
        run_self_update(ns)
        return
    if target in ("registry", "index"):
        sync_registry()
        return
    if target in ("deb", "ubuntu"):
        from ship.registry.sync import refresh_ubuntu_registry

        refresh_ubuntu_registry()
        return

    sync_registry()
    installed = load_state().get("installed", {})

    if target:
        _update_one(target, installed)
        return

    if not installed:
        ui.status("Finished", "registry updated (no packages installed)")
        return

    include_all = bool(ns.get("all", False))
    only_github = bool(ns.get("github", False))

    # --- Live check phase with SyncUI ---
    pkg_items: list[tuple[str, dict]] = []
    for n, d in sorted(installed.items()):
        is_gh = str(d.get("source", "")).startswith("github:")
        if only_github:
            if is_gh:
                pkg_items.append((n, d))
        elif include_all:
            if is_gh or get_pkg_manifest(n):
                pkg_items.append((n, d))
        else:
            if not is_gh and get_pkg_manifest(n):
                pkg_items.append((n, d))

    pkg_names = [n for n, _ in pkg_items]

    sync = SyncUI(pkg_names, heading="Checking installed packages for updates")
    sync.start()

    def _check_pkg(item: tuple[str, dict]) -> tuple[str, str, str | None]:
        pkg_name, data = item
        sync.set_checking(pkg_name)
        curr_ver = data.get("version", "")
        source = str(data.get("source", ""))
        new_ver: str | None = None

        if source.startswith("github:"):
            repo_slug = clean_repo_slug(source.removeprefix("github:"))
            channel = data.get("channel", "stable")
            try:
                up_channels = _fetch_upstream_by_channel(repo_slug)
                up_tag = up_channels.get(channel) or up_channels.get("stable")
                if (
                    up_tag
                    and not versions_equal(curr_ver, up_tag)
                    and semver_sort_key(up_tag) > semver_sort_key(curr_ver)
                ):
                    new_ver = up_tag
            except (OSError, ValueError):
                pass
        else:
            manifest = get_pkg_manifest(pkg_name)
            if not manifest:
                sync.set_result(pkg_name, PkgState.SKIPPED, note="no manifest")
                return pkg_name, curr_ver, None
            versions = manifest.get("versions", {})
            channel = data.get("channel") or classify_channel_for_version(
                curr_ver, versions
            )
            latest = _latest_for_channel(versions, channel)

            if (
                latest
                and not versions_equal(curr_ver, latest)
                and semver_sort_key(latest) > semver_sort_key(curr_ver)
            ):
                new_ver = latest
            else:
                repo_url = manifest.get("repository", "")
                m = re.search(r"github\.com/([^/]+/[^/]+)", repo_url)
                if m:
                    slug = clean_repo_slug(m.group(1))
                    try:
                        up_channels = _fetch_upstream_by_channel(slug)
                        up_tag = up_channels.get(channel) or up_channels.get("stable")
                        if (
                            up_tag
                            and not versions_equal(curr_ver, up_tag)
                            and semver_sort_key(up_tag) > semver_sort_key(curr_ver)
                        ):
                            new_ver = up_tag
                    except (OSError, ValueError):
                        pass

        if new_ver:
            sync.set_result(
                pkg_name, PkgState.OUTDATED, current=curr_ver, latest=new_ver
            )
        else:
            sync.set_result(pkg_name, PkgState.OK, current=curr_ver, latest=curr_ver)

        return pkg_name, curr_ver, new_ver

    max_workers = min(8, max(1, len(pkg_items)))
    upgrades: list[tuple[str, str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for pkg_name, curr_ver, new_ver in executor.map(_check_pkg, pkg_items):
            if new_ver:
                upgrades.append((pkg_name, curr_ver, new_ver))

    sync.finish()

    if not upgrades:
        return

    ui.blank()
    if not ui.confirm("Proceed with upgrade?", default=False):
        ui.status("Cancelled", "upgrade aborted")
        return

    # --- Live install phase with UpdateUI ---
    upd = UpdateUI([n for n, _, _ in upgrades])
    upd.start()

    for pkg_name, old_v, new_v in upgrades:
        upd.set_installing(pkg_name)
        try:
            entry = installed.get(pkg_name, {})
            source = str(entry.get("source", ""))
            if source.startswith("github:"):
                repo_slug = clean_repo_slug(source.removeprefix("github:"))
                install_from_github(repo_slug, tag=new_v)
            else:
                manifest = get_pkg_manifest(pkg_name)
                if manifest and new_v in manifest.get("versions", {}):
                    install_package(pkg_name, new_v)
                else:
                    repo_url = manifest.get("repository", "") if manifest else ""
                    m = re.search(r"github\.com/([^/]+/[^/]+)", repo_url)
                    if m:
                        install_from_github(clean_repo_slug(m.group(1)), tag=new_v)
                    else:
                        install_package(pkg_name, new_v)
            upd.set_done(pkg_name, success=True)
        except (OSError, RuntimeError, ValueError):
            upd.set_done(pkg_name, success=False)

    upd.finish()


def _update_one(target: str, installed: dict) -> None:
    if target not in installed:
        if "/" in target:
            install_from_github(target)
            return
        if not get_pkg_manifest(target):
            ui.warn(f"Package '{target}' is not in the registry.")
            run_check_upstream(Namespace(values={"package": target}))
            return
        install_package(target)
        return

    entry = installed[target]
    source = entry.get("source", "registry")
    curr_ver = entry.get("version", "")

    if str(source).startswith("github:"):
        repo_slug = str(source).removeprefix("github:")
        ui.status("Checking", f"GitHub updates for {repo_slug}...")
        install_from_github(repo_slug)
        return

    manifest = get_pkg_manifest(target)
    if not manifest:
        ui.die(f"Manifest for '{target}' not found in registry.")

    versions = manifest.get("versions", {})
    channel = entry.get("channel") or classify_channel_for_version(curr_ver, versions)
    latest = _latest_for_channel(versions, channel)

    if not latest or versions_equal(curr_ver, latest):
        ui.status(
            "Finished",
            f"{target} is already up to date ({format_version(curr_ver)} [{channel}])",
        )
        return
    if semver_sort_key(curr_ver) >= semver_sort_key(latest):
        ui.status(
            "Finished",
            f"{target} ({format_version(curr_ver)} [{channel}]) is equal to or newer than "
            f"registry {channel} ({format_version(latest)})",
        )
        return

    ui.status(
        "Updating",
        f"{target} {format_version(curr_ver)} -> {format_version(latest)} [{channel}]",
    )
    install_package(target, latest)


def _latest_for_channel(versions: dict, channel: str) -> str | None:
    """Stay on the installed channel; only fall back to default for unknown channels."""
    if channel in ("stable", "prerelease", "nightly"):
        return select_latest_in_channel(versions, channel) or select_default_version(
            versions
        )
    return select_default_version(versions)


def run_check_upstream(ns: Namespace) -> None:
    pkg_name = ns.get("package")
    if not pkg_name or pkg_name == "all":
        _check_all_upstream()
        return

    _check_single_upstream(pkg_name)


def _check_all_upstream() -> None:
    """Scan all installed packages or all registry packages for upstream updates."""
    from ship.core.settings import get_pkgs_dir

    pkgs_dir = get_pkgs_dir()
    manifest_files = sorted(pkgs_dir.glob("*.json"))
    if not manifest_files:
        ui.die("No registry manifests found.")

    # Collect only packages that have a GitHub repo
    checkable: list[tuple[str, str, dict]] = []
    for mf in manifest_files:
        pkg_name = mf.stem
        manifest = get_pkg_manifest(pkg_name)
        if not manifest or "repository" not in manifest:
            continue
        repo_url = manifest["repository"]
        match = re.search(r"github\.com/([^/]+/[^/]+)", repo_url)
        if not match:
            continue
        checkable.append((pkg_name, clean_repo_slug(match.group(1)), manifest))

    pkg_names = [n for n, _, _ in checkable]
    sync = SyncUI(pkg_names, heading="Checking registry packages against upstream")
    sync.start()

    outdated: list[tuple[str, str, str, str]] = []

    for pkg_name, upstream_repo, manifest in checkable:
        sync.set_checking(pkg_name)
        registry_versions = manifest.get("versions", {})
        try:
            upstream_by_channel = _fetch_upstream_by_channel(upstream_repo)
        except (OSError, ValueError):
            sync.set_result(pkg_name, PkgState.ERROR, note="fetch failed")
            continue
        if not upstream_by_channel:
            sync.set_result(pkg_name, PkgState.SKIPPED, note="no releases")
            continue

        pkg_outdated = False
        first_cur = ""
        first_up = ""
        for channel in ("stable", "prerelease", "nightly"):
            upstream_tag = upstream_by_channel.get(channel)
            registry_ver = select_latest_in_channel(registry_versions, channel)
            if not upstream_tag:
                continue
            if registry_ver and versions_equal(registry_ver, upstream_tag):
                continue
            if registry_ver and semver_sort_key(registry_ver) >= semver_sort_key(
                upstream_tag
            ):
                continue
            outdated.append((pkg_name, channel, registry_ver or "none", upstream_tag))
            if not pkg_outdated:
                first_cur = registry_ver or "none"
                first_up = upstream_tag
            pkg_outdated = True

        if pkg_outdated:
            sync.set_result(
                pkg_name, PkgState.OUTDATED, current=first_cur, latest=first_up
            )
        else:
            # Pick a representative "current" version for display
            reg_stable = select_latest_in_channel(registry_versions, "stable") or ""
            sync.set_result(pkg_name, PkgState.OK, current=reg_stable)

    sync.finish()

    if not outdated:
        return

    ui.blank()
    print(
        ui.style(
            f"Outdated packages ({len(outdated)} channel updates available):", "bold"
        )
    )
    for pkg_name, channel, reg_ver, up_tag in outdated:
        print(
            f"  • {ui.style(pkg_name, 'package')} [{channel}] {format_version(reg_ver)} -> {ui.style(format_version(up_tag), 'version')}"
        )
    ui.blank()


def _check_single_upstream(pkg_name: str) -> None:
    manifest = get_pkg_manifest(pkg_name)
    if not manifest:
        ui.die(
            f"Package '{pkg_name}' not found in registry. Submit it using: ship publish <owner/repo>"
        )

    repo_url = manifest.get("repository", "")
    match = re.search(r"github\.com/([^/]+/[^/]+)", repo_url)
    if not match:
        ui.die(f"Could not determine upstream GitHub repository for '{pkg_name}'.")

    upstream_repo = clean_repo_slug(match.group(1))
    ui.status("Checking", f"upstream GitHub releases for {upstream_repo}...")

    registry_versions = manifest.get("versions", {})
    upstream_by_channel = _fetch_upstream_by_channel(upstream_repo)
    if not upstream_by_channel:
        ui.die(f"No usable release tags found upstream for {upstream_repo}.")

    # Prefer proposing a stable bump; fall back to the package's default channel.
    default_channel = classify_channel_for_version(
        select_default_version(registry_versions) or "",
        registry_versions,
    )
    report_channels = ("stable", "prerelease", "nightly")

    ui.blank()
    print(ui.style(f"{pkg_name} channel comparison:", "bold"))
    actionable: list[tuple[str, str, str]] = []
    for channel in report_channels:
        upstream_tag = upstream_by_channel.get(channel)
        registry_ver = select_latest_in_channel(registry_versions, channel)
        _print_channel_row(channel, registry_ver, upstream_tag)
        if not upstream_tag:
            continue
        if registry_ver and versions_equal(registry_ver, upstream_tag):
            continue
        if registry_ver and semver_sort_key(registry_ver) >= semver_sort_key(
            upstream_tag
        ):
            continue
        actionable.append((channel, registry_ver or "—", upstream_tag))
    ui.blank()

    if not actionable:
        ui.status(
            "Up-to-date",
            f"{pkg_name} registry channels match upstream (stable/prerelease/nightly as available)",
        )
        return

    # Never treat a newer RC/nightly as a stable update.
    stable_bump = next((row for row in actionable if row[0] == "stable"), None)
    if stable_bump:
        channel, reg_ver, upstream_tag = stable_bump
        ui.warn(
            f"Upstream {channel} ({format_version(upstream_tag)}) is ahead of "
            f"registry {channel} ({format_version(reg_ver)})."
        )
        if ui.confirm("Propose this stable update to the registry now?", default=True):
            run_publish(
                Namespace(
                    values={"repo": upstream_repo, "tag": _publish_tag(upstream_tag)}
                )
            )
        else:
            ui.status("Skipped", "update proposal cancelled")
        return

    # Only non-stable channels are ahead — report, don't scare as a stable upgrade.
    primary = next(
        (row for row in actionable if row[0] == default_channel),
        actionable[0],
    )
    channel, reg_ver, upstream_tag = primary
    ui.info(
        f"Upstream has a newer {channel} release "
        f"({format_version(upstream_tag)}); registry {channel} is "
        f"{format_version(reg_ver)}. Stable is unchanged."
    )
    if ui.confirm(
        f"Propose this {channel} update to the registry now?",
        default=False,
    ):
        run_publish(
            Namespace(values={"repo": upstream_repo, "tag": _publish_tag(upstream_tag)})
        )
    else:
        ui.status("Skipped", "update proposal cancelled")


def _publish_tag(version: str) -> str:
    return version if version.startswith(("v", "V")) else f"v{version}"


_SENTINEL_TAGS = frozenset({"latest", "edge", "head", "trunk", "tip"})


def _fetch_upstream_by_channel(upstream_repo: str) -> dict[str, str]:
    """Fetch releases for upstream repo and return latest tag per channel.

    First checks /releases/latest for fast stable lookup, then page 1 releases.
    Only paginates further if non-stable channels are needed.
    """
    _ALL_CHANNELS = frozenset({"stable", "prerelease", "nightly"})
    best: dict[str, str] = {}

    # Fast path: check /releases/latest first
    latest_rel = fetch_github_json(
        f"https://api.github.com/repos/{upstream_repo}/releases/latest"
    )
    if isinstance(latest_rel, dict) and latest_rel.get("tag_name"):
        best["stable"] = latest_rel["tag_name"]

    url = f"https://api.github.com/repos/{upstream_repo}/releases?per_page=30&page=1"
    page_releases = fetch_github_json(url)
    if isinstance(page_releases, list) and page_releases:
        best = _latest_upstream_by_channel(list(page_releases), existing=best)

    # If stable is already found, stop immediately unless looking for more
    if "stable" in best or best.keys() >= _ALL_CHANNELS:
        return best

    page = 2
    while page <= 3:
        url = f"https://api.github.com/repos/{upstream_repo}/releases?per_page=30&page={page}"
        page_releases = fetch_github_json(url)
        if not isinstance(page_releases, list) or not page_releases:
            break
        best = _latest_upstream_by_channel(list(page_releases), existing=best)
        if best.keys() >= _ALL_CHANNELS or "stable" in best:
            break
        page += 1
    return best


def _latest_upstream_by_channel(
    releases: list[dict], existing: dict[str, str] | None = None
) -> dict[str, str]:
    """Pick the newest GitHub release tag per channel (stable/prerelease/nightly)."""
    best: dict[str, str] = dict(existing) if existing else {}
    for release in releases:
        if release.get("draft"):
            continue
        tag = str(release.get("tag_name") or "").strip()
        if not tag or tag.lower() in _SENTINEL_TAGS:
            # Skip non-version sentinel tags (e.g. cvc5 uses tag_name="latest"
            # for their rolling prerelease; it carries no version information).
            continue
        channel = classify_channel(tag)
        # Honour GitHub's prerelease flag when the tag looks stable.
        if release.get("prerelease") and channel == "stable":
            channel = "prerelease"
        current = best.get(channel)
        if current is None or semver_sort_key(tag) > semver_sort_key(current):
            best[channel] = tag
    return best


def _print_channel_row(
    channel: str,
    registry_ver: str | None,
    upstream_tag: str | None,
) -> None:
    style = {
        "stable": "channel_stable",
        "prerelease": "channel_prerelease",
        "nightly": "channel_nightly",
    }.get(channel, "muted")
    label = ui.style(f"{channel:<11}", style)
    reg = format_version(registry_ver) if registry_ver else ui.style("—", "muted")
    up = format_version(upstream_tag) if upstream_tag else ui.style("—", "muted")
    if registry_ver and upstream_tag and versions_equal(registry_ver, upstream_tag):
        mark = ui.style("ok", "success")
    elif upstream_tag and (
        not registry_ver
        or semver_sort_key(upstream_tag) > semver_sort_key(registry_ver)
    ):
        mark = ui.style("ahead", "warning")
    elif registry_ver and not upstream_tag:
        mark = ui.style("local-only", "muted")
    else:
        mark = ui.style("behind/equal", "muted")
    print(f"  {label}  registry {reg}  ·  upstream {up}  [{mark}]")


def run_self_update(_ns: Namespace) -> None:
    ui.status("Checking", "for ship updates...")
    self_path = Path(__file__).resolve()

    # Prefer git pull when running from a checkout (cli/commands -> repo root).
    repo_probe = (
        self_path.parents[3] if len(self_path.parents) >= 4 else self_path.parent
    )
    res = subprocess.run(
        ["git", "-C", str(repo_probe), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if res.returncode == 0:
        git_root = Path(res.stdout.strip())
        if (git_root / ".git").is_dir() and (
            git_root / "ship" / "__init__.py"
        ).is_file():
            ui.status("Updating", f"git repository at {git_root}...")
            pull = subprocess.run(
                ["git", "-C", str(git_root), "pull", "--ff-only"],
                check=False,
                capture_output=True,
            )
            if pull.returncode == 0:
                ui.status("Finished", "ship updated from local git repository")
                return

    remote_ver = _remote_package_version()
    if remote_ver and remote_ver == __version__:
        ui.status("Finished", f"ship is already up to date (v{__version__})")
        return

    entry = settings.ship_bin_dir / "ship"
    if not entry.is_file():
        entry = Path.home() / ".local" / "bin" / "ship"
    tmp_path = settings.ship_cache_dir / "ship_update.tmp"
    fetch_file(settings.ship_update_url, tmp_path)
    try:
        tmp_path.chmod(0o755)
        target = entry if entry.is_file() else self_path
        shutil.move(tmp_path, target)
        if remote_ver:
            ui.status("Finished", f"updated ship v{__version__} -> v{remote_ver}")
        else:
            ui.status("Finished", "ship entrypoint refreshed")
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        ui.die(f"Self-update failed: {exc}")


def _remote_package_version() -> str | None:
    """Read __version__ from the upstream package, not the entrypoint script."""
    url = settings.ship_update_url.replace("/bin/ship", "/ship/__init__.py")
    if url == settings.ship_update_url:
        return None
    req = urllib.request.Request(url, headers={"User-Agent": f"ship/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else None
