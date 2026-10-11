"""Plugin contract for extending OZ-ISA without modifying the core."""
from __future__ import annotations
from .isa import OP_REGISTRY, OP_BY_NAME, OP_BY_ID, OpDef
from .values import OzError


class Plugin:
    """A plugin provides extra OpDefs + handler functions.

    handlers: dict op_name -> fn(*args) (bound at registration time to a
    Runtime-compatible callable receiving the runtime as first arg, or plain fn).
    """
    def __init__(self, name, version, ops, handlers):
        self.name = name
        self.version = version
        self.ops = ops
        self.handlers = handlers

    def describe(self):
        return {"name": self.name, "version": self.version,
                "ops": [o.to_dict() for o in self.ops]}


def register_plugin(plugin, runtime_cls=None):
    """Register plugin ops globally and attach handlers to Runtime.

    Prefers explicitly installed, trusted plugins. Raises on ID/name collision.
    """
    from . import runtime as rt_mod
    target = runtime_cls or rt_mod.Runtime
    for op in plugin.ops:
        if op.name in OP_BY_NAME:
            raise OzError("PLUGIN_CONFLICT", f"Op name already registered: {op.name}")
        if op.op_id in OP_BY_ID:
            raise OzError("PLUGIN_CONFLICT", f"Op id already registered: {op.op_id}")
        if not (1000 <= op.op_id <= 60000):
            raise OzError("PLUGIN_ERROR", "Plugin op IDs must be in 1000..60000.")
        OP_REGISTRY.append(op)
        OP_BY_NAME[op.name] = op
        OP_BY_ID[op.op_id] = op
        handler = plugin.handlers.get(op.name)
        if handler is None:
            raise OzError("PLUGIN_ERROR", f"Missing handler for {op.name}")
        setattr(target, "_op_" + op.name.replace(".", "_"), handler)
    return plugin.describe()
