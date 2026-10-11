import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openzen import OpenZenClient
from openzen.parser import parse_source
from openzen.validator import validate
from openzen.values import OzError


class ValidatorTests(unittest.TestCase):
    def test_unknown_op(self):
        p = parse_source('PROGRAM t\nLET x = NOPE.OP 1\nRETURN $x\nEND\n')
        with self.assertRaises(OzError):
            validate(p)

    def test_undefined_var(self):
        p = parse_source('PROGRAM t\nLET x = CORE.ADD $missing 1\nRETURN $x\nEND\n')
        with self.assertRaises(OzError):
            validate(p)

    def test_arity(self):
        p = parse_source('PROGRAM t\nLET x = CORE.ADD 1\nRETURN $x\nEND\n')
        with self.assertRaises(OzError):
            validate(p)

    def test_type_error_literal(self):
        p = parse_source('PROGRAM t\nLET x = CORE.ADD "a" 1\nRETURN $x\nEND\n')
        with self.assertRaises(OzError):
            validate(p)

    def test_ok_reports_caps(self):
        p = parse_source('PROGRAM t\nLET e = FS.LIST "."\nRETURN $e\nEND\n')
        caps = validate(p)
        self.assertIn("fs.read", caps)

    def test_loop_bound(self):
        from openzen.program import Program
        p = Program("t", [{"kind": "for", "target": "i", "iterable": {"literal": [1]},
                           "body": [], "max_iter": 10**9}])
        with self.assertRaises(OzError):
            validate(p)


if __name__ == "__main__":
    unittest.main()
