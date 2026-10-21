# .github/scripts/resolve_release.py
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request

args = sys.argv[1:]
dry_run = "--dry-run" in args or "-d" in args
if dry_run:
    args = [a for a in args if a not in ("--dry-run", "-d")]

repo = args[0] if len(args) > 0 else os.environ.get("TARGET_REPO")
tag = args[1] if len(args) > 1 else os.environ.get("TARGET_TAG", "latest")
token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

if not repo:
    print("Error: TARGET_REPO is not set and no repo argument provided.")
    print("Usage: python3 resolve_release.py <owner/repo> [tag] [--dry-run]")
    sys.exit(1)

# Smart generic repository naming resolution
owner = repo.split("/")[0].lower()
raw_repo_name = repo.split("/")[-1].lower()
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
pkg_name = owner if raw_repo_name in GENERIC_NAMES else raw_repo_name

headers = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "ship-registry-indexer",
}
if token:
    headers["Authorization"] = f"Bearer {token}"


def fetch_json(url):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


release = None
is_explicit_tag = bool(tag and tag not in ("latest", "stable"))

if is_explicit_tag:
    clean_t = tag.lstrip("v")
    candidate_urls = [
        f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
        f"https://api.github.com/repos/{repo}/releases/tags/v{clean_t}",
        f"https://api.github.com/repos/{repo}/releases/tags/{clean_t}",
        f"https://api.github.com/repos/{repo}/releases/tags/{pkg_name}-{clean_t}",
        f"https://api.github.com/repos/{repo}/releases/tags/{pkg_name}-v{clean_t}",
    ]
    for url in candidate_urls:
        try:
            print(f"Checking {url}...")
            cand = fetch_json(url)
            if cand and "assets" in cand:
                release = cand
                break
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            OSError,
        ) as e:
            print(f"Skipping candidate {url}: {e}")
            continue

if not release and not is_explicit_tag:
    try:
        print(f"Querying official latest release for {repo}...")
        latest_cand = fetch_json(f"https://api.github.com/repos/{repo}/releases/latest")
        if latest_cand and "assets" in latest_cand:
            release = latest_cand
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        print(
            f"Notice: /releases/latest not available ({e}), falling back to releases list..."
        )

if not release:
    try:
        print(f"Querying releases list for {repo}...")
        releases_list = fetch_json(f"https://api.github.com/repos/{repo}/releases")
        if isinstance(releases_list, list) and releases_list:
            if is_explicit_tag:
                clean_target = tag.lower().lstrip("v")
                for r in releases_list:
                    r_tag = str(r.get("tag_name", "")).lower().lstrip("v")
                    if r_tag == clean_target or r_tag == f"{pkg_name}-{clean_target}":
                        release = r
                        break
            else:
                stables = [
                    r
                    for r in releases_list
                    if not r.get("prerelease", False)
                    and "nightly" not in str(r.get("tag_name", "")).lower()
                ]
                prereleases = [
                    r
                    for r in releases_list
                    if r.get("prerelease", False)
                    and "nightly" not in str(r.get("tag_name", "")).lower()
                ]

                if stables:
                    release = stables[0]
                elif prereleases:
                    release = prereleases[0]
                else:
                    release = releases_list[0]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        print(f"Warning: Failed to fetch releases list: {e}")

if not release:
    print(f"Error: Could not find any valid release for {repo} (tag: {tag})")
    if not dry_run:
        gh_out = os.environ.get("GITHUB_OUTPUT")
        if gh_out:
            with open(gh_out, "a") as f:
                f.write("updated=false\n")
    sys.exit(1)

repo_url = f"https://api.github.com/repos/{repo}"
repo_data = {}
try:
    repo_req = urllib.request.Request(repo_url, headers=headers)
    with urllib.request.urlopen(repo_req) as r_resp:
        repo_data = json.loads(r_resp.read().decode())
except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
    print(f"Warning: Could not fetch repo metadata: {e}")

raw_tag = str(release.get("tag_name", ""))
version = raw_tag

for prefix in (f"{pkg_name}-", f"{pkg_name}_", f"{pkg_name}v"):
    if version.lower().startswith(prefix):
        version = version[len(prefix) :]
        break

version = version.lstrip("v")
assets = release.get("assets", [])

is_prerelease = release.get("prerelease", False)
tag_lower = raw_tag.lower()
if "nightly" in tag_lower:
    channel = "nightly"
elif is_prerelease or any(
    pre in tag_lower for pre in ("-alpha", "-beta", "-rc", "-dev", "-preview", "-pre")
):
    channel = "prerelease"
else:
    channel = "stable"

print(
    f"Processing {repo} @ version {version} [{channel}] ({len(assets)} total assets found)"
)

pkgs_dir = "pkgs"
os.makedirs(pkgs_dir, exist_ok=True)
pkg_file = os.path.join(pkgs_dir, f"{pkg_name}.json")

