#!/usr/bin/env python3
"""Verify that a continuing actor has already loaded the stable authority set.

Implements `contracts/ROLE_CONTEXT_LOADING.md` 1.2 under DEC-2026-0040 and
DEC-2026-0082.

There are five active roles, each scoped to one ruleset. DEC-2026-0082 retired
the Dispatcher that DEC-2026-0081 had added, and this module refuses it by name
rather than merely forgetting it: a request for a retired role must say what
retired it, so an operator reading the error learns the governance instead of
guessing at a typo. Manifest language 1.1 stays *parseable* for history, but
parsing a 1.1 manifest never reactivates the role -- no published Decision or
report is rewritten, and no receipt layout changes.

The repository, not an agent's memory, is the source of authority. That rule is
what this tool preserves: it never tells a role what the governance files say, it
only answers whether the exact bytes this session already read are still the
bytes on disk. A hit means "you may skip re-reading"; it never means "here is a
summary you may rely on".

Two commands:

    role_context.py verify  -- cache_hit, or reload_required plus the exact paths
    role_context.py record  -- attest that the emitted set was read this session

Everything about the design is fail-closed. A missing file, a pattern that
escapes the repository root, a duplicate resolved path, an unknown role, an
unreadable byte, a changed manifest, a changed schema, a changed authority file,
or a different session is a miss or an error -- never a hit. There is no
mtime shortcut, no partial hit, and no fallback to an older receipt, because a
role that wrongly believes it has current instructions is worse than one that
reads them again.

Exit codes:
    0: cache_hit (verify), or receipt written (record)
    1: reload_required -- read the emitted paths, then call record
    2: verification error -- fails closed, no receipt is trusted or written
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only in an incomplete runtime
    print(
        "PyYAML is required. Install it with: python -m pip install PyYAML",
        file=sys.stderr,
    )
    raise SystemExit(2)


MANIFEST_PATH = PurePosixPath("contracts/ROLE_CONTEXT_MANIFEST.yaml")
SCHEMA_PATH = PurePosixPath("schemas/common/role-context-manifest.schema.json")
RECEIPT_DIR = PurePosixPath(".local/role-context")

#: The five graph-processing roles. Each is scoped to one ruleset and inherits
#: the manifest's common patterns. This is the complete set of active roles.
WORKER_ROLES = ("architect", "analyst", "builder", "reviewer", "integrator")

ROLES = WORKER_ROLES

#: Roles a Decision has withdrawn, mapped to the Decision that withdrew them.
#:
#: Kept by name so a request for one fails with its own reason. Dropping the
#: name instead would report "unrecognized role", which reads like a typo and
#: sends the operator looking for a spelling mistake rather than for the ruling.
RETIRED_ROLES: dict[str, str] = {"dispatcher": "DEC-2026-0082"}

#: Manifest languages this verifier can parse. 1.0 is the five-role language and
#: is the one in force. 1.1 added a sixth role that DEC-2026-0082 retired; it
#: stays parseable so a historical manifest still reads, and `resolve_paths`
#: refuses the retired role regardless of which language declared it. An
#: unsupported version is an error, never a guess.
SUPPORTED_MANIFEST_SCHEMA_VERSIONS = ("1.0", "1.1")

#: The receipt encoding. DEC-2026-0082 keeps it at 1: the manifest language
#: selection changed, the receipt layout did not, and a new format would
#: invalidate every live receipt without invalidating anything the manifest and
#: schema hashes do not already catch.
SUPPORTED_CACHE_FORMAT_VERSION = 1

#: Directories the stable cache may never contain, whatever the manifest says.
#:
#: The manifest is governance and is checked by its schema, but a pattern is easy
#: to widen by accident -- `rulesets/{ruleset}/*` would pull in canonical data,
#: and a cached canonical baseline is exactly how a role would come to act on a
#: graph state that no longer exists. This guard is independent of the manifest so
#: that widening one cannot silently widen the other. DEC-2026-0040 acceptance
#: test 5 names these areas.
EXCLUDED_PREFIXES = (
    "books/",
    "build/",
    ".local/",
    ".git/",
)
EXCLUDED_SEGMENTS = (
    "canonical",
    "escalations",
    "decision-implementations",
    "decision-implementation-reviews",
    "manifests",
    "reports",
    "snapshots",
    "packets",
    "artifacts",
)
#: Live, mutable data files. `nodes.csv` is the registry the Builder must re-read
#: every task; the manifest's registry patterns deliberately name only `.yaml`
#: and `.json`, and this makes that deliberate rather than incidental.
EXCLUDED_SUFFIXES = (".csv",)


class ContextError(Exception):
    """A verification error. Always fails closed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _relative(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _excluded(relative: str) -> str:
    """The reason a resolved path may not be cached, or an empty string."""
    if any(relative.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return f"{relative} is under an excluded tree"
    parts = relative.split("/")
    for segment in EXCLUDED_SEGMENTS:
        if segment in parts:
            return f"{relative} contains the excluded path segment {segment!r}"
    if any(relative.endswith(suffix) for suffix in EXCLUDED_SUFFIXES):
        return f"{relative} is mutable data, not stable authority"
    return ""


def _inherits_common(role: str, entry: Any) -> bool:
    """Whether `role`'s effective set includes the manifest's common patterns.

    Omitted means true, which is what keeps every 1.0 manifest valid. The value
    is read strictly: `isinstance(value, bool)` rejects `1`, `"true"`, `None`
    and every other near-miss, because a truthy string silently granting a role
    the common set is precisely the failure this opt-out exists to prevent.
    """
    if not isinstance(entry, dict):
        raise ContextError(f"{MANIFEST_PATH} role {role!r} is not a mapping")
    if "inherit_common_patterns" not in entry:
        return True
    value = entry["inherit_common_patterns"]
    if not isinstance(value, bool):
        raise ContextError(
            f"{MANIFEST_PATH} role {role!r} declares inherit_common_patterns "
            f"{value!r}; it must be a boolean"
        )
    return value


def _check_retired_entry(role: str, entry: Any) -> None:
    """Shape-check a retired role's historical manifest entry.

    A 1.1 manifest still parses (DEC-2026-0082 keeps the language readable), so
    a malformed entry is still an error -- a manifest is either well-formed or
    it is not, and silently tolerating rubbish under one key would weaken the
    check for every other. It grants the role nothing: `validate_scope` refuses
    it before any set is resolved.
    """
    if not isinstance(entry, dict):
        raise ContextError(f"{MANIFEST_PATH} role {role!r} is not a mapping")
    if entry.get("inherit_common_patterns") is not False:
        raise ContextError(
            f"{MANIFEST_PATH} retired role {role!r} must still declare "
            f"inherit_common_patterns: false as it did when it was active"
        )


def load_manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST_PATH
    if not path.is_file():
        raise ContextError(f"the role context manifest is missing: {MANIFEST_PATH}")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContextError(f"{MANIFEST_PATH} is not readable YAML: {exc}") from exc
    if not isinstance(document, dict):
        raise ContextError(f"{MANIFEST_PATH} does not contain a mapping")

    version = document.get("schema_version")
    if version not in SUPPORTED_MANIFEST_SCHEMA_VERSIONS:
        raise ContextError(
            f"{MANIFEST_PATH} declares schema_version {version!r}; this verifier "
            f"implements {', '.join(SUPPORTED_MANIFEST_SCHEMA_VERSIONS)}"
        )
    cache_format = document.get("cache_format_version")
    if cache_format != SUPPORTED_CACHE_FORMAT_VERSION:
        raise ContextError(
            f"{MANIFEST_PATH} declares cache_format_version {cache_format!r}; this "
            f"verifier implements {SUPPORTED_CACHE_FORMAT_VERSION}"
        )

    roles = document.get("roles")
    if not isinstance(roles, dict):
        raise ContextError(f"{MANIFEST_PATH} declares no roles mapping")

    # The five workers are required by every manifest language. Dispatcher is
    # required by 1.1 and forbidden in 1.0, so a legacy manifest stays valid for
    # the roles it was written for and a Dispatcher request against it fails
    # closed rather than resolving an entry that governance never approved.
    retired = sorted(set(roles) & set(RETIRED_ROLES))
    missing = sorted(set(WORKER_ROLES) - set(roles))
    if missing:
        raise ContextError(
            f"{MANIFEST_PATH} at schema_version {version} omits role(s): "
            f"{', '.join(missing)}"
        )
    unexpected = sorted(set(roles) - set(ROLES) - set(RETIRED_ROLES))
    if unexpected:
        raise ContextError(
            f"{MANIFEST_PATH} declares unknown role(s): {', '.join(unexpected)}"
        )
    # A retired role belongs only to the language that introduced it. Version
    # 1.0 predates it, so finding one there is a malformed manifest rather than
    # history; version 1.1 may still carry it, inert.
    for name in retired:
        if version == "1.0":
            raise ContextError(
                f"{MANIFEST_PATH} declares {name!r} at schema_version 1.0; that role "
                f"was added in 1.1 and retired by {RETIRED_ROLES[name]}"
            )

    # Validated for every declared role, not only the one being resolved. The
    # manifest is governance: if it is malformed anywhere, no role's set may be
    # trusted, and a worker verifying today should not depend on nobody having
    # asked for another role yet.
    for name in sorted(roles):
        entry = roles[name]
        if name in RETIRED_ROLES:
            _check_retired_entry(name, entry)
        elif not _inherits_common(name, entry):
            raise ContextError(
                f"{MANIFEST_PATH} role {name!r} declares inherit_common_patterns: "
                f"false; every active role inherits the common set"
            )
    return document


def validate_scope(role: str, ruleset: str | None, book: str | None) -> None:
    """Reject a role or scope this verifier may not serve.

    Every public entry point calls this, so a retired role is refused before any
    manifest read, path resolution, or receipt read/write -- an invalid request
    leaves the cache exactly as it found it.
    """
    if role in RETIRED_ROLES:
        raise ContextError(
            f"role {role!r} was retired by {RETIRED_ROLES[role]} and has no context to "
            f"verify; the active roles are {', '.join(ROLES)}"
        )
    if role not in ROLES:
        raise ContextError(f"unrecognized role {role!r}; expected one of {', '.join(ROLES)}")
    if ruleset is None:
        raise ContextError(f"role {role!r} requires a ruleset")
    if not str(ruleset).strip():
        raise ContextError(f"role {role!r} requires a non-empty ruleset")


def _expand(root: Path, pattern: str, ruleset: str, book: str | None) -> list[Path]:
    """One manifest pattern, resolved lexically inside the repository root.

    A pattern naming `{book}` without a book in scope contributes nothing rather
    than resolving to a literal `{book}` directory: the scope is what makes the
    path set deterministic, so an unfilled placeholder is absence, not a guess.
    """
    if "{book}" in pattern and not book:
        return []
    filled = pattern.replace("{ruleset}", ruleset).replace("{book}", book or "")
    if "{" in filled or "}" in filled:
        raise ContextError(f"pattern {pattern!r} has an unresolved placeholder")

    resolved_root = root.resolve()
    if any(character in filled for character in "*?[") or "**" in filled:
        found = sorted(root.glob(filled))
    else:
        literal = root / filled
        if not literal.is_file():
            # A literal path is a governance claim that the file exists. Globs may
            # legitimately match nothing; a named file that is gone means the
            # manifest and the repository disagree.
            raise ContextError(f"pattern {pattern!r} names {filled}, which does not exist")
        found = [literal]

    paths: list[Path] = []
    for candidate in found:
        if not candidate.is_file():
            continue
        try:
            resolved = candidate.resolve()
            resolved.relative_to(resolved_root)
        except ValueError as exc:
            raise ContextError(
                f"pattern {pattern!r} resolved {candidate} outside the repository root"
            ) from exc
        paths.append(candidate)
    return paths


def effective_patterns(manifest: dict[str, Any], role: str) -> list[str]:
    """The patterns one role resolves: common plus its own, or its own alone."""
    entry = manifest["roles"].get(role)
    if entry is None:
        raise ContextError(
            f"{MANIFEST_PATH} declares no entry for role {role!r}"
        )
    patterns: list[str] = []
    if _inherits_common(role, entry):
        patterns += list(manifest.get("common_patterns") or [])
    patterns += list((entry or {}).get("stable_patterns") or [])
    return patterns


def resolve_paths(
    root: Path, manifest: dict[str, Any], role: str, ruleset: str, book: str | None
) -> list[str]:
    """The deterministic, sorted, duplicate-free stable authority set."""
    validate_scope(role, ruleset, book)
    patterns = effective_patterns(manifest, role)
    if not patterns:
        raise ContextError(f"the manifest declares no patterns for role {role!r}")

    seen: dict[str, str] = {}
    for pattern in patterns:
        for path in _expand(root, str(pattern), ruleset, book):
            relative = _relative(root, path)
            reason = _excluded(relative)
            if reason:
                raise ContextError(f"pattern {pattern!r} would cache {reason}")
            previous = seen.get(relative)
            if previous is not None and previous != str(pattern):
                # ROLE_CONTEXT_LOADING 1.0 makes a duplicate resolved path a
                # verifier error rather than something to collapse quietly. Two
                # patterns claiming one file means the manifest states the same
                # authority twice, and the fix belongs in the manifest: silently
                # picking one would make the set depend on pattern order, which
                # is exactly the determinism the contract requires.
                raise ContextError(
                    f"patterns {previous!r} and {pattern!r} both resolve {relative}; "
                    f"the manifest declares that authority twice"
                )
            seen[relative] = str(pattern)
    if not seen:
        where = "repository-wide" if ruleset is None else f"for ruleset {ruleset!r}"
        raise ContextError(f"role {role!r} resolved no stable authority files {where}")
    return sorted(seen)


def checksum_set(root: Path, relatives: Iterable[str]) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for relative in relatives:
        path = root / relative
        try:
            checksums[relative] = _sha256(path)
        except OSError as exc:
            raise ContextError(f"{relative} is not readable: {exc}") from exc
    return checksums


def _scope_key(root: Path, role: str, ruleset: str, book: str | None, session: str) -> str:
    # NUL-separated so no field value can impersonate a boundary: a session
    # ID containing the separator would otherwise let two different scopes
    # hash to one receipt file.
    material = "\0".join(
        [str(root.resolve()).replace("\\", "/"), role, ruleset, book or "", session]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def receipt_path(
    root: Path, role: str, ruleset: str, book: str | None, session: str
) -> Path:
    validate_scope(role, ruleset, book)
    name = f"{role}-{ruleset}-{book or 'no-book'}-{_scope_key(root, role, ruleset, book, session)}.json"
    return root / RECEIPT_DIR / name


def build_receipt(
    root: Path, role: str, ruleset: str, book: str | None, session: str
) -> dict[str, Any]:
    """The receipt's whole content. Contains no authority-file contents.

    Only what is needed to answer "is the set I read still exactly this set":
    the cache format, the scope it applies to, and a path/checksum pair per file.
    No prose, no summary, no excerpt -- a receipt a role could read instructions
    out of would replace the repository as the authority.
    """
    validate_scope(role, ruleset, book)
    manifest = load_manifest(root)
    relatives = resolve_paths(root, manifest, role, ruleset, book)
    schema = root / SCHEMA_PATH
    if not schema.is_file():
        raise ContextError(f"the manifest schema is missing: {SCHEMA_PATH}")
    return {
        "cache_format_version": manifest.get("cache_format_version"),
        "repository_root": str(root.resolve()).replace("\\", "/"),
        "role": role,
        "scope": {"ruleset_id": ruleset, "book_id": book},
        "session_id": session,
        "manifest_path": str(MANIFEST_PATH),
        "manifest_checksum": _sha256(root / MANIFEST_PATH),
        "manifest_schema_path": str(SCHEMA_PATH),
        "manifest_schema_checksum": _sha256(schema),
        "stable_authority": checksum_set(root, relatives),
    }


#: Every field a hit requires to be identical. Listed rather than compared with a
#: whole-document equality so that adding a field to a receipt cannot silently
#: stop being checked -- and so a mismatch can name which field moved.
RECEIPT_IDENTITY_FIELDS = (
    "cache_format_version",
    "repository_root",
    "role",
    "scope",
    "session_id",
    "manifest_path",
    "manifest_checksum",
    "manifest_schema_path",
    "manifest_schema_checksum",
)


def compare(current: dict[str, Any], stored: Any) -> list[str]:
    """Why the stored receipt does not cover the current state."""
    if not isinstance(stored, dict):
        return ["the stored receipt is not a mapping"]
    differences: list[str] = []

    # Both scope keys must be present, even when their value is null. An absent
    # key is a malformed receipt, not a null scope: a receipt written by an
    # older tool that had no concept of a scope-free role would otherwise
    # compare equal to a Dispatcher's and hand it a hit.
    stored_scope = stored.get("scope")
    if isinstance(stored_scope, dict):
        absent = [key for key in ("ruleset_id", "book_id") if key not in stored_scope]
        if absent:
            differences.append(
                f"the receipt's scope omits {', '.join(absent)}; a missing scope key is "
                f"malformed, not a null scope"
            )
    else:
        differences.append(f"the receipt's scope is not a mapping: {stored_scope!r}")

    for field in RECEIPT_IDENTITY_FIELDS:
        if stored.get(field) != current.get(field):
            differences.append(
                f"{field} changed: receipt {stored.get(field)!r} != current {current.get(field)!r}"
            )
    stored_files = stored.get("stable_authority")
    if not isinstance(stored_files, dict):
        differences.append("the receipt records no stable_authority set")
        return differences
    current_files = current["stable_authority"]
    for relative in sorted(set(current_files) - set(stored_files)):
        differences.append(f"{relative} is new to the stable set")
    for relative in sorted(set(stored_files) - set(current_files)):
        differences.append(f"{relative} is no longer in the stable set")
    for relative in sorted(set(current_files) & set(stored_files)):
        if current_files[relative] != stored_files[relative]:
            differences.append(f"{relative} changed on disk")
    return differences


def verify(root: Path, role: str, ruleset: str, book: str | None, session: str) -> dict[str, Any]:
    current = build_receipt(root, role, ruleset, book, session)
    path = receipt_path(root, role, ruleset, book, session)
    result = {
        "command": "verify",
        "role": role,
        "scope": current["scope"],
        "session_id": session,
        "receipt_path": _relative(root, path) if path.exists() else None,
        "stable_authority_paths": sorted(current["stable_authority"]),
    }
    if not path.is_file():
        result["status"] = "reload_required"
        result["differences"] = ["no receipt exists for this role, scope and session"]
        return result
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # A corrupt receipt is not evidence of anything. Fails closed rather than
        # being repaired or partially trusted.
        result["status"] = "reload_required"
        result["differences"] = [f"the receipt is unreadable: {exc}"]
        return result
    differences = compare(current, stored)
    result["status"] = "cache_hit" if not differences else "reload_required"
    if differences:
        result["differences"] = differences
    return result


def record(root: Path, role: str, ruleset: str, book: str | None, session: str) -> dict[str, Any]:
    """Write the attestation that this session read the stable authority set.

    The tool cannot observe a role reading a file, so this is an attestation and
    not a proof. The contract places the obligation on the role: `record` must
    follow a `verify` whose emitted set was actually read, and must never be
    called on a miss to skip the reading.
    """
    current = build_receipt(root, role, ruleset, book, session)
    path = receipt_path(root, role, ruleset, book, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return {
        "command": "record",
        "status": "recorded",
        "role": role,
        "scope": current["scope"],
        "session_id": session,
        "receipt_path": _relative(root, path),
        "stable_authority_paths": sorted(current["stable_authority"]),
    }


def _print_human(result: dict[str, Any]) -> None:
    status = result["status"]
    scope = result["scope"]
    where = f"{scope['ruleset_id']}" + (f"/{scope['book_id']}" if scope["book_id"] else "")
    print(f"{status}: role={result['role']} scope={where} session={result['session_id']}")
    for difference in result.get("differences") or []:
        print(f"  - {difference}")
    count = len(result["stable_authority_paths"])
    if status == "cache_hit":
        print(f"  {count} stable authority file(s) unchanged; no reload needed")
        return
    # Only paths are ever printed, never file contents: emitting a summary of the
    # governance files would let a role act on this output instead of on them.
    verb = "attested as read" if status == "recorded" else "read these"
    print(f"  {verb} {count} stable authority file(s):")
    for relative in result["stable_authority_paths"]:
        print(f"    {relative}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="role_context",
        description="Verify or record a same-session stable role context receipt.",
    )
    parser.add_argument("command", choices=("verify", "record"))
    parser.add_argument("--root", type=Path, default=Path("."))
    # Deliberately not an argparse `choices` list. A retired role must be told
    # it was retired and by which Decision; argparse would answer "invalid
    # choice", which reads like a spelling mistake. `validate_scope` below makes
    # that distinction and still exits 2 without touching the cache.
    parser.add_argument(
        "--role", required=True, help=f"one of: {', '.join(ROLES)}"
    )
    parser.add_argument("--ruleset", required=True)
    parser.add_argument("--book", default=None)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--json", action="store_true", help="emit the result as JSON")
    args = parser.parse_args(argv)

    # Before any path resolution, receipt read, or receipt write: an invalid
    # invocation must leave the cache exactly as it found it.
    try:
        validate_scope(args.role, args.ruleset, args.book)
    except ContextError as exc:
        print(f"role context verification failed: {exc}", file=sys.stderr)
        return 2

    root: Path = args.root
    if not root.is_dir():
        print(f"repository root is not a directory: {root}", file=sys.stderr)
        return 2
    if not (root / "README.md").is_file():
        print(f"{root} does not look like the repository root", file=sys.stderr)
        return 2

    try:
        if args.command == "verify":
            result = verify(root, args.role, args.ruleset, args.book, args.session_id)
        else:
            result = record(root, args.role, args.ruleset, args.book, args.session_id)
    except ContextError as exc:
        print(f"role context verification failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        _print_human(result)
    return 0 if result["status"] in ("cache_hit", "recorded") else 1


if __name__ == "__main__":
    raise SystemExit(main())
