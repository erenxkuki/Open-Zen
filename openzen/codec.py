"""OZB binary format encoder/decoder (v1).

Layout (big-endian):
  magic      4 bytes  4F 5A 42 31  ("OZB1")
  fmt_ver    u8  (=1)
  isa_major  u8
  isa_minor  u8
  flags      u8  (bit0 = CRC32 present)
  name_len   u16, name utf-8
  stmt_count u32
  statements...
  [crc32 u32]  (of all preceding bytes, if flag set)

Value encoding: tag u8 + payload
  0 NULL
  1 INT   i64
  2 FLOAT f64
  3 BOOL  u8 (0/1)
  4 STRING u32 len + utf8
  5 BYTES  u32 len + raw
  6 ARRAY  u32 n + items
  7 MAP    u32 n + (key: u16 len + utf8, value)*
  8 VARREF u16 len + utf8

Statement encoding: kind u8
  1 LET:         target(varstr) + op_id u16 + arg_count u16 + args(values)
  2 LET_LITERAL: target(varstr) + value
  3 RETURN:      value
  4 IF:          cond(value) + then_count u32 + then... + else_count u32 + else...
  5 FOR:         target(varstr) + iterable(value) + max_iter u32 + body_count u32 + body...

Opcall expressions in cond/iterable positions are encoded as values with
tag 9 OPCALL: op_id u16 + arg_count u16 + args.
"""
from __future__ import annotations
import struct
import zlib
from .isa import OP_BY_NAME, OP_BY_ID
from .program import Program, is_varref, is_literal
from .values import OzError

MAGIC = b"OZB1"
FORMAT_VERSION = 1

TAG_NULL = 0
TAG_INT = 1
TAG_FLOAT = 2
TAG_BOOL = 3
TAG_STRING = 4
TAG_BYTES = 5
TAG_ARRAY = 6
TAG_MAP = 7
TAG_VARREF = 8
TAG_OPCALL = 9

KIND_LET = 1
KIND_LET_LITERAL = 2
KIND_RETURN = 3
KIND_IF = 4
KIND_FOR = 5

MAX_NAME = 256
MAX_STMTS = 5000


class _Writer:
    def __init__(self):
        self.buf = bytearray()

    def u8(self, v):
        self.buf += struct.pack(">B", v)

    def u16(self, v):
        self.buf += struct.pack(">H", v)

    def u32(self, v):
        self.buf += struct.pack(">I", v)

    def i64(self, v):
        self.buf += struct.pack(">q", v)

    def f64(self, v):
        self.buf += struct.pack(">d", v)

    def varstr(self, s):
        b = s.encode("utf-8")
        if len(b) > 65535:
            raise OzError("LIMIT_EXCEEDED", "String too long for OZB.")
        self.u16(len(b))
        self.buf += b

    def bytes32(self, b):
        if len(b) > 16 * 1024 * 1024:
            raise OzError("LIMIT_EXCEEDED", "Blob too large for OZB (max 16 MiB).")
        self.u32(len(b))
        self.buf += b

    def bytes_raw(self, b):
        self.buf += b


def _write_value(w, node):
    """node is IR expr: {"var":..} | {"literal":..} | {"kind":"opcall",...}."""
    if is_varref(node):
        w.u8(TAG_VARREF)
        w.varstr(node["var"])
    elif is_literal(node):
        _write_literal(w, node["literal"])
    elif isinstance(node, dict) and node.get("kind") == "opcall":
        op = node["op"]
        spec = OP_BY_NAME.get(op)
        if spec is None:
            raise OzError("UNKNOWN_OPERATION", f"Unknown op in encode: {op!r}")
        w.u8(TAG_OPCALL)
        w.u16(spec.op_id)
        args = node.get("args", [])
        w.u16(len(args))
        for a in args:
            _write_value(w, a)
    else:
        raise OzError("INVALID_PROGRAM", f"Cannot encode value: {node!r}")


def _write_literal(w, v):
    if v is None:
        w.u8(TAG_NULL)
    elif isinstance(v, bool):
        w.u8(TAG_BOOL)
        w.u8(1 if v else 0)
    elif isinstance(v, int):
        if v < -(2**63) or v > 2**63 - 1:
            raise OzError("LIMIT_EXCEEDED", f"Int out of i64 range: {v}")
        w.u8(TAG_INT)
        w.i64(v)
    elif isinstance(v, float):
        w.u8(TAG_FLOAT)
        w.f64(v)
    elif isinstance(v, str):
        w.u8(TAG_STRING)
        w.bytes32(v.encode("utf-8"))
    elif isinstance(v, (bytes, bytearray)):
        w.u8(TAG_BYTES)
        w.bytes32(bytes(v))
    elif isinstance(v, list):
        w.u8(TAG_ARRAY)
        w.u32(len(v))
        for item in v:
            _write_literal(w, item)
    elif isinstance(v, dict):
        w.u8(TAG_MAP)
        w.u32(len(v))
        for k in sorted(v.keys(), key=str):
            if not isinstance(k, str):
                raise OzError("INVALID_PROGRAM", "Map keys must be strings for OZB.")
            w.varstr(k)
            _write_literal(w, v[k])
    else:
        raise OzError("INVALID_PROGRAM", f"Unsupported literal type: {type(v).__name__}")


