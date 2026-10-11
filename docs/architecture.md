# Open Zen Architecture

```text
 ██████╗ ██████╗ ███████╗███╗   ██╗    ███████╗███████╗███╗   ██╗
██╔═══██╗██╔══██╗██╔════╝████╗  ██║    ╚══███╔╝██╔════╝████╗  ██║
██║   ██║██████╔╝█████╗  ██╔██╗ ██║      ███╔╝ █████╗  ██╔██╗ ██║
██║   ██║██╔═══╝ ██╔══╝  ██║╚██╗██║     ███╔╝  ██╔══╝  ██║╚██╗██║
╚██████╔╝██║     ███████╗██║ ╚████║    ███████╗███████╗██║ ╚████║
 ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═══╝    ╚══════╝╚══════╝╚═╝  ╚═══╝
        AI-NATIVE INSTRUCTION LANGUAGE & EXECUTION RUNTIME
```

## Pipeline

Source (.oz) → lexer/parser → typed IR → static validation → OZB binary →
runtime validation → capability/approval checks → sandboxed execution → structured result.

## Why this shape

- JSON IR is canonical; text syntax is sugar for humans and small models.
- The runtime re-validates everything (binary included). The compiler is untrusted.
- Capabilities are deny-by-default; the model is never the authorizer.
- OS access goes through `OsAdapter`, which enforces sandbox roots and symlink checks.
  Windows is the first target; POSIX uses the same adapter (no shell strings anywhere).

## Components

- `openzen/isa.py` — op registry (stable numeric IDs), schemas, capabilities.
- `openzen/parser.py` — line-oriented text parser.
- `openzen/validator.py` — scope, arity, literal-type, and budget checks.
- `openzen/codec.py` — OZB encoder/decoder (`OZB1`, CRC32, forward-compat flags).
- `openzen/runtime.py` — tree-walking interpreter, budgets, cancellation, traces.
- `openzen/os_adapter.py` — sandboxed FS backend.
- `openzen/capabilities.py` — explicit grants.
- `openzen/api_server.py` — stdlib HTTP API.
- `openzen/client.py` — SDK (embedded + HTTP).
- `openzen/ai_adapter.py` — provider-independent model interface.
- `openzen/plugin.py` — versioned extension contract (IDs 1000–60000).

## Novel vs reused

Reused deliberately: JSON, SHA-256, CRC32, HTTP, OS syscalls.
Original: OZ-ISA op set and semantics, OZB container format, capability-gated
interpreter, and the intent→validated-program→verified-result workflow.
Binary encoding is a representation choice, not a security boundary.
