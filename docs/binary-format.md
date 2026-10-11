# OZB Binary Format v1

```
magic      4  "OZB1" (4F 5A 42 31)
fmt_ver    u8 =1
isa_major  u8
isa_minor  u8
flags      u8 (bit0=CRC32)
name       u16 len + utf8
stmts      u32 count + statements
crc        u32 CRC32 of preceding bytes (iff flag set)
```

Values: NULL(0) INT(1,i64) FLOAT(2,f64) BOOL(3) STRING(4,u32+utf8)
BYTES(5,u32+raw) ARRAY(6,u32+literal items) MAP(7,u32+sorted key/values)
VARREF(8) OPCALL(9, op_id u16 + args) — OPCALL only in cond/iterable positions.

Statements: LET(1) LET_LITERAL(2) RETURN(3) IF(4) FOR(5). See `openzen/codec.py`.

Rules: big-endian; literals ≤16 MiB blobs; reject trailing bytes, unknown
tags/kinds/flags, bad UTF-8, CRC mismatch; unknown op IDs rejected; decoder
re-runs the static validator. Major ISA mismatch rejected; newer minor rejected
in strict mode. OZB is untrusted input, not a sandbox.