def _write_stmt(w, s, depth=0):
    if depth > 32:
        raise OzError("INVALID_PROGRAM", "Nesting too deep.")
    k = s["kind"]
    if k == "let":
        spec = OP_BY_NAME.get(s["op"])
        if spec is None:
            raise OzError("UNKNOWN_OPERATION", s["op"])
        w.u8(KIND_LET)
        w.varstr(s["target"])
        w.u16(spec.op_id)
        w.u16(len(s["args"]))
        for a in s["args"]:
            _write_value(w, a)
    elif k == "let_literal":
        w.u8(KIND_LET_LITERAL)
        w.varstr(s["target"])
        _write_value(w, s["value"])
    elif k == "return":
        w.u8(KIND_RETURN)
        _write_value(w, s["value"])
    elif k == "if":
        w.u8(KIND_IF)
        _write_value(w, s["cond"])
        w.u32(len(s["then"]))
        for t in s["then"]:
            _write_stmt(w, t, depth + 1)
        w.u32(len(s["else"]))
        for t in s["else"]:
            _write_stmt(w, t, depth + 1)
    elif k == "for":
        w.u8(KIND_FOR)
        w.varstr(s["target"])
        _write_value(w, s["iterable"])
        w.u32(int(s.get("max_iter", 1000)))
        w.u32(len(s["body"]))
        for t in s["body"]:
            _write_stmt(w, t, depth + 1)
    else:
        raise OzError("UNSUPPORTED_STATEMENT", f"Cannot encode: {k!r}")


def encode(program, with_crc=True):
    from .validator import validate
    validate(program)
    w = _Writer()
    w.bytes_raw(MAGIC)
    w.u8(FORMAT_VERSION)
    w.u8(program.isa_version[0])
    w.u8(program.isa_version[1])
    flags = 0x01 if with_crc else 0x00
    w.u8(flags)
    w.varstr(program.name)
    if len(program.statements) > MAX_STMTS:
        raise OzError("LIMIT_EXCEEDED", "Too many statements.")
    w.u32(len(program.statements))
    for s in program.statements:
        _write_stmt(w, s)
    data = bytes(w.buf)
    if with_crc:
        data += struct.pack(">I", zlib.crc32(data) & 0xFFFFFFFF)
    return data


class _Reader:
    def __init__(self, data):
        self.d = data
        self.p = 0

    def need(self, n):
        if self.p + n > len(self.d):
            raise OzError("MALFORMED_BINARY", "Truncated OZB input.")
        b = self.d[self.p:self.p + n]
        self.p += n
        return b

    def u8(self):
        return struct.unpack(">B", self.need(1))[0]

    def u16(self):
        return struct.unpack(">H", self.need(2))[0]

    def u32(self):
        return struct.unpack(">I", self.need(4))[0]

    def i64(self):
        return struct.unpack(">q", self.need(8))[0]

    def f64(self):
        return struct.unpack(">d", self.need(8))[0]

    def varstr(self):
        n = self.u16()
        b = self.need(n)
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            raise OzError("MALFORMED_BINARY", "Invalid UTF-8 in OZB string.")

    def bytes32(self):
        n = self.u32()
        if n > 16 * 1024 * 1024:
            raise OzError("MALFORMED_BINARY", "Blob length too large.")
        return self.need(n)


