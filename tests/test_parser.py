import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openzen.parser import parse_source
from openzen.values import OzError


class ParserTests(unittest.TestCase):
    def test_minimal(self):
        p = parse_source('PROGRAM hello\nLET x = CORE.ADD 1 2\nRETURN $x\nEND\n')
        self.assertEqual(p.name, "hello")
        self.assertEqual(len(p.statements), 2)

    def test_if_else(self):
        p = parse_source('PROGRAM t\nLET x = 1\nIF CORE.GT $x 0 THEN\nLET y = 2\nELSE\nLET y = 3\nEND\nRETURN $y\nEND\n')
        self.assertEqual(p.statements[1]["kind"], "if")

    def test_for(self):
        p = parse_source('PROGRAM t\nLET xs = DATA.SORT $ys\nFOR i IN $xs DO\nLET y = CORE.ADD $i 1\nEND\nRETURN $xs\nEND\n'.replace("$ys", "1"))
        # '1' literal iterable is fine for parsing
        self.assertEqual(p.statements[1]["kind"], "for")

    def test_rejects_unknown_statement(self):
        with self.assertRaises(OzError):
            parse_source('PROGRAM t\nFROBNICATE 1\nEND\n')

    def test_rejects_missing_end(self):
        with self.assertRaises(OzError):
            parse_source('PROGRAM t\nLET x = 1\n')

    def test_comments_and_strings(self):
        p = parse_source('PROGRAM t # comment\nLET s = "a b # not comment"\nRETURN $s\nEND\n')
        self.assertEqual(p.statements[0]["value"], {"literal": "a b # not comment"})

    def test_nested_opcall_rejected(self):
        with self.assertRaises(OzError):
            parse_source('PROGRAM t\nLET x = CORE.ADD CORE.ADD 1 2 3\nEND\n')


if __name__ == "__main__":
    unittest.main()
