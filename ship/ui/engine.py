"""Built-in terminal UI engine — status lines, tables, prompts, styled text."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TextIO

from ship.ui.format import pad_visible
from ship.ui.progress import Progress
from ship.ui.theme import DEFAULT_THEME, Style, Theme


def _env_wants_color(stream: TextIO) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return stream.isatty()


@dataclass(slots=True)
class Column:
    header: str
    width: int
    style: str | None = None


class UI:
    """Single renderer used by CLI and install/runtime status output."""

    __slots__ = ("action_width", "color", "err", "out", "theme")

    def __init__(
        self,
        *,
        out: TextIO | None = None,
        err: TextIO | None = None,
        theme: Theme | None = None,
        color: bool | None = None,
        action_width: int = 12,
    ) -> None:
        self.out = out or sys.stdout
        self.err = err or sys.stderr
        self.theme = theme or DEFAULT_THEME
        self.color = _env_wants_color(self.out) if color is None else color
        self.action_width = action_width

    def style(self, text: object, name: str | Style) -> str:
        style = name if isinstance(name, Style) else getattr(self.theme, name)
        return style.wrap(text, enabled=self.color)

    def c(self, text: object, color_code: str) -> str:
        """Low-level ANSI paint kept for rare call sites that need raw codes."""
        if not self.color:
            return str(text)
        return f"\033[{color_code}m{text}\033[0m"

    def _line(self, action: str, message: str, style: Style, *, stream: TextIO) -> None:
        verb = style.wrap(action.rjust(self.action_width), enabled=self.color)
        print(f"{verb} {message}", file=stream)

    def status(self, action: str, message: str) -> None:
        self._line(action, message, self.theme.action, stream=self.out)

    def info(self, message: str) -> None:
        self._line("info:", message, self.theme.info, stream=self.out)

    def warn(self, message: str) -> None:
        self._line("warning:", message, self.theme.warning, stream=self.err)

    def die(self, message: str, code: int = 1) -> None:
        self._line("error:", message, self.theme.error, stream=self.err)
        raise SystemExit(code)

    def blank(self) -> None:
        print(file=self.out)

    def heading(self, text: str) -> None:
        print(self.style(text, self.theme.bold), file=self.out)

    def title(self, text: str) -> None:
        print(self.style(text, self.theme.package), file=self.out)

    def bullet(self, text: str, *, mark: str = "•") -> None:
        print(f"  {mark} {text}", file=self.out)

    def kv(self, key: str, value: str, *, key_width: int = 14) -> None:
        print(f"  {key:<{key_width}} {value}", file=self.out)

    def channel_style(self, channel: str) -> Style:
        return {
            "stable": self.theme.channel_stable,
            "prerelease": self.theme.channel_prerelease,
            "nightly": self.theme.channel_nightly,
        }.get(channel, self.theme.muted)

    def table(
        self,
        columns: Sequence[Column],
        rows: Iterable[Sequence[object]],
        *,
        indent: str = "  ",
    ) -> None:
        header = indent + " ".join(
            pad_visible(self.style(col.header, self.theme.bold), col.width)
            for col in columns
        )
        rule = indent + " ".join(
            pad_visible(
                self.style("─" * max(1, col.width - 2), self.theme.dim), col.width
            )
            for col in columns
        )
        print(header, file=self.out)
        print(rule, file=self.out)
        for row in rows:
            cells = []
            for col, cell in zip(columns, row, strict=False):
                painted = self.style(cell, col.style) if col.style else str(cell)
                cells.append(pad_visible(painted, col.width))
            print(indent + " ".join(cells), file=self.out)

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        suffix = " [Y/n]: " if default else " [y/N]: "
        try:
            answer = input(prompt + suffix).strip().casefold()
        except (EOFError, KeyboardInterrupt):
            print(file=self.out)
            return False
        if not answer:
            return default
        return answer in {"y", "yes"}

    def progress(
        self,
        action: str,
        label: str,
        *,
        unit: str = "bytes",
        total: int | None = None,
    ) -> Progress:
        return Progress(
            action,
            label,
            unit=unit,
            total=total,
            theme=self.theme,
            color=self.color,
            status_fn=self.status,
        )


# Process-wide default UI — install/runtime/cli all share one renderer.
ui = UI()


def c(text: object, color_code: str) -> str:
    return ui.c(text, color_code)


def status(action: str, message: str) -> None:
    ui.status(action, message)


def info(message: str) -> None:
    ui.info(message)


def warn(message: str) -> None:
    ui.warn(message)


def die(message: str, code: int = 1) -> None:
    ui.die(message, code)
