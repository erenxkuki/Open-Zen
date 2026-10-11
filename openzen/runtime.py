"""Execution engine: interpreter with budgets, capabilities, tracing, cancellation."""
from __future__ import annotations
import base64
import csv
import hashlib
import io
import json
import platform
import re
import subprocess
import threading
import time
import urllib.request
import urllib.parse
import uuid as uuid_mod
from dataclasses import dataclass, field

from .isa import OP_BY_NAME
from .program import Program, is_varref, is_literal
from .values import OzError, oz_typeof, canonical_json, check_type_matches, is_number
from .capabilities import Capabilities
from .os_adapter import OsAdapter

MAX_OUTPUT_BYTES = 1 * 1024 * 1024


@dataclass
class ExecutionBudgets:
    max_steps: int = 10000
    max_time_ms: int = 5000
    max_output_bytes: int = MAX_OUTPUT_BYTES
    max_loop_iter: int = 10000


@dataclass
class RuntimeConfig:
    capabilities: Capabilities = field(default_factory=Capabilities.none)
    budgets: ExecutionBudgets = field(default_factory=ExecutionBudgets)
    approval_callback: object = None  # fn(op_name, details) -> bool
    os_adapter: OsAdapter | None = None
    step_callback: object = None  # fn(event) -> None; called before each statement


@dataclass
class ExecutionResult:
    status: str  # ok | error | cancelled
    value: object = None
    error: dict | None = None
    trace: list = field(default_factory=list)
    steps: int = 0
    elapsed_ms: int = 0

    def to_dict(self):
        return {"status": self.status, "result": self.value, "error": self.error,
                "trace": self.trace, "steps": self.steps, "elapsed_ms": self.elapsed_ms}


class CancellationToken:
    def __init__(self):
        self._ev = threading.Event()

    def cancel(self):
        self._ev.set()

    @property
    def cancelled(self):
        return self._ev.is_set()


