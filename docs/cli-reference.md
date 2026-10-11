# CLI Reference (`oz` / `python -m openzen`)

Conventions (stable):

- **stdout is machine-readable**: JSON results, raw `.ozb` bytes, tables.
  Piping `run` into `jq` or files never breaks.
- **Pipeline stages go to stderr** (`[01]`–`[07]`), silenced with `--quiet`.
- **Colors** (white/cyan/green/yellow/red/gray) disable automatically on
  non-TTYs and with `NO_COLOR=1`, `OZ_PLAIN=1`, or `--plain`.
- **History**: runs append to `.openzen/history.jsonl` (override with
  `--history FILE`, disable with `--no-history`).

| Command | Purpose |
|---|---|
| `version` | Brand header + build facts (version, OZ-ISA, OZB, platform) |
| `banner` | Brand banner |
| `shell` | Interactive Zen Shell (`run`, `validate`, `inspect`, `explain`, `permissions`, `status`, `doctor`, …) |
| `run` | Execute; `--format json` (default) or `human`; `--step` pauses per instruction |
| `trace` | Full lifecycle: policy → binary → trace tree → result. Free text is rejected with an honest pointer to model adapters |
| `validate` / `compile` | Type-check (JSON) / emit `.ozb` bytes |
| `inspect` | Byte-offset table + disassembly (`--format json` for tooling) |
| `explain` | Instruction summary with required capabilities |
| `permissions` | Policy box for the given `--sandbox` / `--allow-*` flags |
| `plugins` | Core count + installed extensions (op IDs ≥ 1000) |
| `logs` / `replay N` | Recorded runs; replay re-executes under current policy |
| `test` | Conformance suite (`--select SUBSTR` to filter) |
| `benchmark` | Measured compile/decode/execute timings, this machine only |
| `doctor` | Installation + smoke-run diagnostics |
| `capabilities` | Operation registry (JSON) |
| `serve` | Local API with engineering header on startup |

Capability flags: `--sandbox DIR` (repeatable), `--read-only`,
`--allow-fs-read`, `--allow-sys-info`, `--allow-proc-list`,
`--allow-programs NAME`, `--allow-env NAME`, `--allow-host HOST`,
`--allow-kill`, `--allow-delete`, `--auto-approve`,
`--max-steps N`, `--max-time-ms N`.
