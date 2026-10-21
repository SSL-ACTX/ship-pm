#!/usr/bin/env python3
"""
repair_pkgs.py — Audit and repair ship package JSON manifests.

Fixes applied
─────────────
1. WRONG CHANNEL   — per-version "channel" field disagrees with the version
                     string's canonical classification. Updated to match what
                     ship.version.classify_channel() computes (manifest
                     overrides that falsely promote a dev/nightly build to
                     "stable" are corrected; genuine author overrides that
                     *demote* a stable-looking string are kept).

2. STACKED NIGHTLY — more than one nightly version is present in a package's
                     versions dict.  Only the latest (by semver_sort_key) is
                     kept; older nightly entries are pruned.

3. BAD VERSION KEY — version keys that contain "/" or "@" will break archive
                     cache paths and store directory names.  The slash is
                     replaced with a hyphen (e.g. "release/v5.17.0" →
                     "v5.17.0") and the entry is re-keyed.

Run with --dry-run to preview changes without writing files.
Run with --yes    to apply all fixes without confirmation prompts.
"""

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: make sure ship package is importable from the repo root.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ship.version import classify_channel, semver_sort_key  # noqa: E402

PKGS_DIR = REPO_ROOT / "pkgs"

# ANSI helpers
def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"

ok    = lambda s: _c(s, "1;32")
warn  = lambda s: _c(s, "1;33")
err   = lambda s: _c(s, "1;31")
bold  = lambda s: _c(s, "1")
dim   = lambda s: _c(s, "2")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_nightly_like(version_str: str) -> bool:
    """True when the version string looks like a nightly/dev/rolling build."""
    v = version_str.lower()
    return (
        v.startswith("dev-")
        or "nightly" in v
        or "master" in v
        or "main" in v
        or "latest-build" in v
    )


def _canonical_channel(version_str: str, version_data: dict) -> str:
    """
    The correct channel for this version.

    Rules (in priority order):
      1. If the manifest declares "nightly" or "prerelease" → keep it.
      2. If the version string looks like a nightly/dev build, ignore a
         manifest "stable" override and return "nightly".
      3. Otherwise trust the heuristic from classify_channel().
    """
    declared = str(version_data.get("channel", "")).strip().lower()
    if declared in ("nightly", "prerelease"):
        return declared
    heuristic = classify_channel(version_str)
    if declared == "stable" and heuristic == "nightly":
        # Manifest tried to promote a nightly build to stable — reject that.
        return "nightly"
    # Use heuristic for everything else (covers missing channel field too).
    return heuristic


def _sanitize_version_key(key: str) -> str:
    """Return a safe version key (no "/" or "@")."""
    # Strip common "release/" or "v" prefix clutter; keep the version part.
    sanitized = key
    # "release/v5.17.0" → "v5.17.0"
    if "/" in sanitized:
        sanitized = sanitized.split("/")[-1]
    # "@" is also illegal in path components.
    sanitized = sanitized.replace("@", "-")
    return sanitized


# ---------------------------------------------------------------------------
# Per-file audit + repair
# ---------------------------------------------------------------------------

class Change:
    def __init__(self, kind: str, version: str, detail: str):
        self.kind = kind       # "channel" | "stacked_nightly" | "bad_key"
        self.version = version
        self.detail = detail

    def __str__(self) -> str:
        label = {
            "channel":         warn("channel fix"),
            "stacked_nightly": warn("prune nightly"),
            "bad_key":         warn("rekey version"),
        }.get(self.kind, warn(self.kind))
        return f"  {label}: {bold(self.version)} — {self.detail}"


