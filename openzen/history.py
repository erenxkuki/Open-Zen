"""Persistent execution history (JSONL) for `oz logs` / `oz replay`.

Records are plain facts about past runs. Replay re-executes the stored
program through the current runtime and current capabilities — results may
legitimately differ from the original run (different sandbox, budgets, data).
"""
from __future__ import annotations
import json
import os
import time

MAX_PROGRAM_BYTES = 256 * 1024


def append(path, record):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def read(path, limit=20):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out[-limit:]


def build_record(prog, res, input_kind):
    preview = ""
    try:
        preview = json.dumps(res.value)[:500]
    except Exception:
        preview = repr(res.value)[:500]
    prog_dict = prog.to_dict()
    prog_json = json.dumps(prog_dict)
    stored = len(prog_json.encode("utf-8")) <= MAX_PROGRAM_BYTES
    return {
        "ts": int(time.time()),
        "program": prog.name,
        "isa": f"{prog.isa_version[0]}.{prog.isa_version[1]}",
        "input": input_kind,
        "status": res.status,
        "result_preview": preview,
        "error": res.error,
        "steps": res.steps,
        "elapsed_ms": res.elapsed_ms,
        "program_stored": stored,
        "program_full": prog_dict if stored else None,
    }
