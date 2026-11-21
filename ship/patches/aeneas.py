from ship.api import PackageRecipe

PATCH = PackageRecipe("aeneas").export(discover_all_bins=True)