class Runtime:
    def __init__(self, config=None):
        self.config = config or RuntimeConfig()
        if self.config.os_adapter is None:
            self.config.os_adapter = OsAdapter(
                allowed_dirs=self.config.capabilities.allowed_dirs)

    # ---- public entry points ----
    def execute_source(self, text, token=None):
        from .parser import parse_source
        from .validator import validate
        prog = parse_source(text)
        validate(prog)
        return self.execute_program(prog, token)

    def execute_bytes(self, data, token=None):
        from .codec import decode
        prog = decode(data)
        return self.execute_program(prog, token)

    def execute_program(self, program, token=None):
        from .validator import validate
        validate(program)
        return self._run(program, token or CancellationToken())

    # ---- core loop ----
    def _run(self, program: Program, token: CancellationToken):
        t0 = time.monotonic()
        state = {"env": {}, "steps": 0, "trace": [], "deadline": t0 + self.config.budgets.max_time_ms / 1000.0}
        outcome = {"returned": False, "value": None}
        try:
            self._exec_block(program.statements, state, token, outcome, program.name)
            if not outcome["returned"]:
                raise OzError("NO_RETURN", "Program did not execute RETURN.")
            self._check_output_size(outcome["value"])
            return ExecutionResult("ok", outcome["value"], None, state["trace"],
                                   state["steps"], int((time.monotonic() - t0) * 1000))
        except OzError as e:
            return ExecutionResult("error", None, e.to_dict(), state["trace"],
                                   state["steps"], int((time.monotonic() - t0) * 1000))
        except _Cancelled:
            return ExecutionResult("cancelled", None,
                                   {"code": "CANCELLED", "message": "Execution cancelled.", "details": {}},
                                   state["trace"], state["steps"], int((time.monotonic() - t0) * 1000))

    def _poll(self, state, token):
        if token.cancelled:
            raise _Cancelled()
        if time.monotonic() > state["deadline"]:
            raise OzError("TIME_BUDGET_EXCEEDED", "Execution time budget exceeded.")
        if state["steps"] >= self.config.budgets.max_steps:
            raise OzError("STEP_BUDGET_EXCEEDED",
                          f"Step budget exceeded ({self.config.budgets.max_steps}).")

    def _exec_block(self, stmts, state, token, outcome, prog_name, depth=0):
        for s in stmts:
            if outcome["returned"]:
                break
            if token.cancelled:
                raise _Cancelled()
            self._poll(state, token)
            cb = self.config.step_callback
            if cb is not None:
                try:
                    cb({"depth": depth, "stmt": s, "steps": state["steps"],
                        "env": sorted(state["env"].keys())})
                except (_Cancelled, OzError):
                    raise
                except Exception as e:
                    raise OzError("EXECUTION_ERROR", f"Step callback failed: {e}")
            k = s["kind"]
            if k == "let":
                v = self._eval_opcall(s["op"], s["args"], state, token)
                state["env"][s["target"]] = v
                state["steps"] += 1
                state["trace"].append({"op": s["op"], "target": s["target"], "ok": True})
            elif k == "let_literal":
                v = self._resolve_value(s["value"], state, token)
                state["env"][s["target"]] = v
                state["steps"] += 1
                state["trace"].append({"op": "LET_LITERAL", "target": s["target"], "ok": True})
            elif k == "return":
                outcome["value"] = self._resolve_arg(s["value"], state, token)
                outcome["returned"] = True
                state["steps"] += 1
                state["trace"].append({"op": "RETURN", "ok": True})
            elif k == "if":
                cond = self._resolve_arg(s["cond"], state, token)
                branch = s["then"] if self._truthy(cond) else s["else"]
                state["steps"] += 1
                state["trace"].append({"op": "IF", "taken": "then" if self._truthy(cond) else "else", "ok": True})
                # scoped copy: propagate new vars? v1: branches share env but don't leak (copy-restore new keys)
                before = set(state["env"].keys())
                self._exec_block(branch, state, token, outcome, prog_name, depth + 1)
                for key in list(state["env"].keys()):
                    if key not in before:
                        del state["env"][key]
            elif k == "for":
                items = self._resolve_arg(s["iterable"], state, token)
                if not isinstance(items, list):
                    raise OzError("TYPE_ERROR", "FOR iterable must be an array.")
                bound = min(len(items), int(s.get("max_iter", 1000)), self.config.budgets.max_loop_iter)
                if len(items) > bound:
                    raise OzError("LIMIT_EXCEEDED", f"Loop over {len(items)} items exceeds bound {bound}.")
                state["trace"].append({"op": "FOR", "target": s["target"], "count": len(items), "ok": True})
                had = s["target"] in state["env"]
                saved = state["env"].get(s["target"])
                for item in items:
                    self._poll(state, token)
                    if outcome["returned"]:
                        break
                    state["env"][s["target"]] = item
                    state["steps"] += 1
                    before = set(state["env"].keys())
                    self._exec_block(s["body"], state, token, outcome, prog_name, depth + 1)
                    for key in list(state["env"].keys()):
                        if key not in before and key != s["target"]:
                            del state["env"][key]
                if had:
                    state["env"][s["target"]] = saved
                else:
                    state["env"].pop(s["target"], None)
            else:
                raise OzError("UNSUPPORTED_STATEMENT", f"Unsupported: {k!r}")

    # ---- values ----
    def _resolve_value(self, node, state, token=None):
        if is_varref(node):
            name = node["var"]
            if name not in state["env"]:
                raise OzError("UNDEFINED_VARIABLE", f"Undefined variable at runtime: {name!r}")
            return state["env"][name]
        if is_literal(node):
            return node["literal"]
        if isinstance(node, dict) and node.get("kind") == "opcall":
            if token is None:
                raise OzError("INVALID_PROGRAM", "Inline opcall needs evaluation context.")
            return self._eval_opcall(node["op"], node.get("args", []), state, token)
        raise OzError("INVALID_PROGRAM", f"Bad value: {node!r}")

    def _resolve_arg(self, node, state, token):
        return self._resolve_value(node, state, token)

    @staticmethod
    def _truthy(v):
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        if isinstance(v, (int, float)):
            return v != 0
        if isinstance(v, (str, list, dict, bytes, bytearray)):
            return len(v) > 0
        return True

    def _check_output_size(self, v):
        b = canonical_json(v).encode("utf-8")
        if len(b) > self.config.budgets.max_output_bytes:
            raise OzError("LIMIT_EXCEEDED", "Result exceeds output-size budget.")

    # ---- op dispatch ----
    def _eval_opcall(self, op, args, state, token):
        spec = OP_BY_NAME.get(op)
        if spec is None:
            raise OzError("UNKNOWN_OPERATION", f"Unknown operation: {op!r}")
        self.config.capabilities.check(op, spec.capability)
        if self.config.capabilities.needs_approval(op):
            cb = self.config.approval_callback
            if cb is None:
                raise OzError("APPROVAL_REQUIRED",
                              f"Operation {op} requires explicit approval.",
                              {"op": op})
            try:
                ok = bool(cb(op, {"args": [self._safe_preview(a, state) for a in args]}))
            except Exception as e:
                raise OzError("APPROVAL_REQUIRED", f"Approval callback failed for {op}: {e}")
            if not ok:
                raise OzError("APPROVAL_DENIED", f"Operation {op} was not approved.", {"op": op})
        vals = [self._resolve_arg(a, state, token) for a in args]
        # static-ish runtime arity/type check
        if len(vals) != len(spec.params):
            raise OzError("ARITY_MISMATCH", f"{op} expects {len(spec.params)} args.")
        for (pname, ptype), v in zip(spec.params, vals):
            if ptype == "any":
                continue
            if ptype == "number":
                if not is_number(v):
                    raise OzError("TYPE_ERROR", f"{op}.{pname} expects number, got {oz_typeof(v)}.")
            elif not check_type_matches(ptype, v):
                raise OzError("TYPE_ERROR", f"{op}.{pname} expects {ptype}, got {oz_typeof(v)}.")
        handler = getattr(self, "_op_" + op.replace(".", "_"), None)
        if handler is None:
            raise OzError("UNKNOWN_OPERATION", f"No handler for {op!r}")
        try:
            return handler(*vals)
        except OzError:
            raise
        except Exception as e:
            raise OzError("EXECUTION_ERROR", f"{op} failed: {e}")

    def _safe_preview(self, node, state):
        try:
            if is_varref(node):
                v = state["env"].get(node["var"], "<unbound>")
                s = canonical_json(v)
                return s[:200]
            return canonical_json(node.get("literal"))[:200]
        except Exception:
            return "<?>"


