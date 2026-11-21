"""Termux runtime integration for hax and its managed tools (charon, aeneas)."""

from __future__ import annotations

from ship.api import (
    PackageRecipe,
    PatchReport,
    patch_external_toolchain,
)
from ship.core.settings import settings
from ship.ui import status

HAX_CACHE_TOOLS = settings.home / ".cache" / "hax" / "tools"


def patch_hax_tools(report: PatchReport | None = None) -> PatchReport:
    """Patch hax-managed external toolchains (charon, charon-driver, aeneas) in ~/.cache/hax/tools."""
    owns_report = report is None
    report = report or PatchReport("hax")

    if HAX_CACHE_TOOLS.is_dir():
        patch_external_toolchain(
            root_dir=HAX_CACHE_TOOLS,
            subdirs=(),
            report=report,
        )

    if owns_report:
        for change in report.changes:
            status("Patching", report.describe(change))
    return report


PATCH = (
    PackageRecipe("hax")
    .on_subcommand(
        binaries=("hax",),
        triggers=("into", "tools", "extract", "json"),
        post_exec_call="ship.patches.hax:patch_hax_tools",
        targets=("aarch64-*",),
    )
    .on_reapply(patch_hax_tools)
    .to_patch()
)
