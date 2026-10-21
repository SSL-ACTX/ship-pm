"""Cargo/uv-style live multi-package sync UI for check-upstream and update."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import TextIO

from ship.ui.progress import terminal_width
from ship.ui.theme import DEFAULT_THEME, Theme

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_FPS = 10
_FRAME = 1.0 / _FPS


class PkgState(Enum):
    PENDING = auto()
    CHECKING = auto()
    OK = auto()
    OUTDATED = auto()
    SKIPPED = auto()
    ERROR = auto()


@dataclass
class PkgRow:
    name: str
    state: PkgState = PkgState.PENDING
    current: str = ""
    latest: str = ""
    channel: str = "stable"
    note: str = ""


class SyncUI:
    """Live multi-line terminal display for check-upstream and update.

    A background thread redraws at 10fps independent of the main thread's
    blocking API calls, so the spinner stays smooth.
    """

    def __init__(
        self,
        names: list[str],
        *,
        heading: str = "Checking packages",
        theme: Theme | None = None,
        out: TextIO | None = None,
        color: bool | None = None,
    ) -> None:
        self._names = list(names)
        self._rows: dict[str, PkgRow] = {n: PkgRow(name=n) for n in names}
        self._heading = heading
        self._theme = theme or DEFAULT_THEME
        self._out = out or sys.stdout
        self._color = self._out.isatty() if color is None else color
        self._tty = self._out.isatty()
        self._started = time.monotonic()
        self._drawn = 0
        self._spinner_i = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _c(self, text: object, style) -> str:
        return style.wrap(str(text), enabled=self._color)

    def _state_glyph(self, row: PkgRow, spinner_char: str) -> str:
        t = self._theme
        match row.state:
            case PkgState.CHECKING:
                return self._c(spinner_char, t.info)
            case PkgState.OK:
                return self._c("✓", t.success)
            case PkgState.OUTDATED:
                return self._c("↑", t.warning)
            case PkgState.SKIPPED:
                return self._c("—", t.muted)
            case PkgState.ERROR:
                return self._c("✗", t.error)
            case _:
                return self._c("·", t.dim)

    def _render_lines(self, spinner_char: str) -> list[str]:
        t = self._theme
        cols = terminal_width()
        name_w = min(
            max((len(r.name) for r in self._rows.values()), default=10) + 2, 24
        )
        lines: list[str] = []
        for name in self._names:
            row = self._rows[name]
            glyph = self._state_glyph(row, spinner_char)
            padded_name = row.name.ljust(name_w)
            if row.state == PkgState.CHECKING:
                detail = self._c("checking...", t.dim)
            elif row.state == PkgState.OK:
                ver = (
                    self._c(row.current or row.latest, t.version)
                    if (row.current or row.latest)
                    else ""
                )
                detail = f"{ver}  {self._c('up to date', t.muted)}"
            elif row.state == PkgState.OUTDATED:
                cur = self._c(row.current or "?", t.muted)
                new = self._c(row.latest or "?", t.warning)
                detail = f"{cur} → {new}"
                if row.note:
                    detail += f"  {self._c(row.note, t.muted)}"
            elif row.state == PkgState.SKIPPED:
                detail = self._c(row.note or "skipped", t.muted)
            elif row.state == PkgState.ERROR:
                detail = self._c(row.note or "error", t.error)
            else:
                detail = ""
            line = f"  {glyph} {self._c(padded_name, t.bold)} {detail}"
            lines.append(line[: cols + 60])
        return lines

    def _erase(self) -> None:
        if self._drawn:
            self._out.write(f"\033[{self._drawn}A\033[0J")

    def _paint(self, lines: list[str]) -> None:
        self._out.write("\n".join(lines) + "\n")
        self._out.flush()
        self._drawn = len(lines)

    def _spin_loop(self) -> None:
        while not self._stop.is_set():
            deadline = time.monotonic() + _FRAME
            with self._lock:
                sc = _SPINNER[self._spinner_i % len(_SPINNER)]
                self._spinner_i += 1
                lines = self._render_lines(sc)
                self._erase()
                self._paint(lines)
            sleep = deadline - time.monotonic()
            if sleep > 0:
                time.sleep(sleep)

    def start(self) -> None:
        t = self._theme
        heading = f"  {self._c(self._heading, t.bold)} ({len(self._names)} packages)"
        if self._tty:
            self._out.write(heading + "\n")
            self._out.flush()
            with self._lock:
                self._paint(self._render_lines(_SPINNER[0]))
            self._thread = threading.Thread(target=self._spin_loop, daemon=True)
            self._thread.start()
        else:
            print(heading, file=self._out)

    def set_checking(self, name: str) -> None:
        with self._lock:
            if name in self._rows:
                self._rows[name].state = PkgState.CHECKING

    def set_result(
        self,
        name: str,
        state: PkgState,
        *,
        current: str = "",
        latest: str = "",
        channel: str = "stable",
        note: str = "",
    ) -> None:
        with self._lock:
            if name in self._rows:
                row = self._rows[name]
                row.state = state
                row.current = current
                row.latest = latest
                row.channel = channel
                row.note = note
        if not self._tty:
            sym = {
                PkgState.OK: "✓",
                PkgState.OUTDATED: "↑",
                PkgState.SKIPPED: "—",
                PkgState.ERROR: "✗",
            }.get(state, "?")
            if state == PkgState.OUTDATED:
                print(f"  {sym} {name}  {current} → {latest}", file=self._out)
            else:
                print(f"  {sym} {name}  {note or state.name.lower()}", file=self._out)

    def finish(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()

        t = self._theme
        elapsed = time.monotonic() - self._started
        counts = {s: 0 for s in PkgState}
        for row in self._rows.values():
            counts[row.state] += 1

        n_outdated = counts[PkgState.OUTDATED]
        n_ok = counts[PkgState.OK]
        n_skip = counts[PkgState.SKIPPED] + counts[PkgState.ERROR]

        parts: list[str] = []
        if n_outdated:
            parts.append(self._c(f"{n_outdated} outdated", t.warning))
        if n_ok:
            parts.append(self._c(f"{n_ok} up to date", t.success))
        if n_skip:
            parts.append(self._c(f"{n_skip} skipped", t.muted))

        summary = ", ".join(parts) if parts else self._c("nothing to report", t.muted)
        elapsed_str = self._c(f"({elapsed:.1f}s)", t.dim)

        if self._tty:
            with self._lock:
                self._erase()
                self._paint(self._render_lines("·"))
            print(
                f"\n  {self._c('Finished', t.success)}  {summary}  {elapsed_str}",
                file=self._out,
            )
        else:
            name_w = max((len(n) for n in self._names), default=10) + 2
            sym_map = {
                PkgState.OK: "✓",
                PkgState.OUTDATED: "↑",
                PkgState.SKIPPED: "—",
                PkgState.ERROR: "✗",
                PkgState.PENDING: "·",
                PkgState.CHECKING: "?",
            }
            for name in self._names:
                row = self._rows[name]
                sym = sym_map.get(row.state, "?")
                if row.state == PkgState.OUTDATED:
                    detail = f"{row.current} → {row.latest}"
                elif row.state == PkgState.OK:
                    detail = f"{row.current}  (up to date)"
                else:
                    detail = row.note or row.state.name.lower()
                print(f"  {sym} {name.ljust(name_w)} {detail}", file=self._out)
            print(
                f"\n  Finished  {n_outdated} outdated, {n_ok} up to date, {n_skip} skipped  ({elapsed:.1f}s)",
                file=self._out,
            )


class UpdateUI:
    """Install tracking display — no background thread.

    Install already prints its own download/link/patch progress.
    We just show a status line per package and a final summary.
    No spinner thread means no interleaving with install output.
    """

    def __init__(
        self,
        names: list[str],
        *,
        theme: Theme | None = None,
        out: TextIO | None = None,
        color: bool | None = None,
    ) -> None:
        self._names = list(names)
        self._theme = theme or DEFAULT_THEME
        self._out = out or sys.stdout
        self._color = self._out.isatty() if color is None else color
        self._states: dict[str, str] = {n: "pending" for n in names}
        self._started = time.monotonic()

    def _c(self, text: object, style) -> str:
        return style.wrap(str(text), enabled=self._color)

    def start(self) -> None:
        t = self._theme
        n = len(self._names)
        print(
            f"\n  {self._c('Installing', t.action)} {n} package{'s' if n != 1 else ''}",
            file=self._out,
        )

    def set_installing(self, name: str) -> None:
        self._states[name] = "installing"
        t = self._theme
        print(
            f"\n  {self._c('Installing', t.action)} {self._c(name, t.bold)}",
            file=self._out,
        )

    def set_done(self, name: str, *, success: bool = True) -> None:
        self._states[name] = "done" if success else "failed"
        t = self._theme
        if success:
            print(
                f"  {self._c('Installed', t.success)} {self._c(name, t.bold)}",
                file=self._out,
            )
        else:
            print(
                f"  {self._c('Failed', t.error)} {self._c(name, t.bold)}",
                file=self._out,
            )

    def finish(self) -> None:
        t = self._theme
        elapsed = time.monotonic() - self._started
        done = sum(1 for s in self._states.values() if s == "done")
        failed = sum(1 for s in self._states.values() if s == "failed")
        parts = [self._c(f"{done} installed", t.success)]
        if failed:
            parts.append(self._c(f"{failed} failed", t.error))
        summary = ", ".join(parts)
        elapsed_str = self._c(f"({elapsed:.1f}s)", t.dim)
        print(
            f"\n  {self._c('Finished', t.success)}  {summary}  {elapsed_str}",
            file=self._out,
        )
