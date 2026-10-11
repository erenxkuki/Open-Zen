"""Local runtime API server (stdlib only). Binds localhost by default.

Routes:
  GET  /v1/health
  GET  /v1/capabilities
  POST /v1/programs/validate   {source? | program?} -> {ok, required_capabilities?, error?}
  POST /v1/programs/compile    {source? | program?} -> {ok, ozb_hex?, size?, error?}
  POST /v1/executions          {source? | program? | ozb_hex?} -> execution dict (+ execution_id)
  GET  /v1/executions/{id}
  POST /v1/executions/{id}/cancel
  GET  /v1/executions/{id}/trace
"""
from __future__ import annotations
import json
import threading
import uuid
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .isa import OP_REGISTRY, ISA_VERSION
from .values import OzError
from .runtime import Runtime, RuntimeConfig, ExecutionBudgets, CancellationToken
from .capabilities import Capabilities
from .os_adapter import OsAdapter

MAX_BODY = 2 * 1024 * 1024


def make_runtime(sandbox_dirs=(), allow_write=True, approval_callback=None):
    caps = Capabilities.sandbox(list(sandbox_dirs), write=allow_write) if sandbox_dirs else Capabilities()
    adapter = OsAdapter(allowed_dirs=caps.allowed_dirs)
    auto_approve = (lambda op, details: True) if approval_callback == "auto" else approval_callback
    return Runtime(RuntimeConfig(capabilities=caps, budgets=ExecutionBudgets(),
                                 approval_callback=auto_approve, os_adapter=adapter))


class _Store:
    def __init__(self):
        self.lock = threading.Lock()
        self.items = {}

    def put(self, eid, record):
        with self.lock:
            self.items[eid] = record

    def get(self, eid):
        with self.lock:
            return self.items.get(eid)


