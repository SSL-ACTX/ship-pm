"""Terminal styling, ANSI visible-width calculation, and cargo-styled output."""

import re
import sys

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
