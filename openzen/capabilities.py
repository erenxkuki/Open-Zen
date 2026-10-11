"""Capability manager: explicit grants for sensitive operations."""
from __future__ import annotations
from dataclasses import dataclass, field
from .values import OzError


@dataclass
class Capabilities:
    allow_fs_read: bool = False
    allow_fs_write: bool = False
    allow_fs_delete: bool = False
    allowed_dirs: list = field(default_factory=list)  # absolute paths
    allow_proc_list: bool = False
    allowed_programs: list = field(default_factory=list)  # executable names/paths
    allow_proc_kill: bool = False
    allow_sys_info: bool = False
    allowed_env_vars: list = field(default_factory=list)  # exact env var names
    allowed_hosts: list = field(default_factory=list)  # exact hostnames or suffixes like ".example.com"
    require_approval_for: tuple = ("FS.DELETE", "PROC.LAUNCH", "PROC.KILL", "NET.FETCH")

    def requires(self, capability):
        mapping = {
            "compute": True,
            "fs.read": self.allow_fs_read,
            "fs.write": self.allow_fs_write,
            "fs.delete": self.allow_fs_delete,
            "proc.list": self.allow_proc_list,
            "proc.launch": bool(self.allowed_programs),
            "proc.kill": self.allow_proc_kill,
            "sys.info": self.allow_sys_info,
            "sys.env": bool(self.allowed_env_vars),
            "net.fetch": bool(self.allowed_hosts),
        }
        return mapping.get(capability, False)

    def check(self, op_name, capability):
        if capability == "compute":
            return
        if not self.requires(capability):
            raise OzError("CAPABILITY_DENIED",
                          f"Operation {op_name} requires capability '{capability}', which was not granted.",
                          {"op": op_name, "capability": capability})

    def needs_approval(self, op_name):
        return op_name in self.require_approval_for

    def to_dict(self):
        return {
            "allow_fs_read": self.allow_fs_read,
            "allow_fs_write": self.allow_fs_write,
            "allow_fs_delete": self.allow_fs_delete,
            "allowed_dirs": list(self.allowed_dirs),
            "allow_proc_list": self.allow_proc_list,
            "allowed_programs": list(self.allowed_programs),
            "allow_proc_kill": self.allow_proc_kill,
            "allow_sys_info": self.allow_sys_info,
            "allowed_env_vars": list(self.allowed_env_vars),
            "allowed_hosts": list(self.allowed_hosts),
        }

    @staticmethod
    def sandbox(directories, write=True):
        import os
        absdirs = [os.path.abspath(d) for d in directories]
        return Capabilities(
            allow_fs_read=True, allow_fs_write=write, allow_fs_delete=False,
            allowed_dirs=absdirs, allow_proc_list=False,
            allowed_programs=[], allow_proc_kill=False, allow_sys_info=True,
        )

    @staticmethod
    def none():
        return Capabilities()
