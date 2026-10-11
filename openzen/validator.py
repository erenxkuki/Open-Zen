"""Static validator + type checker for OZ-ISA programs."""
from __future__ import annotations
from .isa import OP_BY_NAME, ISA_VERSION
from .program import is_varref, is_literal
from .values import OzError, oz_typeof, check_type_matches, is_number

MAX_PROGRAM_STMTS = 5000
MAX_LOOP_BOUND = 10000
MAX_VAR_NAME = 64


def _expr_vars(node, out):
    if isinstance(node, dict):
        if is_varref(node):
            out.add(node["var"])
        elif is_literal(node):
            pass
        elif node.get("kind") == "opcall":
            for a in node.get("args", []):
                _expr_vars(a, out)
    return out


def validate(program, strict_isa=True):
    """Validate program; returns list of required capabilities.

    Raises OzError on first problem.
    """
    if program.isa_version[0] != ISA_VERSION[0]:
        raise OzError("UNSUPPORTED_ISA",
                      f"Unsupported ISA major version {program.isa_version}; runtime supports {ISA_VERSION}.")
    if strict_isa and program.isa_version > ISA_VERSION:
        raise OzError("UNSUPPORTED_ISA", f"Program ISA {program.isa_version} is newer than runtime {ISA_VERSION}.")
    if not program.name or not isinstance(program.name, str):
        raise OzError("INVALID_PROGRAM", "Program name must be a non-empty string.")
    if not isinstance(program.statements, list) or not program.statements:
        raise OzError("INVALID_PROGRAM", "Program must contain at least one statement.")
    scope = set()
    _check_block(program.statements, scope, depth=0)
    return program.required_capabilities()


def _check_block(stmts, scope, depth):
    if depth > 32:
        raise OzError("INVALID_PROGRAM", "Block nesting too deep (max 32).")
    if len(stmts) > MAX_PROGRAM_STMTS:
        raise OzError("LIMIT_EXCEEDED", f"Too many statements (max {MAX_PROGRAM_STMTS}).")
    has_return = False
    for s in stmts:
        if not isinstance(s, dict) or "kind" not in s:
            raise OzError("INVALID_PROGRAM", f"Bad statement: {s!r}")
        k = s["kind"]
        if k == "let":
            _check_let(s, scope)
        elif k == "let_literal":
            _check_let_literal(s, scope)
        elif k == "return":
            _check_value_expr(s.get("value"), scope)
            has_return = True
        elif k == "if":
            _check_value_expr(s.get("cond"), scope)
            if not isinstance(s.get("then"), list) or not isinstance(s.get("else"), list):
                raise OzError("INVALID_PROGRAM", "IF requires 'then' and 'else' lists.")
            _check_block(s["then"], set(scope), depth + 1)
            _check_block(s["else"], set(scope), depth + 1)
            # vars assigned inside branches do not escape (conservative)
        elif k == "for":
            tgt = s.get("target")
            if not isinstance(tgt, str) or not tgt or len(tgt) > MAX_VAR_NAME:
                raise OzError("INVALID_PROGRAM", f"Bad FOR target: {tgt!r}")
            mb = s.get("max_iter", 1000)
            if not isinstance(mb, int) or mb < 1 or mb > MAX_LOOP_BOUND:
                raise OzError("LIMIT_EXCEEDED", f"FOR max_iter must be 1..{MAX_LOOP_BOUND}.")
            _check_value_expr(s.get("iterable"), scope)
            inner = set(scope)
            inner.add(tgt)
            if not isinstance(s.get("body"), list):
                raise OzError("INVALID_PROGRAM", "FOR requires 'body' list.")
            _check_block(s["body"], inner, depth + 1)
        else:
            raise OzError("UNSUPPORTED_STATEMENT", f"Unsupported statement kind: {k!r}")
    return has_return


