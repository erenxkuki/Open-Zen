import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openzen import OpenZenClient
from openzen.program import Program
from openzen.values import OzError


def prog_of(*stmts, name="t", ret="r"):
    return Program(name, list(stmts) + [{"kind": "return", "value": {"var": ret}}])


class PremiumCoreTests(unittest.TestCase):
    def setUp(self):
        self.c = OpenZenClient.local()

    def test_base64_roundtrip(self):
        p = prog_of({"kind": "let", "target": "e", "op": "CORE.BASE64_ENCODE",
                     "args": [{"literal": "hello ✓"}]},
                    {"kind": "let", "target": "r", "op": "CORE.BASE64_DECODE",
                     "args": [{"var": "e"}]})
        ex = self.c.execute(p)
        self.assertTrue(ex.ok)
        self.assertEqual(ex.result, "hello ✓")

    def test_base64_invalid(self):
        p = prog_of({"kind": "let", "target": "r", "op": "CORE.BASE64_DECODE",
                     "args": [{"literal": "!!!not-base64!!!"}]})
        ex = self.c.execute(p)
        self.assertEqual(ex.status, "error")
        self.assertEqual(ex.error["code"], "INVALID_BASE64")

    def test_regex(self):
        p = prog_of({"kind": "let", "target": "r", "op": "CORE.REGEX_MATCH",
                     "args": [{"literal": r"\d+"}, {"literal": "a1b22c333"}]})
        ex = self.c.execute(p)
        self.assertTrue(ex.ok)
        self.assertEqual(ex.result, ["1", "22", "333"])

    def test_regex_bad_pattern(self):
        p = prog_of({"kind": "let", "target": "r", "op": "CORE.REGEX_MATCH",
                     "args": [{"literal": "([a"}, {"literal": "x"}]})
        ex = self.c.execute(p)
        self.assertEqual(ex.error["code"], "INVALID_PATTERN")

    def test_uuid4_shape(self):
        import re
        p = prog_of({"kind": "let", "target": "r", "op": "CORE.UUID4", "args": []})
        ex = self.c.execute(p)
        self.assertTrue(ex.ok)
        self.assertTrue(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", ex.result))

    def test_time_now(self):
        import time
        p = prog_of({"kind": "let", "target": "r", "op": "TIME.NOW", "args": []})
        c = OpenZenClient.local()
        c._runtime.config.capabilities.allow_sys_info = True
        ex = c.execute(p)
        self.assertTrue(ex.ok)
        self.assertTrue(abs(ex.result - int(time.time())) < 60)

    def test_time_denied_by_default(self):
        p = prog_of({"kind": "let", "target": "r", "op": "TIME.NOW", "args": []})
        ex = self.c.execute(p)
        self.assertEqual(ex.error["code"], "CAPABILITY_DENIED")


class PremiumDataTests(unittest.TestCase):
    def setUp(self):
        self.c = OpenZenClient.local()

    def test_project(self):
        p = prog_of(
            {"kind": "let_literal", "target": "rows",
             "value": {"literal": [{"a": 1, "b": 2}, {"a": 3, "b": 4}]}},
            {"kind": "let", "target": "r", "op": "DATA.PROJECT",
             "args": [{"var": "rows"}, {"literal": ["a"]}]})
        ex = self.c.execute(p)
        self.assertTrue(ex.ok)
        self.assertEqual(ex.result, [{"a": 1}, {"a": 3}])

    def test_project_missing_field(self):
        p = prog_of(
            {"kind": "let_literal", "target": "rows", "value": {"literal": [{"a": 1}]}},
            {"kind": "let", "target": "r", "op": "DATA.PROJECT",
             "args": [{"var": "rows"}, {"literal": ["zzz"]}]})
        ex = self.c.execute(p)
        self.assertEqual(ex.error["code"], "KEY_ERROR")

    def test_json_get(self):
        p = prog_of({"kind": "let", "target": "r", "op": "DATA.JSON_GET",
                     "args": [{"literal": '{"a": {"b": [10, 20]}}'}, {"literal": "a.b.1"}]})
        ex = self.c.execute(p)
        self.assertTrue(ex.ok)
        self.assertEqual(ex.result, 20)

    def test_csv_parse(self):
        p = prog_of({"kind": "let", "target": "r", "op": "DATA.CSV_PARSE",
                     "args": [{"literal": "name,age\namy,30\nbo,25\n"}]})
        ex = self.c.execute(p)
        self.assertTrue(ex.ok)
        self.assertEqual(ex.result, [{"name": "amy", "age": "30"}, {"name": "bo", "age": "25"}])

    def test_csv_ragged_rejected(self):
        p = prog_of({"kind": "let", "target": "r", "op": "DATA.CSV_PARSE",
                     "args": [{"literal": "a,b\n1\n"}]})
        ex = self.c.execute(p)
        self.assertEqual(ex.error["code"], "INVALID_CSV")


class PremiumFsTests(unittest.TestCase):
    def test_copy_glob_append(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "a.txt"), "w") as f:
                f.write("hi")
            c = OpenZenClient.local(sandbox_dirs=[d])
            p = Program("t", [
                {"kind": "let", "target": "cp", "op": "FS.COPY",
                 "args": [{"literal": "a.txt"}, {"literal": "sub/b.txt"}]},
                {"kind": "let", "target": "g", "op": "FS.GLOB",
                 "args": [{"literal": "."}, {"literal": "*.txt"}]},
                {"kind": "let", "target": "ap", "op": "FS.APPEND_TEXT",
                 "args": [{"literal": "a.txt"}, {"literal": " there"}]},
                {"kind": "let", "target": "r", "op": "FS.READ_TEXT",
                 "args": [{"literal": "a.txt"}]},
                {"kind": "return", "value": {"var": "r"}},
            ])
            ex = c.execute(p)
            self.assertTrue(ex.ok, ex.error)
            self.assertEqual(ex.result, "hi there")
            trace_ops = [t["op"] for t in ex.trace]
            self.assertEqual(trace_ops, ["FS.COPY", "FS.GLOB", "FS.APPEND_TEXT", "FS.READ_TEXT", "RETURN"])

    def test_glob_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            c = OpenZenClient.local(sandbox_dirs=[d])
            p = prog_of({"kind": "let", "target": "r", "op": "FS.GLOB",
                         "args": [{"literal": "."}, {"literal": "../*.txt"}]})
            ex = c.execute(p)
            self.assertEqual(ex.error["code"], "PATH_ESCAPE")


