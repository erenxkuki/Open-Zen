"""`oz doctor`: real installation and runtime diagnostics."""
from __future__ import annotations
import os
import sys


def run_checks(sandbox_dirs=()):
    """Return [(name, passed, detail)]. All checks execute for real."""
    checks = []

    def add(name, passed, detail=""):
        checks.append((name, bool(passed), detail))

    add("python >= 3.10", sys.version_info >= (3, 10), ".".join(map(str, sys.version_info[:3])))
    try:
        import openzen  # noqa: F401
        from openzen.isa import OP_REGISTRY
        add("package import", True, f"{len(OP_REGISTRY)} ops registered")
    except Exception as e:  # pragma: no cover
        add("package import", False, str(e)[:100])
        return checks
    root = os.path.dirname(os.path.dirname(os.path.abspath(openzen.__file__)))
    spec_p = os.path.join(root, "spec", "isa", "oz-isa-1.0.json")
    add("ISA spec present", os.path.exists(spec_p), spec_p if os.path.exists(spec_p) else "missing (run scripts/gen_spec.py)")
    ex_p = os.path.join(root, "examples", "arithmetic.oz")
    add("examples present", os.path.exists(ex_p), os.path.dirname(ex_p))
    try:
        from openzen import OpenZenClient
        c = OpenZenClient.local()
        ex = c.execute_source("PROGRAM doctor_smoke\nLET x = CORE.ADD 20 22\nRETURN $x\nEND\n")
        add("smoke run", ex.ok and ex.result == 42, f"20+22={ex.result}")
    except Exception as e:
        add("smoke run", False, str(e)[:120])
    for d in sandbox_dirs or []:
        ok = os.path.isdir(d) and os.access(d, os.R_OK | os.W_OK)
        add(f"sandbox {d}", ok, "readable+writable" if ok else "missing or not writable")
    return checks
