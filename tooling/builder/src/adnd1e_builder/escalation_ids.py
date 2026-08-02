"""Escalation identifier validation and allocation — DEC-2026-0006.

New escalation IDs use a UTC timestamp form that is valid in Windows filenames:

    ESC-YYYY-MM-DDTHH.mm.ss.fffZ

Dots replace ISO 8601 time colons, milliseconds are mandatory, and a
same-millisecond collision appends `-02`, then `-03`. Legacy `ESC-YYYY-NNNN` IDs
remain valid provenance keys and are never renamed.

Builder owns `validator_implementation` for this decision. Allocation uses
exclusive file creation so two roles filing in the same millisecond cannot claim
one ID.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Transcribed from DEC-2026-0006 identifier_contract.validation_pattern.
TIMESTAMP_PATTERN = re.compile(
    r"^ESC-[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}\.[0-9]{2}\.[0-9]{2}\.[0-9]{3}Z"
    r"(?:-(?:0[2-9]|[1-9][0-9]+))?$"
)

# Pre-decision form. Still resolvable, never reissued.
LEGACY_PATTERN = re.compile(r"^ESC-[0-9]{4}-[0-9]{4}$")

STATE_FOLDERS = ("pending", "decided", "archived")


def is_valid(escalation_id: str) -> bool:
    """True for either the timestamp form or a legacy ID."""
    return bool(TIMESTAMP_PATTERN.match(escalation_id) or LEGACY_PATTERN.match(escalation_id))


def is_timestamp_form(escalation_id: str) -> bool:
    return bool(TIMESTAMP_PATTERN.match(escalation_id))


def is_legacy(escalation_id: str) -> bool:
    return bool(LEGACY_PATTERN.match(escalation_id))


@dataclass
class Finding:
    severity: str
    rule: str
    detail: str
    path: str | None = None

    def as_dict(self) -> dict:
        out = {"severity": self.severity, "rule": self.rule, "detail": self.detail}
        if self.path:
            out["path"] = self.path
        return out


@dataclass
class AuditResult:
    findings: list[Finding] = field(default_factory=list)
    checked: int = 0
    timestamp_form: int = 0
    legacy_form: int = 0

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)


def audit(ruleset_root: str | Path) -> AuditResult:
    """Check every escalation file against the identifier contract.

    Verifies the ID shape, filename-stem equality, and ruleset-wide uniqueness
    across all state folders (DEC-2026-0006 acceptance tests).
    """
    import yaml

    root = Path(ruleset_root) / "escalations"
    result = AuditResult()
    seen: dict[str, str] = {}

    for folder in STATE_FOLDERS:
        directory = root / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.yaml")):
            result.checked += 1
            relative = f"escalations/{folder}/{path.name}"
            stem = path.stem

            try:
                document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as exc:
                result.findings.append(
                    Finding("error", "escalation_unparseable", str(exc), relative)
                )
                continue

            declared = str(document.get("id") or "").strip()

            if not is_valid(stem):
                result.findings.append(
                    Finding(
                        "error",
                        "escalation_id_malformed",
                        f"filename stem {stem!r} matches neither the timestamp form "
                        f"ESC-YYYY-MM-DDTHH.mm.ss.fffZ nor a legacy ESC-YYYY-NNNN ID",
                        relative,
                    )
                )
            elif is_timestamp_form(stem):
                result.timestamp_form += 1
            else:
                result.legacy_form += 1

            if declared != stem:
                result.findings.append(
                    Finding(
                        "error",
                        "escalation_filename_mismatch",
                        f"YAML id {declared!r} does not equal filename stem {stem!r}; "
                        f"FILE_NAMING requires the filename to be <id>.yaml",
                        relative,
                    )
                )

            if ":" in stem:
                result.findings.append(
                    Finding(
                        "error",
                        "escalation_id_contains_colon",
                        f"{stem!r} contains a colon and is not a valid Windows filename",
                        relative,
                    )
                )

            key = declared or stem
            if key in seen:
                result.findings.append(
                    Finding(
                        "error",
                        "escalation_id_duplicated",
                        f"{key!r} already appears at {seen[key]}; IDs must be unique across "
                        f"every escalation state folder",
                        relative,
                    )
                )
            else:
                seen[key] = relative

    return result


def allocate(ruleset_root: str | Path, folder: str = "pending", now: datetime | None = None) -> Path:
    """Reserve a new escalation ID by exclusive file creation.

    Returns the created path. The file is created empty so the ID cannot be
    claimed twice; the caller writes the package into it.
    """
    root = Path(ruleset_root) / "escalations" / folder
    root.mkdir(parents=True, exist_ok=True)

    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    base = (
        f"ESC-{moment.year:04d}-{moment.month:02d}-{moment.day:02d}"
        f"T{moment.hour:02d}.{moment.minute:02d}.{moment.second:02d}"
        f".{moment.microsecond // 1000:03d}Z"
    )

    for occurrence in range(1, 100):
        candidate = base if occurrence == 1 else f"{base}-{occurrence:02d}"
        path = root / f"{candidate}.yaml"
        try:
            path.touch(exist_ok=False)
        except FileExistsError:
            continue
        return path

    raise RuntimeError(f"could not allocate an escalation ID for {base}: 99 occurrences exhausted")
