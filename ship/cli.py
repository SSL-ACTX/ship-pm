"""Command line interface handling and subcommand routing."""

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from ship import __version__
from ship.admin import (
    accept_package_submission,
    list_package_submissions,
    reject_package_submission,
    review_package_submission,
)
from ship.config import (
    SHIP_BACKUP_DIR,
    SHIP_BRIDGE_URL,
    SHIP_CACHE_DIR,
    SHIP_REGISTRY_REPO,
    SHIP_UPDATE_URL,
    get_pkgs_dir,
    init_dirs,
    load_state,
)
from ship.github import install_from_github
from ship.github_auth import GitHubCLIError, get_github_identity, get_github_token
from ship.platform import detect_target_keys
from ship.registry import (
    ensure_registry,
    fetch_file,
    get_pkg_manifest,
    sync_registry,
)
from ship.store import (
    install_package,
    remove_package,
    repatch_package,
    rollback_binary,
    rollback_package,
)
from ship.ui import c, die, pad_visible, status, warn
from ship.version import (
    classify_channel,
    format_version,
    select_default_version,
    semver_sort_key,
)

PUBLISH_TIMEOUT_SECONDS = 30


def clean_repo_slug(raw_input: str) -> str:
    cleaned = re.sub(r"^https?://github\.com/", "", raw_input).strip()
    cleaned = cleaned.rstrip("/")
    cleaned = cleaned.removesuffix(".git")
    return cleaned.rstrip("/")


def format_size(size_bytes: int | None) -> str:
    """Format a byte count with readable binary units."""
    if size_bytes is None:
        return "unknown"
    try:
        size = float(size_bytes)
    except (TypeError, ValueError):
        return "unknown"
    if size < 0:
        return "unknown"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return "unknown"


def format_license(license_id: str) -> str:
    """Turn selected short SPDX identifiers into clearer display names."""
    value = license_id.strip()
    if value.casefold() == "zlib":
        return "Zlib License"
    return value


def installed_size_bytes(install_dir: Path) -> int | None:
    """Sum regular file sizes in an installed package without following links."""
    if not install_dir.is_dir():
        return None
    total = 0
    for root, _, files in os.walk(install_dir, followlinks=False):
        for filename in files:
            path = Path(root) / filename
            try:
                if not path.is_symlink():
                    total += path.stat().st_size
            except OSError:
                continue
    return total


def cmd_list() -> None:
    state = load_state()
    installed = state.get("installed", {})
    if not installed:
        print(f"\n{c('info:', '1;36')} No packages installed.\n")
        return

    print(f"\n{c('Installed Packages:', '1;4')}\n")
    h_pkg = pad_visible(c("PACKAGE", "1"), 16)
    h_ver = pad_visible(c("VERSION", "1"), 16)
    h_tgt = pad_visible(c("TARGET", "1"), 24)
    h_dat = pad_visible(c("INSTALLED", "1"), 12)
    print(f"  {h_pkg} {h_ver} {h_tgt} {h_dat}")

    sep_pkg = pad_visible(c("─" * 14, "2"), 16)
    sep_ver = pad_visible(c("─" * 14, "2"), 16)
    sep_tgt = pad_visible(c("─" * 22, "2"), 24)
    sep_dat = pad_visible(c("─" * 10, "2"), 12)
    print(f"  {sep_pkg} {sep_ver} {sep_tgt} {sep_dat}")

    for name, data in sorted(installed.items()):
        ver = format_version(data.get("version"))
        channel = data.get("channel") or classify_channel(data.get("version", ""))
        ver_color = (
            "1;32"
            if channel == "stable"
            else ("1;33" if channel == "prerelease" else "1;35")
        )

        tgt = data.get("target_key", "universal")
        inst_at = data.get("installed_at", "")[:10]

        col_pkg = pad_visible(c(name, "1"), 16)
        col_ver = pad_visible(c(ver, ver_color), 16)
        col_tgt = pad_visible(c(tgt, "2"), 24)
        col_dat = pad_visible(inst_at, 12)
        print(f"  {col_pkg} {col_ver} {col_tgt} {col_dat}")

    print(f"\n{c('Finished', '1;32')} {len(installed)} package(s) tracked in store.\n")


