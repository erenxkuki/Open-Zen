import json, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openzen.parser import parse_source
from openzen.codec import encode


class GoldenTests(unittest.TestCase):
    """Golden vectors: encoding and decoding must agree byte-for-byte."""

    def test_golden_arithmetic(self):
        path = os.path.join(os.path.dirname(__file__), "golden", "arithmetic.oz")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        p = parse_source(src)
        data = encode(p)
        from openzen.codec import decode
        q = decode(data)
        self.assertEqual(p.to_dict(), q.to_dict())
        vec_path = os.path.join(os.path.dirname(__file__), "golden", "arithmetic.ozb.hex")
        if os.path.exists(vec_path):
            with open(vec_path, encoding="utf-8") as f:
                want = bytes.fromhex(f.read().strip())
            self.assertEqual(data, want)

    def test_golden_all_types(self):
        p = parse_source('PROGRAM types\nLET s = "hi"\nLET i = 7\nLET f = 2.5\nLET b = true\nLET n = null\nLET total = CORE.ADD $i 1\nRETURN $total\nEND\n')
        data = encode(p)
        from openzen.codec import decode
        self.assertEqual(decode(data).to_dict(), p.to_dict())


if __name__ == "__main__":
    unittest.main()
