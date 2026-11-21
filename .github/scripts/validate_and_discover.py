#!/usr/bin/env python3
"""JSON schema validation and parallel upstream release discovery."""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from ship.registry.sources import get_source_recipe

SCHEMA_FILE = Path("docs/registry.schema.json")
PKGS_DIR = Path("pkgs")


def validate_manifest(path: Path, data: dict) -> list[str]:
    errors = []
    if "description" not in data or not isinstance(data["description"], str):
        errors.append(f"{path.name}: missing or invalid 'description'")
    if "repository" not in data or not isinstance(data["repository"], str):
        errors.append(f"{path.name}: missing or invalid 'repository'")
    if "versions" not in data or not isinstance(data["versions"], dict):
        errors.append(f"{path.name}: missing or invalid 'versions' object")
    else:
        for ver, vdata in data["versions"].items():
            if not isinstance(vdata, dict):
                errors.append(f"{path.name}@{ver}: version must be an object")
                continue
            targets = vdata.get("targets", {})
            if not isinstance(targets, dict) or not targets:
                errors.append(
                    f"{path.name}@{ver}: 'targets' must be a non-empty object"
                )
            for target_name, tdata in targets.items():
                if "url" not in tdata or not isinstance(tdata["url"], str):
                    errors.append(
                        f"{path.name}@{ver}/{target_name}: target missing 'url'"
                    )
    return errors


def fetch_latest_release(repo_slug: str, token: str | None = None) -> str | None:
    url = f"https://api.github.com/repos/{repo_slug}/releases?per_page=5"
    headers = {"User-Agent": "ship-pm-sync"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            releases = json.loads(resp.read())
            if isinstance(releases, list) and releases:
                for r in releases:
                    tag = r.get("tag_name", "")
                    if tag and not r.get("draft", False):
                        return tag
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        print(
            f"Warning: Failed to fetch releases for {repo_slug}: {e}", file=sys.stderr
        )
    return None


def main():
    target_package = os.environ.get("TARGET_PACKAGE", "all").strip().lower()
    gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

    all_errors = []
    updates_needed = []

    for pkg_path in sorted(PKGS_DIR.glob("*.json")):
        pkg_name = pkg_path.stem
        if target_package not in ("all", "") and pkg_name != target_package:
            continue

        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            all_errors.append(f"{pkg_path.name}: Invalid JSON: {e}")
            continue

        # Validate schema
        errors = validate_manifest(pkg_path, data)
        all_errors.extend(errors)

        # Check for custom source recipe (e.g. Racket)
        recipe = get_source_recipe(pkg_name)
        if recipe:
            discovered = recipe.discover_versions()
            if discovered:
                # Latest version
                latest_v = discovered[-1]
                existing_versions = set(data.get("versions", {}).keys())
                if latest_v not in existing_versions:
                    print(
                        f"Update detected (custom recipe): {pkg_name} needs update to {latest_v}"
                    )
                    updates_needed.append(
                        {
                            "pkg": pkg_name,
                            "repo": f"custom:{pkg_name}",
                            "latest_tag": latest_v,
                        }
                    )
            continue

        # Check repository URL
        repo_url = data.get("repository", "")
        if "github.com/" not in repo_url:
            continue

        parts = repo_url.split("github.com/")[-1].strip("/").split("/")
        if len(parts) < 2:
            continue
        owner, repo_name = parts[0], parts[1]
        repo_slug = f"{owner}/{repo_name}"

        # Check latest tag upstream
        latest_tag = fetch_latest_release(repo_slug, token=gh_token)
        if not latest_tag:
            continue

        clean_latest = latest_tag.lstrip("v")
        # Check if version exists in manifest
        existing_versions = set(data.get("versions", {}).keys())
        tag_already_present = any(
            v == clean_latest
            or v == latest_tag
            or v == f"{repo_name.lower()}-{clean_latest}"
            for v in existing_versions
        )

        if not tag_already_present:
            print(f"Update detected: {pkg_name} needs update to {latest_tag}")
            updates_needed.append(
                {
                    "pkg": pkg_name,
                    "repo": repo_slug,
                    "latest_tag": latest_tag,
                }
            )

    if all_errors:
        print("\nJSON Validation Errors:", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    print(f"\nManifest validation passed! Found {len(updates_needed)} updates to sync.")

    # Output GitHub Actions matrix format
    has_updates = "true" if updates_needed else "false"
    matrix_json = (
        json.dumps({"include": updates_needed})
        if updates_needed
        else json.dumps({"include": []})
    )

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"has_updates={has_updates}\n")
            f.write(f"matrix={matrix_json}\n")
    else:
        print(f"has_updates={has_updates}")
        print(f"matrix={matrix_json}")


if __name__ == "__main__":
    main()
