"""Named terminal styles. Call sites use names — never raw ANSI codes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Style:
    """ANSI SGR parameters (without escape wrappers)."""

    code: str

    def wrap(self, text: object, *, enabled: bool) -> str:
        if not enabled:
            return str(text)
        return f"\033[{self.code}m{text}\033[0m"


@dataclass(frozen=True, slots=True)
class Theme:
    """Cargo-inspired status palette used by the UI engine."""

    bold: Style = Style("1")
    dim: Style = Style("2")
    underline: Style = Style("4")

    success: Style = Style("1;32")
    error: Style = Style("1;31")
    warning: Style = Style("1;33")
    info: Style = Style("1;36")
    accent: Style = Style("1;34")
    highlight: Style = Style("1;35")
    label: Style = Style("1;32")
    muted: Style = Style("2")

    # Semantic aliases for status verbs / channel badges
    action: Style = Style("1;32")
    package: Style = Style("1;32")
    version: Style = Style("1;34")
    channel_stable: Style = Style("1;32")
    channel_prerelease: Style = Style("1;33")
    channel_nightly: Style = Style("1;35")


DEFAULT_THEME = Theme()
