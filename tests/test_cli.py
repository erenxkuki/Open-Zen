import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = {**os.environ, "NO_COLOR": "1", "PYTHONUTF8": "1"}


def oz(*args, input=None, cwd=None):
    return subprocess.run([sys.executable, "-m", "openzen", *args],
                          capture_output=True, text=True, encoding="utf-8",
                          timeout=120, cwd=cwd or ROOT, env=ENV, input=input)


class CliTests(unittest.TestCase):
    def test_version(self):
        r = oz("version")
        self.assertEqual(r.returncode, 0)
        self.assertIn("VERSION", r.stdout)
        self.assertIn("OZ-ISA", r.stdout)
        self.assertIn("OZB", r.stdout)

    def test_doctor(self):
        r = oz("doctor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("all checks passed", r.stdout)

    def test_permissions_default_denied(self):
        r = oz("permissions")
        self.assertEqual(r.returncode, 0)
        self.assertIn("EXECUTION POLICY", r.stdout)
        self.assertIn("DENIED", r.stdout)

    def test_permissions_sandbox(self):
        with tempfile.TemporaryDirectory() as d:
            r = oz("permissions", "--sandbox", d)
            self.assertIn("GRANTED", r.stdout)
            self.assertIn(d, r.stdout)

    def test_inspect_real_offsets(self):
        r = oz("inspect", "--source", "examples/arithmetic.oz")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OFFSET", r.stdout)
        self.assertIn("CORE.ADD", r.stdout)
        self.assertIn("COMPUTE", r.stdout)

    def test_inspect_json(self):
        r = oz("inspect", "--format", "json", "--source", "examples/arithmetic.oz")
        detail = json.loads(r.stdout)
        self.assertEqual(detail["name"], "arithmetic")
        self.assertTrue(all("offset" in i and "op" in i for i in detail["items"]))
        offsets = [i["offset"] for i in detail["items"]]
        self.assertEqual(offsets, sorted(offsets))

    def test_explain(self):
        r = oz("explain", "--source", "examples/arithmetic.oz")
        self.assertIn("CORE.ADD", r.stdout)
        self.assertIn("compute only", r.stdout.lower())

    def test_plugins_core_only(self):
        r = oz("plugins")
        self.assertIn("core:", r.stdout)
        self.assertIn("extensions: none installed", r.stdout)

    def test_benchmark_real_numbers(self):
        r = oz("benchmark", "--iters", "5")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ms/run", r.stdout)
        self.assertIn("measured on this machine", r.stdout)

    def test_conformance_select(self):
        r = oz("test", "--select", "ValidatorTests")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK", r.stderr + r.stdout)

    def test_run_stdout_stays_json(self):
        r = oz("run", "--no-history", "--source", "examples/arithmetic.oz")
        self.assertEqual(r.returncode, 0, r.stderr)
        body = json.loads(r.stdout)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["result"], 80)
        for stage in ("[01]", "[04]", "[07]"):
            self.assertIn(stage, r.stderr)

    def test_run_quiet(self):
        r = oz("run", "--quiet", "--no-history", "--source", "examples/arithmetic.oz")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stderr, "")
        self.assertEqual(json.loads(r.stdout)["result"], 80)

    def test_run_human(self):
        r = oz("run", "--no-history", "--format", "human", "--source", "examples/arithmetic.oz")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("EXECUTION POLICY", r.stdout)
        self.assertIn("TRACE", r.stdout)
        self.assertIn("RESULT", r.stdout)

    def test_run_failure_exit_code(self):
        r = oz("run", "--no-history", "--source", "examples/inspect_workspace.oz")
        self.assertEqual(r.returncode, 1)  # fs.read not granted
        body = json.loads(r.stdout)
        self.assertEqual(body["error"]["code"], "CAPABILITY_DENIED")

    def test_trace_lifecycle(self):
        r = oz("trace", "--no-history", "--source", "examples/arithmetic.oz")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("EXECUTION POLICY", r.stdout)
        self.assertIn("ozb prefix", r.stdout)
        self.assertIn("RESULT", r.stdout)

    def test_trace_nl_guard(self):
        r = oz("trace", "--no-history", "--expr", "Find duplicate files in ./test-data and report them.")
        self.assertEqual(r.returncode, 2)
        self.assertIn("model adapter", r.stdout + r.stderr)

    def test_step_mode_runs_through(self):
        r = oz("run", "--no-history", "--step", "--source", "examples/arithmetic.oz", input="")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("step 0000", r.stderr)
        self.assertEqual(json.loads(r.stdout)["result"], 80)

    def test_logs_and_replay(self):
        with tempfile.TemporaryDirectory() as d:
            hist = os.path.join(d, "h.jsonl")
            r = oz("run", "--history", hist, "--source", "examples/arithmetic.oz")
            self.assertEqual(r.returncode, 0, r.stderr)
            r = oz("logs", "--history", hist)
            self.assertIn("arithmetic", r.stdout)
            r = oz("replay", "--history", hist, "0")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)["result"], 80)

    def test_logs_empty(self):
        with tempfile.TemporaryDirectory() as d:
            r = oz("logs", "--history", os.path.join(d, "none.jsonl"))
            self.assertIn("no execution history", r.stdout)

    def test_shell_roundtrip(self):
        r = oz("shell", "--no-history", input="help\npermissions\nfrobnicate\nversion\nexit\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("commands execute for real", r.stdout)
        self.assertIn("EXECUTION POLICY", r.stdout)
        self.assertIn("unknown command", r.stdout)
        self.assertIn("VERSION", r.stdout)


if __name__ == "__main__":
    unittest.main()