def cmd_update(target: str = "") -> None:
    if target in ("self", "ship"):
        cmd_self_update()
        return

    if target in ("registry", "index"):
        sync_registry()
        return

    sync_registry()
    state = load_state()
    installed = state.get("installed", {})

    if target:
        if target not in installed:
            manifest = get_pkg_manifest(target)
            if not manifest:
                warn(f"Package '{target}' is not in the registry.")
                cmd_check_upstream(target)
                return
            install_package(target)
            return

        curr_ver = installed[target].get("version", "")
        curr_channel = installed[target].get("channel", classify_channel(curr_ver))

        manifest = get_pkg_manifest(target)
        if not manifest:
            die(f"Manifest for '{target}' not found in registry.")

        versions = manifest.get("versions", {})
        if curr_channel == "nightly":
            nightlies = [v for v in versions if classify_channel(v) == "nightly"]
            latest_ver = (
                nightlies[-1] if nightlies else select_default_version(versions)
            )
        else:
            latest_ver = select_default_version(versions)

        if curr_ver == latest_ver:
            status(
                "Finished",
                f"{target} is already up to date ({format_version(curr_ver)})",
            )
        else:
            status(
                "Updating",
                f"{target} {format_version(curr_ver)} -> {format_version(latest_ver)}",
            )
            install_package(target, latest_ver)
        return

    if not installed:
        status("Finished", "registry updated (no packages installed)")
        return

    updated_count = 0
    for pkg_name, data in installed.items():
        curr_ver = data.get("version", "")
        manifest = get_pkg_manifest(pkg_name)
        if not manifest:
            continue

        versions = manifest.get("versions", {})
        latest_ver = select_default_version(versions)

        if curr_ver != latest_ver:
            status(
                "Updating",
                f"{pkg_name} {format_version(curr_ver)} -> {format_version(latest_ver)}",
            )
            install_package(pkg_name, latest_ver)
            updated_count += 1

    if updated_count == 0:
        status("Finished", "all installed packages are up to date")
    else:
        status("Finished", f"updated {updated_count} package(s)")


