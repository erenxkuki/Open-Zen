"""Terminal theme: restrained monochrome + status colors, with plain-text mode.

Palette: white primary, cyan instructions/runtime, green success,
yellow approval, red errors, gray metadata. Colors are disabled when
stdout/stderr are not TTYs, when NO_COLOR/OZ_PLAIN is set, or with --plain.
Symbol glyphs are kept in plain mode (UTF-8 text, no ANSI codes) so CI logs
and screen readers still get the structure.
"""
from __future__ import annotations
import os
import sys

CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "white": "\033[37m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "gray": "\033[90m",
}

_enabled = False
_quiet = False


def configure(plain=False, quiet=False):
    global _enabled, _quiet
    _quiet = quiet
    if plain or os.environ.get("NO_COLOR") or os.environ.get("OZ_PLAIN"):
        _enabled = False
        return
    try:
        tty = sys.stdout.isatty() or sys.stderr.isatty()
    except Exception:
        tty = False
    _enabled = bool(tty)


def enabled():
    return _enabled


def quiet():
    return _quiet


def paint(text, *names):
    if not _enabled or not names:
        return text
    return "".join(CODES[n] for n in names) + text + CODES["reset"]


# Status symbols (kept in plain mode; color carries the severity).
SYM_OK = "✓"
SYM_NEED = "?"
SYM_DENY = "✗"
SYM_DOT = "●"
SYM_TREE = ("├── ", "└── ", "│   ", "    ")