def _read_value(r, depth=0):
    if depth > 32:
        raise OzError("MALFORMED_BINARY", "Value nesting too deep.")
    tag = r.u8()
    if tag == TAG_NULL:
        return {"literal": None}
    if tag == TAG_INT:
        return {"literal": r.i64()}
    if tag == TAG_FLOAT:
        return {"literal": r.f64()}
    if tag == TAG_BOOL:
        b = r.u8()
        if b not in (0, 1):
            raise OzError("MALFORMED_BINARY", "Bad bool encoding.")
        return {"literal": bool(b)}
    if tag == TAG_STRING:
        return {"literal": r.bytes32().decode("utf-8", errors="strict")}
    if tag == TAG_BYTES:
        return {"literal": r.bytes32()}
    if tag == TAG_ARRAY:
        n = r.u32()
        if n > 100000:
            raise OzError("MALFORMED_BINARY", "Array too large.")
        items = []
        for _ in range(n):
            node = _read_value(r, depth + 1)
            if not is_literal(node):
                raise OzError("MALFORMED_BINARY", "Array items must be literals in OZB.")
            items.append(node["literal"])
        return {"literal": items}
    if tag == TAG_MAP:
        n = r.u32()
        if n > 100000:
            raise OzError("MALFORMED_BINARY", "Map too large.")
        m = {}
        for _ in range(n):
            k = r.varstr()
            node = _read_value(r, depth + 1)
            if not is_literal(node):
                raise OzError("MALFORMED_BINARY", "Map values must be literals in OZB.")
            m[k] = node["literal"]
        return {"literal": m}
    if tag == TAG_VARREF:
        return {"var": r.varstr()}
    if tag == TAG_OPCALL:
        op_id = r.u16()
        spec = OP_BY_ID.get(op_id)
        if spec is None:
            raise OzError("UNKNOWN_OPERATION", f"Unknown op id in OZB: {op_id}")
        n = r.u16()
        if n > 16:
            raise OzError("MALFORMED_BINARY", "Too many op args.")
        args = [_read_value(r, depth + 1) for _ in range(n)]
        return {"kind": "opcall", "op": spec.name, "args": args}
    raise OzError("MALFORMED_BINARY", f"Unknown value tag: {tag}")


def _read_stmt(r, depth=0, events=None):
    if depth > 32:
        raise OzError("MALFORMED_BINARY", "Statement nesting too deep.")
    pos = r.p
    kind = r.u8()

    def emit(stmt, op=None):
        if events is not None:
            events.append({"offset": pos, "depth": depth,
                           "kind": stmt["kind"], "op": op, "stmt": stmt})
    if kind == KIND_LET:
        target = r.varstr()
        op_id = r.u16()
        spec = OP_BY_ID.get(op_id)
        if spec is None:
            raise OzError("UNKNOWN_OPERATION", f"Unknown op id: {op_id}")
        n = r.u16()
        if n > 16:
            raise OzError("MALFORMED_BINARY", "Too many args.")
        args = [_read_value(r) for _ in range(n)]
        stmt = {"kind": "let", "target": target, "op": spec.name, "args": args}
        emit(stmt, spec.name)
        return stmt
    if kind == KIND_LET_LITERAL:
        target = r.varstr()
        v = _read_value(r)
        stmt = {"kind": "let_literal", "target": target, "value": v}
        emit(stmt)
        return stmt
    if kind == KIND_RETURN:
        stmt = {"kind": "return", "value": _read_value(r)}
        emit(stmt)
        return stmt
    if kind == KIND_IF:
        cond = _read_value(r)
        tn = r.u32()
        if tn > MAX_STMTS:
            raise OzError("MALFORMED_BINARY", "Then-branch too large.")
        then = [_read_stmt(r, depth + 1, events) for _ in range(tn)]
        en = r.u32()
        if en > MAX_STMTS:
            raise OzError("MALFORMED_BINARY", "Else-branch too large.")
        els = [_read_stmt(r, depth + 1, events) for _ in range(en)]
        stmt = {"kind": "if", "cond": cond, "then": then, "else": els}
        emit(stmt)
        return stmt
    if kind == KIND_FOR:
        target = r.varstr()
        it = _read_value(r)
        mx = r.u32()
        bn = r.u32()
        if bn > MAX_STMTS:
            raise OzError("MALFORMED_BINARY", "Loop body too large.")
        body = [_read_stmt(r, depth + 1, events) for _ in range(bn)]
        stmt = {"kind": "for", "target": target, "iterable": it, "body": body, "max_iter": mx}
        emit(stmt)
        return stmt
    raise OzError("MALFORMED_BINARY", f"Unknown statement kind: {kind}")