# module-level marker to avoid importing threading bits
class _Cancelled(Exception):
    pass


# ---- op handlers (attached to Runtime) ----

def _arith(op):
    def handler(self, a, b):
        if isinstance(a, bool) or isinstance(b, bool):
            raise OzError("TYPE_ERROR", f"{op} requires numbers.")
        if op == "CORE.ADD":
            return a + b
        if op == "CORE.SUB":
            return a - b
        if op == "CORE.MUL":
            return a * b
        if op == "CORE.DIV":
            if b == 0:
                raise OzError("DIVISION_BY_ZERO", "Division by zero.")
            return a / b if isinstance(a, float) or isinstance(b, float) else a / b
        if op == "CORE.MOD":
            if not isinstance(a, int) or not isinstance(b, int):
                raise OzError("TYPE_ERROR", "MOD requires integers.")
            if b == 0:
                raise OzError("DIVISION_BY_ZERO", "Modulo by zero.")
            return a % b
    return handler


for _op in ("CORE.ADD", "CORE.SUB", "CORE.MUL", "CORE.DIV", "CORE.MOD"):
    setattr(Runtime, "_op_" + _op.replace(".", "_"), _arith(_op))

Runtime._op_CORE_EQ = lambda self, a, b: canonical_json(a) == canonical_json(b)
Runtime._op_CORE_NE = lambda self, a, b: canonical_json(a) != canonical_json(b)
Runtime._op_CORE_LT = lambda self, a, b: a < b
Runtime._op_CORE_LTE = lambda self, a, b: a <= b
Runtime._op_CORE_GT = lambda self, a, b: a > b
Runtime._op_CORE_GTE = lambda self, a, b: a >= b
Runtime._op_CORE_AND = lambda self, a, b: bool(a) and bool(b)
Runtime._op_CORE_OR = lambda self, a, b: bool(a) or bool(b)
Runtime._op_CORE_NOT = lambda self, a: not a
Runtime._op_CORE_CONCAT = lambda self, a, b: a + b


