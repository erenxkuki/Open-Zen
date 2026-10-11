# SDK Guide

```python
from openzen import OpenZenClient
client = OpenZenClient.local(sandbox_dirs=["./demo/sandbox"])
p = client.program("demo")
p.let("entries", "FS.LIST", ".")
p.let("summary", "DATA.SUMMARIZE", {"var": "entries"})
p.ret({"var": "summary"})
ex = client.execute(p)
print(ex.result, ex.trace)
```

- `client.validate(p)` — static check, returns required capabilities.
- `client.compile(p)` — OZB bytes; `client.disassemble(bytes)` — listing.
- `client.execute_source("PROGRAM ...")` — parse + run.
- `OpenZenClient.remote("http://127.0.0.1:8765")` — HTTP mode (same methods).
- Errors raise `OzError` (validate) or return `status:"error"` executions.
- CLI mirrors the SDK: `validate|compile|inspect|run|capabilities|serve`
  (`python -m openzen run --help`).
- AI pattern: see `examples/ai_client_example.py` — always validate model
  output before executing.
