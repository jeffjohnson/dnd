"""Snapshot and rollback for canonical state.

Step 3 of the transactional integration sequence, and the mechanism behind
"do not partially mutate canonical state" in the failure-handling rules. The
snapshot is taken before the first write and restored in full if any later step
raises, so canonical files are either wholly updated or wholly untouched.

Snapshots hold exact bytes. Restoring must not reformat a file it did not
change.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .checksums import checksum_file


@dataclass
class Snapshot:
    directory: Path
    files: dict[Path, str]  # original path -> checksum at snapshot time

    @classmethod
    def take(cls, paths: list[Path], directory: Path) -> "Snapshot":
        directory.mkdir(parents=True, exist_ok=True)
        files = {}
        for path in paths:
            if not path.exists():
                continue
            shutil.copy2(path, directory / path.name)
            files[path] = checksum_file(path)
        return cls(directory=directory, files=files)

    def restore(self) -> list[Path]:
        """Put every snapshotted file back exactly as it was."""
        restored = []
        for path in self.files:
            backup = self.directory / path.name
            if backup.exists():
                shutil.copy2(backup, path)
                restored.append(path)
        return restored

    def verify_unchanged(self) -> list[Path]:
        """Files that differ from the snapshot. Empty means nothing was written."""
        return [p for p, digest in self.files.items()
                if not p.exists() or checksum_file(p) != digest]

    def as_dict(self, root: Path) -> dict:
        return {
            "path": self.directory.relative_to(root).as_posix()
            if self.directory.is_relative_to(root) else str(self.directory),
            "files": {p.relative_to(root).as_posix(): digest for p, digest in self.files.items()},
        }


class Transaction:
    """Context manager that rolls canonical state back on any exception."""

    def __init__(self, paths: list[Path], directory: Path):
        self.paths = paths
        self.directory = directory
        self.snapshot: Snapshot | None = None
        self.rolled_back = False

    def __enter__(self) -> "Transaction":
        self.snapshot = Snapshot.take(self.paths, self.directory)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None and self.snapshot is not None:
            self.snapshot.restore()
            self.rolled_back = True
        return False  # never swallow the failure
