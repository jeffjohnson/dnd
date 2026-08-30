#!/usr/bin/env python3
"""Validate the exact bytes of one staged artifact before it is published.

Six malformed YAML artifacts reached durable publication across three roles in
three days. Every one was caught afterwards -- by a scanner crash, an opaque
ScannerError from whichever test sweep reached it first, or a Reviewer reading
it -- and each needed its own checksummed Architect exception to stop being a
permanent error, because a published artifact cannot be edited or withdrawn.

All six were writable-and-wrong in the same way: text assembled by hand, where a
value containing `: ` or a line of continuation prose silently changes the
document's shape. The defect is cheap to catch and expensive to publish, so
DEC-2026-0072 requires the check to happen before the write.

What this command deliberately does not do:

    It reads the staged file and its schema and nothing else. No corpus sweep,
    no packet reload, no canonical data. A preflight that reads the repository
    would make every publication depend on the repository being healthy, which
    is exactly the coupling that turned one bad Review into five broken suites.

    It takes the schema as an argument rather than guessing it from the
    filename. A name is a claim about what an artifact is; the caller knows what
    it is publishing, and inferring authority from a string is how the wrong
    rules get applied to the right file.

    It never writes the destination. Deciding to publish is the caller's, and
    this command exists to be able to say no first.

Exit codes:
    0: the staged bytes parse and satisfy the schema
    1: they do not, and the reason is on stderr
    2: the command could not run the check it was asked for
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only in an incomplete runtime
    print(
        "PyYAML is required. Install it with: python -m pip install PyYAML",
        file=sys.stderr,
    )
    raise SystemExit(2)


def _schema_registry(schema_path: Path):
    """A validator for `schema_path`, with its sibling schemas resolvable.

    Sibling resolution matters because every artifact schema in this repository
    references `artifact-envelope.schema.json`. Loading the target alone would
    fail on the reference and report the artifact as unvalidatable when the only
    real problem is that the loader never looked next door.
    """
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    resources = []
    for sibling in sorted(schema_path.parent.glob("*.json")):
        resources.append((
            sibling.name,
            Resource(
                contents=json.loads(sibling.read_text(encoding="utf-8")),
                specification=DRAFT202012,
            ),
        ))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=Registry().with_resources(resources))


def validate_staged(staged: Path, schema_path: Path) -> list[str]:
    """Why these exact staged bytes must not be published, or [].

    Returns reasons rather than raising so a caller can report all of them and
    decide what to do; an empty list is the only thing that means "publish".
    """
    if not staged.is_file():
        return [f"{staged} does not exist; there is nothing to validate"]
    if not schema_path.is_file():
        return [
            f"{schema_path} does not exist; the applicable schema must be named "
            f"explicitly and must be present"
        ]

    try:
        text = staged.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{staged} cannot be read as UTF-8: {exc}"]

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        # The whole point of the command. Reported with the parser's own message
        # because that names the line, and with the file, because the caller is
        # usually holding several.
        return [f"{staged} is not valid YAML: {exc}"]

    if not isinstance(document, dict):
        kind = type(document).__name__ if document is not None else "empty"
        return [f"{staged} has a {kind} root; an artifact document must be a mapping"]

    try:
        validator = _schema_registry(schema_path)
    except ImportError as exc:
        return [
            f"cannot validate {staged} against {schema_path.name}: {exc}. The "
            f"jsonschema and referencing packages are required for the "
            f"DEC-2026-0072 preflight"
        ]
    except (OSError, ValueError) as exc:
        return [f"{schema_path} could not be loaded: {exc}"]

    try:
        errors = sorted(validator.iter_errors(document), key=lambda e: list(e.path))
    except Exception as exc:  # pragma: no cover - a malformed schema, not artifact
        return [f"{schema_path.name} could not be applied: {exc}"]

    return [
        f"{staged} fails {schema_path.name} at {list(error.path) or 'the document root'}: "
        f"{error.message}"
        for error in errors
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate_artifact",
        description=(
            "Validate one staged YAML artifact against an explicitly named schema, "
            "before it is written to its durable path."
        ),
    )
    parser.add_argument("staged", type=Path, help="the staged file to check")
    parser.add_argument(
        "--schema", type=Path, required=True,
        help="the applicable JSON Schema; named explicitly, never inferred",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="report nothing on success",
    )
    args = parser.parse_args(argv)

    reasons = validate_staged(args.staged, args.schema)
    if reasons:
        print(
            f"{args.staged}: publication refused; {len(reasons)} problem(s):",
            file=sys.stderr,
        )
        for reason in reasons:
            print(f"  {reason}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"{args.staged}: valid against {args.schema.name}; safe to publish")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
