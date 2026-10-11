"""Interactive Zen Shell: a real terminal interface to the runtime.

Every command executes against the live runtime with the shell's granted
capabilities. Unknown commands get honest errors with close-match hints.
"""
from __future__ import annotations
import cmd
import difflib
import json
import os

from . import theme
from .banner import header
from .display import policy_box, trace_tree, explain_program, fmt_error, describe_stmt
from .values import OzError


class ZenShell(cmd.Cmd):
    intro = None
    prompt = "oz> "

    def __init__(self, runtime, history_path=None):
        super().__init__()
        self.rt = runtime
        self.history_path = history_path
        self.last_result = None

    # ---- plumbing ----
    def emptyline(self):
        pass

    def default(self, line):
        names = [n[3:] for n in self.get_names() if n.startswith("do_")]
        hint = difflib.get_close_matches(line.split()[0] if line.split() else "",
                                         names, n=1)
        print(theme.paint(f"unknown command: {line!r}", "red"))
        if hint:
            print(theme.paint(f"did you mean: {hint[0]}", "gray"))
        print(theme.paint("type 'help' for commands.", "gray"))

    def _load_file(self, arg):
        path = arg.strip().strip('"')
        if not path:
            print(theme.paint("usage: <command> <file.oz|file.ozb>", "yellow"))
            return None, None
        if path.endswith(".ozb"):
            with open(path, "rb") as f:
                from .codec import decode
                return decode(f.read()), "ozb"
        with open(path, "r", encoding="utf-8") as f:
            from .parser import parse_source
            return parse_source(f.read()), "source"

    # ---- commands ----
    def do_help(self, arg):
        print(theme.paint("Open Zen shell — commands execute for real.", "bold", "white"))
        for name, doc in sorted([
            ("run <file>", "validate + compile + execute, show pipeline"),
            ("validate <file>", "type-check and show required capabilities"),
            ("inspect <file>", "byte offsets and decoded instructions"),
            ("explain <file>", "human-readable instruction summary"),
            ("permissions", "show this shell's execution policy"),
            ("capabilities", "operation count by family"),
            ("status", "runtime budgets and grants"),
            ("doctor", "diagnose the installation"),
            ("version", "build facts"),
            ("banner", "brand header"),
            ("exit", "leave the shell"),
        ]):
            print(f"  {theme.paint(name, 'cyan')}  {theme.paint(doc, 'gray')}")

    def do_banner(self, arg):
        from .banner import print_banner
        print_banner()

    def do_version(self, arg):
        from . import __version__
        from .isa import ISA_VERSION
        from .codec import FORMAT_VERSION
        print(header(status="READY", version=__version__,
                     isa=f"{ISA_VERSION[0]}.{ISA_VERSION[1]}", fmt=FORMAT_VERSION))

    def do_status(self, arg):
        b = self.rt.config.budgets
        print(theme.paint("runtime status: READY", "green"))
        print(f"  budgets: steps={b.max_steps} time={b.max_time_ms}ms output={b.max_output_bytes}B")
        print(policy_box(self.rt.config.capabilities))

    def do_permissions(self, arg):
        print(policy_box(self.rt.config.capabilities))

    def do_capabilities(self, arg):
        from .isa import OP_REGISTRY
        fams = {}
        for o in OP_REGISTRY:
            fams[o.capability] = fams.get(o.capability, 0) + 1
        print(theme.paint(f"{len(OP_REGISTRY)} operations:", "bold", "white"))
        for cap, n in sorted(fams.items()):
            print(f"  {theme.paint(cap, 'cyan')}  {n}")

    def do_validate(self, arg):
        try:
            prog, _ = self._load_file(arg)
            if prog is None:
                return
            from .validator import validate
            caps = validate(prog)
            print(theme.paint(f"✓ {prog.name}: type check passed", "green"))
            print(theme.paint(f"  requires: {', '.join(caps) if caps else 'compute only'}", "gray"))
        except (OzError, OSError) as e:
            print(fmt_error(e.to_dict() if isinstance(e, OzError) else
                            {"code": "IO_ERROR", "message": str(e)}))

    def do_run(self, arg):
        try:
            prog, kind = self._load_file(arg)
            if prog is None:
                return
            from .validator import validate
            from .codec import encode
            caps = validate(prog)
            data = encode(prog)
            print(theme.paint(f"✓ validated ({len(data)}B OZB)  requires: {', '.join(caps) if caps else 'compute'}", "gray"))
            res = self.rt.execute_program(prog)
            self.last_result = res
            if res.status == "ok":
                print(theme.paint("✓ result:", "green"), json.dumps(res.value)[:2000])
                print(theme.paint(f"  {res.steps} steps, {res.elapsed_ms}ms", "gray"))
            else:
                print(fmt_error(res.error))
        except (OzError, OSError) as e:
            print(fmt_error(e.to_dict() if isinstance(e, OzError) else
                            {"code": "IO_ERROR", "message": str(e)}))

    def do_inspect(self, arg):
        try:
            prog, kind = self._load_file(arg)
            if prog is None:
                return
            from .codec import encode, inspect_detail
            from .display import inspect_table
            print(inspect_table(inspect_detail(encode(prog))))
        except (OzError, OSError) as e:
            print(fmt_error(e.to_dict() if isinstance(e, OzError) else
                            {"code": "IO_ERROR", "message": str(e)}))

    def do_explain(self, arg):
        try:
            prog, _ = self._load_file(arg)
            if prog is None:
                return
            print(explain_program(prog))
        except (OzError, OSError) as e:
            print(fmt_error(e.to_dict() if isinstance(e, OzError) else
                            {"code": "IO_ERROR", "message": str(e)}))

    def do_doctor(self, arg):
        from .doctor import run_checks
        ok = True
        for name, passed, detail in run_checks(sandbox_dirs=self.rt.config.capabilities.allowed_dirs):
            mark = theme.paint("✓", "green") if passed else theme.paint("✗", "red")
            print(f"  {mark} {name}  {theme.paint(detail, 'gray')}")
            ok = ok and passed
        print(theme.paint("doctor: all checks passed" if ok else "doctor: issues found", "green" if ok else "red"))

    def do_exit(self, arg):
        print(theme.paint("leaving zen.", "gray"))
        return True

    do_quit = do_exit
    do_EOF = do_exit


def launch(runtime, history_path=None):
    from . import __version__
    from .isa import ISA_VERSION
    from .codec import FORMAT_VERSION
    print(header(status="READY", version=__version__,
                 isa=f"{ISA_VERSION[0]}.{ISA_VERSION[1]}", fmt=FORMAT_VERSION))
    ZenShell(runtime, history_path).cmdloop()
