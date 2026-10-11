"""Bounded Pandoc packet preparation and byte-preserving claim planning."""
from dataclasses import asdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for relative in ("tooling/common", "tooling/builder/src"):
    sys.path.insert(0, str(ROOT / relative))

from artifact_io import Output, PublicationError, artifact_schemas, contained, digest, load_mapping, validate_content
from adnd1e_builder.pagemarkers import parse_source


def packet_inputs(root: Path, path: Path) -> dict:
    path = contained(root, path)
    manifest = None
    if path.is_dir():
        path = path / "packet.yaml"
    if path.name == "packet.yaml":
        manifest = load_mapping(path)
        source = contained(root, path.parent / manifest.get("source_file", "source.md"))
        if not source.is_relative_to(path.parent):
            raise PublicationError("claimed source must stay inside its packet directory")
    else:
        source = path
    raw = source.read_bytes()
    if manifest and manifest.get("source_checksum"):
        material = raw.replace(b"\r\n", b"\n") if manifest.get("source_checksum_basis") == "lf_normalized" else raw
        if digest(material) != manifest["source_checksum"]:
            raise PublicationError(f"claimed source checksum mismatch: {source}")
    parsed = parse_source(source)
    if parsed.malformed_markers:
        raise PublicationError("malformed page markers: " + str([asdict(item) for item in parsed.malformed_markers]))
    if not parsed.pages or any(marker.unknown for marker in parsed.page_classes):
        raise PublicationError("packet needs resolvable pages and supported page classes")
    result = {"source_path": source.relative_to(root).as_posix(), "checksum": digest(raw),
              "source_text": raw.decode("utf-8-sig"), "pages": list(parsed.pages),
              "page_classes": [asdict(item) for item in parsed.page_classes],
              "parser_warnings": parsed.warnings, "supplied_inputs": [], "missing_supplied_inputs": []}
    for name in ("node_registry_slice.csv", "local_neighborhood.json", "general_rule_slice.json"):
        supplied = source.parent / name
        if supplied.is_file():
            result["supplied_inputs"].append({"path": supplied.relative_to(root).as_posix(),
                                               "checksum": digest(supplied.read_bytes()),
                                               "content": supplied.read_text(encoding="utf-8-sig")})
        else:
            result["missing_supplied_inputs"].append(name)
    return result


def plan_claim(root: Path, incoming: Path, staged_manifest: Path, active_packets: set[str]):
    incoming, staged_manifest = contained(root, incoming), contained(root, staged_manifest)
    document = load_mapping(staged_manifest)
    raw_manifest = staged_manifest.read_bytes()
    errors = validate_content(raw_manifest, artifact_schemas(root, "source-packet", document.get("ruleset_id", "")))
    if errors:
        raise PublicationError("invalid claim: " + "; ".join(errors))
    ruleset, book = document.get("ruleset_id"), document.get("book_id")
    packet = document.get("packet_id")
    if not packet or document.get("id") != packet or not packet.startswith("PKT-") or Path(packet).name != packet:
        raise PublicationError("claim must explicitly declare a matching valid packet ID")
    if active_packets:
        raise PublicationError(f"another packet is active: {sorted(active_packets)}")
    if (ruleset, book) == ("basicdnd", "rc"):
        raise PublicationError("RC is owner-paused")
    base = contained(root, f"books/{ruleset}/{book}/packets")
    sources_path = contained(root, f"rulesets/{ruleset}/registries/sources.yaml")
    sources = load_mapping(sources_path)
    if not any(entry.get("source_id") == document.get("source_id") and entry.get("book_id") == book
               for entry in sources.get("sources", [])):
        raise PublicationError("claim source_id is not registered for this book")
    if not incoming.is_relative_to(base / "incoming"):
        raise PublicationError("claim input is outside its incoming book scope")
    source = incoming.read_bytes()
    material = source.replace(b"\r\n", b"\n") if document.get("source_checksum_basis") == "lf_normalized" else source
    if document.get("source_checksum") != digest(material):
        raise PublicationError("claim must pin the actual incoming source bytes")
    if document.get("source_file") != "source.md" or document.get("status") != "claimed":
        raise PublicationError("claim must declare source_file: source.md and status: claimed")
    if document.get("original_filename") != incoming.name:
        raise PublicationError("claim must retain the exact original_filename")
    packet_inputs(root, incoming)
    target = contained(root, base / "claimed" / packet)
    if target.exists():
        raise PublicationError("claim directory already exists; never replace an immutable claim")
    for other in (base / "claimed").glob("*/packet.yaml"):
        old = load_mapping(other)
        if old.get("original_filename") == incoming.name:
            raise PublicationError(f"incoming file already claimed by {old.get('id')}")
    expected = {incoming.relative_to(root).as_posix(): digest(source),
                staged_manifest.relative_to(root).as_posix(): digest(raw_manifest),
                sources_path.relative_to(root).as_posix(): digest(sources_path.read_bytes())}
    return [Output(target / "packet.yaml", raw_manifest, artifact_schemas(root, "source-packet", ruleset)),
            Output(target / "source.md", source)], expected