existing_pkg_data = {}
if os.path.exists(pkg_file):
    with open(pkg_file, "r", encoding="utf-8") as f:
        existing_pkg_data = json.load(f)

if not dry_run and version in existing_pkg_data.get("versions", {}):
    print(f"Package {pkg_name}@{version} already exists in {pkg_file}. Skipping PR.")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write("updated=false\n")
    sys.exit(0)

checksum_map = {}
checksum_asset_names = set()
signature_asset_names = set()

SIG_EXTENSIONS = (".sig", ".asc", ".minisig", ".pem", ".cert", ".crt", ".sbom")
ARCHIVE_EXTENSIONS = (
    ".tar.gz",
    ".tgz",
    ".tar.xz",
    ".txz",
    ".tar.bz2",
    ".tbz2",
    ".tar.zst",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
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

for asset in assets:
    name = asset.get("name", "").lower()
    if any(
        name.endswith(ext)
        for ext in [".sha256", ".sha256sum", ".sha512", ".md5", "hashes.txt"]
    ) or any(k in name for k in ["sha256", "checksum", "hashes"]):
        checksum_asset_names.add(asset["name"])
        try:
            c_req = urllib.request.Request(
                asset["browser_download_url"],
                headers={"User-Agent": "ship-registry-indexer"},
            )
            with urllib.request.urlopen(c_req) as c_resp:
                content = c_resp.read().decode("utf-8", errors="ignore")
                for line in content.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        h = parts[0] if len(parts[0]) == 64 else parts[1]
                        fn = parts[1] if len(parts[0]) == 64 else parts[0]
                        if len(h) == 64 and all(
                            c in "0123456789abcdefABCDEF" for c in h
                        ):
                            checksum_map[os.path.basename(fn)] = h.lower()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"Warning: Failed to parse checksum file {asset['name']}: {e}")
    elif any(name.endswith(ext) for ext in SIG_EXTENSIONS):
        signature_asset_names.add(asset["name"])


def parse_asset_target(filename):
    fn = filename.lower()

    if any(fn.endswith(ext) for ext in SIG_EXTENSIONS):
        return None
    if any(fn.endswith(ext) for ext in SKIP_EXTENSIONS):
        return None
    if any(k in fn for k in BUILD_ARTIFACT_PATTERNS):
        return None
    if any(k in fn for k in ["doc.zip", "docs.zip", "-doc.", "-docs."]):
        return None

    clean_name = fn
    is_archive = False
    for ext in ARCHIVE_EXTENSIONS:
        if clean_name.endswith(ext):
            clean_name = clean_name[: -len(ext)]
            is_archive = True
            break

    clean_name = clean_name.removesuffix(".exe")

    # 1. Detect Operating System
    if any(k in clean_name for k in ["linux", "glibc", "manylinux", "musl", "alpine"]):
        os_name = "linux"
    elif any(
        k in clean_name for k in ["apple", "darwin", "macos", "osx", "mac-", "-mac"]
    ):
        os_name = "darwin"
    elif (
        any(
            k in clean_name
            for k in [
                "windows",
                "pc-windows",
                "win64",
                "win32",
                "-win-",
                "-win.",
                "_win_",
                "_win.",
            ]
        )
        or clean_name.endswith(("-win", "_win", "windows"))
        or fn.endswith(".exe")
    ):
        os_name = "windows"
    elif "openbsd" in clean_name:
        os_name = "openbsd"
    elif "freebsd" in clean_name:
        os_name = "freebsd"
    elif "netbsd" in clean_name:
        os_name = "netbsd"
    elif "android" in clean_name or "termux" in clean_name:
        os_name = "android"
    else:
        return None

    # 2. Detect Architecture
    if any(k in clean_name for k in ["x86_64", "amd64", "x64"]):
        arch = "x86_64"
    elif any(k in clean_name for k in ["aarch64", "arm64", "mac-arm", "-mac-arm"]):
        arch = "aarch64"
    elif any(
        k in clean_name
        for k in ["armv7", "armhf", "arm32", "arm-unknown", "linux-arm", "-linux-arm"]
    ):
        arch = "armv7"
    elif any(k in clean_name for k in ["armv6", "armel"]):
        arch = "armv6"
    elif "riscv64" in clean_name:
        arch = "riscv64"
    elif "ppc64le" in clean_name:
        arch = "powerpc64le"
    elif "s390x" in clean_name:
        arch = "s390x"
    elif any(
        k in clean_name for k in ["i686", "i386", "386", "-x86-", "-x86.", "-x86"]
    ):
        arch = "i686"
    else:
        # Platform-specific release assets without an architecture token
        # conventionally target x86_64. Reject explicitly universal/source
        # artifacts above rather than assigning them a machine architecture.
        if any(k in clean_name for k in ("universal", "source", "src", "-all", "_all")):
            return None
        arch = "x86_64"

    # 3. Detect ABI / Libc
    if "musl" in clean_name or "alpine" in clean_name:
        abi = "musl"
    elif "msvc" in clean_name:
        abi = "msvc"
    elif "gnu" in clean_name or "glibc" in clean_name:
        abi = "gnu"
    else:
        abi = "gnu"

    # 4. Formulate Triple Key
    if os_name == "linux":
        target_triple = f"{arch}-linux-{abi}"
    elif os_name == "darwin":
        target_triple = f"{arch}-apple-darwin"
    elif os_name == "windows":
        target_triple = f"{arch}-pc-windows-{abi if abi in ('msvc', 'gnu') else 'msvc'}"
    elif os_name == "openbsd":
        target_triple = f"{arch}-openbsd"
    elif os_name == "freebsd":
        target_triple = f"{arch}-freebsd"
    elif os_name == "netbsd":
        target_triple = f"{arch}-netbsd"
    elif os_name == "android":
        target_triple = f"{arch}-android"
    else:
        return None

    return target_triple, is_archive


