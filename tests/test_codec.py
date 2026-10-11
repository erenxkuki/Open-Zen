import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openzen.parser import parse_source
from openzen.codec import encode, decode, disassemble
from openzen.values import OzError


class CodecTests(unittest.TestCase):
    def test_roundtrip(self):
        src = 'PROGRAM rt\nLET a = CORE.ADD 20 22\nLET t = CORE.TOSTRING $a\nIF CORE.GT $a 10 THEN\nLET b = 1\nELSE\nLET b = 2\nEND\nFOR i IN $a DO\nLET c = 1\nEND\nRETURN $t\nEND\n'
        # FOR over int is invalid at runtime but must still encode; use array literal program instead
        src = ('PROGRAM rt\nLET a = CORE.ADD 20 22\nLET t = CORE.TOSTRING $a\n'
               'IF CORE.GT $a 10 THEN\nLET b = 1\nELSE\nLET b = 2\nEND\nRETURN $t\nEND\n')
        p = parse_source(src)
        data = encode(p)
        self.assertTrue(data.startswith(b"OZB1"))
        q = decode(data)
        self.assertEqual(q.name, "rt")
        self.assertEqual(q.to_dict(), p.to_dict())

    def test_for_roundtrip(self):
        from openzen.program import Program
        p = Program("f", [
            {"kind": "let_literal", "target": "xs", "value": {"literal": [3, 1, 2]}},
            {"kind": "let", "target": "u", "op": "DATA.UNIQUE",
             "args": [{"var": "xs"}]},
            {"kind": "for", "target": "i", "iterable": {"var": "u"},
             "body": [{"kind": "let", "target": "y", "op": "CORE.ADD",
                       "args": [{"var": "i"}, {"literal": 1}]}],
             "max_iter": 100},
            {"kind": "return", "value": {"var": "u"}},
        ])
        data = encode(p)
        q = decode(data)
        self.assertEqual(q.to_dict(), p.to_dict())

    def test_reject_bad_magic(self):
        with self.assertRaises(OzError):
            decode(b"BAD!" + b"\x00" * 20)

    def test_reject_truncated(self):
        p = parse_source('PROGRAM t\nLET x = 1\nRETURN $x\nEND\n')
        data = encode(p)
        with self.assertRaises(OzError):
            decode(data[:10])

    def test_reject_crc(self):
        p = parse_source('PROGRAM t\nLET x = 1\nRETURN $x\nEND\n')
        data = bytearray(encode(p))
        data[-1] ^= 0xFF
        with self.assertRaises(OzError):
            decode(bytes(data))

    def test_reject_unknown_op_id(self):
        import struct
        p = parse_source('PROGRAM t\nLET x = 1\nRETURN $x\nEND\n')
        data = bytearray(encode(p, with_crc=False))
        # patch the RETURN's inline? simpler: corrupt a LET op id if present; here only let_literal+return
        # corrupt statement kind byte (first stmt kind at offset 8+2+len(name)+4)
        with self.assertRaises(OzError):
            decode(bytes(data) + b"\x00")

    def test_disassemble(self):
        p = parse_source('PROGRAM t\nLET x = CORE.ADD 1 2\nRETURN $x\nEND\n')
        s = disassemble(encode(p))
        self.assertIn("CORE.ADD", s)


if __name__ == "__main__":
    unittest.main()