def _op_CORE_LEN(self, v):
    if isinstance(v, (str, list, dict, bytes, bytearray)):
        return len(v)
    raise OzError("TYPE_ERROR", f"LEN unsupported for {oz_typeof(v)}.")
Runtime._op_CORE_LEN = _op_CORE_LEN


def _op_CORE_SLICE(self, v, start, end):
    if not isinstance(start, int) or not isinstance(end, int):
        raise OzError("TYPE_ERROR", "SLICE bounds must be ints.")
    try:
        return v[start:end]
    except Exception:
        raise OzError("TYPE_ERROR", "SLICE unsupported for this type.")
Runtime._op_CORE_SLICE = _op_CORE_SLICE


def _op_CORE_TOSTRING(self, v):
    if isinstance(v, str):
        return v
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).hex()
    return canonical_json(v)
Runtime._op_CORE_TOSTRING = _op_CORE_TOSTRING


def _op_CORE_HASH_SHA256(self, v):
    if isinstance(v, (bytes, bytearray)):
        return hashlib.sha256(bytes(v)).hexdigest()
    if isinstance(v, str):
        return hashlib.sha256(v.encode("utf-8")).hexdigest()
    return hashlib.sha256(canonical_json(v).encode("utf-8")).hexdigest()
Runtime._op_CORE_HASH_SHA256 = _op_CORE_HASH_SHA256


def _op_CORE_TO_JSON(self, v):
    if isinstance(v, (bytes, bytearray)):
        raise OzError("TYPE_ERROR", "TO_JSON does not accept bytes; convert first.")
    return canonical_json(v)
Runtime._op_CORE_TO_JSON = _op_CORE_TO_JSON


def _op_CORE_FROM_JSON(self, s):
    try:
        return json.loads(s)
    except Exception as e:
        raise OzError("INVALID_JSON", f"FROM_JSON failed: {e}")
Runtime._op_CORE_FROM_JSON = _op_CORE_FROM_JSON


def _op_CORE_GET(self, v, key):
    try:
        if isinstance(v, dict):
            if not isinstance(key, str):
                raise OzError("TYPE_ERROR", "GET on map requires string key.")
            if key not in v:
                raise OzError("KEY_ERROR", f"Key not found: {key!r}")
            return v[key]
        if isinstance(v, list):
            if not isinstance(key, int) or isinstance(key, bool):
                raise OzError("TYPE_ERROR", "GET on array requires int index.")
            return v[key]
        if isinstance(v, str):
            if not isinstance(key, int) or isinstance(key, bool):
                raise OzError("TYPE_ERROR", "GET on string requires int index.")
            return v[key]
    except IndexError:
        raise OzError("INDEX_ERROR", "Index out of range.")
    raise OzError("TYPE_ERROR", f"GET unsupported for {oz_typeof(v)}.")
Runtime._op_CORE_GET = _op_CORE_GET


def _op_CORE_KEYS(self, v):
    return sorted(v.keys(), key=str)
Runtime._op_CORE_KEYS = _op_CORE_KEYS


def _op_CORE_TYPEOF(self, v):
    return oz_typeof(v)