class PremiumSysNetTests(unittest.TestCase):
    def test_env_allowlisted(self):
        os.environ["OZ_TEST_VAR"] = "s3cret-value"
        try:
            c = OpenZenClient.local()
            c._runtime.config.capabilities.allowed_env_vars = ["OZ_TEST_VAR"]
            p = prog_of({"kind": "let", "target": "r", "op": "SYS.ENV",
                         "args": [{"literal": "OZ_TEST_VAR"}]})
            ex = c.execute(p)
            self.assertTrue(ex.ok)
            self.assertEqual(ex.result, "s3cret-value")
        finally:
            del os.environ["OZ_TEST_VAR"]

    def test_env_denied(self):
        os.environ["OZ_NOPE"] = "x"
        try:
            c = OpenZenClient.local()
            p = prog_of({"kind": "let", "target": "r", "op": "SYS.ENV",
                         "args": [{"literal": "OZ_NOPE"}]})
            ex = c.execute(p)
            self.assertEqual(ex.error["code"], "CAPABILITY_DENIED")
        finally:
            del os.environ["OZ_NOPE"]

    def test_net_denied_by_default(self):
        c = OpenZenClient.local()
        p = prog_of({"kind": "let", "target": "r", "op": "NET.FETCH",
                     "args": [{"literal": "https://example.com/"}]})
        ex = c.execute(p)
        self.assertEqual(ex.status, "error")
        self.assertIn(ex.error["code"], ("CAPABILITY_DENIED", "APPROVAL_REQUIRED"))

    def test_net_host_not_allowlisted(self):
        c = OpenZenClient.local()
        c._runtime.config.capabilities.allowed_hosts = ["example.com"]
        c._runtime.config.approval_callback = lambda op, d: True
        p = prog_of({"kind": "let", "target": "r", "op": "NET.FETCH",
                     "args": [{"literal": "https://evil.example/"}]})
        ex = c.execute(p)
        self.assertEqual(ex.error["code"], "CAPABILITY_DENIED")

    def test_net_bad_scheme(self):
        c = OpenZenClient.local()
        c._runtime.config.capabilities.allowed_hosts = ["x"]
        c._runtime.config.approval_callback = lambda op, d: True
        p = prog_of({"kind": "let", "target": "r", "op": "NET.FETCH",
                     "args": [{"literal": "file:///etc/passwd"}]})
        ex = c.execute(p)
        self.assertEqual(ex.error["code"], "INVALID_URL")

    def test_net_fetch_local_server(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = b'{"hello": "world"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        httpd = HTTPServer(("127.0.0.1", 0), H)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            c = OpenZenClient.local()
            c._runtime.config.capabilities.allowed_hosts = ["127.0.0.1"]
            c._runtime.config.approval_callback = lambda op, d: True
            p = prog_of({"kind": "let", "target": "r", "op": "NET.FETCH",
                         "args": [{"literal": f"http://127.0.0.1:{port}/data"}]})
            ex = c.execute(p)
            self.assertTrue(ex.ok, ex.error)
            self.assertEqual(ex.result["status"], 200)
            self.assertIn("hello", ex.result["body"])
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()


class BannerTests(unittest.TestCase):
    def test_banner_content(self):
        from openzen.banner import BANNER, TAGLINE, full_banner
        self.assertIn("██████", BANNER)
        self.assertEqual(len(BANNER.splitlines()), 6)
        self.assertEqual(TAGLINE, "AI-NATIVE INSTRUCTION LANGUAGE & EXECUTION RUNTIME")
        text = full_banner()
        self.assertIn(TAGLINE, text)

    def test_banner_asset_matches(self):
        from openzen.banner import full_banner
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "assets", "banner.txt")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), full_banner())

    def test_cli_banner_command(self):
        import subprocess
        r = subprocess.run([sys.executable, "-m", "openzen", "banner"],
                           capture_output=True, text=True, encoding="utf-8",
                           timeout=30,
                           cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.assertEqual(r.returncode, 0)
        self.assertIn("██████", r.stdout)
        self.assertIn("AI-NATIVE INSTRUCTION LANGUAGE & EXECUTION RUNTIME", r.stdout)
