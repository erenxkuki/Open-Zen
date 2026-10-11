import os, sys, random, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openzen.codec import encode, decode
from openzen.parser import parse_source
from openzen.values import OzError


class FuzzTests(unittest.TestCase):
    def test_decode_random_rejects_or_roundtrips(self):
        rng = random.Random(1234)
        crashes = 0
        for _ in range(500):
            n = rng.randint(0, 60)
            blob = bytes(rng.randrange(256) for _ in range(n))
            try:
                decode(blob)
            except OzError:
                pass
            except Exception as e:
                crashes += 1
        self.assertEqual(crashes, 0, "decoder raised non-OzError on fuzz input")

    def test_parser_fuzz_no_crash_outside_ozerror(self):
        rng = random.Random(99)
        alphabet = "PROGRAM LET RETURN IF THEN ELSE FOR IN DO END $_.\"#=0123456789CORE.ADD \n"
        for _ in range(300):
            s = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 120)))
            try:
                parse_source(s)
            except OzError:
                pass
            except Exception:
                self.fail("parser raised non-OzError")


if __name__ == "__main__":
    unittest.main()
