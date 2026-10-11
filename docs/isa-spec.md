# OZ-ISA v1.0 (summary)

Full machine-readable registry: `spec/isa/oz-isa-1.0.json` (generated from `openzen/isa.py`).
Human-readable text syntax: see `openzen/parser.py` docstring.

## Values

`int` (i64) · `float` (f64) · `bool` · `string` (UTF-8) · `bytes` ·
`array` · `map` (string keys) · `null`. `number` = int|float (schema only).

## Statements

- `LET <var> = <OP> <args...>` — checked op call.
- `LET <var> = <literal|var>` — bind.
- `IF <expr> THEN ... [ELSE ...] END`
- `FOR <var> IN <array> DO ... END` — bounded (`max_iter ≤ 10000`).
- `RETURN <expr>` — exactly-once return required at runtime.

No nested op calls in v1 (use LET temporaries). Branch bindings do not leak.
`FOR` restores the loop variable afterwards.

## Operations (v1)

Core: ADD SUB MUL DIV MOD EQ NE LT LTE GT GTE AND OR NOT CONCAT LEN SLICE
TOSTRING HASH_SHA256 TO_JSON FROM_JSON GET KEYS TYPEOF
BASE64_ENCODE BASE64_DECODE REGEX_MATCH UUID4 (non-deterministic).
Data: SORT SORT_BY FILTER_EQ SEARCH_TEXT GROUP_BY FIND_DUPLICATES SUMMARIZE AGG_SUM UNIQUE
PROJECT JSON_GET CSV_PARSE.
FS: LIST STAT READ_TEXT MKDIR WRITE_TEXT MOVE DELETE(approval) HASH_FILE SEARCH_TEXT
COPY GLOB APPEND_TEXT.
Proc/sys: LIST LAUNCH(approval+allowlist) KILL(approval) SYS.INFO SYS.ENV(allowlist).
Time/net: TIME.NOW, NET.FETCH(allowlist+approval).

Each op declares params, return type, capability, determinism, and approval.
Unknown ops are rejected; literal arg types are checked statically, variable
arg types at runtime.

## Errors

Structured codes: PARSE_ERROR INVALID_PROGRAM UNKNOWN_OPERATION ARITY_MISMATCH
TYPE_ERROR UNDEFINED_VARIABLE CAPABILITY_DENIED APPROVAL_REQUIRED APPROVAL_DENIED
PATH_ESCAPE FS_ERROR DIVISION_BY_ZERO LIMIT_EXCEEDED STEP_BUDGET_EXCEEDED
TIME_BUDGET_EXCEEDED CANCELLED MALFORMED_BINARY UNSUPPORTED_* NO_RETURN.
