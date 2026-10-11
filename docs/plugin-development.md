# Plugin Development

1. Pick op IDs in **1000–60000** and namespaced names (`MYPKG.VERB`).
2. Define `OpDef(name, id, version, params[(name,type)], returns, capability, ...)`
   using value types from `docs/isa-spec.md`.
3. Implement handlers `fn(runtime_self, *args)` raising `OzError` on failure.
4. Wrap in `Plugin(name, version, ops, handlers)` and call
   `register_plugin(plugin)` at install time.
5. Test independently: validate → encode/decode → execute with least-privilege
   capabilities → negative tests (traversal, oversized input).
6. Ship with schema docs + compatibility notes (ISA version, op versions).

Core stays small; see `plugins/example_upper/plugin_upper.py`. Never auto-load
untrusted plugin code — install explicitly and review it.
