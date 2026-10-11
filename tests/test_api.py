import json, os, sys, threading, time, unittest, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openzen.api_server import build_handler, make_runtime
from http.server import ThreadingHTTPServer


def _free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = _free_port()
        handler = build_handler(lambda: make_runtime())
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", cls.port), handler)
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()
        time.sleep(0.2)
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _post(self, path, obj):
        req = urllib.request.Request(self.base + path, data=json.dumps(obj).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def _get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as r:
            return r.status, json.loads(r.read().decode())

    def test_health(self):
        code, body = self._get("/v1/health")
        self.assertEqual(code, 200)
        self.assertEqual(body["status"], "ok")

    def test_validate(self):
        code, body = self._post("/v1/programs/validate", {"source": "PROGRAM t\nLET x = CORE.ADD 1 2\nRETURN $x\nEND\n"})
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])

    def test_execute_ok(self):
        code, body = self._post("/v1/executions", {"source": "PROGRAM t\nLET x = CORE.ADD 1 2\nRETURN $x\nEND\n"})
        self.assertEqual(code, 200)
        self.assertEqual(body["result"], 3)

    def test_execute_rejects_bad(self):
        code, body = self._post("/v1/executions", {"source": "PROGRAM t\nLET x = NOPE.OP 1\nRETURN $x\nEND\n"})
        self.assertIn(code, (400, 422))

    def test_cancel_unknown(self):
        code, body = self._post("/v1/executions/ex_nope/cancel", {})
        self.assertEqual(code, 404)


if __name__ == "__main__":
    unittest.main()
