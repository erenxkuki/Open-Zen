"""Python SDK: typed program builder + embedded/local execution."""
from __future__ import annotations
import json
import urllib.request
from .program import Program, var, lit
from .isa import OP_BY_NAME
from .values import OzError


class ProgramBuilder:
    def __init__(self, name="program"):
        self.name = name
        self.statements = []

    def _arg(self, v):
        if isinstance(v, dict) and ("var" in v or "literal" in v or "kind" in v):
            return v
        return lit(v)

    def let(self, target, op, *args):
        if op not in OP_BY_NAME:
            raise OzError("UNKNOWN_OPERATION", f"Unknown op: {op!r}")
        self.statements.append({"kind": "let", "target": target, "op": op,
                                "args": [self._arg(a) for a in args]})
        return var(target)

    def assign(self, target, value):
        self.statements.append({"kind": "let_literal", "target": target,
                                "value": self._arg(value)})
        return var(target)

    def ret(self, value):
        self.statements.append({"kind": "return", "value": self._arg(value)})
        return self

    def _wrap_expr(self, e):
        return self._arg(e)

    def if_(self, cond, then_fn, else_fn=None):
        tb = ProgramBuilder(self.name + "_then")
        then_fn(tb)
        eb = ProgramBuilder(self.name + "_else")
        if else_fn:
            else_fn(eb)
        self.statements.append({"kind": "if", "cond": self._wrap_expr(cond),
                                "then": tb.statements, "else": eb.statements})
        return self

    def for_(self, target, iterable, body_fn, max_iter=1000):
        bb = ProgramBuilder(self.name + "_body")
        body_fn(bb)
        self.statements.append({"kind": "for", "target": target,
                                "iterable": self._wrap_expr(iterable),
                                "body": bb.statements, "max_iter": max_iter})
        return self

    # convenience core ops
    def add(self, a, b): return {"kind": "opcall", "op": "CORE.ADD", "args": [self._arg(a), self._arg(b)]}

    def build(self):
        return Program(self.name, self.statements)

    def to_json(self):
        return self.build().to_json()

    def compile(self):
        from .codec import encode
        return encode(self.build())


class Execution:
    def __init__(self, result_dict):
        self._d = result_dict

    @property
    def status(self): return self._d.get("status")
    @property
    def result(self): return self._d.get("result")
    @property
    def error(self): return self._d.get("error")
    @property
    def trace(self): return self._d.get("trace", [])
    @property
    def ok(self): return self.status == "ok"

    def raise_on_error(self):
        if not self.ok:
            raise OzError((self.error or {}).get("code", "EXECUTION_ERROR"),
                          (self.error or {}).get("message", "Execution failed."),
                          (self.error or {}).get("details", {}))
        return self.result


class OpenZenClient:
    """Client supporting embedded runtime (default) or HTTP runtime API."""

    def __init__(self, base_url=None, runtime=None):
        self.base_url = (base_url or "").rstrip("/")
        self._runtime = runtime

    @staticmethod
    def local(**kw):
        """Embedded runtime with given capability kwargs.

        e.g. OpenZenClient.local(sandbox_dirs=[...], allow_write=True)
        """
        from .capabilities import Capabilities
        from .runtime import Runtime, RuntimeConfig, ExecutionBudgets
        from .os_adapter import OsAdapter
        sandbox_dirs = kw.pop("sandbox_dirs", [])
        if sandbox_dirs:
            caps = Capabilities.sandbox(sandbox_dirs, write=kw.pop("allow_write", True))
            for k, v in kw.items():
                if hasattr(caps, k):
                    setattr(caps, k, v)
        else:
            caps = kw.pop("capabilities", None) or Capabilities()
        budgets = kw.pop("budgets", None) or ExecutionBudgets()
        approval = kw.pop("approval_callback", None)
        adapter = OsAdapter(allowed_dirs=caps.allowed_dirs)
        rt = Runtime(RuntimeConfig(capabilities=caps, budgets=budgets,
                                   approval_callback=approval, os_adapter=adapter))
        return OpenZenClient(runtime=rt)

    @staticmethod
    def remote(base_url):
        return OpenZenClient(base_url=base_url)

    def program(self, name="program"):
        return ProgramBuilder(name)

    # -- validation / compile (local, no server round-trip) --
    def validate(self, builder_or_program):
        from .validator import validate
        prog = builder_or_program.build() if isinstance(builder_or_program, ProgramBuilder) else builder_or_program
        return validate(prog)

    def compile(self, builder_or_program):
        from .codec import encode
        prog = builder_or_program.build() if isinstance(builder_or_program, ProgramBuilder) else builder_or_program
        return encode(prog)

    def disassemble(self, data):
        from .codec import disassemble
        return disassemble(data)

    def capabilities(self):
        if self.base_url:
            return self._get("/v1/capabilities")
        from .isa import OP_REGISTRY
        return {"isa_version": "1.0", "operations": [o.to_dict() for o in OP_REGISTRY]}

    def execute(self, builder_or_program, timeout=30):
        prog = builder_or_program.build() if isinstance(builder_or_program, ProgramBuilder) else builder_or_program
        if self.base_url:
            payload = json.dumps(prog.to_dict()).encode()
            return Execution(self._post("/v1/executions", payload, timeout=timeout))
        if self._runtime is None:
            raise OzError("NO_RUNTIME", "No embedded runtime configured.")
        res = self._runtime.execute_program(prog)
        return Execution(res.to_dict())

    def execute_source(self, text, timeout=30):
        if self.base_url:
            return Execution(self._post("/v1/executions", json.dumps({"source": text}).encode(), timeout=timeout))
        from .parser import parse_source
        prog = parse_source(text)
        return self.execute(prog, timeout=timeout)

    def _get(self, path):
        req = urllib.request.Request(self.base_url + path, method="GET")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())

    def _post(self, path, payload, timeout=30):
        req = urllib.request.Request(self.base_url + path, data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
