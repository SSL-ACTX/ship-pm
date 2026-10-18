import os
import json
import re
import urllib.request
import hashlib
import sys

repo = os.environ.get("TARGET_REPO")
tag = os.environ.get("TARGET_TAG", "latest")
token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

if not repo:
    print("Error: TARGET_REPO is not set.")
    sys.exit(1)

pkg_name = repo.split("/")[-1].lower()

headers = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "ship-registry-indexer"
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
        f"https://api.github.com/repos/{repo}/releases/tags/v{tag}" if not tag.startswith("v") else f"https://api.github.com/repos/{repo}/releases/tags/{tag.lstrip('v')}"
    ]
    for url in candidate_urls:
        try:
            print(f"Checking {url}...")
            release = fetch_json(url)
            if release and "assets" in release:
                break
        except Exception:
            continue

# If not found yet, query /releases list to match tag or get latest release (including prereleases)
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
                # Default to first available release
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
        gh_out = os.environ.get("GITHUB_OUTPUT")
        if gh_out:
            with open(gh_out, "a") as f:
                f.write("updated=false\n")
        sys.exit(1)

# Fetch repo-level metadata (description, homepage, license, author)
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

print(f"Processing {repo} @ version {version} ({len(assets)} assets)")

# 2. Check if already recorded in registry.json (Deduplication)
registry_path = "registry.json"
if not os.path.exists(registry_path):
    registry = {"repository": f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', '')}", "packages": {}}
else:
    with open(registry_path, "r") as f:
        registry = json.load(f)

packages = registry.setdefault("packages", {})
if pkg_name in packages and version in packages[pkg_name].get("versions", {}):
    print(f"Package {pkg_name}@{version} already exists in registry.json. Skipping PR.")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write("updated=false\n")
    sys.exit(0)

# 3. Extract SHA256 checksum files if bundled in assets
checksum_map = {}
for asset in assets:
    name = asset.get("name", "").lower()
    if any(k in name for k in ["sha256", "checksum", "hashes"]):
        print(f"Reading checksum file: {asset['name']}")
        try:
            c_req = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": "ship-registry-indexer"})
            with urllib.request.urlopen(c_req) as c_resp:
                content = c_resp.read().decode("utf-8", errors="ignore")
                for line in content.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        h = parts[0] if len(parts[0]) == 64 else parts[1]
                        fn = parts[1] if len(parts[0]) == 64 else parts[0]
                        if len(h) == 64 and all(c in "0123456789abcdefABCDEF" for c in h):
                            checksum_map[os.path.basename(fn)] = h.lower()
        except Exception as e:
            print(f"Warning: Failed to parse checksum file {asset['name']}: {e}")

# 4. Map assets to ship target triples
target_patterns = {
    "x86_64-linux-gnu": [r"(x86_64|amd64)", r"linux", r"gnu"],
    "x86_64-linux-musl": [r"(x86_64|amd64)", r"linux", r"musl"],
    "aarch64-linux-gnu": [r"(aarch64|arm64)", r"linux", r"gnu"],
    "aarch64-linux-musl": [r"(aarch64|arm64)", r"linux", r"musl"],
    "armv7-linux-gnu": [r"(armv7|armhf)", r"linux"],
    "i686-linux-gnu": [r"(i686|i386)", r"linux", r"gnu"],
    "i686-linux-musl": [r"(i686|i386)", r"linux", r"musl"]
}

targets_found = {}

for target_key, patterns in target_patterns.items():
    for a in assets:
        name = a.get("name", "").lower()
        # Skip package managers & non-archives
        if any(name.endswith(ext) for ext in [".deb", ".rpm", ".apk", ".msi", ".exe", ".dmg"]):
            continue

        if all(re.search(pat, name) for pat in patterns):
            url = a.get("browser_download_url")
            asset_filename = a.get("name")
            sha = checksum_map.get(asset_filename, "")

            # If hash is not in a checksum file, stream asset and compute SHA256
            if not sha:
                print(f"Calculating SHA-256 for {asset_filename}...")
                hasher = hashlib.sha256()
                d_req = urllib.request.Request(url, headers={"User-Agent": "ship-registry-indexer"})
                with urllib.request.urlopen(d_req) as resp:
                    while chunk := resp.read(65536):
                        hasher.update(chunk)
                sha = hasher.hexdigest()

            targets_found[target_key] = {
                "url": url,
                "sha256": sha
            }
            break

if not targets_found:
    print("Could not match any supported targets. No PR will be opened.")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write("updated=false\n")
    sys.exit(0)

# 5. Update registry structure
description = (
    repo_data.get("description")
    or (release.get("body", "").splitlines()[0][:120] if release.get("body") else None)
    or f"Pre-built binaries for {repo}"
)
homepage = repo_data.get("homepage") or ""
author = repo_data.get("owner", {}).get("login") or repo.split("/")[0]
repo_link = repo_data.get("html_url") or f"https://github.com/{repo}"
license_info = (repo_data.get("license") or {}).get("spdx_id") or ""

if pkg_name not in packages:
    packages[pkg_name] = {
        "description": description,
        "author": author,
        "repository": repo_link,
        "versions": {}
    }
    if homepage:
        packages[pkg_name]["homepage"] = homepage
    if license_info and license_info != "NOASSERTION":
        packages[pkg_name]["license"] = license_info
else:
    # Update existing package fields if previously missing
    packages[pkg_name].setdefault("description", description)
    packages[pkg_name].setdefault("author", author)
    packages[pkg_name].setdefault("repository", repo_link)
    if homepage and "homepage" not in packages[pkg_name]:
        packages[pkg_name]["homepage"] = homepage
    if license_info and license_info != "NOASSERTION" and "license" not in packages[pkg_name]:
        packages[pkg_name]["license"] = license_info

packages[pkg_name]["versions"][version] = {
    "binaries": {
        pkg_name: f"bin/{pkg_name}"
    },
    "targets": targets_found
}

with open(registry_path, "w") as f:
    json.dump(registry, f, indent=2)

print(f"Successfully generated metadata for {pkg_name}@{version} with targets: {list(targets_found.keys())}")

# Set step outputs for GitHub Actions
gh_out = os.environ.get("GITHUB_OUTPUT")
if gh_out:
    with open(gh_out, "a") as f:
        f.write("updated=true\n")
        f.write(f"pkg={pkg_name}\n")
        f.write(f"version={version}\n")
        f.write(f"repo={repo}\n")
        f.write(f"targets={', '.join(targets_found.keys())}\n")
