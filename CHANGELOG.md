# Changelog

## 0.3.0 — systems-engineering terminal
- Engineering header (`version`, shell startup, `serve`): brand, pipeline,
  VERSION/ARCH/FORMAT/RUNTIME lines from live build facts.
- Live 7-stage pipeline on stderr for `run`/`trace`; stdout stays JSON-clean.
- Interactive `shell` (validate/run/inspect/explain/permissions/status/doctor).
- `permissions` policy box (GRANTED/APPROVAL/DENIED from real grants),
  `inspect` byte-offset table, `explain`, `plugins`, `logs`/`replay`
  (JSONL history), `test` (conformance), `benchmark`, `doctor`, `version`,
  `trace` (full lifecycle + honest NL guard), `--step` instruction stepping.
- Restrained color system (white/cyan/green/yellow/red/gray) with NO_COLOR,
  `--plain`, `--quiet`, non-TTY auto-disable. `oz` console-script alias.
- No invented metrics: every stage, offset, and status is a real event.
- 13 new ops (59 total): BASE64_ENCODE/DECODE, REGEX_MATCH, UUID4, PROJECT,
  JSON_GET, CSV_PARSE, FS.COPY/GLOB/APPEND_TEXT, SYS.ENV (allowlisted),
  TIME.NOW, NET.FETCH (host allowlist + approval + redirect checks).
- New `sys.env` / `net.fetch` capabilities, CLI flags
  (`--allow-env`, `--allow-host`), project logo in `assets/`.
- 20 new tests (66 total passing). No breaking changes: all op IDs stable.
- Known limits: NET.FETCH is GET-only with no cookie/auth support in v1;
  regex has no execution timeout (pattern/input size bounds are the mitigation).

## 0.1.0 — initial working release
- OZ-ISA v1.0: core/data/FS/proc ops, typed IR, static validation.
- OZB v1 binary with CRC + golden round-trip tests.
- Sandboxed interpreter: budgets, cancellation, traces, approvals.
- Local HTTP API, Python SDK, CLI, mock AI adapter, demo.
- Security + plugin docs, reproducible benchmarks.
- Known limits: Windows-first (POSIX via same adapter, less tested);
  no container backend; no auth on local API (binds localhost); v1 text
  syntax has no nested op calls or first-class functions.
