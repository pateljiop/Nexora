"""Read-only workspace tools constrained to an explicitly configured local root."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
MAX_ENTRIES = 200
MAX_DEPTH = 2
MAX_READ_BYTES = 256 * 1024
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
