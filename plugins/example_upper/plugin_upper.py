"""Minimal plugin example: STRING.UPPER (op id 1000). Install explicitly; never auto-load."""
from openzen.isa import OpDef
from openzen.plugin import Plugin, register_plugin

ops = [OpDef("STRING.UPPER", 1000, 1, [("s", "string")], "string", "compute", True, "Uppercase ASCII.")]
handlers = {"STRING.UPPER": lambda self, s: s.upper()}

plugin = Plugin("example_upper", "1.0", ops, handlers)

if __name__ == "__main__":
    print(register_plugin(plugin))
    from openzen import OpenZenClient
    c = OpenZenClient.local()
    print(c.execute_source('PROGRAM t\nLET x = STRING.UPPER "hi"\nRETURN $x\nEND\n').result)
