# .github/scripts/resolve_release.py
import hashlib
import json
import os
import sys
import urllib.request

# Parse CLI arguments or environment variables
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

pkg_name = repo.split("/")[-1].lower()

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

# If a specific tag was requested
if tag and tag != "latest":
    candidate_urls = [
        f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
        f"https://api.github.com/repos/{repo}/releases/tags/v{tag}"
        if not tag.startswith("v")
        else f"https://api.github.com/repos/{repo}/releases/tags/{tag.lstrip('v')}",
    ]
    for url in candidate_urls:
        try:
            print(f"Checking {url}...")
            release = fetch_json(url)
            if release and "assets" in release:
                break
        except Exception:
            continue

# If not found yet, query /releases list to match tag or get latest release
if not release:
    try:
        print(f"Querying releases list for {repo}...")
        releases_list = fetch_json(f"https://api.github.com/repos/{repo}/releases")
        if isinstance(releases_list, list) and releases_list:
            if tag and tag != "latest":
                clean_target = tag.lstrip("v")
                for r in releases_list:
                    r_tag = r.get("tag_name", "").lstrip("v")
                    if r_tag == clean_target:
                        release = r
                        break
            if not release:
                release = releases_list[0]
    except Exception as e:
        print(f"Warning: Failed to fetch releases list: {e}")

# Fallback to /releases/latest
if not release:
    try:
        print(f"Querying /releases/latest for {repo}...")
        release = fetch_json(f"https://api.github.com/repos/{repo}/releases/latest")
    except Exception as e:
        print(f"Error: Could not find any valid release for {repo} (tag: {tag}): {e}")
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
except Exception as e:
    print(f"Warning: Could not fetch repo metadata: {e}")

raw_tag = release.get("tag_name", "")
version = raw_tag.lstrip("v")
assets = release.get("assets", [])

print(f"Processing {repo} @ version {version} ({len(assets)} total assets found)")

registry_path = "registry.json"
registry = {}
if os.path.exists(registry_path):
    with open(registry_path, "r") as f:
        registry = json.load(f)

packages = registry.setdefault("packages", {})
if (
    not dry_run
    and pkg_name in packages
    and version in packages[pkg_name].get("versions", {})
):
    print(f"Package {pkg_name}@{version} already exists in registry.json. Skipping PR.")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write("updated=false\n")
    sys.exit(0)

# Extract SHA256 checksum files
checksum_map = {}
checksum_asset_names = set()
for asset in assets:
    name = asset.get("name", "").lower()
    if any(k in name for k in ["sha256", "checksum", "hashes", "sha256sum"]):
        checksum_asset_names.add(asset["name"])
        print(f"Reading checksum file: {asset['name']}")
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
        except Exception as e:
            print(f"Warning: Failed to parse checksum file {asset['name']}: {e}")


