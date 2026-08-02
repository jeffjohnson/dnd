"""SHA-256 helpers.

`schemas/common/approved-bundle.schema.json` pins every checksum as lowercase
hex with a `sha256:` prefix, which is the form the Builder already writes for
`gur_checksum`. Every checksum this package emits or compares uses that form.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

PREFIX = "sha256:"


def checksum_bytes(data: bytes) -> str:
    return PREFIX + hashlib.sha256(data).hexdigest()


def checksum_file(path: Path) -> str:
    """Checksum a file's exact bytes. Never normalise line endings first."""
    return checksum_bytes(Path(path).read_bytes())


def matches(path: Path, expected: str | None) -> tuple[bool, str]:
    """Return (ok, actual). A missing expectation is not a match, it is unpinned."""
    actual = checksum_file(path)
    return (expected is not None and actual == expected), actual
