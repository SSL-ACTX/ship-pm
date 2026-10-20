"""Optional package-specific install and runtime adjustments.

Platform compatibility belongs in :mod:`ship.patchers`; behavior needed by
one package belongs in a module named after that package in this directory.
Package modules are deliberately optional and expose small named functions.
"""

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

    callback = getattr(module, stage, None) if module else None
    if callback and not handlers:
        callback(install_dir=install_dir, target_key=target_key)
    return report


def apply_reapply_handlers(
    package_name: str, report: PatchReport | None = None
) -> PatchReport:
    """Run package hooks that reapply package-managed changes outside its tree."""
    report = report or PatchReport(package_name)
    module = get_package_patch(package_name)
    package_patch = getattr(module, "PATCH", None) if module else None
    handlers: tuple[ReapplyHandler, ...] = (
        package_patch.reapply if isinstance(package_patch, PackagePatch) else ()
    )
    for handler in handlers:
        handler(report)
    return report


def get_runtime_wrapper_hooks(binary_name: str) -> tuple[str, str]:
    """Collect optional runtime hooks declared by package patch modules."""
    for module in _patch_modules():
        hook = getattr(module, "runtime_wrapper_hooks", None)
        if hook:
            before, after = hook(binary_name)
            if before or after:
                return before, after
    return "", ""


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
        patches.extend(getattr(module, "RUNTIME_PATCHES", ()))
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

        # Legacy hook modules continue to contribute during migration.
        hook = getattr(module, "runtime_wrapper_hooks", None)
        if hook:
            before, after = hook(binary_name)
            before_parts.extend([before] if before else [])
            after_parts.extend([after] if after else [])
        legacy_command = getattr(module, "runtime_exec_command", None)
        if not command and legacy_command:
            command = legacy_command(binary_name, real_binary, target_key) or ""

    return "\n".join(before_parts), "\n".join(after_parts), command


def get_runtime_exec_command(
    binary_name: str, real_binary: Path, target_key: str
) -> str | None:
    """Return a package-specific launcher command, if the package needs one."""
    for module in _patch_modules():
        command = getattr(module, "runtime_exec_command", None)
        if command:
            result = command(binary_name, real_binary, target_key)
            if result:
                return result
    return None
