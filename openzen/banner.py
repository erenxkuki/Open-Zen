"""Canonical Open Zen ASCII brand banner (terminal block font, UTF-8)."""
from __future__ import annotations

BANNER = """ ██████╗ ██████╗ ███████╗███╗   ██╗    ███████╗███████╗███╗   ██╗
██╔═══██╗██╔══██╗██╔════╝████╗  ██║    ╚══███╔╝██╔════╝████╗  ██║
██║   ██║██████╔╝█████╗  ██╔██╗ ██║      ███╔╝ █████╗  ██╔██╗ ██║
██║   ██║██╔═══╝ ██╔══╝  ██║╚██╗██║     ███╔╝  ██╔══╝  ██║╚██╗██║
╚██████╔╝██║     ███████╗██║ ╚████║    ███████╗███████╗██║ ╚████║
 ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═══╝    ╚══════╝╚══════╝╚═╝  ╚═══╝"""

TAGLINE = "AI-NATIVE INSTRUCTION LANGUAGE & EXECUTION RUNTIME"

RULE = "━" * 54
PIPELINE = "Intelligence  →  Instructions  →  Binary  →  Execution"


def full_banner():
    width = max(len(line) for line in BANNER.splitlines())
    pad = max((width - len(TAGLINE)) // 2, 0)
    return BANNER + "\n" + " " * pad + TAGLINE + "\n"


def header(status="READY", version="?", isa="1.0", fmt="1"):
    """Systems-engineering header: brand, pipeline, build facts, runtime state."""
    width = max(len(line) for line in BANNER.splitlines())
    pad = max((width - len(TAGLINE)) // 2, 0)
    return "\n".join([
        BANNER,
        "",
        " " * pad + TAGLINE,
        "  " + RULE,
        "  " + PIPELINE,
        "",
        f"  VERSION    v{version}",
        f"  ARCH       OZ-ISA v{isa}",
        f"  FORMAT     OZB v{fmt}",
        f"  RUNTIME    ● {status}",
    ]) + "\n"


def print_banner():
    """Print the banner, tolerating legacy non-UTF-8 consoles."""
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        print(full_banner())
    except UnicodeEncodeError:
        print("OPEN ZEN\n" + TAGLINE)
