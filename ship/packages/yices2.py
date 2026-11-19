"""Package patch for Yices 2 SMT solver."""

from ship.api import PackageRecipe

PATCH = (
    PackageRecipe("yices2")
    .export(
        only=("yices", "yices-smt", "yices-smt2", "yices-sat", "yices2"),
        exclude=("install-yices",),
        aliases={"yices2": "yices"},
    )
    .to_patch()
)
