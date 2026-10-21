"""Optional package-specific install and runtime patch recipes."""

from importlib import import_module
from pathlib import Path
from pkgutil import iter_modules
from types import ModuleType

from ship.patches.api import (
    InstallPatch,
    InstallStage,
    PackagePatch,
    PatchContext,
    PatchRecipe,
    PatchReport,
    ReapplyHandler,
    RuntimePatch,
)


def _patch_modules():
    """Yield package patch modules in stable order for runtime discovery."""
    modules = iter_modules([str(Path(__file__).parent)])
    for info in sorted(modules, key=lambda item: item.name):
        if not info.name.startswith("_") and info.name != "api":
            yield import_module(f"ship.patches.{info.name}")


def get_package_patch(package_name: str) -> ModuleType | None:
    """Load an in-tree patch module for a package, if one exists."""
    module_name = package_name.lower().replace("-", "_")
    if not module_name.isidentifier():
        return None
    try:
        return import_module(f"ship.patches.{module_name}")
    except ModuleNotFoundError as exc:
        # Only treat the requested package module being absent as optional.
        if exc.name == f"ship.patches.{module_name}":
            return None
        raise


def apply_package_patch(
    package_name: str,
    stage: InstallStage,
    install_dir: Path,
    target_key: str,
    report: PatchReport | None = None,
) -> PatchReport:
    """Run package handlers for one install stage and return their change report."""
    report = report or PatchReport(package_name)
    module = get_package_patch(package_name)
    package_patch = getattr(module, "PATCH", None) if module else None
    handlers: tuple[InstallPatch, ...] = (
        getattr(package_patch, stage, ())
        if isinstance(package_patch, PackagePatch)
        else ()
    )
    context = PatchContext(package_name, stage, install_dir, target_key, report)
    for handler in handlers:
        if handler.matches(target_key):
            handler.handler(context)

    return report


def apply_reapply_handlers(
    package_name: str, report: PatchReport | None = None
) -> PatchReport:
    """Run declared handlers that reapply package-managed external changes."""
    report = report or PatchReport(package_name)
    module = get_package_patch(package_name)
    package_patch = getattr(module, "PATCH", None) if module else None
    handlers: tuple[ReapplyHandler, ...] = (
        package_patch.reapply if isinstance(package_patch, PackagePatch) else ()
    )
    for handler in handlers:
        handler(report)
    return report


def get_runtime_patch(
    binary_name: str, real_binary: Path, target_key: str
) -> tuple[str, str, str]:
    """Compose all matching recipes; the first nonempty command wins."""
    before_parts: list[str] = []
    after_parts: list[str] = []
    command = ""
    for module in _patch_modules():
        package_patch = getattr(module, "PATCH", None)
        patches = (
            list(package_patch.runtime)
            if isinstance(package_patch, PackagePatch)
            else []
        )
        for patch in patches:
            if not isinstance(patch, RuntimePatch) or not patch.matches(
                binary_name, target_key
            ):
                continue
            before = patch.resolve(patch.before, binary_name, real_binary, target_key)
            after = patch.resolve(patch.after, binary_name, real_binary, target_key)
            before_parts.extend([before] if before else [])
            after_parts.extend([after] if after else [])
            if not command:
                command = patch.resolve(
                    patch.command, binary_name, real_binary, target_key
                )

    return "\n".join(before_parts), "\n".join(after_parts), command
