"""Termux runtime integration for Juliaup and the Julia launcher."""

import json

from ship.api import (
    PackageRecipe,
    PatchReport,
    patch_external_toolchain,
)
from ship.core.settings import settings
from ship.runtime import apply_patchers
from ship.ui import status

# Julia's compiled caches pair .ji metadata with checksum-sensitive .so files.
# Rewriting those shared objects makes the cache invalid, so don't traverse them.
PATCH_SKIP_DIRS = (
    "artifacts",
    "clones",
    "compiled",
    "downloads",
    "logs",
    "packages",
    "registries",
    "scratchspaces",
)

_JULIAUP_STATE = settings.home / ".julia" / "juliaup" / "juliaup.json"


def _read_juliaup_state() -> dict:
    try:
        return json.loads(_JULIAUP_STATE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _link_julia_bin(report: PatchReport) -> None:
    """Ensure the active julia binary is linked into ship's bin directory."""
    state = _read_juliaup_state()
    default_channel = state.get("Default")
    channels = state.get("InstalledChannels", {})
    versions = state.get("InstalledVersions", {})
    root = settings.home / ".julia" / "juliaup"

    version_key = (
        channels.get(default_channel, {}).get("Version") if default_channel else None
    )
    if not version_key:
        version_key = next(iter(versions), None)
    if not version_key:
        return

    rel = versions[version_key].get("BinaryPath", "")
    julia_bin = (root / rel).resolve()
    if not julia_bin.is_file():
        return

    try:
        after_plus = version_key.split("+", 1)[1]
        platform = after_plus.split(".", 1)[1]
        target_key = platform.replace(".", "-")
    except IndexError:
        target_key = "aarch64-linux-gnu"

    julia_bin.chmod(0o755)
    patched = apply_patchers(julia_bin, target_key, report)

    internal = settings.ship_internal_bin / "julia"
    public = settings.ship_bin_dir / "julia"

    internal.unlink(missing_ok=True)
    internal.symlink_to(patched)

    if public.is_symlink():
        public.unlink()
    elif public.exists():
        return

    public.symlink_to(patched)
    report.add(public, "link julia", str(patched))


def patch_toolchain_dir(report: PatchReport | None = None) -> PatchReport:
    """Patch Juliaup-managed glibc executables after Julia installs them."""
    owns_report = report is None
    report = report or PatchReport("juliaup")
    root = settings.home / ".julia" / "juliaup"

    patch_external_toolchain(
        root_dir=root,
        subdirs=(),
        skip_dirs=PATCH_SKIP_DIRS,
        report=report,
    )

    _link_julia_bin(report)

    if owns_report:
        for change in report.changes:
            status("Patching", report.describe(change))
    return report


PATCH = (
    PackageRecipe("juliaup")
    .on_subcommand(
        binaries=("juliaup",),
        triggers=("add", "update", "install", "default"),
        post_exec_call="ship.patches.juliaup:patch_toolchain_dir",
        targets=("aarch64-*",),
    )
    .on_reapply(patch_toolchain_dir)
    .to_patch()
)
