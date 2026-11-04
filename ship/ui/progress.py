"""TTY progress renderer used by downloads and extraction."""

from __future__ import annotations

import shutil
import sys
import time

from ship.ui.format import format_size
from ship.ui.theme import DEFAULT_THEME, Theme


def terminal_width() -> int:
    try:
        return max(40, min(120, shutil.get_terminal_size().columns))
    except OSError:
        return 80


class Progress:
    """Compact progress line with a quiet non-TTY fallback."""

    __slots__ = (
        "_color",
        "_status",
        "_theme",
        "action",
        "current",
        "finished",
        "label",
        "last_draw",
        "started",
        "total",
        "tty",
        "unit",
    )

    def __init__(
        self,
        action: str,
        label: str,
        *,
        unit: str = "bytes",
        total: int | None = None,
        theme: Theme | None = None,
        color: bool | None = None,
        status_fn=None,
    ) -> None:
        self.action = action
        self.label = label
        self.unit = unit
        self.total = total if total and total > 0 else None
        self.current = 0
        self.started = time.monotonic()
        self.last_draw = 0.0
        self.tty = sys.stdout.isatty()
        self.finished = False
        self._theme = theme or DEFAULT_THEME
        self._color = sys.stdout.isatty() if color is None else color
        self._status = status_fn
        if self.tty:
            self._draw(force=True)
        elif self._status is not None:
            self._status(action, label)

    def set_total(self, total: int | None) -> None:
        self.total = total if total and total > 0 else None
        self._draw(force=True)

    def update(self, current: int, total: int | None = None) -> None:
        self.current = max(0, current)
        if total is not None:
            self.total = total if total > 0 else None
        self._draw()

    def _paint(self, text: object, style) -> str:
        return style.wrap(text, enabled=self._color)

    def _draw(self, *, force: bool = False, action: str | None = None) -> None:
        if not self.tty or self.finished:
            return
        now = time.monotonic()
        if not force and now - self.last_draw < 0.05:
            return
        self.last_draw = now

        columns = terminal_width()
        show_amount = columns >= 72
        bar_width = max(5, min(20, columns - 45))
        label_limit = max(
            4,
            min(38, columns - (bar_width + 28 + (18 if show_amount else 0))),
        )
        label = self.label
        if len(label) > label_limit:
            label = "…" + label[-(label_limit - 1) :]

        theme = self._theme
        if self.total is not None:
            fraction = min(1.0, self.current / self.total)
            filled = int(fraction * bar_width)
            bar = self._paint("=" * filled, theme.info) + self._paint(
                " " * (bar_width - filled), theme.dim
            )
            percent = f"{fraction * 100:3.0f}%"
            if self.unit == "bytes":
                amount = f"{format_size(self.current)} / {format_size(self.total)}"
            else:
                amount = f"{self.current} / {self.total} {self.unit}"
            progress = f"[{bar}] {percent}" + (f" {amount}" if show_amount else "")
        else:
            spinner = "|/-\\"[int(now * 10) % 4]
            amount = (
                format_size(self.current)
                if self.unit == "bytes"
                else f"{self.current} {self.unit}"
            )
            progress = f"{self._paint(spinner, theme.info)} {amount}"

        verb = (action or self.action).rjust(12)
        message = f"{self._paint(verb, theme.action)} {label} {progress}"
        sys.stdout.write("\r\033[2K" + message)
        sys.stdout.flush()

    def finish(self, *, success: bool = True, detail: str = "") -> None:
        if self.finished:
            return
        elapsed = max(time.monotonic() - self.started, 0.001)
        self.finished = True
        action = {
            "Downloading": "Downloaded",
            "Extracting": "Extracted",
        }.get(self.action, self.action)
        if not success:
            action = "Failed"
        elif self.total is None and self.current:
            self.total = self.current

        if self.unit == "bytes":
            result = format_size(self.current)
        else:
            result = f"{self.current} {self.unit}"
        if self.action == "Downloading" and success:
            result += f" in {elapsed:.1f}s"
        if detail:
            result += f" ({detail})"

        if self.tty:
            self.finished = False
            self._draw(force=True, action=action)
            self.finished = True
            sys.stdout.write("\n")
            sys.stdout.flush()
        elif self._status is not None:
            self._status(action, f"{self.label}: {result}")
