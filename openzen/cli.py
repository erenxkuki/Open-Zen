"""Open Zen CLI: a systems-engineering terminal for OZ-ISA.

Conventions:
- stdout stays machine-readable (JSON / bytes / tables for piping).
- Live pipeline stages go to stderr, silenced with --quiet.
- Colors honor NO_COLOR / --plain and TTY detection (see openzen.theme).
- Every displayed number, offset, and status reflects real execution state.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import unittest


# ---------- shared setup ----------

def _common_flags():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--plain", action="store_true", help="Disable colors (keep structure)")
    p.add_argument("--no-color", action="store_true", help="Alias for --plain")
    p.add_argument("--quiet", action="store_true", help="Suppress pipeline stages on stderr")
    p.add_argument("--history", default=None, help="History file (default .openzen/history.jsonl)")
    p.add_argument("--no-history", action="store_true", help="Do not record execution history")
    return p


COMMON = _common_flags()
DEFAULT_HISTORY = os.path.join(".openzen", "history.jsonl")


def _init_theme(args):
    from openzen import theme
    for stream in (sys.stdout, sys.stderr):
        try:
            # Legacy Windows consoles default to cp1252, which cannot render
            # the engineering glyphs (━ │ ✓ →). Prefer UTF-8 everywhere.
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    theme.configure(plain=bool(getattr(args, "plain", False) or getattr(args, "no_color", False)),
                    quiet=bool(getattr(args, "quiet", False)))


def _history_path(args):
    if getattr(args, "no_history", False):
        return None
    return getattr(args, "history", None) or DEFAULT_HISTORY


def _caps_from_args(args):
    from openzen.capabilities import Capabilities
    dirs = getattr(args, "sandbox", None) or []
    if dirs:
        caps = Capabilities.sandbox(dirs, write=not getattr(args, "read_only", False))
    else:
        caps = Capabilities()
        if getattr(args, "allow_fs_read", False):
            caps.allow_fs_read = True
    if getattr(args, "allow_sys_info", False):
        caps.allow_sys_info = True
    if getattr(args, "allow_proc_list", False):
        caps.allow_proc_list = True
    if getattr(args, "allow_programs", None):
        caps.allowed_programs = args.allow_programs
    if getattr(args, "allow_kill", False):
        caps.allow_proc_kill = True
    if getattr(args, "allow_delete", False):
        caps.allow_fs_delete = True
    if getattr(args, "allow_env", None):
        caps.allowed_env_vars = args.allow_env
    if getattr(args, "allow_host", None):
        caps.allowed_hosts = args.allow_host
    return caps


def _make_runtime(args):
    from openzen.capabilities import Capabilities  # noqa: F401
    from openzen.runtime import Runtime, RuntimeConfig, ExecutionBudgets
    from openzen.os_adapter import OsAdapter
    caps = _caps_from_args(args)
    approval = (lambda op, d: True) if getattr(args, "auto_approve", False) else None
    adapter = OsAdapter(allowed_dirs=caps.allowed_dirs)
    budgets = ExecutionBudgets(max_steps=getattr(args, "max_steps", 10000),
                               max_time_ms=getattr(args, "max_time_ms", 5000))
    return Runtime(RuntimeConfig(capabilities=caps, budgets=budgets,
                                 approval_callback=approval, os_adapter=adapter))


def _load_raw(args):
    """Return (kind, payload): kind in source-text/source-json/program-json/ozb."""
    if getattr(args, "ozb", None):
        with open(args.ozb, "rb") as f:
            return ("ozb", f.read())
    text = None
    if getattr(args, "source", None):
        with open(args.source, "r", encoding="utf-8") as f:
            text = f.read()
        kind = "source-json" if getattr(args, "json_program", False) else "source-text"
        return (kind, text)
    if getattr(args, "expr", None) is not None:
        kind = "source-json" if getattr(args, "json_program", False) else "source-text"
        return (kind, args.expr)
    data = sys.stdin.buffer.read() if getattr(args, "ozb_stdin", False) else sys.stdin.read()
    if getattr(args, "json_program", False):
        return ("source-json", data)
    return ("source-text", data)


def _decode_input(kind, payload):
    from openzen.parser import parse_source
    from openzen.program import load_json_program
    from openzen.codec import decode
    if kind == "ozb":
        return decode(payload)
    if kind == "source-json":
        return load_json_program(json.loads(payload) if isinstance(payload, str) else payload)
    if kind == "program-json":
        return load_json_program(payload)
    return parse_source(payload)


# ---------- execution pipeline (stages reflect real events) ----------

def run_pipeline(prog_input, rt, input_kind, hist_path=None, fmt="json", step=False, verbose=False):
    from openzen import display
    from openzen.display import estage, ok_line, warn_line, err_line
    from openzen.validator import validate
    from openzen.codec import encode
    from openzen.values import OzError
    from openzen.runtime import CancellationToken, _Cancelled

    if isinstance(prog_input, tuple):
        kind, payload = prog_input
        estage(1, "INTENT RECEIVED", f"{kind}")
        try:
            prog = _decode_input(kind, payload)
        except OzError as e:
            err_line("INTENT REJECTED", f"{e.code}: {e.message}")
            raise
        if kind == "ozb":
            estage(2, "OZB DECODED", f"{prog.name}, {len(prog.statements)} statements")
        else:
            estage(2, "OZ-ISA GENERATED", f"{prog.name}, {len(prog.statements)} statements")
    else:
        prog = prog_input
        estage(1, "INTENT RECEIVED", f"program: {prog.name}")
        estage(2, "OZ-ISA READY", f"{len(prog.statements)} statements")

    try:
        caps = validate(prog)
    except OzError as e:
        err_line("TYPE CHECK FAILED", f"{e.code}: {e.message}")
        raise
    estage(3, "TYPE CHECK PASSED", f"requires: {', '.join(caps) if caps else 'compute only'}")

    granted = rt.config.capabilities
    missing = [c for c in caps if not granted.requires(c)]
    appr = [o for o in _ops_in(prog) if granted.needs_approval(o)]
    if missing:
        estage(4, "PERMISSIONS INCOMPLETE", "missing: " + ", ".join(missing))
        warn_line("EXECUTION WILL BE DENIED", "grant with --sandbox / --allow-* flags")
    else:
        estage(4, "PERMISSIONS VERIFIED", ", ".join(caps) if caps else "compute only")
    for o in appr:
        warn_line("APPROVAL REQUIRED", o)

    data = encode(prog)
    estage(5, "OZB PROGRAM COMPILED", f"{len(data)} bytes")

    token = CancellationToken()
    if step:
        _install_stepper(rt, token)
    estage(6, "RUNTIME EXECUTING", prog.name)
    res = rt.execute_program(prog, token)
    if res.status == "ok":
        ok_line("RESULT VERIFIED", f"{len(json.dumps(res.value))}B JSON, {res.steps} steps, {res.elapsed_ms}ms")
    else:
        err_line("EXECUTION FAILED", (res.error or {}).get("code", ""))
    estage(7, "PIPELINE COMPLETE", res.status.upper())

    if hist_path:
        from openzen import history as hist
        try:
            hist.append(hist_path, hist.build_record(prog, res, input_kind
                          if isinstance(input_kind, str) else "program"))
        except OSError as e:
            warn_line("HISTORY NOT RECORDED", str(e)[:100])
    if fmt == "human":
        _print_human(prog, res, data, verbose)
    else:
        print(json.dumps(res.to_dict(), default=str))
    return res


def _ops_in(prog):
    out = []

    def walk(stmts):
        for s in stmts:
            if s.get("kind") == "let":
                out.append(s["op"])
            elif s.get("kind") == "if":
                walk(s.get("then", []))
                walk(s.get("else", []))
            elif s.get("kind") == "for":
                walk(s.get("body", []))
    walk(prog.statements)
    return out


def _install_stepper(rt, token):
    from openzen.display import describe_stmt
    from openzen import theme
    from openzen.runtime import _Cancelled
    state = {"prompt": True}

    def cb(ev):
        line = theme.paint(f"  step {ev['steps']:04d} ", "gray") + \
            theme.paint(describe_stmt(ev["stmt"]), "cyan")
        print(line, file=sys.stderr, flush=True)
        if state["prompt"] and sys.stdin.isatty():
            try:
                ans = input("  [enter]=next q=abort c=continue> ").strip().lower()
            except EOFError:
                return
            if ans == "q":
                token.cancel()
                raise _Cancelled()
            if ans == "c":
                state["prompt"] = False
    rt.config.step_callback = cb


def _print_human(prog, res, data, verbose):
    from openzen import display
    from openzen.display import trace_tree, policy_box, fmt_error
    from openzen import theme
    print(policy_box(_current_caps()))
    if verbose:
        from openzen.codec import inspect_detail
        print(display.inspect_table(inspect_detail(data)))
        print(theme.paint(f"  ozb prefix: {data.hex()[:64]}…", "gray"))
    print(trace_tree(res.trace))
    if res.status == "ok":
        print(theme.paint("✓ RESULT", "green", "bold"))
        print(json.dumps(res.value, indent=2)[:8000])
    else:
        print(fmt_error(res.error))
    print(theme.paint(f"  {res.steps} steps · {res.elapsed_ms}ms", "gray"))


def _current_caps():
    return _CURRENT_CAPS


_CURRENT_CAPS = None


# ---------- commands ----------

def cmd_validate(args):
    _init_theme(args)
    from openzen.validator import validate
    kind, payload = _load_raw(args)
    prog = _decode_input(kind, payload)
    caps = validate(prog)
    print(json.dumps({"ok": True, "program": prog.name, "required_capabilities": caps}, indent=2))


def cmd_compile(args):
    _init_theme(args)
    from openzen.codec import encode
    kind, payload = _load_raw(args)
    prog = _decode_input(kind, payload)
    data = encode(prog)
    if args.out:
        with open(args.out, "wb") as f:
            f.write(data)
        print(f"Wrote {len(data)} bytes to {args.out}", file=sys.stderr)
    else:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()


def cmd_inspect(args):
    _init_theme(args)
    from openzen.codec import encode, decode, disassemble, inspect_detail
    from openzen.display import inspect_table
    if args.ozb:
        with open(args.ozb, "rb") as f:
            data = f.read()
        decode(data)  # validates
    else:
        kind, payload = _load_raw(args)
        prog = _decode_input(kind, payload)
        data = encode(prog)
    if getattr(args, "format", "human") == "json":
        print(json.dumps(inspect_detail(data), indent=2))
    else:
        print(inspect_table(inspect_detail(data)))
        print()
        print(disassemble(data))


def cmd_run(args):
    _init_theme(args)
    global _CURRENT_CAPS
    rt = _make_runtime(args)
    _CURRENT_CAPS = rt.config.capabilities
    kind, payload = _load_raw(args)
    res = run_pipeline((kind, payload), rt, kind, hist_path=_history_path(args),
                       fmt=getattr(args, "format", "json"),
                       step=getattr(args, "step", False), verbose=False)
    if res.status != "ok":
        sys.exit(1)


def cmd_trace(args):
    _init_theme(args)
    global _CURRENT_CAPS
    from openzen.values import OzError
    rt = _make_runtime(args)
    _CURRENT_CAPS = rt.config.capabilities
    kind, payload = _load_raw(args)
    if kind == "source-text" and getattr(args, "expr", None) is not None:
        from openzen.parser import parse_source
        try:
            parse_source(payload)
        except OzError:
            from openzen import theme
            print(theme.paint("oz trace needs an OZ-ISA program, not free text.", "yellow"))
            print(theme.paint("Natural language requires a configured model adapter — see", "gray"))
            print(theme.paint("examples/ai_client_example.py (parse → validate → execute, never raw).", "gray"))
            sys.exit(2)
    res = run_pipeline((kind, payload), rt, kind, hist_path=_history_path(args),
                       fmt="human", step=getattr(args, "step", False), verbose=True)
    if res.status != "ok":
        sys.exit(1)


def cmd_explain(args):
    _init_theme(args)
    from openzen.display import explain_program
    kind, payload = _load_raw(args)
    prog = _decode_input(kind, payload)
    print(explain_program(prog))


def cmd_permissions(args):
    _init_theme(args)
    from openzen.display import policy_box
    print(policy_box(_caps_from_args(args)))


def cmd_plugins(args):
    _init_theme(args)
    from openzen.isa import OP_REGISTRY
    from openzen import theme
    core = [o for o in OP_REGISTRY if o.op_id < 1000]
    ext = [o for o in OP_REGISTRY if o.op_id >= 1000]
    print(theme.paint(f"core: {len(core)} operations (ids 0–999)", "white"))
    if not ext:
        print(theme.paint("extensions: none installed", "gray"))
        print(theme.paint("see plugins/example_upper/ + docs/plugin-development.md", "gray"))
    else:
        print(theme.paint(f"extensions: {len(ext)} operations", "white"))
        for o in sorted(ext, key=lambda o: o.op_id):
            print(f"  {theme.paint(o.name, 'cyan')}  id={o.op_id} v{o.version}  {theme.paint(o.description, 'gray')}")


def cmd_logs(args):
    _init_theme(args)
    from openzen import history as hist
    from openzen import theme
    import datetime
    path = _history_path(args) or DEFAULT_HISTORY
    recs = hist.read(path, limit=getattr(args, "limit", 20))
    if not recs:
        print(theme.paint(f"no execution history at {path}", "gray"))
        print(theme.paint("record runs with: oz run --source prog.oz [--history FILE]", "gray"))
        return
    print(theme.paint(f"history: {path} (last {len(recs)})", "bold", "white"))
    for i, r in enumerate(recs):
        ts = datetime.datetime.fromtimestamp(r.get("ts", 0)).strftime("%m-%d %H:%M:%S")
        st = r.get("status", "?")
        color = "green" if st == "ok" else ("red" if st == "error" else "yellow")
        print(f"  [{i}] {ts} {theme.paint(r.get('program', '?'), 'cyan')} "
              f"{theme.paint(st.upper(), color)} {r.get('steps', 0)} steps {r.get('elapsed_ms', 0)}ms")
        if r.get("error"):
            print(f"      {theme.paint(r['error'].get('code', ''), 'red')}")


def cmd_replay(args):
    _init_theme(args)
    from openzen import history as hist
    from openzen import theme
    from openzen.program import load_json_program
    path = _history_path(args) or DEFAULT_HISTORY
    recs = hist.read(path, limit=100000)
    try:
        rec = recs[args.index]
    except IndexError:
        print(theme.paint(f"no history entry [{args.index}] in {path}", "red"))
        sys.exit(1)
    if not rec.get("program_stored") or not rec.get("program_full"):
        print(theme.paint("entry has no stored program; cannot replay.", "red"))
        sys.exit(1)
    print(theme.paint(f"replaying [{args.index}] {rec.get('program')} "
                      f"(originally {rec.get('status')}) — current runtime, current policy.",
                      "yellow"), file=sys.stderr)
    rt = _make_runtime(args)
    prog = load_json_program(rec["program_full"])
    res = rt.execute_program(prog)
    print(json.dumps(res.to_dict(), default=str))
    if res.status != "ok":
        sys.exit(1)


def cmd_test(args):
    _init_theme(args)
    from openzen import theme
    import openzen
    tests_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(openzen.__file__))), "tests")
    if not os.path.isdir(tests_dir):
        # installed package without bundled tests
        print(theme.paint("conformance tests are not bundled with this install.", "yellow"))
        print(theme.paint("clone the repository to run: python -m unittest discover -s tests", "gray"))
        sys.exit(2)
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=tests_dir, pattern="test_*.py")
    sel = getattr(args, "select", None)
    if sel:
        suite = unittest.TestSuite(t for t in _flatten(suite) if sel in t.id())
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    print(theme.paint(f"conformance: {result.testsRun} ran, "
                      f"{len(result.failures)} failed, {len(result.errors)} errors",
                      "green" if result.wasSuccessful() else "red"))
    if not result.wasSuccessful():
        sys.exit(1)


def _flatten(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from _flatten(t)
        else:
            yield t


def cmd_benchmark(args):
    _init_theme(args)
    import time
    from openzen import theme
    from openzen.parser import parse_source
    from openzen.codec import encode, decode
    from openzen import OpenZenClient
    n = getattr(args, "iters", 300)
    src = ("PROGRAM bench\nLET a = CORE.ADD 1 2\nLET b = CORE.MUL $a 3\n"
           "LET c = CORE.HASH_SHA256 $b\nRETURN $c\nEND\n")
    p = parse_source(src)
    data = encode(p)
    c = OpenZenClient.local()

    def bench(fn):
        t0 = time.perf_counter()
        for _ in range(n):
            fn()
        return (time.perf_counter() - t0) / n * 1000

    rows = [
        ("compile (validate+encode)", bench(lambda: encode(p)), f"{len(data)} bytes"),
        ("decode (validate+parse)", bench(lambda: decode(data)), ""),
        ("execute (embedded)", bench(lambda: c.execute(p)), ""),
    ]
    print(theme.paint(f"benchmark — {n} iters, measured on this machine (no claims beyond these numbers):", "bold", "white"))
    for name, ms, extra in rows:
        print(f"  {name.ljust(28)} {theme.paint(f'{ms:.3f} ms/run', 'cyan')}  {theme.paint(extra, 'gray')}")


def cmd_doctor(args):
    _init_theme(args)
    from openzen.doctor import run_checks
    from openzen import theme
    ok = True
    for name, passed, detail in run_checks(sandbox_dirs=getattr(args, "sandbox", None) or []):
        mark = theme.paint("✓", "green") if passed else theme.paint("✗", "red")
        print(f"  {mark} {name}  {theme.paint(detail, 'gray')}")
        ok = ok and passed
    print(theme.paint("doctor: all checks passed" if ok else "doctor: issues found",
                      "green" if ok else "red"))
    if not ok:
        sys.exit(1)


def cmd_version(args):
    _init_theme(args)
    from openzen import __version__, theme
    from openzen.banner import header
    from openzen.isa import ISA_VERSION, OP_REGISTRY
    from openzen.codec import FORMAT_VERSION
    import platform
    print(header(status="READY", version=__version__,
                 isa=f"{ISA_VERSION[0]}.{ISA_VERSION[1]}", fmt=FORMAT_VERSION))
    print(theme.paint(f"operations: {len(OP_REGISTRY)}   "
                      f"python: {platform.python_version()}   os: {platform.system()}", "gray"))


def cmd_caps(_args):
    _init_theme(_args)
    from openzen.isa import OP_REGISTRY
    print(json.dumps({"isa_version": "1.0",
                      "operations": [o.to_dict() for o in OP_REGISTRY]}, indent=2))


def cmd_banner(_args):
    _init_theme(_args)
    from openzen.banner import print_banner
    print_banner()


def cmd_shell(args):
    _init_theme(args)
    from openzen.shell import launch
    launch(_make_runtime(args), history_path=_history_path(args))


def cmd_serve(args):
    _init_theme(args)
    from openzen.api_server import serve
    serve(host=args.host, port=args.port, sandbox_dirs=getattr(args, "sandbox", None) or (),
          allow_write=not getattr(args, "read_only", False),
          approval="auto" if getattr(args, "auto_approve", False) else "deny")


# ---------- parser ----------

def _add_io(sp):
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--source", help="Text source file (.oz)")
    g.add_argument("--expr", help="Inline source text")
    g.add_argument("--ozb", help="Compiled .ozb file")
    sp.add_argument("--json-program", action="store_true", help="Input is JSON program")


def _add_rt(sp):
    sp.add_argument("--sandbox", action="append", default=[], help="Allowed directory (repeatable)")
    sp.add_argument("--read-only", action="store_true")
    sp.add_argument("--allow-fs-read", action="store_true")
    sp.add_argument("--allow-sys-info", action="store_true")
    sp.add_argument("--allow-proc-list", action="store_true")
    sp.add_argument("--allow-programs", action="append", default=[])
    sp.add_argument("--allow-env", action="append", default=[], help="Allowlisted env var for SYS.ENV")
    sp.add_argument("--allow-host", action="append", default=[], help="Allowlisted host for NET.FETCH")
    sp.add_argument("--allow-kill", action="store_true")
    sp.add_argument("--allow-delete", action="store_true")
    sp.add_argument("--auto-approve", action="store_true", help="Approve sensitive ops automatically")
    sp.add_argument("--max-steps", type=int, default=10000)
    sp.add_argument("--max-time-ms", type=int, default=5000)


def build_parser():
    p = argparse.ArgumentParser(prog="openzen", description="Open Zen — AI-native instruction language & runtime",
                                parents=[COMMON])
    sub = p.add_subparsers(dest="cmd", required=True)

    def new(name, help, parents=()):
        return sub.add_parser(name, help=help, parents=[COMMON, *parents])

    s = new("validate", "Parse + type-check a program"); _add_io(s); s.set_defaults(fn=cmd_validate)
    s = new("compile", "Compile source to .ozb"); _add_io(s)
    s.add_argument("--out", help="Output file"); s.set_defaults(fn=cmd_compile)
    s = new("inspect", "Decode .ozb: offsets, opcodes, families"); _add_io(s)
    s.add_argument("--format", choices=["human", "json"], default="human"); s.set_defaults(fn=cmd_inspect)
    s = new("run", "Execute with live pipeline display"); _add_io(s); _add_rt(s)
    s.add_argument("--format", choices=["json", "human"], default="json")
    s.add_argument("--step", action="store_true", help="Pause before each instruction")
    s.set_defaults(fn=cmd_run)
    s = new("trace", "Full lifecycle: intent → binary → trace → result"); _add_io(s); _add_rt(s)
    s.add_argument("--step", action="store_true"); s.set_defaults(fn=cmd_trace)
    s = new("explain", "Human-readable instruction summary"); _add_io(s); s.set_defaults(fn=cmd_explain)
    s = new("permissions", "Show execution policy for these flags"); _add_rt(s); s.set_defaults(fn=cmd_permissions)
    s = new("plugins", "List installed operation extensions"); s.set_defaults(fn=cmd_plugins)
    s = new("logs", "Show recorded execution history"); s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_logs)
    s = new("replay", "Re-execute a recorded entry with current policy"); _add_rt(s)
    s.add_argument("index", type=int); s.set_defaults(fn=cmd_replay)
    s = new("test", "Run language + runtime conformance tests")
    s.add_argument("--select", default=None, help="Only tests whose id contains SUBSTR"); s.set_defaults(fn=cmd_test)
    s = new("benchmark", "Measure compile/decode/execute on this machine")
    s.add_argument("--iters", type=int, default=300); s.set_defaults(fn=cmd_benchmark)
    s = new("doctor", "Diagnose installation and runtime"); _add_rt(s); s.set_defaults(fn=cmd_doctor)
    s = new("version", "Brand header + build facts"); s.set_defaults(fn=cmd_version)
    s = new("capabilities", "List operations (JSON)"); s.set_defaults(fn=cmd_caps)
    s = new("banner", "Print the brand banner"); s.set_defaults(fn=cmd_banner)
    s = new("shell", "Interactive Zen Shell"); _add_rt(s); s.set_defaults(fn=cmd_shell)
    s = new("serve", "Start local API server")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8765)
    _add_rt(s); s.set_defaults(fn=cmd_serve)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
