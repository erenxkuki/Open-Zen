"""Program IR: constructors, JSON loading, dict conversion."""
from __future__ import annotations
import json
from .values import OzError


def var(name):
    return {"var": name}


def lit(value):
    return {"literal": value}


def is_varref(node):
    return isinstance(node, dict) and set(node.keys()) == {"var"} and isinstance(node["var"], str)


def is_literal(node):
    return isinstance(node, dict) and set(node.keys()) == {"literal"}


class Program:
    def __init__(self, name, statements, isa_version=(1, 0)):
        self.name = name
        self.statements = statements
        self.isa_version = tuple(isa_version)

    def to_dict(self):
        return {
            "name": self.name,
            "isa_version": f"{self.isa_version[0]}.{self.isa_version[1]}",
            "statements": self.statements,
        }

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2)

    def required_capabilities(self):
        from .isa import OP_BY_NAME
        caps = set()
        def walk(stmts):
            for s in stmts:
                k = s.get("kind")
                if k == "let":
                    op = OP_BY_NAME.get(s.get("op"))
                    if op:
                        caps.add(op.capability)
                elif k == "if":
                    walk(s.get("then", []))
                    walk(s.get("else", []))
                elif k == "for":
                    walk(s.get("body", []))
        walk(self.statements)
        caps.discard("compute")
        return sorted(caps)


def load_json_program(data):
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise OzError("INVALID_PROGRAM", "Program must be a JSON object.")
    name = data.get("name", "program")
    isa_v = data.get("isa_version", "1.0")
    try:
        major, minor = str(isa_v).split(".")
        isa_version = (int(major), int(minor))
    except Exception:
        raise OzError("INVALID_PROGRAM", f"Bad isa_version: {isa_v!r}")
    stmts = data.get("statements")
    if not isinstance(stmts, list):
        raise OzError("INVALID_PROGRAM", "'statements' must be a list.")
    return Program(str(name), stmts, isa_version)
