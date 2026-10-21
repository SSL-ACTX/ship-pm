"""Pure formatting helpers for the UI engine."""

from __future__ import annotations

import re

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_LICENSE_NAMES = {
    "zlib": "Zlib License",
}


def strip_ansi(text: object) -> str:
    return ANSI_RE.sub("", str(text))


def visible_len(text: object) -> int:
    return len(strip_ansi(text))


def pad_visible(text: object, width: int, align: str = "left") -> str:
    extra = width - visible_len(text)
    if extra <= 0:
        return str(text)
    spaces = " " * extra
    return f"{text}{spaces}" if align == "left" else f"{spaces}{text}"


def format_size(size_bytes: int | float | None) -> str:
    """Format a byte count with binary units."""
    if size_bytes is None:
        return "unknown"
    try:
        value = float(size_bytes)
    except (TypeError, ValueError):
        return "unknown"
    if value < 0:
        return "unknown"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return "unknown"


def format_license(license_id: str) -> str:
    value = license_id.strip()
    return _LICENSE_NAMES.get(value.casefold(), value)