def cmd_check_upstream(pkg_name: str) -> None:
    manifest = get_pkg_manifest(pkg_name)
    if not manifest:
        die(
            f"Package '{pkg_name}' not found in registry. Submit it using: ship publish <owner/repo>"
        )

    repo_url = manifest.get("repository", "")
    match = re.search(r"github\.com/([^/]+/[^/]+)", repo_url)
    if not match:
        die(f"Could not determine upstream GitHub repository for '{pkg_name}'.")

    upstream_repo = clean_repo_slug(match.group(1))
    status("Checking", f"upstream GitHub releases for {upstream_repo}...")

    versions = list(manifest.get("versions", {}).keys())
    reg_ver = select_default_version(versions) or "none"

    api_url = f"https://api.github.com/repos/{upstream_repo}/releases"
    req = urllib.request.Request(api_url, headers={"User-Agent": "ship-pm"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            latest_tag = data[0].get("tag_name", "").lstrip("v") if data else ""
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        die(f"Failed to query upstream releases for {upstream_repo}: {e}")

    if not latest_tag:
        die(f"No release tags found upstream for {upstream_repo}.")

    if latest_tag != reg_ver:
        warn(
            f"Upstream release ({format_version(latest_tag)}) is newer than registry version ({format_version(reg_ver)})!"
        )
        try:
            choice = (
                input("Propose this update to central registry now? [Y/n]: ")
                .strip()
                .lower()
            )
            if choice not in ("n", "no"):
                cmd_publish(upstream_repo, f"v{latest_tag}")
            else:
                status("Skipped", "update proposal cancelled")
        except (KeyboardInterrupt, EOFError):
            print()
    else:
        status(
            "Up-to-date",
            f"{pkg_name} in registry is already aligned with upstream ({format_version(latest_tag)})",
        )


def cmd_self_update() -> None:
    status("Checking", "for ship updates...")
    self_path = Path(__file__).resolve()

    res = subprocess.run(
        f"git -C '{self_path.parent}' rev-parse --show-toplevel",
        shell=True,
        check=False,
        capture_output=True,
        text=True,
    )
    if res.returncode == 0:
        git_root = Path(res.stdout.strip())
        if (git_root / ".git").is_dir():
            status("Updating", f"git repository at {git_root}...")
            pull = subprocess.run(
                f"git -C '{git_root}' pull --ff-only",
                shell=True,
                check=False,
                capture_output=True,
            )
            if pull.returncode == 0:
                status("Finished", "ship updated from local git repository")
                return

    tmp_path = SHIP_CACHE_DIR / "ship_update.tmp"
    fetch_file(SHIP_UPDATE_URL, tmp_path)

    try:
        content = tmp_path.read_text(encoding="utf-8")
        ver_match = re.search(r'VERSION\s*=\s*"([^"]+)"', content)
        remote_ver = ver_match.group(1) if ver_match else "unknown"

        if remote_ver == __version__:
            status("Finished", f"ship is already up to date (v{__version__})")
            tmp_path.unlink(missing_ok=True)
            return

        tmp_path.chmod(0o755)
        shutil.move(tmp_path, self_path)
        status("Finished", f"updated ship v{__version__} -> v{remote_ver}")
    except OSError as e:
        tmp_path.unlink(missing_ok=True)
        die(f"Self-update failed: {e}")


def cmd_search(query: str = "") -> None:
    ensure_registry()
    pkgs_dir = get_pkgs_dir()
    state = load_state()
    installed = state.get("installed", {})

    q = query.lower().strip()
    matched = 0

    print()
    for f in sorted(pkgs_dir.glob("*.json")):
        name = f.stem
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        desc = data.get("description", "")
        versions = list(data.get("versions", {}).keys())
        latest = select_default_version(versions) or "unknown"
        channel = classify_channel(latest)

        if q and not (q in name.lower() or q in desc.lower()):
            continue

        matched += 1
        is_inst = name in installed
        inst_tag = f" {c('[installed]', '1;36')}" if is_inst else ""
        ch_tag = f" {c('[' + channel + ']', '2')}" if channel != "stable" else ""

        print(
            f"  {c(name, '1;32')} {c(format_version(latest), '1;34')}{ch_tag}{inst_tag}"
        )
        if desc:
            print(f"    {desc}")
        print()

    if matched == 0:
        if q:
            print(f"  No packages matching '{query}'.\n")
        else:
            print("  No packages available in registry.\n")


def cmd_info(pkg_name: str) -> None:
    manifest = get_pkg_manifest(pkg_name)
    if not manifest:
        die(f"Package '{pkg_name}' not found in registry.")

    state = load_state()
    inst = state.get("installed", {}).get(pkg_name)
    host_targets = detect_target_keys()

    print(f"\n{c(pkg_name, '1;32')}")
    if "description" in manifest:
        print(f"  {'Description:':<14} {manifest['description']}")
    if "author" in manifest:
        print(f"  {'Author:':<14} {manifest['author']}")
    if "repository" in manifest:
        print(f"  {'Repository:':<14} {manifest['repository']}")
    if "license" in manifest:
        print(f"  {'License:':<14} {format_license(str(manifest['license']))}")

    all_versions = sorted(manifest.get("versions", {}).keys(), key=semver_sort_key)
    stables = [v for v in all_versions if classify_channel(v) == "stable"]
    prereleases = [v for v in all_versions if classify_channel(v) == "prerelease"]
    nightlies = [v for v in all_versions if classify_channel(v) == "nightly"]

    if stables:
        shown = ", ".join(format_version(version) for version in stables)
        print(f"  {'Stable:':<14} {c(shown, '1;32')}")
    if prereleases:
        shown = ", ".join(format_version(version) for version in prereleases)
        print(f"  {'Pre-release:':<14} {c(shown, '1;33')}")
    if nightlies:
        shown = ", ".join(format_version(version) for version in nightlies)
        print(f"  {'Nightly:':<14} {c(shown, '1;35')}")

    if inst:
        inst_ch = inst.get("channel", classify_channel(inst.get("version", "")))
        print(
            f"  {'Status:':<14} {c('Installed', '1;32')} ({format_version(inst.get('version'))} [{inst_ch}] via {inst.get('target_key')})"
        )
    else:
        print(f"  {'Status:':<14} {c('Not installed', '2')}")

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
            SHIP_CACHE_DIR
            / f"{pkg_name}-{info_version}-{Path(target_data['url']).name}"
        )
        if archive.is_file():
            download_size = archive.stat().st_size
    size_suffix = f" ({info_target})" if info_target else ""
    print(f"  {'Download size:':<14} {format_size(download_size)}{size_suffix}")

    if inst:
        install_path = inst.get("install_dir")
        installed_bytes = (
            installed_size_bytes(Path(install_path)) if install_path else None
        )
        print(f"  {'Installed size:':<14} {format_size(installed_bytes)}")

    if default_ver:
        targets = manifest.get("versions", {}).get(default_ver, {}).get("targets", {})
        if targets:
            print(
                f"\n  {c(f'Targets for default ({format_version(default_ver)}):', '1')}"
            )
            for t in targets:
                marker = c(" [host match]", "1;32") if t in host_targets else ""
                print(f"    • {t}{marker}")
    print()


def cmd_publish(repo: str, tag: str = "latest") -> None:
    repo = clean_repo_slug(repo)
    if "/" not in repo:
        die("Invalid repository format. Expected 'owner/repo'.")

    try:
        identity = get_github_identity()
        token = get_github_token()
    except GitHubCLIError as exc:
        die(str(exc))

    status(
        "Publishing",
        f"{repo} (tag: {tag}) as @{identity.login} to central registry bridge...",
    )
    payload = json.dumps({"repo": repo, "tag": tag}).encode("utf-8")
    req = urllib.request.Request(
        SHIP_BRIDGE_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"ship/{__version__}",
            "Authorization": f"Bearer {token}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=PUBLISH_TIMEOUT_SECONDS) as resp:
            status(
                "Finished",
                f"publish request accepted for @{identity.login} (HTTP {resp.status})",
            )
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8", errors="replace")).get(
                "error", ""
            )
        except (json.JSONDecodeError, AttributeError):
            detail = ""
        suffix = f": {detail}" if detail else ""
        die(f"Registry bridge rejected the publish request (HTTP {e.code}){suffix}")
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            die(
                f"Publish request timed out after {PUBLISH_TIMEOUT_SECONDS} seconds. "
                "The request may already be queued; check before retrying."
            )
        die(f"Publish request failed: {e}")
    except TimeoutError:
        die(
            f"Publish request timed out after {PUBLISH_TIMEOUT_SECONDS} seconds. "
            "The request may already be queued; check before retrying."
        )
    except OSError as e:
        die(f"Publish request failed: {e}")


def cmd_auth(args: list[str]) -> None:
    action = args[0] if args else "status"
    if action == "login" and len(args) == 1:
        if not shutil.which("gh"):
            die(
                "GitHub CLI (`gh`) is required. Install it before running `ship auth login`."
            )
        try:
            result = subprocess.run(["gh", "auth", "login"], check=False)
        except OSError as exc:
            die(f"Could not start GitHub CLI: {exc}")
        if result.returncode:
            die("GitHub login did not complete.")
        action = "status"
    if action != "status" or len(args) > 1:
        die("Usage: ship auth [status|login]")
    try:
        identity = get_github_identity()
    except GitHubCLIError as exc:
        die(str(exc))
    status("GitHub", f"authenticated as @{identity.login} (user ID {identity.user_id})")


def cmd_admin(args: list[str]) -> None:
    if not args:
        die(
            "Usage: ship admin prs | ship admin review <PR> | "
            "ship admin accept <PR> [--yes] | "
            "ship admin reject <PR> [--reason TEXT] [--yes]"
        )
    try:
        if args == ["prs"]:
            list_package_submissions(SHIP_REGISTRY_REPO)
            return
        if len(args) == 2 and args[0] == "review":
            try:
                number = int(args[1])
            except ValueError:
                die("Pull request number must be a positive integer.")
            if number <= 0:
                die("Pull request number must be a positive integer.")
            review_package_submission(SHIP_REGISTRY_REPO, number)
            return
        if args[0] == "accept" and len(args) in (2, 3):
            try:
                number = int(args[1])
            except ValueError:
                die("Pull request number must be a positive integer.")
            if number <= 0 or (len(args) == 3 and args[2] != "--yes"):
                die("Usage: ship admin accept <PR> [--yes]")
            accept_package_submission(
                SHIP_REGISTRY_REPO,
                number,
                assume_yes=len(args) == 3,
            )
            return
        if args[0] == "reject" and len(args) >= 2:
            try:
                number = int(args[1])
            except ValueError:
                die("Pull request number must be a positive integer.")
            if number <= 0:
                die("Pull request number must be a positive integer.")
            reason = "Rejected by registry maintainer."
            reason_provided = False
            assume_yes = False
            idx = 2
            while idx < len(args):
                if args[idx] == "--yes" and not assume_yes:
                    assume_yes = True
                    idx += 1
                elif (
                    args[idx] == "--reason"
                    and idx + 1 < len(args)
                    and not reason_provided
                ):
                    reason = args[idx + 1].strip()
                    if not reason:
                        die("Rejection reason cannot be empty.")
                    reason_provided = True
                    idx += 2
                else:
                    die("Usage: ship admin reject <PR> [--reason TEXT] [--yes]")
            reject_package_submission(
                SHIP_REGISTRY_REPO,
                number,
                reason=reason,
                assume_yes=assume_yes,
            )
            return
    except GitHubCLIError as exc:
        die(str(exc))
    die(
        "Usage: ship admin prs | ship admin review <PR> | "
        "ship admin accept <PR> [--yes] | "
        "ship admin reject <PR> [--reason TEXT] [--yes]"
    )


def cmd_rollback(args: list[str]) -> None:
    if args and args[0] == "--binary":
        if len(args) not in (2, 3) or (len(args) == 3 and args[2] != "--yes"):
            die("Usage: ship rollback --binary <command> [--yes]")
        rollback_binary(args[1], assume_yes=len(args) == 3)
        return
    if len(args) not in (1, 2) or (len(args) == 2 and args[1] != "--yes"):
        die(
            "Usage: ship rollback <package> [--yes] | "
            "ship rollback --binary <command> [--yes]"
        )
    rollback_package(args[0], assume_yes=len(args) == 2)


def cmd_clean() -> None:
    init_dirs()
    status("Cleaning", f"cache files in {SHIP_CACHE_DIR}...")
    for item in SHIP_CACHE_DIR.glob("*"):
        if item.is_file():
            item.unlink(missing_ok=True)
    status("Cleaning", f"backups in {SHIP_BACKUP_DIR}...")
    shutil.rmtree(SHIP_BACKUP_DIR, ignore_errors=True)
    SHIP_BACKUP_DIR.mkdir(exist_ok=True)
    status("Finished", "cache and backups cleaned")


def print_custom_help() -> None:
    print(f"""{c("ship", "1;32")} {__version__}
Agnostic shell package orchestrator for pre-built binaries.

{c("USAGE:", "1")}
    {c("ship", "1;32")} [OPTIONS] <COMMAND>

{c("COMMANDS:", "1")}
    {c("install, i", "1;32")}         Install from registry or GitHub repository
    {c("remove, rm", "1;32")}         Uninstall a package and remove binary symlinks
    {c("rollback", "1;32")}           Restore a package's previous version or a saved command
    {c("repatch", "1;32")}            Reapply patches to an installed package without downloading
    {c("update, u", "1;32")}          Update packages or registry index
    {c("check-upstream", "1;32")}     Check if upstream releases are newer than registry
    {c("search", "1;32")}             Search registry for packages
    {c("info", "1;32")}               Display details and targets for a package
    {c("list, ls", "1;32")}           List installed packages in store
    {c("publish", "1;32")}            Submit a release to the central registry
    {c("auth", "1;32")}               Log in to GitHub or show the authenticated account
{c("admin", "1;32")}              Review, accept, or reject package submissions (admins only)
    {c("self-update", "1;32")}        Upgrade ship to the latest version
    {c("clean", "1;32")}              Purge download caches and backups

{c("OPTIONS:", "1")}
    {c("-t, --target", "1;32")} <TRIPLE>       Override target platform architecture
    {c("--select-target", "1;32")}             Interactively choose target platform
    {c("-V, --version", "1;32")}               Print version info and exit
    {c("-h, --help", "1;32")}                  Print help information

Run '{c("ship <COMMAND> --help", "1")}' for more information on a specific command.
""")


def main() -> None:
    raw_args = sys.argv[1:]

    if not raw_args or any(a in ("-h", "--help", "help") for a in raw_args):
        print_custom_help()
        sys.exit(0)

    if any(a in ("-V", "--version") for a in raw_args):
        print(f"ship {__version__}")
        sys.exit(0)

    interactive_target = False
    target_override = None
    asset_filter = None
    filtered_args = []

    idx = 0
    while idx < len(raw_args):
        arg = raw_args[idx]
        if arg in ("--select-target", "--interactive-target"):
            interactive_target = True
        elif arg in ("-t", "--target"):
            idx += 1
            if idx < len(raw_args):
                target_override = raw_args[idx]
        elif arg.startswith("--target="):
            target_override = arg.split("=", 1)[1]
        elif arg in ("--asset",):
            idx += 1
            if idx < len(raw_args):
                asset_filter = raw_args[idx]
        elif arg.startswith("--asset="):
            asset_filter = arg.split("=", 1)[1]
        else:
            filtered_args.append(arg)
        idx += 1

    if not filtered_args:
        print_custom_help()
        sys.exit(0)

    cmd = filtered_args[0]
    sub_args = filtered_args[1:]

    if cmd in ("install", "i"):
        if not sub_args:
            die(
                "Usage: ship install <package> [version] OR ship install <owner/repo> [tag]"
            )
        pkg_spec = sub_args[0]
        ver = sub_args[1] if len(sub_args) > 1 else None

        if "@" in pkg_spec and not pkg_spec.startswith("git@"):
            pkg_name, explicit_ver = pkg_spec.split("@", 1)
            pkg = pkg_name
            ver = explicit_ver
        else:
            pkg = pkg_spec

        if "/" in pkg:
            install_from_github(
                pkg,
                ver,
                target_override=target_override,
                interactive=interactive_target,
                asset_filter=asset_filter,
            )
        else:
            install_package(
                pkg,
                ver,
                target_override=target_override,
                interactive=interactive_target,
            )

    elif cmd in ("remove", "rm", "uninstall"):
        if not sub_args:
            die("Usage: ship remove <package>")
        remove_package(sub_args[0])

    elif cmd == "rollback":
        cmd_rollback(sub_args)

    elif cmd in ("repatch", "repair"):
        if not sub_args:
            die("Usage: ship repatch <package>")
        repatch_package(sub_args[0])

    elif cmd in ("update", "u"):
        tgt = sub_args[0] if sub_args else ""
        cmd_update(tgt)

    elif cmd in ("check-upstream", "outdated"):
        if not sub_args:
            die("Usage: ship check-upstream <package>")
        cmd_check_upstream(sub_args[0])

    elif cmd in ("list", "ls"):
        cmd_list()

    elif cmd == "search":
        q = sub_args[0] if sub_args else ""
        cmd_search(q)

    elif cmd == "info":
        if not sub_args:
            die("Usage: ship info <package>")
        cmd_info(sub_args[0])

    elif cmd == "publish":
        if not sub_args:
            die("Usage: ship publish <owner/repo> [tag]")
        repo = sub_args[0]
        tag = sub_args[1] if len(sub_args) > 1 else "latest"
        cmd_publish(repo, tag)

    elif cmd == "auth":
        cmd_auth(sub_args)

    elif cmd == "admin":
        cmd_admin(sub_args)

    elif cmd in ("self-update", "upgrade-self"):
        cmd_self_update()

    elif cmd == "clean":
        cmd_clean()

    else:
        die(f"Unknown command: '{cmd}'. Run 'ship --help' for usage.")
