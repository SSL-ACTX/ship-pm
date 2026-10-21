"""Terminal styling, ANSI visible-width calculation, and cargo-styled output."""

import re
import shutil
import sys
import time

USE_COLOR = sys.stdout.isatty()
ANSI_REGEX = re.compile(r"\x1b\[[0-9;]*m")


def c(text: object, color_code: str) -> str:
    if not USE_COLOR:
        return str(text)
    return f"\033[{color_code}m{text}\033[0m"


def visible_len(s: object) -> int:
    return len(ANSI_REGEX.sub("", str(s)))


def pad_visible(s: object, width: int, align: str = "left") -> str:
    extra = width - visible_len(s)
    if extra <= 0:
        return str(s)
    spaces = " " * extra
    return f"{s}{spaces}" if align == "left" else f"{spaces}{s}"


def status(action: str, message: str) -> None:
    print(f"{c(action.rjust(12), '1;32')} {message}")


def info(message: str) -> None:
    print(f"{c('info:'.rjust(12), '1;36')} {message}")


def warn(message: str) -> None:
    print(f"{c('warning:'.rjust(12), '1;33')} {message}", file=sys.stderr)


def die(message: str, code: int = 1) -> None:
    print(f"{c('error:'.rjust(12), '1;31')} {message}", file=sys.stderr)
    sys.exit(code)


def format_size(size: int) -> str:
    """Format a byte count compactly for progress output."""
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"


class Progress:
    """Compact Cargo-like progress line with a quiet non-TTY fallback."""

    def __init__(
        self,
        action: str,
        label: str,
        *,
        unit: str = "bytes",
        total: int | None = None,
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
        if self.tty:
            self._draw(force=True)
        else:
            status(action, label)

    def set_total(self, total: int | None) -> None:
        self.total = total if total and total > 0 else None
        self._draw(force=True)

    def update(self, current: int, total: int | None = None) -> None:
        self.current = max(0, current)
        if total is not None:
            self.total = total if total > 0 else None
        self._draw()

    def _draw(self, *, force: bool = False, action: str | None = None) -> None:
        if not self.tty or self.finished:
            return
        now = time.monotonic()
        if not force and now - self.last_draw < 0.08:
            return
        self.last_draw = now

        columns = _terminal_width()
        show_amount = columns >= 72
        bar_width = max(5, min(20, columns - 45))
        label_limit = max(
            4,
            min(38, columns - (bar_width + 28 + (18 if show_amount else 0))),
        )
        label = self.label
        if len(label) > label_limit:
            label = "…" + label[-(label_limit - 1) :]

        if self.total is not None:
            fraction = min(1.0, self.current / self.total)
            filled = int(fraction * bar_width)
            bar = c("=" * filled, "1;36") + c(" " * (bar_width - filled), "2")
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
            progress = f"{c(spinner, '1;36')} {amount}"

        message = f"{c((action or self.action).rjust(12), '1;32')} {label} {progress}"
        sys.stdout.write("\r\033[2K" + message)
        sys.stdout.flush()

    def finish(self, *, success: bool = True, detail: str = "") -> None:
        if self.finished:
            return
        elapsed = max(time.monotonic() - self.started, 0.001)
        self.finished = True
        action = (
            "Downloaded"
            if self.action == "Downloading"
            else "Extracted"
            if self.action == "Extracting"
            else self.action
        )
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
        else:
            status(action, f"{self.label}: {result}")


def _terminal_width() -> int:
    """Return a safe width for the current output terminal."""
    try:
        return max(40, min(120, shutil.get_terminal_size().columns))
    except OSError:
        return 80
