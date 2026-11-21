"""Unified packaging and runtime configuration for Agda (and agda-bin)."""

from __future__ import annotations

from ship.api import PackageRecipe

_PUBLIC_COMMANDS = ("agda",)

PATCH = PackageRecipe("agda").export(only=_PUBLIC_COMMANDS, allow_empty=True).to_patch()