Runtime._op_CORE_TYPEOF = _op_CORE_TYPEOF


def _op_CORE_BASE64_ENCODE(self, s):
    return base64.b64encode(s.encode("utf-8")).decode("ascii")
Runtime._op_CORE_BASE64_ENCODE = _op_CORE_BASE64_ENCODE


def _op_CORE_BASE64_DECODE(self, s):
    if len(s) > 1024 * 1024:
        raise OzError("LIMIT_EXCEEDED", "Base64 input too large.")
    try:
        return base64.b64decode(s, validate=True).decode("utf-8")
    except Exception:
        raise OzError("INVALID_BASE64", "Input is not valid base64 UTF-8 text.")
Runtime._op_CORE_BASE64_DECODE = _op_CORE_BASE64_DECODE


def _op_CORE_REGEX_MATCH(self, pattern, text):
    if len(pattern) > 1024:
        raise OzError("LIMIT_EXCEEDED", "Regex pattern too long (max 1024 chars).")
    if len(text) > 100000:
        raise OzError("LIMIT_EXCEEDED", "Regex input too long (max 100k chars).")
    try:
        rx = re.compile(pattern)
    except re.error as e:
        raise OzError("INVALID_PATTERN", f"Bad regex: {e}")
    out = []
    for m in rx.finditer(text):
        out.append(m.group(0))
        if len(out) >= 100:
            break
    return out
Runtime._op_CORE_REGEX_MATCH = _op_CORE_REGEX_MATCH


def _op_CORE_UUID4(self):
    return str(uuid_mod.uuid4())
Runtime._op_CORE_UUID4 = _op_CORE_UUID4


# DATA
def _op_DATA_SORT(self, rows):
    try:
        return sorted(rows, key=lambda x: canonical_json(x))
    except Exception as e:
        raise OzError("EXECUTION_ERROR", f"SORT failed: {e}")
Runtime._op_DATA_SORT = _op_DATA_SORT


def _op_DATA_SORT_BY(self, rows, field):
    for r in rows:
        if not isinstance(r, dict) or field not in r:
            raise OzError("KEY_ERROR", f"SORT_BY: missing field {field!r}.")
    try:
        return sorted(rows, key=lambda r: canonical_json(r[field]))
    except Exception as e:
        raise OzError("EXECUTION_ERROR", f"SORT_BY failed: {e}")
Runtime._op_DATA_SORT_BY = _op_DATA_SORT_BY


def _op_DATA_FILTER_EQ(self, rows, field, value):
    out = []
    for r in rows:
        if isinstance(r, dict) and field in r and canonical_json(r[field]) == canonical_json(value):
            out.append(r)
    return out
Runtime._op_DATA_FILTER_EQ = _op_DATA_FILTER_EQ


def _op_DATA_SEARCH_TEXT(self, rows, query):
    out = []
    for r in rows:
        if isinstance(r, str) and query in r:
            out.append(r)
        elif isinstance(r, dict) and query in canonical_json(r):
            out.append(r)
    return out
Runtime._op_DATA_SEARCH_TEXT = _op_DATA_SEARCH_TEXT


def _op_DATA_GROUP_BY(self, rows, field):
    groups = {}
    for r in rows:
        if not isinstance(r, dict) or field not in r:
            raise OzError("KEY_ERROR", f"GROUP_BY: missing field {field!r}.")
        k = str(r[field])
        groups.setdefault(k, []).append(r)
    return groups
Runtime._op_DATA_GROUP_BY = _op_DATA_GROUP_BY


def _op_DATA_FIND_DUPLICATES(self, rows):
    groups = {}
    for r in rows:
        k = canonical_json(r)
        groups.setdefault(k, []).append(r)
    return {k: v for k, v in groups.items() if len(v) > 1}
Runtime._op_DATA_FIND_DUPLICATES = _op_DATA_FIND_DUPLICATES


