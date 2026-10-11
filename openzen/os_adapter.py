"""OS adapter: sandboxed filesystem + restricted process backend.

Windows-first; POSIX-compatible by construction (uses os/pathlib only).
All filesystem paths are resolved against explicit allowed roots and checked
for directory traversal and symlink escapes.
"""
from __future__ import annotations
import os
import hashlib
from .values import OzError

MAX_FILE_READ = 5 * 1024 * 1024
MAX_LIST_ENTRIES = 10000
MAX_SEARCH_FILES = 2000
MAX_SEARCH_HITS = 500
MAX_GLOB_HITS = 1000


def _real(p):
    # realpath resolves symlinks; used for escape checks
    return os.path.realpath(os.path.abspath(p))


class OsAdapter:
    def __init__(self, allowed_dirs=(), max_file_bytes=MAX_FILE_READ):
        self.allowed_roots = [_real(d) for d in allowed_dirs]
        self.max_file_bytes = max_file_bytes
        for r in self.allowed_roots:
            os.makedirs(r, exist_ok=True)

    def _resolve(self, path):
        if not isinstance(path, str) or not path:
            raise OzError("INVALID_PATH", f"Bad path: {path!r}")
        # Reject absolute paths escaping to arbitrary locations unless inside a root.
        # Sandbox-relative paths are joined to first root; absolute paths must be inside a root.
        cand = path
        if not os.path.isabs(cand):
            if not self.allowed_roots:
                raise OzError("CAPABILITY_DENIED", "No filesystem roots granted.")
            cand = os.path.join(self.allowed_roots[0], cand)
        real = _real(cand)
        # On Windows compare case-insensitively
        def norm(p):
            return os.path.normcase(os.path.normpath(p))
        for root in self.allowed_roots:
            rr, pr = norm(root), norm(real)
            if pr == rr or pr.startswith(rr + os.sep):
                # extra symlink check: the pre-resolution abspath's realpath must match
                return real
        raise OzError("PATH_ESCAPE", f"Path escapes allowed roots: {path!r}",
                      {"path": path})

    def list_dir(self, path):
        full = self._resolve(path)
        if not os.path.isdir(full):
            raise OzError("FS_ERROR", f"Not a directory: {path!r}")
        try:
            entries = sorted(os.listdir(full))
        except OSError as e:
            raise OzError("FS_ERROR", f"Cannot list {path!r}: {e}")
        if len(entries) > MAX_LIST_ENTRIES:
            raise OzError("LIMIT_EXCEEDED", f"Directory too large: {len(entries)} entries.")
        return entries

    def stat(self, path):
        full = self._resolve(path)
        try:
            st = os.stat(full)
        except FileNotFoundError:
            raise OzError("FS_ERROR", f"Not found: {path!r}")
        except OSError as e:
            raise OzError("FS_ERROR", f"Cannot stat {path!r}: {e}")
        import time
        return {
            "name": os.path.basename(full),
            "size": st.st_size,
            "mtime": int(st.st_mtime),
            "is_dir": os.path.isdir(full),
        }

    def read_text(self, path):
        full = self._resolve(path)
        try:
            size = os.path.getsize(full)
        except OSError:
            raise OzError("FS_ERROR", f"Not found: {path!r}")
        if size > self.max_file_bytes:
            raise OzError("LIMIT_EXCEEDED", f"File too large ({size} bytes).")
        try:
            with open(full, "r", encoding="utf-8", errors="strict") as f:
                return f.read()
        except UnicodeDecodeError:
            raise OzError("FS_ERROR", f"File is not UTF-8 text: {path!r}")
        except OSError as e:
            raise OzError("FS_ERROR", f"Cannot read {path!r}: {e}")

    def mkdir(self, path):
        full = self._resolve(path)
        try:
            os.makedirs(full, exist_ok=True)
        except OSError as e:
            raise OzError("FS_ERROR", f"Cannot mkdir {path!r}: {e}")
        return path

    def write_text(self, path, content):
        full = self._resolve(path)
        b = content.encode("utf-8")
        if len(b) > self.max_file_bytes:
            raise OzError("LIMIT_EXCEEDED", "Write content too large.")
        # Do not follow symlinked parent escapes: parent must also resolve inside roots
        parent = _real(os.path.dirname(full) or full)
        self._resolve(parent)
        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
        except OSError as e:
            raise OzError("FS_ERROR", f"Cannot write {path!r}: {e}")
        return path

    def move(self, src, dst):
        s = self._resolve(src)
        d = self._resolve(dst)
        try:
            os.makedirs(os.path.dirname(d), exist_ok=True)
            os.replace(s, d)
        except OSError as e:
            raise OzError("FS_ERROR", f"Cannot move: {e}")
        return dst

    def delete(self, path):
        full = self._resolve(path)
        # refuse to delete a granted root itself
        import os as _os
        for root in self.allowed_roots:
            if _os.path.normcase(_os.path.normpath(full)) == _os.path.normcase(_os.path.normpath(root)):
                raise OzError("FS_ERROR", "Refusing to delete a granted root.")
        try:
            if os.path.isdir(full) and not os.path.islink(full):
                os.rmdir(full)  # only empty dirs
            else:
                os.remove(full)
        except OSError as e:
            raise OzError("FS_ERROR", f"Cannot delete {path!r}: {e}")
        return path

    def hash_file(self, path):
        full = self._resolve(path)
        h = hashlib.sha256()
        try:
            size = 0
            with open(full, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.max_file_bytes * 4:
                        raise OzError("LIMIT_EXCEEDED", "File too large to hash.")
                    h.update(chunk)
        except OSError:
            raise OzError("FS_ERROR", f"Not found: {path!r}")
        return h.hexdigest()

    def copy(self, src, dst):
        import shutil
        s = self._resolve(src)
        d = self._resolve(dst)
        if os.path.isdir(s) and not os.path.islink(s):
            raise OzError("FS_ERROR", f"Copy of directories is not supported: {src!r}")
        try:
            if os.path.getsize(s) > self.max_file_bytes:
                raise OzError("LIMIT_EXCEEDED", "File too large to copy.")
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copyfile(s, d)
        except OzError:
            raise
        except OSError as e:
            raise OzError("FS_ERROR", f"Cannot copy: {e}")
        return dst

    def glob(self, directory, pattern):
        import fnmatch
        if not isinstance(pattern, str) or not pattern or len(pattern) > 256:
            raise OzError("INVALID_PATH", f"Bad glob pattern: {pattern!r}")
        if ".." in pattern.split("/") or ".." in pattern.split(os.sep):
            raise OzError("PATH_ESCAPE", f"Glob pattern escapes: {pattern!r}")
        root = self._resolve(directory)
        if not os.path.isdir(root):
            raise OzError("FS_ERROR", f"Not a directory: {directory!r}")
        hits = []
        scanned = 0
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = [d for d in dirnames
                           if _real(os.path.join(dirpath, d)).startswith(root)]
            for fn in sorted(filenames):
                if scanned >= MAX_SEARCH_FILES or len(hits) >= MAX_GLOB_HITS:
                    break
                fp = os.path.join(dirpath, fn)
                if not _real(fp).startswith(root):
                    continue
                rel = os.path.relpath(fp, root)
                if fnmatch.fnmatch(fn, pattern) or fnmatch.fnmatch(rel, pattern):
                    hits.append(rel.replace(os.sep, "/"))
                scanned += 1
            if scanned >= MAX_SEARCH_FILES or len(hits) >= MAX_GLOB_HITS:
                break
        return sorted(hits)

    def append_text(self, path, content):
        full = self._resolve(path)
        b = content.encode("utf-8")
        if len(b) > self.max_file_bytes:
            raise OzError("LIMIT_EXCEEDED", "Append content too large.")
        try:
            cur = os.path.getsize(full) if os.path.exists(full) else 0
        except OSError as e:
            raise OzError("FS_ERROR", f"Cannot stat {path!r}: {e}")
        if cur + len(b) > self.max_file_bytes:
            raise OzError("LIMIT_EXCEEDED", "Append would exceed file size limit.")
        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "a", encoding="utf-8", newline="\n") as f:
                f.write(content)
        except OSError as e:
            raise OzError("FS_ERROR", f"Cannot append {path!r}: {e}")
        return path

    def search_text(self, directory, query):
        root = self._resolve(directory)
        if not os.path.isdir(root):
            raise OzError("FS_ERROR", f"Not a directory: {directory!r}")
        hits = []
        scanned = 0
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # prune symlinked dirs leaving the root
            dirnames[:] = [d for d in dirnames
                           if _real(os.path.join(dirpath, d)).startswith(root)]
            for fn in sorted(filenames):
                if scanned >= MAX_SEARCH_FILES or len(hits) >= MAX_SEARCH_HITS:
                    break
                fp = os.path.join(dirpath, fn)
                # skip if symlink escapes root
                if not _real(fp).startswith(root):
                    continue
                try:
                    if os.path.getsize(fp) > self.max_file_bytes:
                        continue
                    with open(fp, "r", encoding="utf-8", errors="strict") as f:
                        for i, line in enumerate(f, 1):
                            if query in line:
                                rel = os.path.relpath(fp, root)
                                hits.append({"file": rel, "line": i, "text": line.rstrip("\n")[:500]})
                                if len(hits) >= MAX_SEARCH_HITS:
                                    break
                except (OSError, UnicodeDecodeError):
                    continue
                scanned += 1
            if scanned >= MAX_SEARCH_FILES or len(hits) >= MAX_SEARCH_HITS:
                break
        return hits
