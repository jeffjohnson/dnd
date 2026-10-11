"""Shared byte validation and create-only publication, not role authority."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile

import yaml

from validate_artifact import validate_staged


class PublicationError(ValueError):
    pass


def contained(root: Path, value: str | Path) -> Path:
    root = Path(root).resolve()
    path = Path(value)
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(root) or path == root:
        raise PublicationError(f"path must stay inside the repository: {value}")
    return path


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def load_mapping(path: Path) -> dict:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise PublicationError(f"cannot read {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise PublicationError(f"{path}: expected a mapping")
    return document


def yaml_bytes(document: dict) -> bytes:
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100).encode("utf-8")


def json_bytes(document: dict) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def verify_inputs(root: Path, expected: dict[str, str]) -> None:
    for relative, checksum in expected.items():
        path = contained(root, relative)
        if not path.is_file() or digest(path.read_bytes()) != checksum:
            raise PublicationError(f"input changed or disappeared: {relative}")


@dataclass(frozen=True)
class Output:
    path: Path
    content: bytes
    schemas: tuple[Path, ...] = ()


def validate_content(content: bytes, schemas: tuple[Path, ...]) -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory(prefix="dnd-validate-") as temporary:
        staged = Path(temporary) / "artifact.yaml"
        staged.write_bytes(content)
        for schema in schemas:
            problems.extend(validate_staged(staged, schema))
    return problems


def validate_outputs(root: Path, outputs: list[Output]) -> list[str]:
    root = root.resolve()
    problems = []
    for output in outputs:
        contained(root, output.path)
        schemas = tuple(contained(root, schema) for schema in output.schemas)
        problems.extend(validate_content(output.content, schemas))
    return problems


def publish(root: Path, outputs: list[Output], *, companions=(), expected_inputs=None) -> list[dict]:
    """Validate the complete set before any exclusive final write.

    This is create-only, not a multi-file filesystem transaction. Ordinary
    exceptions remove only unchanged files created by this invocation; a hard
    process crash can leave an incomplete set, which must never be overwritten.
    """
    root = root.resolve()
    paths = [contained(root, output.path) for output in outputs]
    if len(paths) != len(set(paths)) or not paths:
        raise PublicationError("publication requires a nonempty set of distinct output paths")
    expected_inputs = expected_inputs or {}
    verify_inputs(root, expected_inputs)
    problems = validate_outputs(root, outputs)
    if problems:
        raise PublicationError("staged validation failed:\n" + "\n".join(problems))
    all_paths = set(paths) | {contained(root, path) for path in companions}
    existing = sorted(str(path.relative_to(root)) for path in all_paths if path.exists())
    if existing:
        raise PublicationError(f"create-only publication refused; existing paths: {existing}")
    verify_inputs(root, expected_inputs)
    created: list[tuple[Path, bytes]] = []
    try:
        for path, output in zip(paths, outputs):
            path.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation also closes the check/write race for this path.
            with path.open("xb") as handle:
                created.append((path, output.content))
                handle.write(output.content)
                handle.flush()
                os.fsync(handle.fileno())
            if path.read_bytes() != output.content:
                raise PublicationError(f"published bytes failed reread: {path}")
    except BaseException:
        for path, content in reversed(created):
            if path.is_file() and path.read_bytes() == content:
                path.unlink()
        raise
    return [{"path": path.relative_to(root).as_posix(), "checksum": digest(output.content)}
            for path, output in zip(paths, outputs)]


def artifact_schemas(root: Path, kind: str, ruleset: str) -> tuple[Path, ...]:
    common = root / "schemas" / "common" / f"{kind}.schema.json"
    schemas = [common]
    if kind in {"gur", "gup"}:
        schemas.append(root / "schemas" / ruleset / "graph" / f"{kind}.schema.json")
    return tuple(schemas)
