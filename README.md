# Open Zen

<p align="center">
  <img src="assets/logo.png" alt="Open Zen logo" width="240">
</p>

<p align="center"><b>An open-source, AI-native machine instruction language and universal execution runtime.</b></p>

```text
 ██████╗ ██████╗ ███████╗███╗   ██╗    ███████╗███████╗███╗   ██╗
██╔═══██╗██╔══██╗██╔════╝████╗  ██║    ╚══███╔╝██╔════╝████╗  ██║
██║   ██║██████╔╝█████╗  ██╔██╗ ██║      ███╔╝ █████╗  ██╔██╗ ██║
██║   ██║██╔═══╝ ██╔══╝  ██║╚██╗██║     ███╔╝  ██╔══╝  ██║╚██╗██║
╚██████╔╝██║     ███████╗██║ ╚████║    ███████╗███████╗██║ ╚████║
 ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═══╝    ╚══════╝╚══════╝╚═╝  ╚═══╝
        AI-NATIVE INSTRUCTION LANGUAGE & EXECUTION RUNTIME
```

**AI expresses intent as structured instructions → Open Zen compiles and validates them → a secure runtime executes permitted operations → verified results are returned to the AI.**

Open Zen is the execution technology, not an AI model. It works with any model
provider — or none: every workflow below runs without API keys.

## Why Open Zen

AI models produce text. Computers need guarantees. Open Zen sits between them:

1. A model (or developer) proposes an **OZ-ISA program** — typed, versioned, capability-scoped.
2. Open Zen **parses, type-checks, and compiles** it to **OZB binary**.
3. The runtime **re-validates everything**, enforces **capabilities, approvals, and budgets**, and executes only permitted operations.
4. The caller gets a **verified result or a structured error** — never a silent side effect.

What it is not: a chatbot, a prompt-to-Python generator, an agent framework, or
a shell wrapper. Raw model output is never executed — see `examples/ai_client_example.py`.

## Features

**Language & format**

- **OZ-ISA v1.0** — 59 typed operations: arithmetic, logic, strings, hashing,
  JSON, regex, base64, sorting, filtering, grouping, duplicate detection, CSV,
  sandboxed filesystem, allowlisted processes, environment, timestamps, HTTP fetch.
- **OZB v1 binary** — magic bytes, versioning, CRC32, golden round-trip vectors.
  The runtime validates binary independently; the compiler is untrusted input.
- Human-readable `.oz` source, canonical JSON IR, typed SDK builder.

**Secure runtime**

- Deny-by-default capabilities, no shell strings, no `eval` of generated code.
- Sandbox roots with traversal + symlink-escape defense.
- Approvals fail closed for delete / process spawn / kill / network fetch.
- Step, time, output-size, and loop budgets; cancellation; execution traces.

**Integration**

- Python SDK (embedded runtime or HTTP client) + full terminal (`shell`,
  `run`, `trace`, `inspect`, `explain`, `permissions`, `logs`/`replay`,
  `test`, `benchmark`, `doctor`, `version`).
- Local HTTP API (`/v1/…`, localhost by default) with JSON and `ozb_hex` inputs.
- Plugin contract for new instruction modules without touching the core.

## Requirements

- Python 3.10+ (developed on 3.13, Windows 10/11; Linux/macOS via the same OS-adapter interface).
- No third-party dependencies — the entire runtime, API, SDK, and CLI are standard library.

## Quick start (60 seconds, no keys, no install)

```powershell
git clone https://github.com/erenxkuki/Open-Zen.git
cd Open-Zen                  # folder name matches the repo
python -m openzen version        # brand header + build facts
python -m openzen doctor         # installation + smoke-run diagnostics
python -m openzen run --source examples/arithmetic.oz
```

(`pip install -e .` optionally exposes the `oz` shortcut used below.)

Watch a full lifecycle — intent, policy, binary, trace, verified result:

```powershell
python -m openzen trace --sandbox ./demo/sandbox --source examples/inspect_workspace.oz
```

Open the interactive shell:

```powershell
python -m openzen shell --sandbox ./demo/sandbox
oz> permissions
oz> run examples/inspect_workspace.oz
oz> exit
```

Run the end-to-end duplicate-finder demo (seeds its own sandbox, asserts real duplicates):

```powershell
python demo/demo.py
```

## Example session

`trace` on a 5-instruction program (abridged real output):

```text
[01] INTENT RECEIVED  source-text
[02] OZ-ISA GENERATED  arithmetic, 5 statements
[03] TYPE CHECK PASSED  requires: compute only
[04] PERMISSIONS VERIFIED  compute only
[05] OZB PROGRAM COMPILED  123 bytes
[06] RUNTIME EXECUTING  arithmetic
[07] PIPELINE COMPLETE  OK

PROGRAM:      arithmetic     INSTRUCTIONS: 5    SIZE: 123 bytes
OFFSET    OPCODE     KIND    FAMILY
0x000018  CORE.ADD   EXEC    COMPUTE
...

TRACE  (5 events)
├── CORE.ADD → a ✓
├── CORE.MUL → b ✓
├── CORE.SUB → c ✓
├── CORE.GT → ok ✓
└── RETURN  ✓
✓ RESULT
80
```

