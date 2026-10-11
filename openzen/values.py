"""Typed value model and helpers shared by parser/validator/codec/runtime."""
from __future__ import annotations
import json


def oz_typeof(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int) and not isinstance(v, bool):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "string"
    if isinstance(v, (bytes, bytearray)):
        return "bytes"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "map"
    return "unknown"


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def canonical_json(v):
    """Deterministic JSON encoding for hashing/grouping."""
    def _norm(x):
        if isinstance(x, bytes):
            return {"__bytes__": x.hex()}
        if isinstance(x, bytearray):
            return {"__bytes__": bytes(x).hex()}
        if isinstance(x, list):
            return [_norm(i) for i in x]
        if isinstance(x, dict):
            return {str(k): _norm(x[k]) for k in sorted(x.keys(), key=str)}
        if isinstance(x, float):
            if x != x or x in (float("inf"), float("-inf")):
                return repr(x)
            return x
        return x
    return json.dumps(_norm(v), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def check_type_matches(declared, value):
    """Check a runtime value against a declared schema type name."""
    t = oz_typeof(value)
    if declared == "any":
        return True
    if declared == "number":
        return is_number(value)
    if declared == "null":
        return value is None
    return t == declared


class OzError(Exception):
    """Structured runtime/validation error with a machine-readable code."""
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self):
        return {"code": self.code, "message": self.message, "details": self.details}