def audit_and_repair(path: Path) -> tuple[dict, list[Change]]:
    """
    Load *path*, compute all required changes, apply them to a copy of the
    data, and return (repaired_data, list_of_changes).  The original file is
    NOT written here.
    """
    raw = path.read_text(encoding="utf-8")
    data: dict = json.loads(raw)
    versions: dict = data.get("versions", {})
    changes: list[Change] = []

    # ── Pass 1: fix bad version keys (must happen before channel / nightly
    #            checks so we work with the corrected keys throughout).
    rekeyed: dict = {}
    for vk, vdata in versions.items():
        new_key = _sanitize_version_key(vk)
        if new_key != vk:
            changes.append(
                Change(
                    "bad_key",
                    vk,
                    f'renamed to "{new_key}"',
                )
            )
            rekeyed[new_key] = vdata
        else:
            rekeyed[vk] = vdata
    versions = rekeyed

    # ── Pass 2: fix per-version channel fields.
    for vk, vdata in versions.items():
        correct = _canonical_channel(vk, vdata)
        declared = str(vdata.get("channel", "")).strip().lower()
        if declared != correct:
            old_label = f'"{declared}"' if declared else "(missing)"
            changes.append(
                Change(
                    "channel",
                    vk,
                    f"channel {old_label} → \"{correct}\"",
                )
            )
            vdata["channel"] = correct

    # ── Pass 3: prune stacked nightlies (keep only the newest).
    nightly_keys = [
        vk for vk, vd in versions.items()
        if str(vd.get("channel", "")).lower() == "nightly"
    ]
    if len(nightly_keys) > 1:
        best = max(nightly_keys, key=semver_sort_key)
        for vk in nightly_keys:
            if vk != best:
                changes.append(
                    Change(
                        "stacked_nightly",
                        vk,
                        f'removed (superseded by "{best}")',
                    )
                )
                del versions[vk]

    data["versions"] = versions
    return data, changes


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit and repair ship package JSON manifests.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview changes without writing any files.",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Apply all fixes without asking for confirmation.",
    )
    parser.add_argument(
        "packages",
        nargs="*",
        metavar="PKG",
        help="Limit repair to specific package names (e.g. odin aeneas). "
             "Omit to process all packages.",
    )
    args = parser.parse_args()

    pkg_files = sorted(PKGS_DIR.glob("*.json"))
    if args.packages:
        wanted = {p.lower().removesuffix(".json") for p in args.packages}
        pkg_files = [f for f in pkg_files if f.stem.lower() in wanted]
        if not pkg_files:
            print(err("No matching package files found."))
            sys.exit(1)

    all_changes: list[tuple[Path, dict, list[Change]]] = []

    print(f"\n{bold('Auditing')} {len(pkg_files)} package manifest(s) in {dim(str(PKGS_DIR))}…\n")

    for path in pkg_files:
        try:
            repaired, changes = audit_and_repair(path)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  {err('ERROR')} {path.name}: {exc}")
            continue

        if changes:
            print(f"  {ok('✓')} {bold(path.stem)}  ({len(changes)} fix(es))")
            for ch in changes:
                print(ch)
            all_changes.append((path, repaired, changes))
        else:
            print(f"  {dim('–')} {path.stem}  {dim('(clean)')}")

    print()

    if not all_changes:
        print(ok("All manifests are clean. Nothing to do."))
        return

    n_files = len(all_changes)
    n_total = sum(len(c) for _, _, c in all_changes)
    print(bold(f"Summary: {n_total} fix(es) across {n_files} file(s)."))

    if args.dry_run:
        print(warn("\n--dry-run: no files written.\n"))
        return

    if not args.yes:
        try:
            answer = input("\nApply all fixes? [y/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            answer = ""
        if answer not in ("y", "yes"):
            print(warn("Aborted. No files written."))
            return

    written = 0
    for path, repaired, _ in all_changes:
        try:
            path.write_text(
                json.dumps(repaired, indent=4, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"  {ok('Written')} {path.name}")
            written += 1
        except OSError as exc:
            print(f"  {err('ERROR')} writing {path.name}: {exc}")

    print(f"\n{ok('Done.')} {written}/{n_files} file(s) updated.\n")


if __name__ == "__main__":
    main()