def _check_value_expr(node, scope):
    if node is None:
        raise OzError("INVALID_PROGRAM", "Missing expression.")
    if is_varref(node):
        if node["var"] not in scope:
            raise OzError("UNDEFINED_VARIABLE", f"Undefined variable: {node['var']!r}")
        return
    if is_literal(node):
        _check_literal_size(node["literal"])
        return
    if isinstance(node, dict) and node.get("kind") == "opcall":
        _check_opcall(node.get("op"), node.get("args", []), scope)
        return
    raise OzError("INVALID_PROGRAM", f"Bad expression: {node!r}")


def _check_literal_size(v, depth=0):
    if depth > 16:
        raise OzError("LIMIT_EXCEEDED", "Literal nesting too deep.")
    if isinstance(v, str) and len(v.encode("utf-8")) > 256 * 1024:
        raise OzError("LIMIT_EXCEEDED", "String literal too large (max 256 KiB).")
    if isinstance(v, (bytes, bytearray)) and len(v) > 256 * 1024:
        raise OzError("LIMIT_EXCEEDED", "Bytes literal too large.")
    if isinstance(v, list):
        if len(v) > 10000:
            raise OzError("LIMIT_EXCEEDED", "Array literal too large.")
        for i in v:
            _check_literal_size(i, depth + 1)
    if isinstance(v, dict):
        if len(v) > 10000:
            raise OzError("LIMIT_EXCEEDED", "Map literal too large.")
        for k, vv in v.items():
            if not isinstance(k, str):
                raise OzError("INVALID_PROGRAM", "Map keys must be strings.")
            _check_literal_size(vv, depth + 1)


def _check_let(s, scope):
    tgt = s.get("target")
    op = s.get("op")
    args = s.get("args")
    if not isinstance(tgt, str) or not tgt or len(tgt) > MAX_VAR_NAME:
        raise OzError("INVALID_PROGRAM", f"Bad LET target: {tgt!r}")
    if op not in OP_BY_NAME:
        raise OzError("UNKNOWN_OPERATION", f"Unknown operation: {op!r}")
    if not isinstance(args, list):
        raise OzError("INVALID_PROGRAM", "LET args must be a list.")
    _check_opcall(op, args, scope)
    scope.add(tgt)


def _check_let_literal(s, scope):
    tgt = s.get("target")
    if not isinstance(tgt, str) or not tgt or len(tgt) > MAX_VAR_NAME:
        raise OzError("INVALID_PROGRAM", f"Bad LET target: {tgt!r}")
    v = s.get("value")
    if not is_literal(v) and not is_varref(v):
        raise OzError("INVALID_PROGRAM", "LET literal value must be a literal or variable.")
    if is_varref(v) and v["var"] not in scope:
        raise OzError("UNDEFINED_VARIABLE", f"Undefined variable: {v['var']!r}")
    if is_literal(v):
        _check_literal_size(v["literal"])
    scope.add(tgt)


def _check_opcall(op, args, scope):
    spec = OP_BY_NAME.get(op)
    if spec is None:
        raise OzError("UNKNOWN_OPERATION", f"Unknown operation: {op!r}")
    if len(args) != len(spec.params):
        raise OzError("ARITY_MISMATCH",
                      f"{op} expects {len(spec.params)} args, got {len(args)}.",
                      {"op": op, "expected": len(spec.params), "got": len(args)})
    for (pname, ptype), arg in zip(spec.params, args):
        if is_varref(arg):
            if arg["var"] not in scope:
                raise OzError("UNDEFINED_VARIABLE", f"Undefined variable: {arg['var']!r}")
            # type of var unknown statically; runtime checks
        elif is_literal(arg):
            litv = arg["literal"]
            # allow int where float expected? require number compat
            if ptype == "number":
                if litv is not None and not is_number(litv):
                    raise OzError("TYPE_ERROR", f"{op}.{pname} expects number, got {oz_typeof(litv)}.")
            elif ptype == "any":
                pass
            elif not check_type_matches(ptype, litv):
                raise OzError("TYPE_ERROR",
                              f"{op}.{pname} expects {ptype}, got {oz_typeof(litv)}.",
                              {"op": op, "param": pname})
            _check_literal_size(litv)
        else:
            raise OzError("INVALID_PROGRAM", f"Bad argument to {op}: {arg!r}")