targets_found = {}
target_candidates = {}
asset_match_results = {}

for a in assets:
    asset_name = a.get("name", "")
    if asset_name in checksum_asset_names:
        asset_match_results[asset_name] = "CHECKSUM"
        continue
    if asset_name in signature_asset_names or any(
        asset_name.lower().endswith(ext) for ext in SIG_EXTENSIONS
    ):
        asset_match_results[asset_name] = "SIGNATURE"
        continue

    parsed = parse_asset_target(asset_name)
    if parsed:
        target_key, is_archive = parsed
        asset_match_results[asset_name] = target_key
        target_candidates.setdefault(target_key, []).append((a, is_archive))
    else:
        if any(asset_name.lower().endswith(ext) for ext in SKIP_EXTENSIONS) or any(
            k in asset_name.lower() for k in BUILD_ARTIFACT_PATTERNS
        ):
            asset_match_results[asset_name] = "LANGUAGE/INSTALLER"
        else:
            asset_match_results[asset_name] = "IGNORED"

# Prefer ZIP when a project publishes both ZIP and zstd tarballs. ZIP has
# built-in extraction support on every Python installation Ship supports;
# zstd remains available for projects that publish no portable alternative.
for target_key, candidates in target_candidates.items():

    def candidate_priority(candidate):
        asset, _is_archive = candidate
        name = asset.get("name", "").lower()
        if name.endswith(".zip"):
            format_priority = 0
        elif name.endswith(".tar.zst"):
            format_priority = 1
        else:
            format_priority = 2
        return (format_priority, asset.get("name", "").lower())

    asset, is_archive = min(candidates, key=candidate_priority)
    asset_name = asset.get("name", "")
    url = asset.get("browser_download_url")
    digest = str(asset.get("digest") or "")
    sha = checksum_map.get(asset_name, "")
    if not sha and digest.lower().startswith("sha256:"):
        sha = digest.split(":", 1)[1].lower()

    if not sha:
        if dry_run:
            sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 (mock-dryrun-sha)"
        else:
            print(f"Calculating SHA-256 for selected asset {asset_name}...")
            hasher = hashlib.sha256()
            d_req = urllib.request.Request(
                url, headers={"User-Agent": "ship-registry-indexer"}
            )
            with urllib.request.urlopen(d_req) as resp:
                while chunk := resp.read(65536):
                    hasher.update(chunk)
            sha = hasher.hexdigest()

    if is_archive:
        bin_filename = f"{pkg_name}.exe" if "windows" in target_key else pkg_name
        binaries = {pkg_name: f"bin/{bin_filename}"}
    else:
        binaries = {pkg_name: asset_name}

    target_data = {
        "url": url,
        "sha256": sha,
        "binaries": binaries,
    }
    download_size = asset.get("size")
    if isinstance(download_size, int) and download_size >= 0:
        target_data["download_size_bytes"] = download_size
    targets_found[target_key] = target_data

if dry_run:
    print("\n================ ASSET INSPECTION REPORT ================")
    print(f"Total Assets in Release: {len(assets)}")
    print("-" * 55)
    for a in assets:
        fname = a.get("name")
        res = asset_match_results.get(fname, "IGNORED")
        if res == "CHECKSUM":
            status_text = "🔒 CHECKSUM FILE"
        elif res == "SIGNATURE":
            status_text = "🔏 SIGNATURE FILE"
        elif res == "LANGUAGE/INSTALLER":
            status_text = "📦 SKIPPED BINDING/INSTALLER"
        elif res == "IGNORED":
            status_text = "⚠️ UNMATCHED / IGNORED"
        else:
            status_text = f"✅ MATCHED ({res})"
        print(f"[{status_text}] {fname}")
    print("=========================================================\n")

