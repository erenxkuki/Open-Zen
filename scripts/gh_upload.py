"""Upload this project to GitHub without needing git installed.

Uses the GitHub git-data API (stdlib only) to push every project file in ONE
commit, preserving subdirectories. Skips generated junk (__pycache__,
.openzen history, demo sandbox output, egg-info, …).

1. Create a fine-grained token: GitHub → Settings → Developer settings →
   Personal access tokens → Fine-grained → select ONLY the Open-Zen repo →
   grant "Contents: Read and write". Copy the token (github_pat_...).
2. Dry run (lists exactly what would upload, touches nothing):
     python scripts/gh_upload.py --dry-run
3. Push:
     $env:GITHUB_TOKEN = "github_pat_..."   # PowerShell (session only, not saved)
     python scripts/gh_upload.py --message "Open Zen v0.3.0: full project"

The token is read from $env:GITHUB_TOKEN or typed hidden at a prompt —
never put it in a file.
"""
from __future__ import annotations
import argparse
import base64
import getpass
import json
import os
import sys
import urllib.request
import urllib.error

OWNER = "erenxkuki"
REPO = "Open-Zen"
BRANCH = "main"
API = f"https://api.github.com/repos/{OWNER}/{REPO}"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "build", "dist",
             ".eggs", ".pytest_cache", ".openzen", "htmlcov", "demo/sandbox"}
SKIP_SUFFIX = (".pyc", ".pyo")
SKIP_NAMES = {"Thumbs.db", ".DS_Store", ".coverage"}


def collect():
    """Walk ROOT, return sorted [(relpath, abspath)] of uploadable files."""
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT).replace(os.sep, "/")
        # prune skipped dirs (incl. nested, e.g. demo/sandbox)
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS
                             and f"{rel_dir}/{d}" not in SKIP_DIRS
                             and not d.endswith(".egg-info"))
        for fn in sorted(filenames):
            if fn in SKIP_NAMES or fn.endswith(SKIP_SUFFIX):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
            if rel == "demo/sandbox" or rel.startswith("demo/sandbox/"):
                continue
            out.append((rel, full))
    return sorted(out)


def api(token, method, path, payload=None):
    url = API + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "openzen-uploader",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()[:500]
        except Exception:
            body = ""
        raise SystemExit(f"GitHub API {method} {path} -> HTTP {e.code}: {body}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Upload Open Zen to GitHub (no git needed).")
    ap.add_argument("--dry-run", action="store_true", help="List files only, upload nothing.")
    ap.add_argument("--message", default="Open Zen: full project upload",
                    help="Commit message for the push.")
    ap.add_argument("--token", default=None, help="PAT (prefer $env:GITHUB_TOKEN).")
    ap.add_argument("--owner", default=OWNER)
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--branch", default=BRANCH)
    args = ap.parse_args(argv)

    global API
    API = f"https://api.github.com/repos/{args.owner}/{args.repo}"

    files = collect()
    total = sum(os.path.getsize(f) for _, f in files)
    print(f"{len(files)} files, {total / 1024:.0f} KiB under {ROOT}")
    for rel, full in files:
        print(f"  {rel}  ({os.path.getsize(full)} B)")
    if args.dry_run:
        print("\ndry run: nothing uploaded. Re-run with --message to push.")
        return

    token = args.token or os.environ.get("GITHUB_TOKEN") or getpass.getpass("GitHub token (hidden): ")
    if not token.strip():
        raise SystemExit("no token given.")

    print("\n[1/4] reading base branch…")
    _, ref = api(token, "GET", f"/git/ref/heads/{args.branch}")
    base_sha = ref["object"]["sha"]
    _, base_commit = api(token, "GET", f"/git/commits/{base_sha}")
    base_tree = base_commit["tree"]["sha"]

    print("[2/4] uploading blobs…")
    tree_entries = []
    for i, (rel, full) in enumerate(files, 1):
        with open(full, "rb") as f:
            raw = f.read()
        _, blob = api(token, "POST", "/git/blobs",
                      {"content": base64.b64encode(raw).decode(), "encoding": "base64"})
        tree_entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print(f"  [{i}/{len(files)}] {rel}", end="\r", flush=True)
    print()

    print("[3/4] creating commit…")
    _, tree = api(token, "POST", "/git/trees", {"base_tree": base_tree, "tree": tree_entries})
    _, commit = api(token, "POST", "/git/commits",
                    {"message": args.message, "tree": tree["sha"], "parents": [base_sha]})

    print("[4/4] updating branch…")
    api(token, "PATCH", f"/git/refs/heads/{args.branch}", {"sha": commit["sha"]})
    print(f"\npushed {len(files)} files as commit {commit['sha'][:7]} to "
          f"https://github.com/{args.owner}/{args.repo}/tree/{args.branch}")


if __name__ == "__main__":
    main()
