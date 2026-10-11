"""OZ-ISA v1.0 operation registry.

Single source of truth for op identifiers, schemas, and capabilities.
Op IDs are stable; never reuse a retired ID.
"""
from __future__ import annotations

ISA_VERSION = (1, 0)
OZB_FORMAT_VERSION = 1

# Value type names used in schemas.
T_INT = "int"
T_FLOAT = "float"
T_BOOL = "bool"
T_STRING = "string"
T_BYTES = "bytes"
T_ARRAY = "array"
T_MAP = "map"
T_ANY = "any"
T_NULL = "null"
T_NUMBER = "number"  # int | float

# Capability names.
CAP_COMPUTE = "compute"
CAP_FS_READ = "fs.read"
CAP_FS_WRITE = "fs.write"
CAP_FS_DELETE = "fs.delete"
CAP_PROC_LIST = "proc.list"
CAP_PROC_LAUNCH = "proc.launch"
CAP_PROC_KILL = "proc.kill"
CAP_SYS_INFO = "sys.info"
CAP_SYS_ENV = "sys.env"
CAP_NET_FETCH = "net.fetch"


class OpDef:
    def __init__(self, name, op_id, version, params, returns, capability,
                 deterministic=True, description="", approval=False):
        self.name = name
        self.op_id = op_id
        self.version = version
        self.params = params  # list of (param_name, type_name)
        self.returns = returns
        self.capability = capability
        self.deterministic = deterministic
        self.description = description
        self.approval = approval

    def to_dict(self):
        return {
            "name": self.name,
            "id": self.op_id,
            "version": self.version,
            "params": [{"name": n, "type": t} for n, t in self.params],
            "returns": self.returns,
            "capability": self.capability,
            "deterministic": self.deterministic,
            "approval": self.approval,
            "description": self.description,
        }


