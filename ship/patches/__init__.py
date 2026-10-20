"""Optional package-specific install and runtime adjustments.

Platform compatibility belongs in :mod:`ship.patchers`; behavior needed by
one package belongs in a module named after that package in this directory.
Package modules are deliberately optional and expose small named functions.
"""

from importlib import import_module
from pathlib import Path
from pkgutil import iter_modules
from types import ModuleType


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
    package_name: str, stage: str, install_dir: Path, target_key: str
) -> None:
    """Run an optional package-owned stage hook after extraction or before linking."""
    module = get_package_patch(package_name)
    callback = getattr(module, stage, None) if module else None
    if callback:
        callback(install_dir=install_dir, target_key=target_key)


def get_runtime_wrapper_hooks(binary_name: str) -> tuple[str, str]:
    """Collect optional runtime hooks declared by package patch modules."""
    for module_info in iter_modules([str(Path(__file__).parent)]):
        if module_info.name.startswith("_"):
            continue
        module = import_module(f"ship.patches.{module_info.name}")
        hook = getattr(module, "runtime_wrapper_hooks", None)
        if hook:
            before, after = hook(binary_name)
            if before or after:
                return before, after
    return "", ""


def get_runtime_exec_command(
    binary_name: str, real_binary: Path, target_key: str
) -> str | None:
    """Return a package-specific launcher command, if the package needs one."""
    for module_info in iter_modules([str(Path(__file__).parent)]):
        if module_info.name.startswith("_"):
            continue
        module = import_module(f"ship.patches.{module_info.name}")
        command = getattr(module, "runtime_exec_command", None)
        if command:
            result = command(binary_name, real_binary, target_key)
            if result:
                return result
    return None