if not targets_found:
    print("Could not match any supported targets. No package generated.")
    if not dry_run:
        gh_out = os.environ.get("GITHUB_OUTPUT")
        if gh_out:
            with open(gh_out, "a") as f:
                f.write("updated=false\n")
    sys.exit(0)

description = (
    repo_data.get("description")
    or (release.get("body", "").splitlines()[0][:120] if release.get("body") else None)
    or f"Pre-built binaries for {repo}"
)
homepage = repo_data.get("homepage") or ""
author = repo_data.get("owner", {}).get("login") or repo.split("/")[0]
repo_link = repo_data.get("html_url") or f"https://github.com/{repo}"
license_info = (repo_data.get("license") or {}).get("spdx_id") or ""
release_url = (
    release.get("html_url") or f"https://github.com/{repo}/releases/tag/{raw_tag}"
)

version_entry = {
    "channel": channel,
    "targets": targets_found,
}

if not existing_pkg_data:
    pkg_entry = {
        "description": description,
        "author": author,
        "repository": repo_link,
        "versions": {
            version: version_entry,
        },
    }
    if homepage:
        pkg_entry["homepage"] = homepage
    if license_info and license_info != "NOASSERTION":
        pkg_entry["license"] = license_info
else:
    pkg_entry = existing_pkg_data
    pkg_entry.setdefault("description", description)
    pkg_entry.setdefault("author", author)
    pkg_entry.setdefault("repository", repo_link)
    if homepage and "homepage" not in pkg_entry:
        pkg_entry["homepage"] = homepage
    if license_info and license_info != "NOASSERTION" and "license" not in pkg_entry:
        pkg_entry["license"] = license_info
    pkg_entry.setdefault("versions", {})[version] = version_entry

if dry_run:
    print(f"================ DRY-RUN PKGS/{pkg_name}.json ================")
    print(json.dumps(pkg_entry, indent=2))
    print("==============================================================")
    sys.exit(0)

with open(pkg_file, "w", encoding="utf-8") as f:
    json.dump(pkg_entry, f, indent=2)
    f.write("\n")
print(f"Wrote updated package definition to {pkg_file}")

target_count = len(targets_found)
requester_login = os.environ.get("REQUESTER_LOGIN", "")
requester_id = os.environ.get("REQUESTER_ID", "")
upstream_permission = os.environ.get("UPSTREAM_PERMISSION", "unknown")
if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", requester_login):
    requester_login = ""
if not re.fullmatch(r"[0-9]{1,20}", requester_id):
    requester_id = ""
if upstream_permission not in {"admin", "maintain", "write", "read", "none", "unknown"}:
    upstream_permission = "unknown"
trusted_contributor = bool(
    requester_login and requester_id and upstream_permission in {"admin", "maintain", "write"}
)
publisher_marker = (
    f"<!-- ship-publisher-v1 login={requester_login} id={requester_id} permission={upstream_permission} -->"
    if requester_login and requester_id
    else ""
)
targets_table = "| Target | Binary Path | Download Size | SHA-256 |\n| :--- | :--- | ---: | :--- |\n"
for t_key, t_data in targets_found.items():
    bin_path = next(iter(t_data["binaries"].values()))
    sha = t_data["sha256"]
    sha_short = sha[:12] + "..." if len(sha) > 12 else sha
    size_bytes = t_data.get("download_size_bytes")
    size_text = f"{size_bytes} bytes" if isinstance(size_bytes, int) else "unknown"
    targets_table += f"| `{t_key}` | `{bin_path}` | {size_text} | `{sha_short}` |\n"

gh_out = os.environ.get("GITHUB_OUTPUT")
if gh_out:
    with open(gh_out, "a") as f:
        f.write("updated=true\n")
        f.write(f"pkg={pkg_name}\n")
        f.write(f"version={version}\n")
        f.write(f"channel={channel}\n")
        f.write(f"repo={repo}\n")
        f.write(f"repo_link={repo_link}\n")
        f.write(f"release_url={release_url}\n")
        f.write(f"author={author}\n")
        f.write(f"license={license_info or 'Unknown'}\n")
        f.write(f"target_count={target_count}\n")
        f.write(f"pkg_file={pkg_file}\n")
        f.write(f"requester_login={requester_login}\n")
        f.write(f"requester_id={requester_id}\n")
        f.write(f"upstream_permission={upstream_permission}\n")
        f.write(f"trusted_contributor={'true' if trusted_contributor else 'false'}\n")
        f.write(f"publisher_marker={publisher_marker}\n")
        f.write("description<<EOF\n")
        f.write(description + "\n")
        f.write("EOF\n")
        f.write("targets_table<<EOF\n")
        f.write(targets_table + "\n")
        f.write("EOF\n")

print(f"Successfully generated metadata for {pkg_name}@{version} [{channel}]")
