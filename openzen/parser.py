"""Text source parser for OZ-ISA human-readable syntax (v1, line-oriented)."""
from __future__ import annotations
import re
from .program import Program, var, lit
from .values import OzError

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_OP = re.compile(r"^[A-Z]+\.[A-Z_0-9]+$")
_INT = re.compile(r"^[+-]?\d+$")
_FLOAT = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")


def _strip_comment(line):
    out, in_str, esc = [], False, False
    for ch in line:
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
                out.append(ch)
            elif ch == "#":
                break
            else:
                out.append(ch)
    return "".join(out)


def _tokenize(s):
    toks = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c.isspace():
            i += 1
            continue
        if c == '"':
            j = i + 1
            buf = []
            closed = False
            while j < n:
                ch = s[j]
                if ch == "\\" and j + 1 < n:
                    nxt = s[j + 1]
                    buf.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, nxt))
                    j += 2
                elif ch == '"':
                    closed = True
                    break
                else:
                    buf.append(ch)
                    j += 1
            if not closed:
                raise OzError("PARSE_ERROR", "Unterminated string literal.")
            toks.append(("str", "".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and not s[j].isspace():
                j += 1
            toks.append(("word", s[i:j]))
            i = j
    return toks


def _parse_value_token(kind, text):
    if kind == "str":
        return lit(text)
    w = text
    if w == "true":
        return lit(True)
    if w == "false":
        return lit(False)
    if w == "null":
        return lit(None)
    if _INT.match(w):
        try:
            return lit(int(w))
        except ValueError:
            pass
    if _FLOAT.match(w):
        try:
            return lit(float(w))
        except ValueError:
            pass
    if w.startswith("$"):
        name = w[1:]
        if not _NAME.match(name):
            raise OzError("PARSE_ERROR", f"Bad variable name: {w!r}")
        return var(name)
    if _OP.match(w):
        raise OzError("PARSE_ERROR", f"Unexpected op reference {w!r} in value position.")
    if _NAME.match(w):
        return var(w)
    raise OzError("PARSE_ERROR", f"Cannot parse token: {w!r}")


def _parse_expr(tokens):
    if not tokens:
        raise OzError("PARSE_ERROR", "Empty expression.")
    if tokens[0][0] == "word" and _OP.match(tokens[0][1]):
        op = tokens[0][1]
        args = [_parse_value_token(k, t) if not (k == "word" and _OP.match(t))
                else (_ for _ in ()).throw(OzError("PARSE_ERROR", "Nested op calls are not supported in v1; use LET temporaries."))
                for k, t in tokens[1:]]
        return ("opcall", op, args)
    if len(tokens) == 1:
        k, t = tokens[0]
        return _parse_value_token(k, t)
    raise OzError("PARSE_ERROR", "Invalid expression: bare values and op calls cannot be mixed.")


def _to_ir_expr(parsed):
    if isinstance(parsed, tuple) and parsed[0] == "opcall":
        _, op, args = parsed
        return {"kind": "opcall", "op": op, "args": args}
    return parsed


def parse_source(text):
    prog_name = None
    ended = False
    # stack of frames; each frame: {"type": "root"|"if"|"for", ...}
    root = {"type": "root", "stmts": []}
    stack = [root]

    def emit(s):
        top = stack[-1]
        if top["type"] == "root":
            top["stmts"].append(s)
        elif top["type"] == "if":
            (top["then"] if top["in_else"] is False else top["else"]).append(s)
        elif top["type"] == "for":
            top["body"].append(s)

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        try:
            upper = line.upper()
            if upper.startswith("PROGRAM "):
                if prog_name is not None:
                    raise OzError("PARSE_ERROR", "Duplicate PROGRAM header.")
                name = line[8:].strip()
                if not _NAME.match(name):
                    raise OzError("PARSE_ERROR", f"Bad program name: {name!r}")
                prog_name = name
                continue
            if prog_name is None:
                raise OzError("PARSE_ERROR", "First non-empty line must be PROGRAM <name>.")
            if upper == "END":
                if len(stack) == 1:
                    ended = True
                    break
                fr = stack.pop()
                if fr["type"] == "if":
                    emit({"kind": "if", "cond": fr["cond"], "then": fr["then"], "else": fr["else"]})
                elif fr["type"] == "for":
                    emit({"kind": "for", "target": fr["target"], "iterable": fr["iter"],
                          "body": fr["body"], "max_iter": fr["max_iter"]})
                continue
            if upper == "ELSE":
                if len(stack) < 2 or stack[-1]["type"] != "if" or stack[-1]["in_else"]:
                    raise OzError("PARSE_ERROR", "ELSE without IF.")
                stack[-1]["in_else"] = True
                continue
            toks = _tokenize(line)
            first = toks[0][1].upper() if toks[0][0] == "word" else ""
            if first == "LET":
                try:
                    eq = next(i for i, t in enumerate(toks) if t[0] == "word" and t[1] == "=")
                except StopIteration:
                    raise OzError("PARSE_ERROR", "LET requires '='.")
                if eq != 2 or toks[1][0] != "word" or not _NAME.match(toks[1][1]):
                    raise OzError("PARSE_ERROR", "Usage: LET <var> = <expr>.")
                target = toks[1][1]
                expr = _to_ir_expr(_parse_expr(toks[eq + 1:]))
                if isinstance(expr, dict) and expr.get("kind") == "opcall":
                    emit({"kind": "let", "target": target, "op": expr["op"], "args": expr["args"]})
                elif isinstance(expr, dict):
                    emit({"kind": "let_literal", "target": target, "value": expr})
                else:
                    raise OzError("PARSE_ERROR", "Bad LET expression.")
                continue
            if first == "IF":
                if not (len(toks) >= 3 and toks[-1][0] == "word" and toks[-1][1].upper() == "THEN"):
                    raise OzError("PARSE_ERROR", "Usage: IF <expr> THEN.")
                cond = _to_ir_expr(_parse_expr(toks[1:-1]))
                stack.append({"type": "if", "cond": cond, "then": [], "else": [], "in_else": False})
                continue
            if first == "FOR":
                if not (len(toks) >= 5 and toks[-1][0] == "word" and toks[-1][1].upper() == "DO"
                        and toks[2][0] == "word" and toks[2][1].upper() == "IN"):
                    raise OzError("PARSE_ERROR", "Usage: FOR <var> IN <expr> DO.")
                if toks[1][0] != "word" or not _NAME.match(toks[1][1]):
                    raise OzError("PARSE_ERROR", f"Bad loop variable: {toks[1][1]!r}")
                it = _to_ir_expr(_parse_expr(toks[3:-1]))
                stack.append({"type": "for", "target": toks[1][1], "iter": it,
                              "body": [], "max_iter": 1000})
                continue
            if first == "RETURN":
                expr = _to_ir_expr(_parse_expr(toks[1:]))
                emit({"kind": "return", "value": expr})
                continue
            raise OzError("PARSE_ERROR", f"Unknown statement: {line!r}")
        except OzError as e:
            if "line" not in e.details:
                e.details = {**e.details, "line": lineno, "text": raw.strip()}
            raise

    if prog_name is None:
        raise OzError("PARSE_ERROR", "Missing PROGRAM header.")
    if not ended:
        raise OzError("PARSE_ERROR", "Missing final END.")
    if len(stack) != 1:
        raise OzError("PARSE_ERROR", "Unclosed block (missing END).")
    return Program(prog_name, root["stmts"])