def _op_DATA_SUMMARIZE(self, rows):
    t = oz_typeof(rows)
    if isinstance(rows, list):
        types = {}
        for r in rows:
            types[oz_typeof(r)] = types.get(oz_typeof(r), 0) + 1
        return {"type": "array", "count": len(rows), "element_types": types}
    if isinstance(rows, dict):
        return {"type": "map", "count": len(rows), "keys": sorted(rows.keys(), key=str)[:100]}
    return {"type": t, "count": 1}
Runtime._op_DATA_SUMMARIZE = _op_DATA_SUMMARIZE


def _op_DATA_AGG_SUM(self, rows, field):
    total = 0
    for r in rows:
        if not isinstance(r, dict) or field not in r or not is_number(r[field]):
            raise OzError("TYPE_ERROR", f"AGG_SUM: bad field {field!r}.")
        total += r[field]
    return total
Runtime._op_DATA_AGG_SUM = _op_DATA_AGG_SUM


def _op_DATA_UNIQUE(self, rows):
    seen, out = set(), []
    for r in rows:
        k = canonical_json(r)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out
Runtime._op_DATA_UNIQUE = _op_DATA_UNIQUE


def _op_DATA_PROJECT(self, rows, fields):
    if not all(isinstance(f, str) for f in fields):
        raise OzError("TYPE_ERROR", "PROJECT fields must be an array of strings.")
    if len(fields) > 100:
        raise OzError("LIMIT_EXCEEDED", "Too many PROJECT fields.")
    out = []
    for r in rows:
        if not isinstance(r, dict):
            raise OzError("TYPE_ERROR", "PROJECT rows must be maps.")
        row = {}
        for f in fields:
            if f not in r:
                raise OzError("KEY_ERROR", f"PROJECT: missing field {f!r}.")
            row[f] = r[f]
        out.append(row)
    return out
Runtime._op_DATA_PROJECT = _op_DATA_PROJECT


def _op_DATA_JSON_GET(self, doc, path):
    try:
        cur = json.loads(doc)
    except Exception as e:
        raise OzError("INVALID_JSON", f"JSON_GET failed to parse: {e}")
    if path == "":
        return cur
    if len(path) > 1024:
        raise OzError("LIMIT_EXCEEDED", "JSON path too long.")
    for part in path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                raise OzError("KEY_ERROR", f"JSON_GET: key not found: {part!r}")
            cur = cur[part]
        elif isinstance(cur, list):
            if not part.isdigit():
                raise OzError("TYPE_ERROR", f"JSON_GET: array needs numeric index, got {part!r}.")
            idx = int(part)
            if idx >= len(cur):
                raise OzError("INDEX_ERROR", "JSON_GET: index out of range.")
            cur = cur[idx]
        else:
            raise OzError("TYPE_ERROR", "JSON_GET: cannot descend into scalar.")
    return cur
Runtime._op_DATA_JSON_GET = _op_DATA_JSON_GET


def _op_DATA_CSV_PARSE(self, text):
    if len(text.encode("utf-8")) > 512 * 1024:
        raise OzError("LIMIT_EXCEEDED", "CSV text too large (max 512 KiB).")
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except Exception as e:
        raise OzError("INVALID_CSV", f"CSV parse failed: {e}")
    if not rows:
        return []
    header = rows[0]
    if len(header) > 100:
        raise OzError("LIMIT_EXCEEDED", "Too many CSV columns.")
    if any(not h for h in header):
        raise OzError("INVALID_CSV", "CSV header must not contain empty names.")
    if len(rows) - 1 > 5000:
        raise OzError("LIMIT_EXCEEDED", "Too many CSV rows (max 5000).")
    out = []
    for line in rows[1:]:
        if len(line) != len(header):
            raise OzError("INVALID_CSV", "CSV row length differs from header.")
        out.append(dict(zip(header, line)))
    return out
Runtime._op_DATA_CSV_PARSE = _op_DATA_CSV_PARSE