Every number above is real: 123 binary bytes, 5 executed steps, result `80`.

## Terminal commands

| Command | Purpose |
|---|---|
| `version`, `banner` | Brand header + build facts |
| `shell` | Interactive Zen Shell |
| `run` | Execute (`--format json/human`, `--step`, `--quiet`) |
| `trace` | Full lifecycle display |
| `validate`, `compile` | Type-check / emit `.ozb` |
| `inspect` | Byte offsets + disassembly (`--format json` for tooling) |
| `explain` | Instruction summary in plain language |
| `permissions` | Policy box for the active flags |
| `plugins` | Core count + installed extensions |
| `logs`, `replay N` | History and re-execution under current policy |
| `test`, `benchmark`, `doctor` | Conformance, measured timings, diagnostics |
| `capabilities` | Operation registry (JSON) |
| `serve` | Local API server |

Capability flags: `--sandbox DIR` (repeatable), `--read-only`,
`--allow-fs-read`, `--allow-sys-info`, `--allow-proc-list`,
`--allow-programs`, `--allow-env`, `--allow-host`, `--allow-kill`,
`--allow-delete`, `--auto-approve`. Full reference: `docs/cli-reference.md`.

## Python SDK

```python
from openzen import OpenZenClient

client = OpenZenClient.local(sandbox_dirs=["./demo/sandbox"])

program = client.program("hello")
program.let("result", "CORE.ADD", 20, 22)
program.ret({"var": "result"})

execution = client.execute(program)
print(execution.result)  # 42
```

`OpenZenClient.remote("http://127.0.0.1:8765")` speaks to the local API with
the same interface. AI pattern (validate-before-execute, mock adapter
included): `examples/ai_client_example.py`.

## Local API

```powershell
python -m openzen serve --sandbox ./demo/sandbox --port 8765
```

```powershell
curl -X POST http://127.0.0.1:8765/v1/programs/validate `
  -H "Content-Type: application/json" `
  -d '{"source": "PROGRAM t\nLET x = CORE.ADD 1 2\nRETURN $x\nEND\n"}'
```

Routes: `GET /v1/health`, `GET /v1/capabilities`,
`POST /v1/programs/validate`, `POST /v1/programs/compile`,
`POST /v1/executions`, per-execution fetch/cancel/trace.
Full reference: `docs/api-reference.md`. Binds localhost; do not expose it to a
network without authentication.

## Documentation

| Document | Covers |
|---|---|
| `docs/architecture.md` | Pipeline, components, novel-vs-reused decisions |
| `docs/isa-spec.md` | Value types, statements, all 59 operations, error codes |
| `docs/binary-format.md` | OZB layout, validation, compatibility rules |
| `docs/cli-reference.md` | Every command, flags, stdout/stderr/color conventions |
| `docs/api-reference.md` | Routes, schemas, status codes |
| `docs/security-model.md` | Threat model, isolation modes, approval rules |
| `docs/plugin-development.md` | Writing and testing instruction modules |
| `docs/sdk-guide.md` | SDK patterns |
| `spec/isa/oz-isa-1.0.json` | Machine-readable registry (regenerate: `python scripts/gen_spec.py`) |

## Project layout

```text
open-zen/
  openzen/        runtime package (ISA, parser, validator, codec, runtime,
                  capabilities, API, SDK, CLI, shell, AI adapter, plugins)
  docs/           human specifications and guides
  spec/           machine-readable ISA + schemas
  examples/       sample .oz programs + AI-client example
  demo/           duplicate-finder demonstration (no AI key required)
  tests/          unit / integration / security / golden / fuzz / CLI tests
  benchmarks/     reproducible measurements (measured, never claimed)
  plugins/        example extension (STRING.UPPER)
  scripts/        spec generator
```

## Testing

```powershell
python -m unittest discover -s tests   # full suite (89 tests)
python -m openzen test --select ValidatorTests
python -m openzen benchmark --iters 300
```

## Security

Read `SECURITY.md` and `docs/security-model.md` before granting capabilities.
Filesystem, process, environment, and network operations are deny-by-default;
destructive and high-impact operations additionally require explicit approval.
A model request is never user authorization.

## Known limitations (v0.3.0)

- Windows-first; POSIX shares the adapter but is less tested.
- No container/VM isolation backend — v1 isolation is OS-user privileges plus sandbox directories.
- Local API has no auth; keep it on localhost.
- `NET.FETCH` is GET-only with no cookie/auth support; regex relies on size bounds, not timeouts.
- Text syntax has no array/map literals (use JSON IR or the SDK) and no nested op calls.

## License

Apache-2.0. See `LICENSE`.
