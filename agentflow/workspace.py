"""The shared project directory every agent in a run reads from and writes to."""

from __future__ import annotations

import os
from pathlib import Path

# Directories that are never interesting to list.
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}


class WorkspaceError(Exception):
    """A file operation the workspace refuses or cannot complete."""


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, rel: str) -> Path:
        """Map a workspace-relative path to an absolute one, refusing anything outside the root."""
        if not isinstance(rel, str) or not rel.strip():
            raise WorkspaceError("path must be a non-empty string")
        candidate = (self.root / rel.strip().lstrip("/")).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise WorkspaceError(f"path '{rel}' is outside the workspace")
        return candidate

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def exists(self, rel: str) -> bool:
        try:
            return self.resolve(rel).exists()
        except WorkspaceError:
            return False

    def read_bytes(self, rel: str) -> bytes:
        path = self.resolve(rel)
        if not path.is_file():
            raise WorkspaceError(f"file not found: {rel}")
        return path.read_bytes()

    def read_text(self, rel: str) -> str:
        data = self.read_bytes(rel)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceError(f"{rel} is not a UTF-8 text file") from exc

    def write_text(self, rel: str, content: str) -> int:
        path = self.resolve(rel)
        if path.is_dir():
            raise WorkspaceError(f"{rel} is a directory")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return len(content.encode("utf-8"))

    def write_bytes(self, rel: str, data: bytes) -> None:
        path = self.resolve(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def edit(self, rel: str, old: str, new: str) -> None:
        text = self.read_text(rel)
        count = text.count(old)
        if count == 0:
            raise WorkspaceError(f"old_str not found in {rel}")
        if count > 1:
            raise WorkspaceError(
                f"old_str occurs {count} times in {rel}; include more context so it is unique"
            )
        self.write_text(rel, text.replace(old, new, 1))

    def delete(self, rel: str) -> None:
        path = self.resolve(rel)
        if path == self.root:
            raise WorkspaceError("refusing to delete the workspace root")
        if not path.is_file():
            raise WorkspaceError(f"file not found: {rel}")
        path.unlink()

    def list_files(self, rel: str = ".", limit: int = 500) -> list[str]:
        base = self.resolve(rel)
        if not base.exists():
            raise WorkspaceError(f"directory not found: {rel}")
        if base.is_file():
            return [self.relative(base)]
        found: list[str] = []
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
            for name in sorted(filenames):
                found.append(self.relative(Path(dirpath) / name))
                if len(found) >= limit:
                    return found
        return found
