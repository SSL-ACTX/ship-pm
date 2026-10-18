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

# 1. Fetch release info from GitHub API
api_url = (
    f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    if tag and tag != "latest"
    else f"https://api.github.com/repos/{repo}/releases/latest"
)

print(f"Fetching release data from {api_url}...")
req = urllib.request.Request(
    api_url,
    headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ship-registry-indexer"
    }
)

try:
    with urllib.request.urlopen(req) as resp:
        release = json.loads(resp.read().decode())
except Exception as e:
    print(f"Error fetching release: {e}")
    sys.exit(1)

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
description = release.get("body", "").splitlines()[0][:120] if release.get("body") else f"Pre-built binaries for {repo}"

if pkg_name not in packages:
    packages[pkg_name] = {
        "description": description,
        "versions": {}
    }

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