def _ops():
    O = []
    a = O.append
    # --- core computation ---
    a(OpDef("CORE.ADD", 1, 1, [("a", T_NUMBER), ("b", T_NUMBER)], T_NUMBER, CAP_COMPUTE, True, "Add two numbers."))
    a(OpDef("CORE.SUB", 2, 1, [("a", T_NUMBER), ("b", T_NUMBER)], T_NUMBER, CAP_COMPUTE, True, "Subtract b from a."))
    a(OpDef("CORE.MUL", 3, 1, [("a", T_NUMBER), ("b", T_NUMBER)], T_NUMBER, CAP_COMPUTE, True, "Multiply."))
    a(OpDef("CORE.DIV", 4, 1, [("a", T_NUMBER), ("b", T_NUMBER)], T_NUMBER, CAP_COMPUTE, True, "Divide a by b. Division by zero is an error."))
    a(OpDef("CORE.MOD", 5, 1, [("a", T_INT), ("b", T_INT)], T_INT, CAP_COMPUTE, True, "Integer modulo."))
    a(OpDef("CORE.EQ", 6, 1, [("a", T_ANY), ("b", T_ANY)], T_BOOL, CAP_COMPUTE, True, "Deep equality."))
    a(OpDef("CORE.NE", 7, 1, [("a", T_ANY), ("b", T_ANY)], T_BOOL, CAP_COMPUTE, True, "Deep inequality."))
    a(OpDef("CORE.LT", 8, 1, [("a", T_NUMBER), ("b", T_NUMBER)], T_BOOL, CAP_COMPUTE, True, "Less than."))
    a(OpDef("CORE.LTE", 9, 1, [("a", T_NUMBER), ("b", T_NUMBER)], T_BOOL, CAP_COMPUTE, True, "Less than or equal."))
    a(OpDef("CORE.GT", 10, 1, [("a", T_NUMBER), ("b", T_NUMBER)], T_BOOL, CAP_COMPUTE, True, "Greater than."))
    a(OpDef("CORE.GTE", 11, 1, [("a", T_NUMBER), ("b", T_NUMBER)], T_BOOL, CAP_COMPUTE, True, "Greater than or equal."))
    a(OpDef("CORE.AND", 12, 1, [("a", T_BOOL), ("b", T_BOOL)], T_BOOL, CAP_COMPUTE, True, "Logical and."))
    a(OpDef("CORE.OR", 13, 1, [("a", T_BOOL), ("b", T_BOOL)], T_BOOL, CAP_COMPUTE, True, "Logical or."))
    a(OpDef("CORE.NOT", 14, 1, [("a", T_BOOL)], T_BOOL, CAP_COMPUTE, True, "Logical not."))
    a(OpDef("CORE.CONCAT", 15, 1, [("a", T_STRING), ("b", T_STRING)], T_STRING, CAP_COMPUTE, True, "Concatenate strings."))
    a(OpDef("CORE.LEN", 16, 1, [("v", T_ANY)], T_INT, CAP_COMPUTE, True, "Length of string/array/map/bytes."))
    a(OpDef("CORE.SLICE", 17, 1, [("v", T_ANY), ("start", T_INT), ("end", T_INT)], T_ANY, CAP_COMPUTE, True, "Slice string/array/bytes [start:end]."))
    a(OpDef("CORE.TOSTRING", 18, 1, [("v", T_ANY)], T_STRING, CAP_COMPUTE, True, "Convert value to string."))
    a(OpDef("CORE.HASH_SHA256", 19, 1, [("v", T_ANY)], T_STRING, CAP_COMPUTE, True, "SHA-256 hex of canonical encoding of value, or of bytes/string content."))
    a(OpDef("CORE.TO_JSON", 20, 1, [("v", T_ANY)], T_STRING, CAP_COMPUTE, True, "Serialize value to JSON."))
    a(OpDef("CORE.FROM_JSON", 21, 1, [("s", T_STRING)], T_ANY, CAP_COMPUTE, True, "Parse JSON string."))
    a(OpDef("CORE.GET", 22, 1, [("v", T_ANY), ("key", T_ANY)], T_ANY, CAP_COMPUTE, True, "Get map key or array index."))
    a(OpDef("CORE.KEYS", 23, 1, [("v", T_MAP)], T_ARRAY, CAP_COMPUTE, True, "Sorted keys of a map."))
    a(OpDef("CORE.TYPEOF", 24, 1, [("v", T_ANY)], T_STRING, CAP_COMPUTE, True, "Type name of value."))
    a(OpDef("CORE.BASE64_ENCODE", 25, 1, [("s", T_STRING)], T_STRING, CAP_COMPUTE, True, "Base64-encode a UTF-8 string."))
    a(OpDef("CORE.BASE64_DECODE", 26, 1, [("s", T_STRING)], T_STRING, CAP_COMPUTE, True, "Base64-decode to a UTF-8 string. Invalid input is an error."))
    a(OpDef("CORE.REGEX_MATCH", 27, 1, [("pattern", T_STRING), ("text", T_STRING)], T_ARRAY, CAP_COMPUTE, True, "Return array of non-overlapping matches. Bounded pattern/text sizes; invalid patterns are errors."))
    a(OpDef("CORE.UUID4", 28, 1, [], T_STRING, CAP_COMPUTE, False, "Random UUID v4 string. Non-deterministic by design."))
    # --- data operations ---
    a(OpDef("DATA.SORT", 40, 1, [("rows", T_ARRAY)], T_ARRAY, CAP_COMPUTE, True, "Sort array of scalars canonically."))
    a(OpDef("DATA.SORT_BY", 41, 1, [("rows", T_ARRAY), ("field", T_STRING)], T_ARRAY, CAP_COMPUTE, True, "Sort array of maps by field."))
    a(OpDef("DATA.FILTER_EQ", 42, 1, [("rows", T_ARRAY), ("field", T_STRING), ("value", T_ANY)], T_ARRAY, CAP_COMPUTE, True, "Keep maps where field == value."))
    a(OpDef("DATA.SEARCH_TEXT", 43, 1, [("rows", T_ARRAY), ("query", T_STRING)], T_ARRAY, CAP_COMPUTE, True, "Keep strings/maps containing query substring (case-sensitive)."))
    a(OpDef("DATA.GROUP_BY", 44, 1, [("rows", T_ARRAY), ("field", T_STRING)], T_MAP, CAP_COMPUTE, True, "Group array of maps by field value (keyed by stringified value)."))
    a(OpDef("DATA.FIND_DUPLICATES", 45, 1, [("rows", T_ARRAY)], T_MAP, CAP_COMPUTE, True, "Group identical values; return map of key->array for groups with >1 member. Keys are canonical JSON of the value."))
    a(OpDef("DATA.SUMMARIZE", 46, 1, [("rows", T_ANY)], T_MAP, CAP_COMPUTE, True, "Machine-readable summary: type, count, and for maps key counts."))
    a(OpDef("DATA.AGG_SUM", 47, 1, [("rows", T_ARRAY), ("field", T_STRING)], T_NUMBER, CAP_COMPUTE, True, "Sum numeric field over array of maps."))
    a(OpDef("DATA.UNIQUE", 48, 1, [("rows", T_ARRAY)], T_ARRAY, CAP_COMPUTE, True, "Deduplicated array, order-preserving."))
    a(OpDef("DATA.PROJECT", 49, 1, [("rows", T_ARRAY), ("fields", T_ARRAY)], T_ARRAY, CAP_COMPUTE, True, "Keep only the listed fields of each map. Missing fields are errors."))
    a(OpDef("DATA.JSON_GET", 50, 1, [("doc", T_STRING), ("path", T_STRING)], T_ANY, CAP_COMPUTE, True, 'Dot-path lookup ("a.b.0") in a JSON document. Empty path returns the whole document.'))
    a(OpDef("DATA.CSV_PARSE", 51, 1, [("text", T_STRING)], T_ARRAY, CAP_COMPUTE, True, "Parse CSV text (first row is the header) into an array of maps. Bounded."))
    # --- filesystem ---
    a(OpDef("FS.LIST", 60, 1, [("path", T_STRING)], T_ARRAY, CAP_FS_READ, False, "List directory entries (names only, sorted). Path is sandbox-relative or allowlisted."))
    a(OpDef("FS.STAT", 61, 1, [("path", T_STRING)], T_MAP, CAP_FS_READ, False, "Stat file/dir: {name,size,mtime,is_dir}."))
    a(OpDef("FS.READ_TEXT", 62, 1, [("path", T_STRING)], T_STRING, CAP_FS_READ, False, "Read UTF-8 text file (size-limited)."))
    a(OpDef("FS.MKDIR", 63, 1, [("path", T_STRING)], T_STRING, CAP_FS_WRITE, False, "Create directory (including parents). Returns path."))
    a(OpDef("FS.WRITE_TEXT", 64, 1, [("path", T_STRING), ("content", T_STRING)], T_STRING, CAP_FS_WRITE, False, "Write UTF-8 text file (size-limited). Returns path."))
    a(OpDef("FS.MOVE", 65, 1, [("src", T_STRING), ("dst", T_STRING)], T_STRING, CAP_FS_WRITE, False, "Move/rename within allowed roots. Returns dst."))
    a(OpDef("FS.DELETE", 66, 1, [("path", T_STRING)], T_STRING, CAP_FS_DELETE, False, "Delete file or empty dir. Requires approval.", approval=True))
    a(OpDef("FS.HASH_FILE", 67, 1, [("path", T_STRING)], T_STRING, CAP_FS_READ, False, "SHA-256 hex of file bytes."))
    a(OpDef("FS.SEARCH_TEXT", 68, 1, [("dir", T_STRING), ("query", T_STRING)], T_ARRAY, CAP_FS_READ, False, "Search text files under dir for query; returns [{file,line,text}]. Bounded."))
    a(OpDef("FS.COPY", 69, 1, [("src", T_STRING), ("dst", T_STRING)], T_STRING, CAP_FS_WRITE, False, "Copy a file within allowed roots (size-limited). Returns dst."))
    a(OpDef("FS.GLOB", 70, 1, [("dir", T_STRING), ("pattern", T_STRING)], T_ARRAY, CAP_FS_READ, False, "Match file names under dir with an fnmatch pattern (recursive, bounded). Returns sorted relative paths."))
    a(OpDef("FS.APPEND_TEXT", 71, 1, [("path", T_STRING), ("content", T_STRING)], T_STRING, CAP_FS_WRITE, False, "Append UTF-8 text to a file (total size limited). Returns path."))
    # --- process / system ---
    a(OpDef("PROC.LIST", 80, 1, [], T_ARRAY, CAP_PROC_LIST, False, "List permitted processes [{pid,name}]. May be filtered by platform backend."))
    a(OpDef("PROC.LAUNCH", 81, 1, [("program", T_STRING), ("args", T_ARRAY)], T_MAP, CAP_PROC_LAUNCH, False, "Launch allowlisted program with validated args (no shell). Returns {pid}. Requires approval.", approval=True))
    a(OpDef("PROC.KILL", 82, 1, [("pid", T_INT)], T_STRING, CAP_PROC_KILL, False, "Request termination of authorized process. Requires approval.", approval=True))
    a(OpDef("SYS.INFO", 83, 1, [], T_MAP, CAP_SYS_INFO, False, "Query {os,arch,python}."))
    a(OpDef("SYS.ENV", 84, 1, [("name", T_STRING)], T_STRING, CAP_SYS_ENV, False, "Read one explicitly allowlisted environment variable. Anything else is denied."))
    a(OpDef("TIME.NOW", 90, 1, [], T_INT, CAP_SYS_INFO, False, "Current Unix time (seconds). Non-deterministic by design."))
    a(OpDef("NET.FETCH", 100, 1, [("url", T_STRING)], T_MAP, CAP_NET_FETCH, False, "HTTPS/HTTP GET to an allowlisted host. Bounded size/timeout; redirects stay within the allowlist. Requires approval.", approval=True))
    return O


OP_REGISTRY = _ops()
OP_ID = {op.name: op.op_id for op in OP_REGISTRY}
OP_BY_ID = {op.op_id: op for op in OP_REGISTRY}
OP_BY_NAME = {op.name: op for op in OP_REGISTRY}


def capabilities_for_op(op_name):
    op = OP_BY_NAME.get(op_name)
    return op.capability if op else None
