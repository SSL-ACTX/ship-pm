"""Package-specific patch loader and hook dispatcher."""

import importlib
import pkgutil
import re
from pathlib import Path
from typing import Literal

from ship.patchers.api import (
    ExportPolicy,
    PackagePatch,
    PatchContext,
    PatchReport,
    ReapplyHandler,
)

HookName = Literal["post_extract", "pre_link"]


def get_package_patch(pkg_name: str) -> PackagePatch | None:
    module_name = f"ship.patches.{pkg_name.replace('-', '_')}"
    try:
        mod = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None
    patch = getattr(mod, "PATCH", None)
    return patch if isinstance(patch, PackagePatch) else None


def get_export_policy(pkg_name: str) -> ExportPolicy:
    patch = get_package_patch(pkg_name)
    return patch.export_policy if patch else ExportPolicy()


def get_excluded_link_names(pkg_name: str) -> frozenset[str]:
    patch = get_package_patch(pkg_name)
    return frozenset(patch.excluded_link_names) if patch else frozenset()


def should_discover_all_bins(pkg_name: str) -> bool:
    patch = get_package_patch(pkg_name)
    return bool(patch and patch.discover_all_bins)


def get_reapply_handlers(pkg_name: str) -> tuple[ReapplyHandler, ...]:
    patch = get_package_patch(pkg_name)
    return patch.reapply if patch else ()


def apply_reapply_handlers(pkg_name: str, report: PatchReport) -> None:
    for handler in get_reapply_handlers(pkg_name):
        handler(report)


def apply_package_patch(
    pkg_name: str,
    hook_name: HookName,
    install_dir: Path,
    target_key: str,
    report: PatchReport,
) -> None:
    patch = get_package_patch(pkg_name)
    if not patch:
        return
    hooks = getattr(patch, hook_name, ())
    context = PatchContext(
        package_name=pkg_name,
        stage=hook_name,
        install_dir=install_dir,
        target_key=target_key,
        report=report,
    )
    for entry in hooks:
        if entry.matches(target_key):
            entry.handler(context)


def find_patch_for_binary(binary_name: str) -> PackagePatch | None:
    """Find a PackagePatch that owns or declares binary_name."""
    # 1. Direct module lookup (e.g. odin -> patches/odin.py)
    patch = get_package_patch(binary_name)
    if patch:
        return patch

    # 2. Stripped numeric suffix (e.g. cryptominisat5 -> patches/cryptominisat.py)
    base = re.sub(r"\d+$", "", binary_name)
    if base != binary_name:
        patch = get_package_patch(base)
        if patch:
            return patch

    # 3. Search all patch modules in ship/patches
    patches_dir = Path(__file__).parent
    for _, mod_name, _ in pkgutil.iter_modules([str(patches_dir)]):
        if mod_name.startswith("_") or mod_name == "api":
            continue
        try:
            mod = importlib.import_module(f"ship.patches.{mod_name}")
            p = getattr(mod, "PATCH", None)
            if isinstance(p, PackagePatch):
                for r in p.runtime:
                    if binary_name in r.binaries:
                        return p
        except Exception:
            continue
    return None


def get_runtime_patch(
    binary_name: str,
    real_binary: Path,
    target_key: str,
) -> tuple[str, str, str]:
    patch = find_patch_for_binary(binary_name)
    if not patch:
        return "", "", ""
    for entry in patch.runtime:
        if entry.matches(binary_name, target_key):
            return (
                entry.resolve(entry.before, binary_name, real_binary, target_key),
                entry.resolve(entry.after, binary_name, real_binary, target_key),
                entry.resolve(entry.command, binary_name, real_binary, target_key),
            )
    return "", "", ""
