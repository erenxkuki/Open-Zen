"""Human-facing rendering: pipeline stages, policy box, trace tree, inspector.

Every line reflects a real execution event or real runtime state.
Nothing here is decorative data: no fake CPU/GPU meters, no invented metrics.
"""
from __future__ import annotations
import sys
from . import theme
from .theme import SYM_OK, SYM_NEED, SYM_DENY


def estage(n, label, detail=""):
    """Pipeline stage line to stderr (stdout stays machine-readable)."""
    if theme.quiet():
        return
    line = theme.paint(f"[{n:02d}]", "gray") + " " + theme.paint(label, "bold", "white")
    if detail:
        line += "  " + theme.paint(detail, "gray")
    print(line, file=sys.stderr, flush=True)


def ok_line(label, detail=""):
    if theme.quiet():
        return
    line = theme.paint(f"  {SYM_OK} ", "green") + theme.paint(label, "white")
    if detail:
        line += "  " + theme.paint(detail, "gray")
    print(line, file=sys.stderr, flush=True)


def warn_line(label, detail=""):
    if theme.quiet():
        return
    line = theme.paint(f"  {SYM_NEED} ", "yellow") + theme.paint(label, "yellow")
    if detail:
        line += "  " + theme.paint(detail, "gray")
    print(line, file=sys.stderr, flush=True)


def err_line(label, detail=""):
    line = theme.paint(f"  {SYM_DENY} ", "red") + theme.paint(label, "red")
    if detail:
        line += "  " + theme.paint(detail, "gray")
    print(line, file=sys.stderr, flush=True)


def fmt_error(err):
    code = (err or {}).get("code", "ERROR")
    msg = (err or {}).get("message", "")
    det = (err or {}).get("details", {})
    head = theme.paint(f"{SYM_DENY} {code}", "red", "bold") + ": " + theme.paint(msg, "white")
    if det:
        head += "\n" + theme.paint("  details: " + str(det)[:400], "gray")
    return head


def describe_stmt(s):
    """One-line human description of a statement (used by stepping/explain)."""
    k = s.get("kind")
    if k == "let":
        args = " ".join(_short(a) for a in s.get("args", []))
        return f"LET {s.get('target')} = {s.get('op')}" + (f" {args}" if args else "")
    if k == "let_literal":
        return f"LET {s.get('target')} = {_short(s.get('value'))}"
    if k == "return":
        return f"RETURN {_short(s.get('value'))}"
    if k == "if":
        return f"IF {_short(s.get('cond'))} THEN … (else {len(s.get('else', []))} stmts)"
    if k == "for":
        return f"FOR {s.get('target')} IN {_short(s.get('iterable'))} DO … ({len(s.get('body', []))} stmts)"
    return f"<?> {s!r}"[:100]


def _short(node):
    from .program import is_varref, is_literal
    if is_varref(node):
        return "$" + node["var"]
    if is_literal(node):
        v = node["literal"]
        s = repr(v)
        return s if len(s) <= 40 else s[:37] + "…"
    if isinstance(node, dict) and node.get("kind") == "opcall":
        return node["op"] + "(…)"
    return "?"


def policy_rows(caps):
    """Real capability state as (scope, label, state) rows.

    state: 'granted' | 'approval' (granted but approval-gated) | 'denied'.
    """
    def row(cap, label):
        if not caps.requires(cap):
            return (label.split()[0], label, "denied")
        from .isa import OP_REGISTRY
        gated = any(o.capability == cap and o.name in caps.require_approval_for
                    for o in OP_REGISTRY)
        return (label.split()[0], label, "approval" if gated else "granted")

    rows = [
        row("fs.read", "Filesystem READ"),
        row("fs.write", "Filesystem WRITE"),
        row("fs.delete", "Filesystem DELETE"),
        row("proc.list", "Process LIST"),
        row("proc.launch", "Process SPAWN"),
        row("proc.kill", "Process KILL"),
        row("sys.info", "System INFO"),
        row("sys.env", "Environment VARS"),
        row("net.fetch", "Network FETCH"),
    ]
    return rows


