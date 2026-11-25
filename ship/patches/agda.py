"""Unified packaging and runtime configuration for Agda (and agda-bin)."""

from __future__ import annotations

import os
from pathlib import Path

from ship.api import PackageRecipe, PatchReport
from ship.api.toolkit import PatchContext
from ship.core.profile import get_active_profile
from ship.core.state import load_state

_PUBLIC_COMMANDS = ("agda",)
_STDLIB_PKG_NAME = "ubuntu:agda-stdlib"
_STDLIB_SEARCH_SUBDIRS = ("share/agda-stdlib", "share/agda/lib", "agda-stdlib")
_MANIFEST_NAME = "standard-library.agda-lib"
_AGDA_CONFIG_SUBDIR = ".agda"


def _locate_stdlib_dir(install_dir: Path) -> Path | None:
    """Return the first existing stdlib source tree inside *install_dir*."""
    for subdir in _STDLIB_SEARCH_SUBDIRS:
        candidate = install_dir / subdir
        if candidate.is_dir():
            return candidate
    return None


def _ensure_stdlib_manifest(report: PatchReport) -> None:
    """Write standard-library.agda-lib and update ~/.agda config idempotently."""
    state = load_state()
    pkg_data = state.get("installed", {}).get(_STDLIB_PKG_NAME)
    if not pkg_data:
        return

    install_dir = Path(pkg_data.get("install_dir", ""))
    stdlib_dir = _locate_stdlib_dir(install_dir)
    if not stdlib_dir:
        return

    manifest_path = stdlib_dir / _MANIFEST_NAME
    manifest_content = "name: standard-library\ninclude: .\n"
    if not manifest_path.exists() or manifest_path.read_text() != manifest_content:
        manifest_path.write_text(manifest_content)
        report.add(manifest_path, "write library manifest", _MANIFEST_NAME)

    profile = get_active_profile()
    agda_dir_env = os.environ.get("AGDA_DIR")
    agda_config_dir = (
        Path(agda_dir_env)
        if agda_dir_env and Path(agda_dir_env).is_dir()
        else profile.home / _AGDA_CONFIG_SUBDIR
    )
    agda_config_dir.mkdir(parents=True, exist_ok=True)

    lib_registry = agda_config_dir / "libraries"
    manifest_str = str(manifest_path)
    existing = lib_registry.read_text().splitlines() if lib_registry.exists() else []
    live = [p for p in existing if p == manifest_str or Path(p).exists()]
    if manifest_str not in live:
        live.append(manifest_str)
    if live != existing:
        lib_registry.write_text("\n".join(live) + "\n" if live else "")
        report.add(lib_registry, "update library registry", manifest_str)

    defaults_file = agda_config_dir / "defaults"
    existing_defaults = (
        defaults_file.read_text().splitlines() if defaults_file.exists() else []
    )
    if "standard-library" not in existing_defaults:
        with defaults_file.open("a") as fh:
            fh.write("standard-library\n")
        report.add(defaults_file, "register default library", "standard-library")


def _stdlib_hook(context: PatchContext) -> None:
    _ensure_stdlib_manifest(context.report)


PATCH = (
    PackageRecipe("agda")
    .export(only=_PUBLIC_COMMANDS, allow_empty=True)
    .hook(_stdlib_hook, stage="pre_link", description="write agda stdlib manifest")
    .on_reapply(_ensure_stdlib_manifest)
    .to_patch()
)
