# .github/scripts/build_registry.py
import json
import os
import sys

PKGS_DIR = "pkgs"
REGISTRY_FILE = "registry.json"

# ---------------------------------------------------------------------------
# Inline channel/key repair — mirrors the logic in resolve_release.py so the
# compiled registry is always clean even if a manifest was committed with a
# wrong channel field or a stacked nightly entry.
# ---------------------------------------------------------------------------

_NIGHTLY_SUBSTRINGS = ("nightly", "master", "main", "latest-build")
_PRERELEASE_SUBSTRINGS = (
    "-alpha", "-beta", "-rc", "-dev", "-preview", "-pre",
    "alpha.", "beta.", "rc.",
)


def _classify_channel(version_str: str, declared: str = "") -> str:
    """Return the canonical channel for *version_str*, respecting *declared*
    only when it *demotes* the version (nightly/prerelease) and never when it
    would promote an obvious dev build to stable."""
    if declared in ("nightly", "prerelease"):
        return declared
    t = version_str.lower().strip()
    if any(sub in t for sub in _NIGHTLY_SUBSTRINGS) or t.startswith("dev-"):
        return "nightly"
    if any(sub in t for sub in _PRERELEASE_SUBSTRINGS):
        return "prerelease"
    if declared == "stable":
        return "stable"
    return "stable"


def _repair_versions(versions: dict) -> dict:
    """
    Repair a package's versions dict in-place:

    1. Correct wrong ``channel`` fields.
    2. Sanitize version keys that contain ``/`` or ``@``.
    3. Prune stacked nightly entries (keep only the newest).

    Returns a new dict (preserves insertion order of surviving entries).
    """
    # Pass 1 — fix keys and channels.
    repaired: dict = {}
    for vk, vdata in versions.items():
        # Sanitize the key.
        new_key = vk
        if "/" in new_key:
            new_key = new_key.split("/")[-1]
        new_key = new_key.replace("@", "-")
        if new_key != vk:
            print(f"  build_registry: rekey {vk!r} → {new_key!r}", file=sys.stderr)

        # Fix channel.
        declared = str(vdata.get("channel", "")).strip().lower()
        correct = _classify_channel(new_key, declared)
        if correct != declared:
            print(
                f"  build_registry: channel fix {new_key!r}: {declared!r} → {correct!r}",
                file=sys.stderr,
            )
            vdata = dict(vdata)
            vdata["channel"] = correct

        repaired[new_key] = vdata

    # Pass 2 — prune stacked nightlies.
    nightly_keys = [k for k, v in repaired.items()
                    if str(v.get("channel", "")).lower() == "nightly"]
    if len(nightly_keys) > 1:
        best = max(nightly_keys)
        for old in nightly_keys:
            if old != best:
                print(
                    f"  build_registry: prune stacked nightly {old!r} (keeping {best!r})",
                    file=sys.stderr,
                )
                del repaired[old]

    return repaired


def main():
    if not os.path.isdir(PKGS_DIR):
        print(f"Error: Directory '{PKGS_DIR}' does not exist.", file=sys.stderr)
        sys.exit(1)

    packages = {}
    total_versions = 0

    for fname in sorted(os.listdir(PKGS_DIR)):
        if not fname.endswith(".json"):
            continue
        pkg_name = fname[:-5]
        file_path = os.path.join(PKGS_DIR, fname)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["versions"] = _repair_versions(data.get("versions", {}))
            packages[pkg_name] = data
            total_versions += len(data["versions"])
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Failed to parse '{file_path}': {e}", file=sys.stderr)

    registry = {
        "repository": "https://github.com/SSL-ACTX/ship-pm",
        "packages": packages,
    }

    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, sort_keys=False)
        f.write("\n")

    print(
        f"Successfully compiled {len(packages)} packages ({total_versions} total versions) into {REGISTRY_FILE}"
    )


if __name__ == "__main__":
    main()
