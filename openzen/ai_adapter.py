"""Provider-independent AI adapter interface.

Flow: task -> available instruction schemas -> model produces program JSON/text
-> parse + validate -> capability check -> approval if needed -> execute.
Never executes raw model output without validation.
"""
from __future__ import annotations
import json
from .isa import OP_REGISTRY
from .values import OzError


class ModelAdapter:
    """Implement generate(program_schema_context, task) -> str (source or JSON)."""
    name = "base"

    def generate(self, context, task):
        raise NotImplementedError


class MockAdapter(ModelAdapter):
    """Deterministic adapter returning a canned program (for tests/demo without AI keys)."""
    name = "mock"

    def __init__(self, program_text=None, program_json=None):
        self.program_text = program_text
        self.program_json = program_json

    def generate(self, context, task):
        if self.program_json is not None:
            return json.dumps(self.program_json)
        if self.program_text is not None:
            return self.program_text
        raise OzError("NO_MOCK_PROGRAM", "MockAdapter has no canned program.")


class EchoContextBuilder:
    @staticmethod
    def build(task, max_ops=None):
        ops = OP_REGISTRY if not max_ops else [o for o in OP_REGISTRY if o.name in max_ops]
        return {
            "task": task,
            "isa_version": "1.0",
            "operations": [o.to_dict() for o in ops],
            "rules": [
                "Produce exactly one PROGRAM. Use only listed operations.",
                "No shell commands, no Python, no network URLs.",
                "All filesystem paths must be sandbox-relative.",
            ],
        }


def run_task(task, model, client, context_ops=None, approval_callback=None):
    """Full intent-to-result workflow. Returns dict with stages for display."""
    from .parser import parse_source
    from .program import load_json_program
    from .validator import validate

    context = EchoContextBuilder.build(task)
    raw = model.generate(context, task)
    stages = {"task": task, "model_output": raw, "parsed": None, "validation": None,
              "capabilities": None, "execution": None}
    # Try JSON first, then source syntax
    prog = None
    try:
        maybe = json.loads(raw) if raw.strip().startswith("{") else None
    except Exception:
        maybe = None
    if maybe is not None:
        prog = load_json_program(maybe)
    else:
        prog = parse_source(raw)
    stages["parsed"] = prog.to_dict()
    caps = validate(prog)
    stages["validation"] = {"ok": True, "required_capabilities": caps}
    stages["capabilities"] = caps
    if approval_callback is not None and hasattr(client, "_runtime") and client._runtime is not None:
        client._runtime.config.approval_callback = approval_callback
    ex = client.execute(prog)
    stages["execution"] = {"status": ex.status, "result": ex.result,
                           "error": ex.error, "trace": ex.trace}
    return stages
