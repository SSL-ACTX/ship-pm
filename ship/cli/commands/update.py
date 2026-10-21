"""Update, check-upstream, and self-update commands."""

from __future__ import annotations

import json
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
from ship.registry import fetch_file, get_pkg_manifest, sync_registry
from ship.ui import ui


def run_update(ns: Namespace) -> None:
    target = ns.get("target") or ""
    if target in ("self", "ship"):
        run_self_update(ns)
        return
    if target in ("registry", "index"):
        sync_registry()
        return

    sync_registry()
    installed = load_state().get("installed", {})

    if target:
        _update_one(target, installed)
        return

    if not installed:
        ui.status("Finished", "registry updated (no packages installed)")
        return

    upgrades: list[tuple[str, str, str]] = []
    for pkg_name, data in sorted(installed.items()):
        if str(data.get("source", "")).startswith("github:"):
            continue
        curr_ver = data.get("version", "")
        manifest = get_pkg_manifest(pkg_name)
        if not manifest:
            continue
        versions = manifest.get("versions", {})
        channel = data.get("channel") or classify_channel_for_version(curr_ver, versions)
        latest = _latest_for_channel(versions, channel)
        if not latest or versions_equal(curr_ver, latest):
            continue
        if semver_sort_key(curr_ver) >= semver_sort_key(latest):
            continue
        upgrades.append((pkg_name, curr_ver, latest))

    if not upgrades:
        ui.status("Finished", "all installed packages are up to date")
        return

    ui.blank()
    print(ui.style("Packages to upgrade:", "bold"))
    for name, old_v, new_v in upgrades:
        print(
            f"  • {ui.style(name, 'package')} {format_version(old_v)} -> "
            f"{ui.style(format_version(new_v), 'version')}"
        )

    if not ui.confirm("\nProceed with upgrade?", default=False):
        ui.status("Cancelled", "upgrade aborted")
        return

    for pkg_name, old_v, new_v in upgrades:
        ui.status(
            "Updating",
            f"{pkg_name} {format_version(old_v)} -> {format_version(new_v)}",
        )
        install_package(pkg_name, new_v)
    ui.status("Finished", f"updated {len(upgrades)} package(s)")


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
    pkg_name = ns.package
    manifest = get_pkg_manifest(pkg_name)
    if not manifest:
        ui.die(
            f"Package '{pkg_name}' not found in registry. "
            "Submit it using: ship publish <owner/repo>"
        )

    repo_url = manifest.get("repository", "")
    match = re.search(r"github\.com/([^/]+/[^/]+)", repo_url)
    if not match:
        ui.die(f"Could not determine upstream GitHub repository for '{pkg_name}'.")

    upstream_repo = clean_repo_slug(match.group(1))
    ui.status("Checking", f"upstream GitHub releases for {upstream_repo}...")

    registry_versions = manifest.get("versions", {})
    api_url = f"https://api.github.com/repos/{upstream_repo}/releases?per_page=30"
    req = urllib.request.Request(api_url, headers={"User-Agent": f"ship/{__version__}"})
    try:
        with urllib.request.urlopen(req) as resp:
            releases = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        ui.die(f"Failed to query upstream releases for {upstream_repo}: {exc}")

    if not isinstance(releases, list) or not releases:
        ui.die(f"No release tags found upstream for {upstream_repo}.")

    upstream_by_channel = _latest_upstream_by_channel(releases)
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
        if registry_ver and semver_sort_key(registry_ver) >= semver_sort_key(upstream_tag):
            continue
        actionable.append((channel, registry_ver or "—", upstream_tag))
    ui.blank()

    if not actionable:
        ui.status(
            "Up-to-date",
            f"{pkg_name} registry channels match upstream "
            f"(stable/prerelease/nightly as available)",
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
                Namespace(values={"repo": upstream_repo, "tag": _publish_tag(upstream_tag)})
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


def _latest_upstream_by_channel(releases: list[dict]) -> dict[str, str]:
    """Pick the newest GitHub release tag per channel (stable/prerelease/nightly)."""
    best: dict[str, str] = {}
    for release in releases:
        if release.get("draft"):
            continue
        tag = str(release.get("tag_name") or "").strip()
        if not tag:
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
        not registry_ver or semver_sort_key(upstream_tag) > semver_sort_key(registry_ver)
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
    repo_probe = self_path.parents[3] if len(self_path.parents) >= 4 else self_path.parent
    res = subprocess.run(
        ["git", "-C", str(repo_probe), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if res.returncode == 0:
        git_root = Path(res.stdout.strip())
        if (git_root / ".git").is_dir() and (git_root / "ship" / "__init__.py").is_file():
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