def build_handler(runtime_factory):
    store = _Store()
    state = {"runtime_factory": runtime_factory, "store": store}

    class Handler(BaseHTTPRequestHandler):
        server_version = "OpenZen/0.1"

        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise OzError("LIMIT_EXCEEDED", "Request body too large.")
            raw = self.rfile.read(n) if n else b"{}"
            if not raw:
                return {}
            ctype = self.headers.get("Content-Type", "")
            if "application/json" not in ctype and raw[:1] not in (b"{", b"["):
                raise OzError("INVALID_REQUEST", "Expected JSON body.")
            try:
                obj = json.loads(raw.decode())
            except Exception:
                raise OzError("INVALID_REQUEST", "Malformed JSON body.")
            # binary OZB requests
            if isinstance(obj, dict) and obj.get("ozb_hex") and "program" not in obj and "source" not in obj:
                return obj
            return obj

        def _load_program(self, body):
            from .parser import parse_source
            from .program import load_json_program
            from .codec import decode
            if "ozb_hex" in body:
                try:
                    return decode(bytes.fromhex(body["ozb_hex"]))
                except ValueError:
                    raise OzError("MALFORMED_BINARY", "ozb_hex is not valid hex.")
            if "source" in body:
                return parse_source(body["source"])
            if "program" in body:
                return load_json_program(body["program"])
            # bare program dict
            if "statements" in body:
                return load_json_program(body)
            raise OzError("INVALID_REQUEST", "Body must contain 'source', 'program', or 'ozb_hex'.")

        def do_GET(self):
            try:
                path = urllib.parse.urlparse(self.path).path
                if path == "/v1/health":
                    self._send(200, {"status": "ok", "version": "0.1.0",
                                     "isa_version": f"{ISA_VERSION[0]}.{ISA_VERSION[1]}"})
                elif path == "/v1/capabilities":
                    self._send(200, {"isa_version": f"{ISA_VERSION[0]}.{ISA_VERSION[1]}",
                                     "operations": [o.to_dict() for o in OP_REGISTRY]})
                elif path.startswith("/v1/executions/") and path.endswith("/trace"):
                    eid = path[len("/v1/executions/"):-len("/trace")].strip("/")
                    rec = store.get(eid)
                    if not rec:
                        self._send(404, {"error": {"code": "NOT_FOUND", "message": "Unknown execution."}})
                    else:
                        self._send(200, {"execution_id": eid, "trace": rec.get("result", {}).get("trace", [])})
                elif path.startswith("/v1/executions/"):
                    eid = path[len("/v1/executions/"):].strip("/")
                    rec = store.get(eid)
                    if not rec or "/" in eid:
                        self._send(404, {"error": {"code": "NOT_FOUND", "message": "Unknown execution."}})
                    else:
                        self._send(200, {"execution_id": eid, **rec.get("result", {})})
                else:
                    self._send(404, {"error": {"code": "NOT_FOUND", "message": "Unknown route."}})
            except OzError as e:
                self._send(400, {"error": e.to_dict()})
            except Exception as e:
                self._send(500, {"error": {"code": "INTERNAL", "message": str(e)}})

        def do_POST(self):
            try:
                path = urllib.parse.urlparse(self.path).path
                if path == "/v1/programs/validate":
                    body = self._read_json()
                    prog = self._load_program(body)
                    from .validator import validate
                    caps = validate(prog)
                    self._send(200, {"ok": True, "program": prog.name,
                                     "required_capabilities": caps})
                elif path == "/v1/programs/compile":
                    body = self._read_json()
                    prog = self._load_program(body)
                    from .codec import encode
                    data = encode(prog)
                    self._send(200, {"ok": True, "ozb_hex": data.hex(), "size": len(data)})
                elif path == "/v1/executions":
                    body = self._read_json()
                    prog = self._load_program(body)
                    rt = runtime_factory()
                    token = CancellationToken()
                    eid = "ex_" + uuid.uuid4().hex[:12]
                    store.put(eid, {"token": token, "result": {"status": "running"}})
                    try:
                        res = rt.execute_program(prog, token)
                        rec = {"status": res.status, "result": res.value, "error": res.error,
                               "trace": res.trace, "steps": res.steps, "elapsed_ms": res.elapsed_ms}
                    except Exception as e:
                        rec = {"status": "error",
                               "error": {"code": "EXECUTION_ERROR", "message": str(e)}}
                    store.put(eid, {"token": token, "result": rec})
                    code = 200 if rec.get("status") == "ok" else 422
                    self._send(code, {"execution_id": eid, **rec})
                elif path.startswith("/v1/executions/") and path.endswith("/cancel"):
                    eid = path[len("/v1/executions/"):-len("/cancel")].strip("/")
                    rec = store.get(eid)
                    if not rec:
                        self._send(404, {"error": {"code": "NOT_FOUND", "message": "Unknown execution."}})
                    else:
                        try:
                            rec["token"].cancel()
                        except Exception:
                            pass
                        self._send(200, {"execution_id": eid, "cancelled": True})
                else:
                    self._send(404, {"error": {"code": "NOT_FOUND", "message": "Unknown route."}})
            except OzError as e:
                code = 422 if e.code in ("TYPE_ERROR", "CAPABILITY_DENIED", "APPROVAL_REQUIRED",
                                         "APPROVAL_DENIED", "UNKNOWN_OPERATION") else 400
                self._send(code, {"ok": False, "error": e.to_dict()})
            except Exception as e:
                self._send(500, {"error": {"code": "INTERNAL", "message": str(e)}})

    return Handler


def serve(host="127.0.0.1", port=8765, sandbox_dirs=(), allow_write=True, approval="deny"):
    approval_cb = {"auto": "auto", "deny": None}.get(approval, None)

    def factory():
        return make_runtime(sandbox_dirs, allow_write, approval_cb)

    handler = build_handler(factory)
    httpd = ThreadingHTTPServer((host, port), handler)
    from .banner import header
    from . import __version__
    print(header(status="SERVING", version=__version__,
                 isa=f"{ISA_VERSION[0]}.{ISA_VERSION[1]}", fmt="1"))
    print(f"Open Zen API on http://{host}:{port} (sandbox={list(sandbox_dirs)})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