def _decode_full(data, collect):
    if not isinstance(data, (bytes, bytearray)):
        raise OzError("MALFORMED_BINARY", "OZB input must be bytes.")
    data = bytes(data)
    if len(data) < 4 + 1 + 1 + 1 + 1 + 2 + 4:
        raise OzError("MALFORMED_BINARY", "OZB input too short.")
    if data[:4] != MAGIC:
        raise OzError("MALFORMED_BINARY", f"Bad magic: {data[:4]!r}")
    fmt = data[4]
    if fmt != FORMAT_VERSION:
        raise OzError("UNSUPPORTED_FORMAT", f"Unsupported OZB format version: {fmt}")
    isa_major, isa_minor, flags = data[5], data[6], data[7]
    has_crc = bool(flags & 0x01)
    if flags & 0xFE:
        raise OzError("MALFORMED_BINARY", f"Unknown OZB flags: {flags:#x}")
    body = data
    if has_crc:
        if len(data) < 4:
            raise OzError("MALFORMED_BINARY", "Missing CRC.")
        body, want = data[:-4], struct.unpack(">I", data[-4:])[0]
        got = zlib.crc32(body) & 0xFFFFFFFF
        if got != want:
            raise OzError("MALFORMED_BINARY", "CRC mismatch.")
    r = _Reader(body)
    r.p = 8
    name = r.varstr()
    if len(name) == 0 or len(name) > MAX_NAME:
        raise OzError("MALFORMED_BINARY", "Bad program name.")
    n = r.u32()
    if n > MAX_STMTS:
        raise OzError("MALFORMED_BINARY", "Too many statements.")
    events = [] if collect else None
    stmts = [_read_stmt(r, 0, events) for _ in range(n)]
    if r.p != len(body):
        raise OzError("MALFORMED_BINARY", "Trailing bytes after program.")
    prog = Program(name, stmts, (isa_major, isa_minor))
    from .validator import validate
    validate(prog)
    return prog, events or [], {"format": fmt, "size": len(data)}


def decode(data):
    prog, _, _ = _decode_full(data, False)
    return prog


def _family_of(op_name):
    from .isa import OP_BY_NAME
    spec = OP_BY_NAME.get(op_name)
    if spec is None:
        return "UNKNOWN"
    return {"compute": "COMPUTE", "fs.read": "FILESYSTEM", "fs.write": "FILESYSTEM",
            "fs.delete": "FILESYSTEM", "proc.list": "PROCESS", "proc.launch": "PROCESS",
            "proc.kill": "PROCESS", "sys.info": "SYSTEM", "sys.env": "SYSTEM",
            "net.fetch": "NETWORK"}.get(spec.capability, "UNKNOWN")


def inspect_detail(data):
    """Decode OZB and return real byte offsets per instruction for the inspector."""
    prog, events, meta = _decode_full(data, True)
    kind_label = {"let": "EXEC", "let_literal": "BIND", "return": "OUTPUT",
                  "if": "CONTROL", "for": "CONTROL"}
    items = []
    for e in sorted(events, key=lambda e: e["offset"]):
        if e["kind"] == "let":
            op, family = e["op"], _family_of(e["op"])
        elif e["kind"] == "return":
            op, family = "RETURN", "OUTPUT"
        elif e["kind"] == "let_literal":
            op, family = "LET", "COMPUTE"
        else:
            op, family = e["kind"].upper(), "CONTROL"
        items.append({"offset": e["offset"], "depth": e["depth"], "op": op,
                      "kind": kind_label.get(e["kind"], "?"), "family": family})
    return {"name": prog.name,
            "isa": f"{prog.isa_version[0]}.{prog.isa_version[1]}",
            "format": meta["format"], "size": meta["size"], "items": items}


def disassemble(data):
    """Decode OZB and return human-readable listing."""
    prog = decode(data)
    lines = [f"PROGRAM {prog.name}  ; isa {prog.isa_version[0]}.{prog.isa_version[1]}"]

    def fmt_val(node):
        if is_varref(node):
            return node["var"]
        if is_literal(node):
            return repr(node["literal"])
        if isinstance(node, dict) and node.get("kind") == "opcall":
            return node["op"] + (" " + " ".join(fmt_val(a) for a in node["args"]) if node["args"] else "")
        return "<?>"

    def walk(stmts, ind):
        for s in stmts:
            k = s["kind"]
            pad = "  " * ind
            if k == "let":
                lines.append(f"{pad}LET {s['target']} = {s['op']} " + " ".join(fmt_val(a) for a in s["args"]))
            elif k == "let_literal":
                lines.append(f"{pad}LET {s['target']} = {fmt_val(s['value'])}")
            elif k == "return":
                lines.append(f"{pad}RETURN {fmt_val(s['value'])}")
            elif k == "if":
                lines.append(f"{pad}IF {fmt_val(s['cond'])} THEN")
                walk(s["then"], ind + 1)
                if s["else"]:
                    lines.append(f"{pad}ELSE")
                    walk(s["else"], ind + 1)
                lines.append(f"{pad}END")
            elif k == "for":
                lines.append(f"{pad}FOR {s['target']} IN {fmt_val(s['iterable'])} DO")
                walk(s["body"], ind + 1)
                lines.append(f"{pad}END")
    walk(prog.statements, 1)
    lines.append("END")
    return "\n".join(lines)