def policy_box(caps):
    rows = policy_rows(caps)
    glyph = {"granted": (SYM_OK, "green"), "approval": (SYM_NEED, "yellow"), "denied": (SYM_DENY, "red")}
    word = {"granted": "GRANTED", "approval": "APPROVAL", "denied": "DENIED"}
    width = max(len(r[1]) for r in rows)
    top = "┌──── EXECUTION POLICY " + "─" * (width + 12 - 22) + "┐"
    lines = [theme.paint(top, "gray")]
    for _, label, state in rows:
        g, color = glyph[state]
        lines.append("│ " + theme.paint(label.ljust(width), "white") + "  " +
                     theme.paint(f"{g} {word[state]}", color) + " │")
    lines.append(theme.paint("└" + "─" * (width + 14) + "┘", "gray"))
    extra = []
    if caps.allowed_dirs:
        extra.append(theme.paint("  sandbox: " + ", ".join(caps.allowed_dirs)[:120], "gray"))
    if caps.allowed_programs:
        extra.append(theme.paint("  allowlist programs: " + ", ".join(caps.allowed_programs)[:120], "gray"))
    if caps.allowed_hosts:
        extra.append(theme.paint("  allowlist hosts: " + ", ".join(caps.allowed_hosts)[:120], "gray"))
    if caps.allowed_env_vars:
        extra.append(theme.paint("  allowlist env: " + ", ".join(caps.allowed_env_vars)[:120], "gray"))
    return "\n".join(lines + extra)


def trace_tree(trace):
    """Render the real runtime trace as a tree."""
    if not trace:
        return theme.paint("  (empty trace)", "gray")
    lines = []
    for i, t in enumerate(trace):
        last = i == len(trace) - 1
        fork = "└── " if last else "├── "
        op = t.get("op", "?")
        bits = []
        if "target" in t:
            bits.append(f"→ {t['target']}")
        if t.get("taken"):
            bits.append(f"branch={t['taken']}")
        if t.get("count") is not None:
            bits.append(f"n={t['count']}")
        status = theme.paint(SYM_OK, "green") if t.get("ok") else theme.paint(SYM_DENY, "red")
        lines.append(f"{fork}{theme.paint(op, 'cyan')} {' '.join(bits)} {status}".rstrip())
    head = theme.paint(f"TRACE  ({len(trace)} events)", "bold", "white")
    return head + "\n" + "\n".join(lines)


def inspect_table(detail):
    fam_color = {"COMPUTE": "cyan", "FILESYSTEM": "cyan", "PROCESS": "yellow",
                 "SYSTEM": "cyan", "NETWORK": "yellow", "CONTROL": "white", "OUTPUT": "green"}
    lines = [
        f"PROGRAM:      {theme.paint(detail['name'], 'bold', 'white')}",
        f"ISA:          {detail['isa']}    FORMAT: OZB v{detail['format']}",
        f"INSTRUCTIONS: {len(detail['items'])}    SIZE: {detail['size']} bytes",
        "",
        theme.paint(f"{'OFFSET':<10}{'OPCODE':<22}{'KIND':<14}FAMILY", "gray"),
    ]
    for it in detail["items"]:
        indent = "  " * min(it["depth"], 3)
        lines.append(f"{it['offset']:#08x}  " +
                     theme.paint((indent + it["op"])[:21].ljust(21), fam_color.get(it["family"], "white")) +
                     f" {it['kind']:<13} {it['family']}")
    return "\n".join(lines)


def explain_program(prog):
    from .isa import OP_BY_NAME
    lines = [theme.paint(f"PROGRAM {prog.name} — {len(prog.statements)} top-level statements:", "bold", "white")]

    def walk(stmts, depth):
        for s in stmts:
            pad = "  " * (depth + 1)
            k = s["kind"]
            if k == "let":
                spec = OP_BY_NAME.get(s["op"])
                desc = spec.description if spec else "unknown op"
                cap = f" [{spec.capability}]" if spec else ""
                lines.append(f"{pad}{theme.paint('LET', 'cyan')} {s['target']} = "
                             f"{theme.paint(s['op'], 'cyan')}{theme.paint(cap, 'gray')}")
                lines.append(f"{pad}  └─ {desc}")
            elif k == "let_literal":
                lines.append(f"{pad}{theme.paint('LET', 'cyan')} {s['target']} = {_short(s['value'])}")
            elif k == "return":
                lines.append(f"{pad}{theme.paint('RETURN', 'green')} {_short(s['value'])}")
            elif k == "if":
                lines.append(f"{pad}{theme.paint('IF', 'cyan')} {_short(s['cond'])}")
                walk(s["then"], depth + 1)
                if s["else"]:
                    lines.append(f"{pad}{theme.paint('ELSE', 'cyan')}")
                    walk(s["else"], depth + 1)
            elif k == "for":
                lines.append(f"{pad}{theme.paint('FOR', 'cyan')} {s['target']} over "
                             f"{_short(s['iterable'])} (≤{s.get('max_iter', '?')} iters)")
                walk(s["body"], depth + 1)
    walk(prog.statements, 0)
    req = prog.required_capabilities()
    if req:
        lines.append(theme.paint("requires capabilities: " + ", ".join(req), "yellow"))
    else:
        lines.append(theme.paint("requires no special capabilities (compute only).", "gray"))
    return "\n".join(lines)
