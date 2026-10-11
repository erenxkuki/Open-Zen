import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openzen import OpenZenClient
from openzen.ai_adapter import MockAdapter, run_task


class SdkAiTests(unittest.TestCase):
    def test_sdk_build_execute(self):
        c = OpenZenClient.local()
        p = c.program("demo")
        p.let("r", "CORE.MUL", 6, 7)
        p.ret({"var": "r"})
        ex = c.execute(p)
        self.assertTrue(ex.ok)
        self.assertEqual(ex.result, 42)

    def test_sdk_validate_rejects(self):
        from openzen.values import OzError
        c = OpenZenClient.local()
        p = c.program("bad")
        p.let("r", "CORE.ADD", "not-a-number", 1)
        with self.assertRaises(OzError):
            c.validate(p)

    def test_ai_adapter_mock(self):
        c = OpenZenClient.local()
        stages = run_task("add", MockAdapter(program_text='PROGRAM t\nLET x = CORE.ADD 2 3\nRETURN $x\nEND\n'), c)
        self.assertEqual(stages["execution"]["result"], 5)

    def test_ai_adapter_rejects_bad_output(self):
        from openzen.values import OzError
        c = OpenZenClient.local()
        with self.assertRaises(OzError):
            run_task("x", MockAdapter(program_text='EXEC rm -rf /\n'), c)


if __name__ == "__main__":
    unittest.main()
