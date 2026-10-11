import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openzen import OpenZenClient
from openzen.values import OzError


def local_client(**kw):
    return OpenZenClient.local(**kw)


class RuntimeComputeTests(unittest.TestCase):
    def test_add(self):
        c = local_client()
        p = c.program("t")
        p.let("r", "CORE.ADD", 20, 22)
        p.ret({"var": "r"})
        self.assertEqual(c.execute(p).result, 42)

    def test_branch_and_loop(self):
        # Build via JSON IR (text syntax has no array literals in v1):
        # UNIQUE over [3,1,3] -> [3,1]; loop binds each element; return count.
        from openzen.program import Program
        c = local_client()
        prog = Program("t", [
            {"kind": "let_literal", "target": "xs", "value": {"literal": [3, 1, 3]}},
            {"kind": "let", "target": "u", "op": "DATA.UNIQUE", "args": [{"var": "xs"}]},
            {"kind": "let", "target": "n", "op": "CORE.LEN", "args": [{"var": "u"}]},
            {"kind": "return", "value": {"var": "n"}},
        ])
        ex = c.execute(prog)
        self.assertTrue(ex.ok)
        self.assertEqual(ex.result, 2)

    def test_runtime_type_error(self):
        # UNIQUE over a string must fail at validation (schema) time.
        c = local_client()
        prog = c.program("t")
        prog.statements.append({"kind": "let", "target": "xs", "op": "DATA.UNIQUE",
                                "args": [{"literal": "not-an-array"}]})
        prog.ret({"var": "xs"})
        with self.assertRaises(OzError):
            c.validate(prog.build())

    def test_div_zero(self):
        c = local_client()
        ex = c.execute_source('PROGRAM t\nLET x = CORE.DIV 1 0\nRETURN $x\nEND\n')
        self.assertEqual(ex.status, "error")
        self.assertEqual(ex.error["code"], "DIVISION_BY_ZERO")

    def test_step_budget(self):
        from openzen.runtime import Runtime, RuntimeConfig, ExecutionBudgets
        from openzen.capabilities import Capabilities
        from openzen.parser import parse_source
        rt = Runtime(RuntimeConfig(capabilities=Capabilities(), budgets=ExecutionBudgets(max_steps=2)))
        res = rt.execute_source('PROGRAM t\nLET a = CORE.ADD 1 2\nLET b = CORE.ADD $a 3\nLET c = CORE.ADD $b 4\nRETURN $c\nEND\n')
        self.assertEqual(res.status, "error")
        self.assertIn("BUDGET", res.error["code"])

    def test_cancellation(self):
        from openzen.runtime import Runtime, RuntimeConfig, CancellationToken
        from openzen.capabilities import Capabilities
        from openzen.parser import parse_source
        rt = Runtime(RuntimeConfig(capabilities=Capabilities()))
        tok = CancellationToken()
        tok.cancel()
        res = rt.execute_program(parse_source('PROGRAM t\nLET x = 1\nRETURN $x\nEND\n'), tok)
        self.assertEqual(res.status, "cancelled")

    def test_data_ops(self):
        from openzen.program import Program
        c = local_client()
        prog = Program("t", [
            {"kind": "let_literal", "target": "rows", "value": {"literal": [1, 2, 2]}},
            {"kind": "let", "target": "s", "op": "DATA.SUMMARIZE", "args": [{"var": "rows"}]},
            {"kind": "return", "value": {"var": "s"}},
        ])
        ex = c.execute(prog)
        self.assertTrue(ex.ok)
        self.assertEqual(ex.result["count"], 3)


class FilesystemTests(unittest.TestCase):
    def test_list_and_read(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "a.txt"), "w") as f:
                f.write("hi")
            c = local_client(sandbox_dirs=[d])
            ex = c.execute_source('PROGRAM t\nLET e = FS.LIST "."\nRETURN $e\nEND\n')
            self.assertEqual(ex.status, "ok")
            self.assertIn("a.txt", ex.result)

    def test_denied_without_capability(self):
        c = local_client()
        ex = c.execute_source('PROGRAM t\nLET e = FS.LIST "."\nRETURN $e\nEND\n')
        self.assertEqual(ex.status, "error")
        self.assertEqual(ex.error["code"], "CAPABILITY_DENIED")

    def test_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            c = local_client(sandbox_dirs=[d])
            ex = c.execute_source('PROGRAM t\nLET e = FS.LIST "../../.."\nRETURN $e\nEND\n')
            self.assertEqual(ex.status, "error")
            self.assertIn(ex.error["code"], ("PATH_ESCAPE", "FS_ERROR"))

    def test_delete_requires_approval(self):
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "x.txt")
            with open(fp, "w") as f:
                f.write("x")
            c = local_client(sandbox_dirs=[d])
            c._runtime.config.capabilities.allow_fs_delete = True
            ex = c.execute_source('PROGRAM t\nLET e = FS.DELETE "x.txt"\nRETURN $e\nEND\n')
            self.assertEqual(ex.status, "error")
            self.assertEqual(ex.error["code"], "APPROVAL_REQUIRED")


class ProcTests(unittest.TestCase):
    def test_proc_list_denied(self):
        c = local_client()
        ex = c.execute_source('PROGRAM t\nLET p = PROC.LIST\nRETURN $p\nEND\n')
        self.assertEqual(ex.status, "error")

    def test_proc_launch_not_allowlisted(self):
        from openzen.capabilities import Capabilities
        from openzen.runtime import Runtime, RuntimeConfig
        from openzen.program import Program
        rt = Runtime(RuntimeConfig(capabilities=Capabilities(allowed_programs=["python"]),
                                     approval_callback=lambda op, d: True))
        prog = Program("t", [
            {"kind": "let_literal", "target": "args", "value": {"literal": ["--version"]}},
            {"kind": "let", "target": "r", "op": "PROC.LAUNCH",
             "args": [{"literal": "evilprog"}, {"var": "args"}]},
            {"kind": "return", "value": {"var": "r"}},
        ])
        res = rt.execute_program(prog)
        self.assertEqual(res.status, "error")
        self.assertEqual(res.error["code"], "CAPABILITY_DENIED")


if __name__ == "__main__":
    unittest.main()
