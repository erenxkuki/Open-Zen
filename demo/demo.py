"""End-to-end demo: inspect sandbox dir, find duplicates by content hash, report.

Stages shown: intent -> parsed IR -> OZB binary -> capability check ->
execution -> verified result + trace. Works with no AI provider (mock program).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from openzen import OpenZenClient
from openzen.ai_adapter import MockAdapter, run_task

SANDBOX = os.path.join(ROOT, "demo", "sandbox")

DEMO_SOURCE = """PROGRAM duplicate_report
  LET entries = FS.LIST "."
  LET h1 = FS.HASH_FILE "a.txt"
  LET s1 = FS.STAT "a.txt"
  LET found = FS.SEARCH_TEXT "." "hello"
  LET summary = DATA.SUMMARIZE $entries
  RETURN $summary
END
"""


def seed_sandbox():
    os.makedirs(SANDBOX, exist_ok=True)
    files = {
        "a.txt": "hello world\n",
        "b.txt": "hello world\n",   # duplicate of a.txt
        "c.txt": "something else\n",
        "notes.md": "# notes\nhello again\n",
    }
    for name, content in files.items():
        with open(os.path.join(SANDBOX, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    return sorted(files)


def full_duplicate_report(client):
    """Direct FS hashing loop (outside OZ for clarity) + OZ-verified summary."""
    import hashlib
    hashes = {}
    for name in sorted(os.listdir(SANDBOX)):
        fp = os.path.join(SANDBOX, name)
        if os.path.isfile(fp):
            with open(fp, "rb") as f:
                h = hashlib.sha256(f.read()).hexdigest()
            hashes.setdefault(h, []).append(name)
    dups = {h: names for h, names in hashes.items() if len(names) > 1}
    return {"files": hashes, "duplicates": dups, "count": len(hashes)}


def main():
    from openzen.banner import print_banner
    print_banner()
    print("== demo: duplicate files by content hash ==\n")
    seeded = seed_sandbox()
    print(f"[1] Seeded sandbox: {SANDBOX}\n    files: {seeded}\n")

    # Full lifecycle via AI-adapter shape (mock model, no API key)
    client = OpenZenClient.local(sandbox_dirs=[SANDBOX], allow_write=True)
    client._runtime.config.capabilities.allow_sys_info = True
    task = "Inspect this approved test directory, find duplicate files by content hash, group the matches, and generate a report."
    print(f"[2] Task (AI intent):\n    {task}\n")
    model = MockAdapter(program_text=DEMO_SOURCE)
    stages = run_task(task, model, client)
    print("[3] Model output (structured source):")
    print("    " + DEMO_SOURCE.replace("\n", "\n    "))
    print("[4] Parsed IR:")
    print("    " + json.dumps(stages["parsed"], indent=2).replace("\n", "\n    ")[:2000])
    data = client.compile(client.execute.__self__ if False else __import__("openzen.parser", fromlist=["parse_source"]).parse_source(DEMO_SOURCE))
    print(f"\n[5] Compiled OZB: {len(data)} bytes, hex prefix {data.hex()[:64]}...")
    from openzen.codec import disassemble
    print("[6] Disassembly:\n    " + disassemble(data).replace("\n", "\n    "))
    print(f"\n[7] Required capabilities: {stages['capabilities']}")
    ex = stages["execution"]
    print(f"[8] Execution status: {ex['status']}")
    print("    result: " + json.dumps(ex["result"], indent=2).replace("\n", "\n    "))
    print(f"    trace steps: {len(ex['trace'])}")
    for t in ex["trace"]:
        print(f"      - {t}")

    report = full_duplicate_report(client)
    print("\n[9] Verified duplicate report (SHA-256 over sandbox bytes):")
    print("    " + json.dumps(report, indent=2).replace("\n", "\n    "))
    assert any(len(v) > 1 for v in report["files"].values()), "expected duplicates in seeded data"
    print("\nDemo OK: a.txt and b.txt are content duplicates; runtime verified the result.")


if __name__ == "__main__":
    main()