# Robust, deterministic asset parser
def parse_asset_target(filename):
    fn = filename.lower()

    # Skip non-archive package managers and system installers
    if any(
        fn.endswith(ext)
        for ext in [".deb", ".rpm", ".apk", ".msi", ".dmg", ".pkg", ".zst"]
    ):
        return None
    if not any(
        fn.endswith(ext)
        for ext in [".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".zip"]
    ):
        return None

    # 1. Detect Operating System
    if "linux" in fn:
        os_name = "linux"
    elif any(k in fn for k in ["apple", "darwin", "macos"]):
        os_name = "darwin"
    elif any(k in fn for k in ["windows", "pc-windows", "win64", "win32"]) or (
        "-win-" in fn
    ):
        os_name = "windows"
    elif "openbsd" in fn:
        os_name = "openbsd"
    elif "freebsd" in fn:
        os_name = "freebsd"
    elif "netbsd" in fn:
        os_name = "netbsd"
    elif "android" in fn:
        os_name = "android"
    else:
        return None

    # 2. Detect Architecture
    if any(k in fn for k in ["x86_64", "amd64", "x64"]):
        arch = "x86_64"
    elif any(k in fn for k in ["aarch64", "arm64"]):
        arch = "aarch64"
    elif any(k in fn for k in ["armv7", "armhf", "arm32", "arm-unknown"]):
        arch = "armv7"
    elif any(k in fn for k in ["armv6", "armel"]):
        arch = "armv6"
    elif "riscv64" in fn:
        arch = "riscv64"
    elif any(k in fn for k in ["i686", "i386", "386"]):
        arch = "i686"
    else:
        return None

    # 3. Detect ABI / Libc
    if "musl" in fn:
        abi = "musl"
    elif "msvc" in fn:
        abi = "msvc"
    elif "gnu" in fn or "gnueabihf" in fn:
        abi = "gnu"
    else:
        abi = "gnu"

    # 4. Formulate Triple Key
    if os_name == "linux":
        return f"{arch}-linux-{abi}"
    elif os_name == "darwin":
        return f"{arch}-apple-darwin"
    elif os_name == "windows":
        return f"{arch}-pc-windows-{abi if abi in ('msvc', 'gnu') else 'msvc'}"
    elif os_name == "openbsd":
        return f"{arch}-openbsd"
    elif os_name == "freebsd":
        return f"{arch}-freebsd"
    elif os_name == "netbsd":
        return f"{arch}-netbsd"
    elif os_name == "android":
        return f"{arch}-android"
    return None


targets_found = {}
asset_match_results = {}

for a in assets:
    asset_name = a.get("name", "")
    if asset_name in checksum_asset_names:
        asset_match_results[asset_name] = "CHECKSUM"
        continue

    target_key = parse_asset_target(asset_name)
    if target_key:
        asset_match_results[asset_name] = target_key
        url = a.get("browser_download_url")
        sha = checksum_map.get(asset_name, "")

        if not sha:
            if dry_run:
                sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 (mock-dryrun-sha)"
            else:
                print(f"Calculating SHA-256 for {asset_name}...")
                hasher = hashlib.sha256()
                d_req = urllib.request.Request(
                    url, headers={"User-Agent": "ship-registry-indexer"}
                )
                with urllib.request.urlopen(d_req) as resp:
                    while chunk := resp.read(65536):
                        hasher.update(chunk)
                sha = hasher.hexdigest()

        # Target-aware binary mapping (.exe for windows, standard for unix/mac)
        bin_filename = f"{pkg_name}.exe" if "windows" in target_key else pkg_name

        if target_key not in targets_found:
            targets_found[target_key] = {
                "url": url,
                "sha256": sha,
                "binaries": {pkg_name: f"bin/{bin_filename}"},
            }
    else:
        if any(
            asset_name.lower().endswith(ext)
            for ext in [".deb", ".rpm", ".apk", ".msi", ".dmg", ".pkg", ".zst"]
        ):
            asset_match_results[asset_name] = "INSTALLER"
        else:
            asset_match_results[asset_name] = "IGNORED"

# Dry-run inspection report
if dry_run:
    print("\n================ ASSET INSPECTION REPORT ================")
    print(f"Total Assets in Release: {len(assets)}")
    print("-" * 55)
    for a in assets:
        fname = a.get("name")
        res = asset_match_results.get(fname, "IGNORED")
        if res == "CHECKSUM":
            status = "🔒 CHECKSUM FILE"
        elif res == "INSTALLER":
            status = "📦 SKIPPED INSTALLER"
        elif res == "IGNORED":
            status = "⚠️ UNMATCHED / IGNORED"
        else:
            status = f"✅ MATCHED ({res})"
        print(f"[{status}] {fname}")
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

pkg_entry = {
    "description": description,
    "author": author,
    "repository": repo_link,
    "versions": {
        version: {
            "targets": targets_found,
        }
    },
}
if homepage:
    pkg_entry["homepage"] = homepage
if license_info and license_info != "NOASSERTION":
    pkg_entry["license"] = license_info

if dry_run:
    print("================ DRY-RUN JSON RESULT ================")
    print(json.dumps({pkg_name: pkg_entry}, indent=2))
    print("=====================================================")
    sys.exit(0)

# Update registry.json
if pkg_name not in packages:
    packages[pkg_name] = pkg_entry
else:
    packages[pkg_name].setdefault("description", description)
    packages[pkg_name].setdefault("author", author)
    packages[pkg_name].setdefault("repository", repo_link)
    if homepage and "homepage" not in packages[pkg_name]:
        packages[pkg_name]["homepage"] = homepage
    if (
        license_info
        and license_info != "NOASSERTION"
        and "license" not in packages[pkg_name]
    ):
        packages[pkg_name]["license"] = license_info
    packages[pkg_name]["versions"][version] = pkg_entry["versions"][version]

with open(registry_path, "w") as f:
    json.dump(registry, f, indent=2)

# Format targets table for PR body
target_count = len(targets_found)
targets_table = "| Target | Binary Path | SHA-256 |\n| :--- | :--- | :--- |\n"
for t_key, t_data in targets_found.items():
    bin_path = list(t_data["binaries"].values())[0]
    sha = t_data["sha256"]
    sha_short = sha[:12] + "..." if len(sha) > 12 else sha
    targets_table += f"| `{t_key}` | `{bin_path}` | `{sha_short}` |\n"

gh_out = os.environ.get("GITHUB_OUTPUT")
if gh_out:
    with open(gh_out, "a") as f:
        f.write("updated=true\n")
        f.write(f"pkg={pkg_name}\n")
        f.write(f"version={version}\n")
        f.write(f"repo={repo}\n")
        f.write(f"repo_link={repo_link}\n")
        f.write(f"release_url={release_url}\n")
        f.write(f"author={author}\n")
        f.write(f"license={license_info or 'Unknown'}\n")
        f.write(f"target_count={target_count}\n")
        f.write("description<<EOF\n")
        f.write(description + "\n")
        f.write("EOF\n")
        f.write("targets_table<<EOF\n")
        f.write(targets_table + "\n")
        f.write("EOF\n")

print(
    f"Successfully generated metadata for {pkg_name}@{version} with targets: {list(targets_found.keys())}"
)
