"""Read-only workspace tools constrained to an explicitly configured local root."""
from __future__ import annotations

import os
import difflib
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
MAX_ENTRIES = 200
MAX_DEPTH = 2
MAX_READ_BYTES = 256 * 1024
MAX_WRITE_BYTES = 64 * 1024
BLOCKED_NAMES = {".git", ".env", ".env.local", ".env.production", ".ssh", "data",
                 "node_modules", "__pycache__", ".venv", "venv", ".next", "dist", "build",
                 "secrets", "credentials"}
BLOCKED_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


class WorkspaceError(ValueError):
    pass


class Workspace:
    def __init__(self, root=None):
        configured = root or os.environ.get("NEXORA_WORKSPACE_ROOT") or ROOT
        self.root = Path(configured).expanduser().resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise WorkspaceError("Configured workspace root must be an existing directory.")

    @property
    def root_name(self):
        return self.root.name or str(self.root)

    def _relative_parts(self, relative):
        if relative in (None, "", "."):
            return ()
        if not isinstance(relative, str) or len(relative) > 1000 or "\x00" in relative or "\\" in relative:
            raise WorkspaceError("Workspace path is invalid.")
        path = PurePosixPath(relative)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts) or ":" in relative:
            raise WorkspaceError("Workspace paths must stay relative to the workspace root.")
        if any(self._blocked_name(part) for part in path.parts):
            raise WorkspaceError("This path is excluded from workspace tools.")
        return path.parts

    @staticmethod
    def _blocked_name(name):
        lowered = name.lower()
        return lowered in BLOCKED_NAMES or lowered.endswith(tuple(BLOCKED_SUFFIXES))

    def _resolve(self, relative, must_exist=True):
        parts = self._relative_parts(relative)
        candidate = self.root.joinpath(*parts)
        cursor = self.root
        for part in parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise WorkspaceError("Symbolic links are excluded from workspace tools.")
        try:
            resolved = candidate.resolve(strict=must_exist)
        except (OSError, RuntimeError):
            raise WorkspaceError("Workspace path could not be resolved.") from None
        if resolved != self.root and self.root not in resolved.parents:
            raise WorkspaceError("Workspace path escaped the configured root.")
        return resolved

    def list_files(self, relative="."):
        start = self._resolve(relative)
        if not start.is_dir():
            raise WorkspaceError("Workspace listing requires a directory.")
        entries = []
        stack = [(start, 0)]
        while stack and len(entries) < MAX_ENTRIES:
            folder, depth = stack.pop()
            try:
                children = sorted(folder.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            except OSError:
                continue
            directories = []
            for item in children:
                if item.is_symlink() or self._blocked_name(item.name) or item.name.startswith("."):
                    continue
                try:
                    resolved = item.resolve(strict=True)
                    if resolved != self.root and self.root not in resolved.parents:
                        continue
                    relative_path = resolved.relative_to(self.root).as_posix()
                    is_dir = item.is_dir()
                    stat = item.stat()
                except (OSError, RuntimeError, ValueError):
                    continue
                entries.append({"path": relative_path, "kind": "directory" if is_dir else "file",
                                "size": 0 if is_dir else stat.st_size,
                                "modifiedAt": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds")})
                if is_dir and depth < MAX_DEPTH:
                    directories.append((item, depth + 1))
                if len(entries) >= MAX_ENTRIES:
                    break
            stack.extend(reversed(directories))
        return {"rootName": self.root_name, "relativePath": "." if start == self.root else start.relative_to(self.root).as_posix(),
                "entries": entries, "truncated": len(entries) >= MAX_ENTRIES}

    def preview_write(self, relative, content):
        """Build a bounded unified diff without modifying the workspace."""
        if not isinstance(content, str):
            raise WorkspaceError("Proposed file content must be text.")
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_WRITE_BYTES:
            raise WorkspaceError("Proposed file content exceeds the 64 KiB preview limit.")
        path = self._resolve(relative, must_exist=False)
        if path == self.root:
            raise WorkspaceError("Workspace root cannot be replaced.")
        if not path.parent.is_dir():
            raise WorkspaceError("The destination directory must already exist.")
        created = not path.exists()
        current = ""
        if not created:
            if not path.is_file():
                raise WorkspaceError("Diff previews can target text files only.")
            try:
                existing = path.read_bytes()
                if len(existing) > MAX_READ_BYTES:
                    raise WorkspaceError("Existing file is too large to safely preview.")
                current = existing.decode("utf-8")
            except UnicodeDecodeError:
                raise WorkspaceError("Binary files cannot be diffed by workspace tools.") from None
            except OSError:
                raise WorkspaceError("Existing file could not be checked.") from None
        diff = "".join(difflib.unified_diff(
            current.splitlines(keepends=True), content.splitlines(keepends=True),
            fromfile=f"a/{path.relative_to(self.root).as_posix()}" if not created else "/dev/null",
            tofile=f"b/{path.relative_to(self.root).as_posix()}",
            lineterm="\\n"
        ))
        return {"path": path.relative_to(self.root).as_posix(), "diff": diff,
                "created": created, "proposedBytes": len(encoded), "readOnly": True}

    def write_file(self, relative, content):
        if not isinstance(content, str):
            raise WorkspaceError("Workspace write content must be text.")
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_WRITE_BYTES:
            raise WorkspaceError("Proposed file content exceeds the 64 KiB write limit.")
        path = self._resolve(relative, must_exist=False)
        if path == self.root:
            raise WorkspaceError("Workspace root cannot be replaced.")
        parent = path.parent
        created = not path.exists()
        if not parent.is_dir():
            raise WorkspaceError("The destination directory must already exist.")
        if path.exists():
            if not path.is_file():
                raise WorkspaceError("Workspace writes can target text files only.")
            try:
                existing = path.read_bytes()
                if len(existing) > MAX_READ_BYTES:
                    raise WorkspaceError("Existing file is too large to safely replace.")
                existing.decode("utf-8")
            except UnicodeDecodeError:
                raise WorkspaceError("Binary files cannot be replaced by workspace tools.") from None
            except OSError:
                raise WorkspaceError("Existing file could not be checked.") from None
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=parent, prefix=".nexora-tmp-", delete=False) as handle:
                temp_path = Path(handle.name)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        except OSError:
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise WorkspaceError("Atomic workspace write failed.") from None
        return {"path": path.relative_to(self.root).as_posix(), "bytes": len(encoded),
                "sha256": hashlib.sha256(encoded).hexdigest(), "created": created,
                "readOnly": False}

    def read_file(self, relative):
        path = self._resolve(relative)
        if not path.is_file():
            raise WorkspaceError("Workspace read requires a file.")
        try:
            size = path.stat().st_size
            if size > MAX_READ_BYTES:
                raise WorkspaceError("File is too large to preview (256 KiB limit).")
            content = path.read_bytes()
            if len(content) > MAX_READ_BYTES:
                raise WorkspaceError("File changed while reading; preview limit exceeded.")
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise WorkspaceError("Only UTF-8 text files can be previewed.") from None
        except OSError:
            raise WorkspaceError("File could not be read.") from None
        return {"path": path.relative_to(self.root).as_posix(), "content": text, "bytes": len(content),
                "readOnly": True}
