"""Put the package on sys.path and locate the repository root."""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[2]
SRC = REPO_ROOT / "tooling" / "integrator" / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

RULESET_ID = "adnd1e"