# FS (delegate to adapter)
Runtime._op_FS_LIST = lambda self, path: self.config.os_adapter.list_dir(path)
Runtime._op_FS_STAT = lambda self, path: self.config.os_adapter.stat(path)
Runtime._op_FS_READ_TEXT = lambda self, path: self.config.os_adapter.read_text(path)
Runtime._op_FS_MKDIR = lambda self, path: self.config.os_adapter.mkdir(path)
Runtime._op_FS_WRITE_TEXT = lambda self, path, content: self.config.os_adapter.write_text(path, content)
Runtime._op_FS_MOVE = lambda self, src, dst: self.config.os_adapter.move(src, dst)
Runtime._op_FS_DELETE = lambda self, path: self.config.os_adapter.delete(path)
Runtime._op_FS_HASH_FILE = lambda self, path: self.config.os_adapter.hash_file(path)
Runtime._op_FS_SEARCH_TEXT = lambda self, d, q: self.config.os_adapter.search_text(d, q)
Runtime._op_FS_COPY = lambda self, src, dst: self.config.os_adapter.copy(src, dst)
Runtime._op_FS_GLOB = lambda self, d, pat: self.config.os_adapter.glob(d, pat)
Runtime._op_FS_APPEND_TEXT = lambda self, path, content: self.config.os_adapter.append_text(path, content)


# PROC / SYS
def _op_PROC_LIST(self):
    procs = []
    try:
        if platform.system() == "Windows":
            out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                import csv, io
                for row in csv.reader(io.StringIO(out.stdout)):
                    if len(row) >= 2:
                        try:
                            procs.append({"pid": int(row[1]), "name": row[0]})
                        except ValueError:
                            continue
                    if len(procs) >= 500:
                        break
        else:
            out = subprocess.run(["ps", "-e", "-o", "pid=,comm="],
                                 capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                for line in out.stdout.splitlines():
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2:
                        try:
                            procs.append({"pid": int(parts[0]), "name": parts[1]})
                        except ValueError:
                            continue
                    if len(procs) >= 500:
                        break
    except Exception as e:
        raise OzError("EXECUTION_ERROR", f"PROC.LIST failed: {e}")
    return procs
Runtime._op_PROC_LIST = _op_PROC_LIST


def _op_PROC_LAUNCH(self, program, args):
    import os as _os
    if not isinstance(program, str) or not program:
        raise OzError("INVALID_ARGS", "PROC.LAUNCH requires a program name.")
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise OzError("INVALID_ARGS", "PROC.LAUNCH args must be an array of strings.")
    allowed = self.config.capabilities.allowed_programs
    base = program.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if program not in allowed and base not in [a.lower() for a in allowed]:
        raise OzError("CAPABILITY_DENIED", f"Program not allowlisted: {program!r}")
    for a in args:
        if len(a) > 4096:
            raise OzError("INVALID_ARGS", "Argument too long.")
        if "\x00" in a:
            raise OzError("INVALID_ARGS", "NUL byte in argument.")
    try:
        p = subprocess.Popen([program] + args, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, shell=False, text=True)
        try:
            out, _ = p.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
            out, _ = p.communicate()
            out = (out or "") + "\n[TIMEOUT after 10s]"
        if out and len(out) > 64 * 1024:
            out = out[:64 * 1024] + "\n[TRUNCATED]"
        return {"pid": p.pid, "exit_code": p.returncode, "output": out or ""}
    except FileNotFoundError:
        raise OzError("EXECUTION_ERROR", f"Program not found: {program!r}")
    except OzError:
        raise
    except Exception as e:
        raise OzError("EXECUTION_ERROR", f"PROC.LAUNCH failed: {e}")
Runtime._op_PROC_LAUNCH = _op_PROC_LAUNCH


def _op_PROC_KILL(self, pid):
    if not isinstance(pid, int) or pid <= 0:
        raise OzError("INVALID_ARGS", "PROC.KILL requires a positive pid.")
    try:
        if platform.system() == "Windows":
            r = subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True, text=True, timeout=5)
            if r.returncode != 0:
                raise OzError("EXECUTION_ERROR", f"taskkill failed: {r.stdout.strip() or r.stderr.strip()}")
        else:
            import signal
            os.kill(pid, signal.SIGTERM)
        return "killed"
    except OzError:
        raise
    except Exception as e:
        raise OzError("EXECUTION_ERROR", f"PROC.KILL failed: {e}")
