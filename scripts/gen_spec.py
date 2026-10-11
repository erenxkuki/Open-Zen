"""Regenerate machine-readable specs from openzen/isa.py. Run: python scripts/gen_spec.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openzen.isa import OP_REGISTRY, ISA_VERSION

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.join(root, "spec", "isa", "oz-isa-1.0.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
doc = {"isa_version": f"{ISA_VERSION[0]}.{ISA_VERSION[1]}",
       "operations": [o.to_dict() for o in OP_REGISTRY]}
open(out, "w").write(json.dumps(doc, indent=2))
print(f"Wrote {out} ({len(OP_REGISTRY)} ops)")
schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "OZ program",
    "type": "object",
    "required": ["name", "statements"],
    "properties": {
        "name": {"type": "string"},
        "isa_version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+$"},
        "statements": {"type": "array"},
    },
}
sout = os.path.join(root, "spec", "schemas", "program.schema.json")
os.makedirs(os.path.dirname(sout), exist_ok=True)
open(sout, "w").write(json.dumps(schema, indent=2))
print(f"Wrote {sout}")
