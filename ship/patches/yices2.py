"""Package patch for Yices 2 SMT solver."""

from ship.patchers.api import ExportPolicy, PackagePatch

PATCH = PackagePatch(
    export_policy=ExportPolicy(
        only=("yices", "yices-smt", "yices-smt2", "yices-sat", "yices2"),
        exclude=("install-yices",),
        aliases={"yices2": "yices"},
    ),
)
