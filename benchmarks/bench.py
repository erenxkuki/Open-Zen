"""Reproducible micro-benchmarks. No performance claims beyond these numbers."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openzen.parser import parse_source
from openzen.codec import encode, decode
from openzen import OpenZenClient

SRC = 'PROGRAM bench\nLET a = CORE.ADD 1 2\nLET b = CORE.MUL $a 3\nLET c = CORE.HASH_SHA256 $b\nRETURN $c\nEND\n'

def bench(fn, n=1000):
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t0) / n * 1000

p = parse_source(SRC)
data = encode(p)
c = OpenZenClient.local()
print(f"compile: {bench(lambda: encode(p), 500):.3f} ms/run, size {len(data)} bytes")
print(f"validate+decode: {bench(lambda: decode(data), 500):.3f} ms/run")
print(f"execute: {bench(lambda: c.execute(p), 500):.3f} ms/run")
