"""Declarative CLI engine — truthful help, lazy dispatch, fast cold start."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from ship.ui import ui


@dataclass(frozen=True, slots=True)
class Argument:
    name: str
    help: str = ""
    required: bool = True
    variadic: bool = False


@dataclass(frozen=True, slots=True)
class Option:
    flags: tuple[str, ...]
    dest: str
    help: str = ""
    takes_value: bool = False
    metavar: str = "value"
    default: Any = None
    global_: bool = False


@dataclass(slots=True)
class Namespace:
    command: str | None = None
    rest: list[str] = field(default_factory=list)
    values: dict[str, Any] = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        try:
            return self.values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def get(self, name: str, default: Any = None) -> Any:
        return self.values.get(name, default)


Handler = Callable[[Namespace], None]


def lazy(path: str) -> Handler:
    """Import ``module:attr`` only when the command actually runs."""

    def _handler(ns: Namespace) -> None:
        module_name, _, attr = path.partition(":")
        module = importlib.import_module(module_name)
        getattr(module, attr)(ns)

    _handler.__ship_lazy__ = path  # type: ignore[attr-defined]
    return _handler


@dataclass(slots=True)
class Command:
    name: str
    help: str
    handler: Handler
    aliases: tuple[str, ...] = ()
    args: tuple[Argument, ...] = ()
    opts: tuple[Option, ...] = ()
    usage: str | None = None

    def all_names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)

    def usage_line(self, prog: str) -> str:
        if self.usage:
            return f"{prog} {self.usage}"
        parts = [prog, self.name]
        for opt in self.opts:
            flag = opt.flags[0]
            if opt.takes_value:
                parts.append(f"[{flag} <value>]")
            else:
                parts.append(f"[{flag}]")
        for arg in self.args:
            token = f"<{arg.name}>" if arg.required else f"[{arg.name}]"
            if arg.variadic:
                token = f"{token}..."
            parts.append(token)
        return " ".join(parts)


class CliEngine:
    """Command registry + parser. Help is generated from registered metadata."""

    def __init__(
        self,
        *,
        name: str,
        version: str,
        about: str,
        global_opts: tuple[Option, ...] = (),
    ) -> None:
        self.name = name
        self.version = version
        self.about = about
        self.global_opts = global_opts
        self._commands: dict[str, Command] = {}
        self._primary: list[Command] = []

    def add(self, command: Command) -> None:
        self._primary.append(command)
        for alias in command.all_names():
            if alias in self._commands:
                raise ValueError(f"duplicate command name/alias: {alias}")
            self._commands[alias] = command

    def command(self, *commands: Command) -> None:
        for command in commands:
            self.add(command)

    def find(self, name: str) -> Command | None:
        return self._commands.get(name)

    def render_help(self, command: Command | None = None) -> str:
        if command is None:
            return self._render_root_help()
        return self._render_command_help(command)

    def _paint(self, text: str, style: str) -> str:
        return ui.style(text, style)

    def _render_root_help(self) -> str:
        lines = [
            f"{self._paint(self.name, 'package')} {self.version}",
            self.about,
            "",
            f"{self._paint('USAGE:', 'bold')}",
            f"    {self._paint(self.name, 'package')} [OPTIONS] <COMMAND>",
            "",
            f"{self._paint('COMMANDS:', 'bold')}",
        ]
        width = max(len(self._command_label(cmd)) for cmd in self._primary)
        for cmd in self._primary:
            label = self._command_label(cmd)
            lines.append(
                f"    {self._paint(label.ljust(width), 'package')}  {cmd.help}"
            )
        if self.global_opts:
            lines.append("")
            lines.append(f"{self._paint('OPTIONS:', 'bold')}")
            lines.extend(self._format_options(self.global_opts))
        lines.append("")
        lines.append(
            f"Run '{self._paint(f'{self.name} <COMMAND> --help', 'bold')}' "
            "for command-specific help."
        )
        lines.append("")
        return "\n".join(lines)

    def _command_label(self, cmd: Command) -> str:
        if cmd.aliases:
            return f"{cmd.name}, {', '.join(cmd.aliases)}"
        return cmd.name

    def _format_options(self, opts: Sequence[Option]) -> list[str]:
        labels: list[str] = []
        for opt in opts:
            if opt.takes_value:
                labels.append(f"{', '.join(opt.flags)} <{opt.metavar}>")
            else:
                labels.append(", ".join(opt.flags))
        width = max((len(label) for label in labels), default=0)
        rows = []
        for opt, label in zip(opts, labels, strict=True):
            rows.append(f"    {self._paint(label.ljust(width), 'package')}  {opt.help}")
        return rows

    def _render_command_help(self, command: Command) -> str:
        lines = [
            f"{self._paint(self.name + ' ' + command.name, 'package')} — {command.help}",
            "",
            f"{self._paint('USAGE:', 'bold')}",
            f"    {command.usage_line(self.name)}",
        ]
        if command.args:
            lines.append("")
            lines.append(f"{self._paint('ARGUMENTS:', 'bold')}")
            width = max(len(arg.name) for arg in command.args)
            for arg in command.args:
                req = "" if arg.required else " (optional)"
                help_text = f"{arg.help}{req}" if arg.help else req.lstrip()
                lines.append(
                    f"    {self._paint(arg.name.ljust(width), 'package')}  {help_text}"
                )
        opts = (*self.global_opts, *command.opts)
        if opts:
            lines.append("")
            lines.append(f"{self._paint('OPTIONS:', 'bold')}")
            lines.extend(self._format_options(opts))
        lines.append("")
        return "\n".join(lines)

    def _parse_options(
        self,
        argv: list[str],
        opts: Sequence[Option],
        values: dict[str, Any],
    ) -> list[str]:
        by_flag = {flag: opt for opt in opts for flag in opt.flags}
        rest: list[str] = []
        idx = 0
        while idx < len(argv):
            token = argv[idx]
            if token == "--":
                rest.extend(argv[idx + 1 :])
                break
            if token.startswith("-") and token in by_flag:
                opt = by_flag[token]
                if opt.takes_value:
                    idx += 1
                    if idx >= len(argv):
                        ui.die(f"Option {token} requires a value.")
                    values[opt.dest] = argv[idx]
                else:
                    values[opt.dest] = True
                idx += 1
                continue
            if token.startswith("--") and "=" in token:
                flag, _, value = token.partition("=")
                if flag in by_flag:
                    opt = by_flag[flag]
                    if not opt.takes_value:
                        ui.die(f"Option {flag} does not take a value.")
                    values[opt.dest] = value
                    idx += 1
                    continue
            if token.startswith("-") and len(token) > 2 and not token.startswith("--"):
                # clustered short flags are unsupported — keep literal for clarity
                rest.append(token)
                idx += 1
                continue
            rest.append(token)
            idx += 1
        return rest

    def parse(self, argv: Sequence[str] | None = None) -> Namespace:
        raw = list(sys.argv[1:] if argv is None else argv)
        ns = Namespace()
        for opt in self.global_opts:
            ns.values[opt.dest] = opt.default

        # Fast path: bare help / version before any command lookup work.
        if not raw or raw[0] in {"-h", "--help", "help"}:
            ns.values["_global_help"] = True
            return ns
        if raw[0] in {"-V", "--version"}:
            ns.values["_global_version"] = True
            return ns

        cmd_idx = -1
        command = None
        for i, token in enumerate(raw):
            if token == "--":
                break
            if not token.startswith("-"):
                cand = self.find(token)
                if cand is not None:
                    cmd_idx = i
                    command = cand
                    break

        if command is None:
            # No recognized command; parse global options and exit
            self._parse_options(raw, [opt for opt in self.global_opts], ns.values)
            if not ns.values.get("help") and not ns.values.get("version"):
                first_cmd = next((t for t in raw if not t.startswith("-")), None)
                if first_cmd:
                    ui.die(
                        f"Unknown command: '{first_cmd}'. Run '{self.name} --help' for usage."
                    )
                ns.values["help"] = True
            return ns

        # Parse global options strictly before the command
        self._parse_options(raw[:cmd_idx], [opt for opt in self.global_opts], ns.values)
        ns.command = command.name
        for opt in command.opts:
            ns.values.setdefault(opt.dest, opt.default)

        # After the command name:
        after_cmd = raw[cmd_idx + 1 :]
        if "--" in after_cmd:
            split_idx = after_cmd.index("--")
            before_dd = after_cmd[:split_idx]
            trailing_raw = after_cmd[split_idx + 1 :]
        else:
            before_dd = after_cmd
            trailing_raw = []

        has_variadic = any(arg.variadic for arg in command.args)
        if has_variadic:
            # If command accepts variadic arguments/subcommands, prioritize help flags
            # while letting command-specific options parse.
            opts_to_parse = (
                *[
                    opt
                    for opt in self.global_opts
                    if opt.dest in ("help", "_global_help")
                ],
                *command.opts,
            )
        else:
            opts_to_parse = (*self.global_opts, *command.opts)

        remaining = self._parse_options(before_dd, opts_to_parse, ns.values)
        if trailing_raw:
            remaining.extend(trailing_raw)

        if ns.values.get("_global_help") or ns.values.get("help"):
            return ns

        # Bind positional arguments.
        args = command.args
        if not args:
            ns.rest = remaining
            if remaining:
                ui.die(
                    f"Unexpected argument '{remaining[0]}'.\n"
                    f"Usage: {command.usage_line(self.name)}"
                )
            return ns

        bound: list[str] = []
        idx = 0
        for arg in args:
            if arg.variadic:
                if arg.required and idx >= len(remaining):
                    ui.die(
                        f"Missing argument <{arg.name}>.\n"
                        f"Usage: {command.usage_line(self.name)}"
                    )
                ns.values[arg.name] = remaining[idx:]
                idx = len(remaining)
                break
            if idx >= len(remaining):
                if arg.required:
                    ui.die(
                        f"Missing argument <{arg.name}>.\n"
                        f"Usage: {command.usage_line(self.name)}"
                    )
                ns.values[arg.name] = None
                continue
            ns.values[arg.name] = remaining[idx]
            bound.append(remaining[idx])
            idx += 1
        else:
            if idx < len(remaining):
                ui.die(
                    f"Unexpected argument '{remaining[idx]}'.\n"
                    f"Usage: {command.usage_line(self.name)}"
                )
        ns.rest = remaining[idx:]
        return ns

    def run(self, argv: Sequence[str] | None = None) -> None:
        ns = self.parse(argv)
        if ns.values.get("_global_version") is True:
            print(f"{self.name} {self.version}")
            return
        if ns.values.get("_global_help") and not ns.command:
            print(self.render_help(), end="")
            return
        assert ns.command is not None
        command = self._commands[ns.command]
        if ns.values.get("_global_help") or ns.values.get("help"):
            print(self.render_help(command), end="")
            return
        command.handler(ns)