Runtime._op_PROC_KILL = _op_PROC_KILL


def _op_SYS_INFO(self):
    return {"os": platform.system(), "release": platform.release(), "arch": platform.machine(),
            "python": platform.python_version()}
Runtime._op_SYS_INFO = _op_SYS_INFO


def _op_SYS_ENV(self, name):
    allowed = self.config.capabilities.allowed_env_vars
    if name not in allowed:
        raise OzError("CAPABILITY_DENIED", f"Environment variable not allowlisted: {name!r}",
                      {"op": "SYS.ENV", "capability": "sys.env"})
    import os as _os
    if name not in _os.environ:
        raise OzError("KEY_ERROR", f"Environment variable not set: {name!r}")
    val = _os.environ[name]
    if len(val.encode("utf-8")) > 8192:
        raise OzError("LIMIT_EXCEEDED", "Environment value too large.")
    return val
Runtime._op_SYS_ENV = _op_SYS_ENV


def _op_TIME_NOW(self):
    return int(time.time())
Runtime._op_TIME_NOW = _op_TIME_NOW


NET_MAX_BODY = 512 * 1024
NET_TIMEOUT = 8


def _net_host_allowed(host, allowed):
    h = (host or "").lower().split(":")[0]
    for entry in allowed:
        e = entry.lower()
        if e.startswith("."):
            if h.endswith(e):
                return True
        elif h == e:
            return True
    return False


def _op_NET_FETCH(self, url):
    allowed = self.config.capabilities.allowed_hosts
    try:
        parts = urllib.parse.urlsplit(url)
    except Exception:
        raise OzError("INVALID_URL", f"Bad URL: {url!r}")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise OzError("INVALID_URL", "NET.FETCH requires an absolute http(s) URL.")
    if len(url) > 2048:
        raise OzError("LIMIT_EXCEEDED", "URL too long.")
    current = url
    for _hop in range(4):
        p = urllib.parse.urlsplit(current)
        if p.scheme not in ("http", "https") or not p.hostname:
            raise OzError("INVALID_URL", "Redirect target is not an absolute http(s) URL.")
        if not _net_host_allowed(p.hostname, allowed):
            raise OzError("CAPABILITY_DENIED", f"Host not allowlisted: {p.hostname!r}",
                          {"op": "NET.FETCH", "capability": "net.fetch"})
        req = urllib.request.Request(current, method="GET",
                                     headers={"User-Agent": "OpenZen/0.2"})
        # NoRedirect: surface 3xx for manual, allowlist-checked handling.
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(req, timeout=NET_TIMEOUT) as r:
                status = r.status
                if status in (301, 302, 303, 307, 308):
                    loc = r.headers.get("Location")
                    if not loc:
                        raise OzError("EXECUTION_ERROR", "Redirect without Location.")
                    current = urllib.parse.urljoin(current, loc)
                    continue
                raw = r.read(NET_MAX_BODY + 1)
                truncated = len(raw) > NET_MAX_BODY
                body = raw[:NET_MAX_BODY].decode("utf-8", errors="replace")
                return {"url": current, "status": status, "body": body,
                        "truncated": truncated,
                        "content_type": r.headers.get("Content-Type", "")[:128]}
        except OzError:
            raise
        except Exception as e:
            raise OzError("EXECUTION_ERROR", f"NET.FETCH failed: {e}")
    raise OzError("LIMIT_EXCEEDED", "Too many redirects.")
Runtime._op_NET_FETCH = _op_NET_FETCH
