"""Custom manifest discovery recipes for non-GitHub or special distribution pools."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ship.api.sources import ManifestRecipe

_RECIPES: dict[str, ManifestRecipe] = {}
_DISCOVERED = False


def _discover_recipes() -> None:
    global _DISCOVERED
    if _DISCOVERED:
        return
    _DISCOVERED = True

    sources_dir = Path(__file__).parent
    for py_file in sources_dir.glob("*.py"):
        if py_file.stem in ("__init__",):
            continue
        mod_name = f"ship.registry.sources.{py_file.stem}"
        try:
            mod = importlib.import_module(mod_name)
            recipe = getattr(mod, "RECIPE", None)
            if recipe and hasattr(recipe, "name"):
                _RECIPES[recipe.name.lower()] = recipe
        except (ImportError, AttributeError, ValueError):
            pass


def get_source_recipe(pkg_name: str) -> ManifestRecipe | None:
    """Return a registered ManifestRecipe for pkg_name if one exists."""
    _discover_recipes()
    return _RECIPES.get(pkg_name.lower())


def list_source_recipes() -> dict[str, ManifestRecipe]:
    """Return all registered ManifestRecipe instances."""
    _discover_recipes()
    return dict(_RECIPES)
