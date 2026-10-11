# Security Model

Threat model: the AI model is untrusted input. Programs are untrusted until
parsed, validated, capability-checked, approved, and budget-enforced.

- **Deny by default**: unknown ops rejected; FS/proc/sys require grants.
- **No shell**: process launch uses argv arrays, allowlist match, no `shell=True`.
- **No eval**: Python/JS evaluation is never a substitute for OZ-ISA.
- **Paths**: sandbox-relative or absolute-inside-root; realpath + symlink checks;
  refuses root deletion; `..` escapes rejected (`PATH_ESCAPE`).
- **Approvals**: FS.DELETE / PROC.LAUNCH / PROC.KILL / NET.FETCH need a callback grant;
  without one they fail closed. Model output is never user authorization.
- **Network**: NET.FETCH is deny-by-default with an explicit host allowlist
  (exact or `.suffix` entries), http(s) only, 8 s timeout, 512 KiB body cap,
  and redirects re-checked against the allowlist at every hop. No cookies,
  no credentials, no other methods in v1.
- **Environment**: SYS.ENV reads only explicitly allowlisted variable names;
  values capped at 8 KiB. Never allowlist secrets into model-reachable vars.
- **Budgets**: steps (10k), time (5 s), output (1 MiB), file (5 MiB), loop bounds.
- **Secrets**: never put credentials in programs; they would echo into traces/logs.
- **Network**: the API binds 127.0.0.1; remote use needs authn/authz (not in v1 —
  keep it local). Request cap 2 MiB.
- **Isolation modes**: v1 = OS-user privileges + sandbox dirs. No container/VM
  backend yet; documented limitation — destructive ops additionally need approval.

Report issues per `SECURITY.md`.
