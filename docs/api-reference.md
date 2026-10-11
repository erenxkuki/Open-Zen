# API Reference (v1, local)

Base: `http://127.0.0.1:8765`. JSON in/out. Binary via `ozb_hex`.

- `GET /v1/health` → `{status, version, isa_version}`
- `GET /v1/capabilities` → `{isa_version, operations[]}`
- `POST /v1/programs/validate` `{source|program|ozb_hex}` → `{ok, program, required_capabilities}` or `{ok:false, error}`
- `POST /v1/programs/compile` same input → `{ok, ozb_hex, size}`
- `POST /v1/executions` same input → `{execution_id, status, result, error, trace, steps, elapsed_ms}`
- `GET /v1/executions/{id}` → stored record
- `POST /v1/executions/{id}/cancel` → `{cancelled:true}`
- `GET /v1/executions/{id}/trace` → `{trace}`

Status codes: 200 ok · 400 malformed · 404 unknown id/route · 422 rejected execution
(type/capability/approval errors) · 500 internal. Error shape `{error:{code,message,details}}`.
Request cap 2 MiB. Binds localhost by default; do not expose without auth (see security-model).
