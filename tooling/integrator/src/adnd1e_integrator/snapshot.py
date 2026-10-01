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
    absent: tuple[Path, ...] = ()  # paths that did not exist when the snapshot was taken
    created_dirs: tuple[Path, ...] = ()  # directories the transaction may create

    @classmethod
    def take(
        cls,
        paths: list[Path],
        directory: Path,
        genesis_dirs: tuple[Path, ...] = (),
    ) -> "Snapshot":
        """Record exact bytes, and equally exactly, what was *not* there.

        DEC-2026-0092 fixed a rollback hole here. A missing path used to be
        skipped outright, so restoring a failed genesis transaction put nothing
        back and, having nothing to put back, left every file the transaction
        had just created. "Restore the pre-state" has to mean absence when the
        pre-state was absence.
        """
        directory.mkdir(parents=True, exist_ok=True)
        files = {}
        absent = []
        for path in paths:
            if not path.exists():
                absent.append(path)
                continue
            shutil.copy2(path, directory / path.name)
            files[path] = checksum_file(path)
        return cls(directory=directory, files=files, absent=tuple(absent),
                   created_dirs=tuple(d for d in genesis_dirs if not d.exists()))

    def restore(self) -> list[Path]:
        """Put every snapshotted file back, and remove what was never there."""
        restored = []
        for path in self.files:
            backup = self.directory / path.name
            if backup.exists():
                shutil.copy2(backup, path)
                restored.append(path)
        for path in self.absent:
            if path.exists():
                path.unlink()
                restored.append(path)
        # Only directories this transaction could have created, and only while
        # empty: a non-empty one holds something this transaction did not put
        # there, and removing it would destroy state it never owned.
        for directory in self.created_dirs:
            if directory.exists() and not any(directory.iterdir()):
                directory.rmdir()
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

    def __init__(
        self,
        paths: list[Path],
        directory: Path,
        genesis_dirs: tuple[Path, ...] = (),
        discard_snapshot_on_rollback: bool = False,
    ):
        self.paths = paths
        self.directory = directory
        self.genesis_dirs = genesis_dirs
        self.discard_snapshot_on_rollback = discard_snapshot_on_rollback
        self.snapshot: Snapshot | None = None
        self.rolled_back = False

    def __enter__(self) -> "Transaction":
        self.snapshot = Snapshot.take(self.paths, self.directory, self.genesis_dirs)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None and self.snapshot is not None:
            self.snapshot.restore()
            self.rolled_back = True
            # A rolled-back genesis returns the repository to "this ruleset has
            # never been integrated". A retained snapshot of that non-event is a
            # leftover of a transaction that is supposed to have left none, so
            # DEC-2026-0092 requires it gone too. An ordinary ruleset keeps its
            # snapshot: there the pre-state is real and worth retaining.
            if self.discard_snapshot_on_rollback and self.directory.exists():
                shutil.rmtree(self.directory)
        return False  # never swallow the failure
