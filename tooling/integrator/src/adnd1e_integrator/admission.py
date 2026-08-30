"""Queue admission for Reviews the Integrator cannot parse (DEC-2026-0065).

A malformed Review can change whether a published bundle is withdrawn, so an
unreadable one is never skipped quietly: either an active approved Architect
Decision pins it as historical evidence, or the queue fails closed and offers no
ready bundle at all.

DEC-2026-0065 authorises exactly one exception, the one DEC-2026-0064 records,
and requires the Integrator to re-derive that record from the files rather than
inherit the common scanner's conclusion. Everything here is that re-derivation.
Nothing in this module reads the unreadable Review's content; it reads its bytes
only to confirm the checksum and that it still fails to parse.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

#: DEC-2026-0065 informational_code. One notice, carrying no Review content.
INFORMATIONAL_CODE = "historical_unreadable_review"

#: DEC-2026-0065 fatal_code. Every denied or unrecognised parse failure.
FATAL_CODE = "review_yaml_unreadable"

#: DEC-2026-0070. The one bundle a validated direct-predecessor record names as
#: history. It is reported, never offered: its approving Review is the unreadable
#: file, so no role can read the approval it would be integrated on.
HISTORICAL_BUNDLE_CODE = "historical_unadmitted_bundle"

#: The field an Architect Decision uses to pin a malformed-lineage repair.
LINEAGE_REPAIR_KEY = "review_malformed_lineage_repairs"

#: The block by which a Decision delegates admission to another Decision's
#: repair record. DEC-2026-0065 carries it; DEC-2026-0064 holds the record.
GOVERNING_KEY = "governing_repair_record"

#: DEC-2026-0068 records a *direct* predecessor: the unreadable Review's sole
#: successor is already the active one, with no bridging revision between them.
#: The two-hop shape above cannot express that, because it requires the
#: successor to supersede a bridge that in a one-step lineage is the successor
#: itself.
DIRECT_PREDECESSOR_KEY = "review_direct_predecessor_repairs"

#: DEC-2026-0069 carries this; DEC-2026-0068 holds the record.
DIRECT_GOVERNING_KEY = "governing_direct_predecessor_repair_record"

#: Each delegation form names exactly one field of exactly one shape. Reading
#: the field name from the Decision instead would let a delegation point at any
#: list it liked, which DEC-2026-0069 forbids.
DELEGATIONS = {
    GOVERNING_KEY: LINEAGE_REPAIR_KEY,
    DIRECT_GOVERNING_KEY: DIRECT_PREDECESSOR_KEY,
}


def sha256_of(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass
class Admission:
    """Which unreadable Reviews the queue may omit, and why it may not proceed."""

    #: Resolved path -> the Decision ID that authorises omitting it.
    permitted: dict[str, str] = field(default_factory=dict)
    #: Resolved manifest path -> the Decision ID that excludes it from readiness.
    #: DEC-2026-0070 bounds this to bundles a validated record names exactly.
    historical_bundles: dict[str, str] = field(default_factory=dict)
    #: DEC-2026-0065 requires these to travel separately from fatal diagnostics.
    informational: list[dict] = field(default_factory=list)
    fatal: list[dict] = field(default_factory=list)

    @property
    def fails_closed(self) -> bool:
        return bool(self.fatal)

    def permits(self, path: Path) -> str | None:
        return self.permitted.get(str(Path(path).resolve()))

    def excludes_bundle(self, manifest_path: Path) -> str | None:
        """The Decision excluding this manifest from readiness, if any."""
        return self.historical_bundles.get(str(Path(manifest_path).resolve()))

    def note_historical_bundle(self, bundle_id: str, manifest_path: Path,
                               decision_id: str) -> None:
        target = str(Path(manifest_path).resolve())
        if any(entry.get("path") == target and entry["code"] == HISTORICAL_BUNDLE_CODE
               for entry in self.informational):
            return
        self.informational.append({
            "code": HISTORICAL_BUNDLE_CODE,
            "severity": "info",
            "path": target,
            "bundle_id": bundle_id,
            "authorised_by": decision_id,
            "detail": (
                f"{bundle_id} is approved by a Review that cannot be read, and "
                f"{decision_id} names it as historical evidence. It is withheld from "
                "every queue bucket rather than offered on an unreadable approval."),
        })

    def note_historical(self, path: Path, decision_id: str) -> None:
        """Record the one informational notice for a permitted unreadable file."""
        target = str(Path(path).resolve())
        if any(entry["path"] == target for entry in self.informational):
            return
        self.informational.append({
            "code": INFORMATIONAL_CODE,
            "severity": "info",
            "path": target,
            "authorised_by": decision_id,
            "detail": (
                f"{Path(path).name} is unreadable YAML pinned by {decision_id} as "
                "historical evidence. Its bytes are omitted from Review-lineage "
                "state and none of its content is recovered or used."),
        })

    def note_fatal(self, path: Path, detail: str) -> None:
        self.fatal.append({
            "code": FATAL_CODE,
            "severity": "error",
            "path": str(Path(path).resolve()),
            "detail": detail,
        })


def _decision_documents(root: Path, ruleset_id: str) -> dict[str, tuple[Path, dict]]:
    """Every Architect Decision that parses, by ID."""
    decisions_dir = root / "rulesets" / ruleset_id / "escalations" / "decisions"
    found: dict[str, tuple[Path, dict]] = {}
    if not decisions_dir.exists():
        return found
    for path in sorted(decisions_dir.glob("DEC-*.yaml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError):
            continue
        if isinstance(document, dict) and document.get("id"):
            found[str(document["id"])] = (path, document)
    return found


def _active_ids(decisions: dict[str, tuple[Path, dict]]) -> set[str]:
    """Approved Decisions no other approved Decision supersedes."""
    approved = {i for i, (_, d) in decisions.items()
                if str(d.get("status") or "") == "approved"}
    retired = {str(decisions[i][1].get("supersedes"))
               for i in approved if decisions[i][1].get("supersedes")}
    return approved - retired


def _pinned(root: Path, label: str, block: Any, *, must_parse: bool
            ) -> tuple[list[str], dict | None]:
    """Re-derive one `{id, path, checksum}` reference from the file it names.

    `must_parse` is the load-bearing half. One reference must parse and one must
    still fail, because a record whose unreadable file has quietly become
    readable is describing a repair that is no longer needed, and honouring it
    would silence a genuine parse failure somewhere else.
    """
    if not isinstance(block, dict):
        return [f"{label} is not a mapping"], None
    identifier = str(block.get("id") or "")
    relative = str(block.get("path") or "")
    if not identifier:
        return [f"{label} names no id"], None
    if not relative:
        return [f"{label} names no path"], None

    target = root / relative
    if not target.is_file():
        return [f"{label} names {relative}, which does not exist"], None
    current = sha256_of(target)
    if str(block.get("checksum") or "") != current:
        return ([f"{label} records {block.get('checksum') or 'no checksum'} for "
                 f"{relative}, which now hashes to {current}"], None)

    try:
        document = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        if must_parse:
            return [f"{label} names {relative}, which does not parse"], None
        return [], {"_parse_error": str(exc)}

    if not must_parse:
        return [f"{label} names {relative}, which parses; there is nothing to bridge"], None
    if not isinstance(document, dict):
        return [f"{label} names {relative}, whose YAML root is not a mapping"], None
    if str(document.get("id") or "") != identifier:
        return ([f"{label} names {identifier}, but {relative} declares "
                 f"{document.get('id')!r}"], None)
    return [], document


def _pinned_bytes(root: Path, label: str, block: Any, *, key: str = "path") -> list[str]:
    """Re-hash a pinned file whose content this module never parses.

    The rejection record is JSON and the edge component is CSV. Both are pinned
    as evidence that the successor reconstitutes the same reviewed rows, and for
    that purpose the hash is the whole claim.
    """
    if not isinstance(block, dict):
        return [f"{label} is not a mapping"]
    relative = str(block.get(key) or "")
    if not relative:
        return [f"{label} names no {key}"]
    target = root / relative
    if not target.is_file():
        return [f"{label} names {relative}, which does not exist"]
    current = sha256_of(target)
    if str(block.get("checksum") or "") != current:
        return [f"{label} records {block.get('checksum') or 'no checksum'} for "
                f"{relative}, which now hashes to {current}"]
    return []


def _csv_rows(root: Path, relative: str) -> int:
    """Data rows in a component, header excluded."""
    text = (root / relative).read_text(encoding="utf-8")
    return max(0, len([line for line in text.splitlines() if line.strip()]) - 1)


def direct_predecessor_record_errors(root: Path, decision_id: str, index: int,
                                     record: Any, required_disposition: str) -> list[str]:
    """Why one direct-predecessor repair record is not evidence, or [].

    DEC-2026-0068's shape differs from the two-hop one in a single structural
    way: the unreadable Review's successor is already the active one, so there is
    no bridge to check and the successor is verified against the unreadable file
    directly. Everything else is stricter rather than looser -- the successor
    must also carry a bundle superseding the historical one, and that bundle's
    declared operation partition must match the reviewed component row for row.

    The extra pins are the point. A one-step lineage offers one fewer link to
    corroborate, so the record compensates with the rejection it consumes, the
    component it re-packages, and the exact partition it declares.
    """
    label = f"{decision_id} {DIRECT_PREDECESSOR_KEY}[{index}]"
    if not isinstance(record, dict):
        return [f"{label} is not a mapping"]

    errors: list[str] = []
    disposition = str(record.get("disposition") or "")
    if disposition != required_disposition:
        errors.append(f"{label} declares disposition {disposition!r} rather than "
                      f"{required_disposition!r}")
    if not str(record.get("reason") or "").strip():
        errors.append(f"{label} records no reason")

    documents: dict[str, dict] = {}
    for name, must_parse in (("original_review", True),
                             ("unreadable_review", False),
                             ("historical_bundle", True),
                             ("active_successor_review", True),
                             ("active_successor_bundle", True),
                             ("reviewed_gup", True)):
        found, document = _pinned(root, f"{label} {name}", record.get(name),
                                  must_parse=must_parse)
        errors.extend(found)
        if document is not None:
            documents[name] = document
    if len(documents) < 6:
        return errors

    failure = record["unreadable_review"].get("parse_failure")
    if not isinstance(failure, dict):
        errors.append(f"{label} unreadable_review records no parse_failure")
    else:
        fragment = str(failure.get("message_fragment") or "")
        if not str(failure.get("diagnostic_code") or "").strip():
            errors.append(f"{label} parse_failure records no diagnostic_code")
        if not fragment:
            errors.append(f"{label} parse_failure records no message_fragment")
        elif fragment not in str(documents["unreadable_review"]["_parse_error"]):
            errors.append(
                f"{label} expects the parser to fail with {fragment!r}, but it "
                f"reports {documents['unreadable_review']['_parse_error']!r}")

    # The single link, and its bundle-level twin. Both are checked against the
    # files rather than against the record's restatement of them.
    for name, predecessor in (("active_successor_review", "unreadable_review"),
                              ("active_successor_bundle", "historical_bundle")):
        expected = str(record[predecessor].get("id") or "")
        required = str(record[name].get("required_supersedes") or "")
        if required != expected:
            errors.append(f"{label} {name} requires supersedes {required!r}, which is "
                          f"not the {predecessor} {expected!r}")
        actual = str(documents[name].get("supersedes") or "")
        if actual != expected:
            errors.append(f"{label} {name} supersedes {actual!r} rather than {expected!r}")

    block = record["active_successor_review"]
    successor = documents["active_successor_review"]

    required_leaf = str(block.get("required_disposition") or "")
    leaf = str(successor.get("overall_disposition") or successor.get("status") or "")
    if not required_leaf or leaf != required_leaf:
        errors.append(f"{label} active_successor_review requires disposition "
                      f"{required_leaf!r} and the file declares {leaf!r}")

    required_handoff = block.get("required_handoff")
    handoff = successor.get("handoff")
    if not isinstance(required_handoff, dict) or not isinstance(handoff, dict):
        errors.append(f"{label} active_successor_review has no comparable handoff")
    else:
        for key in ("next_role", "readiness"):
            wanted = str(required_handoff.get(key) or "")
            actual = str(handoff.get(key) or "")
            if not wanted or wanted != actual:
                errors.append(f"{label} active_successor_review requires handoff {key} "
                              f"{wanted!r} and the file declares {actual!r}")

    reviewed = successor.get("reviewed_gup")
    reviewed_id = str((reviewed.get("id") if isinstance(reviewed, dict) else reviewed) or "")
    expected_gup = str(record["reviewed_gup"].get("id") or "")
    if reviewed_id != expected_gup:
        errors.append(f"{label} active_successor_review reviews {reviewed_id!r}, not the "
                      f"recorded {expected_gup!r}")

    emitted = str(successor.get("approved_bundle_emitted") or "")
    expected_bundle = str(record["active_successor_bundle"].get("id") or "")
    if emitted != expected_bundle:
        errors.append(f"{label} active_successor_review emits {emitted!r}, not the "
                      f"recorded {expected_bundle!r}")

    # DEC-2026-0070 excludes the historical bundle from readiness, so what makes
    # it excludable has to be checked here: its approval must come from the
    # unreadable Review itself. A bundle approved by anything readable is an
    # ordinary bundle and stays in the ordinary buckets.
    historical = documents["historical_bundle"]
    approves = historical.get("approves") or {}
    approving = str(approves.get("review_id") or historical.get("review_id") or "")
    unreadable_id = str(record["unreadable_review"].get("id") or "")
    if approving != unreadable_id:
        errors.append(f"{label} historical_bundle is approved by {approving!r}, not by the "
                      f"unreadable {unreadable_id!r}; it is an ordinary bundle")

    errors.extend(_pinned_bytes(root, f"{label} integration_rejection",
                                record.get("integration_rejection")))

    component = record.get("edge_component")
    errors.extend(_pinned_bytes(root, f"{label} edge_component", component))
    declared_rows = None
    if isinstance(component, dict) and not _pinned_bytes(
            root, "probe", component):
        declared_rows = component.get("rows")
        actual_rows = _csv_rows(root, str(component["path"]))
        if int(declared_rows or -1) != actual_rows:
            errors.append(f"{label} edge_component declares {declared_rows} rows and the "
                          f"file carries {actual_rows}")

    # The partition is what the rejected bundle got wrong, so it is what this
    # record has to prove the successor got right.
    required_operations = record.get("required_operations")
    bundle = documents["active_successor_bundle"]
    index_block = bundle.get("operation_index")
    if not isinstance(required_operations, dict) or not isinstance(index_block, dict):
        errors.append(f"{label} has no comparable required_operations and operation_index")
    else:
        for name in ("additions", "pending_additions"):
            wanted = required_operations.get(name)
            rows = index_block.get(name) or []
            if not isinstance(wanted, dict):
                errors.append(f"{label} required_operations names no {name}")
                continue
            if int(wanted.get("count", -1)) != len(rows):
                errors.append(f"{label} required_operations {name} declares "
                              f"{wanted.get('count')} and the bundle carries {len(rows)}")
                continue
            if not rows:
                continue
            first, last = rows[0].get("csv_row"), rows[-1].get("csv_row")
            if int(wanted.get("first_csv_row", -1)) != int(first or -1) or \
                    int(wanted.get("last_csv_row", -1)) != int(last or -1):
                errors.append(
                    f"{label} required_operations {name} spans rows "
                    f"{wanted.get('first_csv_row')} to {wanted.get('last_csv_row')} and the "
                    f"bundle spans {first} to {last}")
        if int(required_operations.get("updates_count", -1)) != len(index_block.get("updates") or []):
            errors.append(f"{label} required_operations updates_count is "
                          f"{required_operations.get('updates_count')} and the bundle "
                          f"carries {len(index_block.get('updates') or [])}")
        node_operations = bundle.get("node_operations") or {}
        if int(required_operations.get("registered_node_count", -1)) != \
                int(node_operations.get("count", -1)):
            errors.append(f"{label} required_operations registered_node_count is "
                          f"{required_operations.get('registered_node_count')} and the "
                          f"bundle declares {node_operations.get('count')}")
        if declared_rows is not None:
            partitioned = sum(len(index_block.get(name) or [])
                              for name in ("additions", "pending_additions", "updates"))
            if partitioned != int(declared_rows or -1):
                errors.append(f"{label} the declared partition covers {partitioned} rows and "
                              f"the pinned component carries {declared_rows}")
    return errors


def repair_record_errors(root: Path, decision_id: str, index: int, record: Any,
                         required_disposition: str) -> list[str]:
    """Why one malformed-lineage repair record is not evidence, or [].

    The record is the claim. Re-deriving every field from the files is what makes
    it evidence, and it is what stops the exception generalising to the next
    unreadable file that happens to have a successor.
    """
    label = f"{decision_id} {LINEAGE_REPAIR_KEY}[{index}]"
    if not isinstance(record, dict):
        return [f"{label} is not a mapping"]

    errors: list[str] = []
    disposition = str(record.get("disposition") or "")
    if disposition != required_disposition:
        errors.append(f"{label} declares disposition {disposition!r} rather than "
                      f"{required_disposition!r}")
    if not str(record.get("reason") or "").strip():
        errors.append(f"{label} records no reason")

    documents: dict[str, dict] = {}
    for name, must_parse in (("original_review", True),
                             ("unreadable_review", False),
                             ("bridge_review", True),
                             ("active_successor_review", True),
                             ("reviewed_gup", True)):
        found, document = _pinned(root, f"{label} {name}", record.get(name),
                                  must_parse=must_parse)
        errors.extend(found)
        if document is not None:
            documents[name] = document
    if len(documents) < 5:
        return errors

    failure = record["unreadable_review"].get("parse_failure")
    if not isinstance(failure, dict):
        errors.append(f"{label} unreadable_review records no parse_failure")
    else:
        fragment = str(failure.get("message_fragment") or "")
        if not str(failure.get("diagnostic_code") or "").strip():
            errors.append(f"{label} parse_failure records no diagnostic_code")
        if not fragment:
            errors.append(f"{label} parse_failure records no message_fragment")
        elif fragment not in str(documents["unreadable_review"]["_parse_error"]):
            errors.append(
                f"{label} expects the parser to fail with {fragment!r}, but it "
                f"reports {documents['unreadable_review']['_parse_error']!r}")

    # Each link is stated by the record and checked against the file, never
    # against the record's own restatement of it.
    for name, predecessor in (("bridge_review", "unreadable_review"),
                              ("active_successor_review", "bridge_review")):
        expected = str(record[predecessor].get("id") or "")
        required = str(record[name].get("required_supersedes") or "")
        if required != expected:
            errors.append(f"{label} {name} requires supersedes {required!r}, which "
                          f"is not the {predecessor} {expected!r}")
        actual = str(documents[name].get("supersedes") or "")
        if actual != expected:
            errors.append(f"{label} {name} supersedes {actual!r} rather than {expected!r}")

    block = record["active_successor_review"]
    successor = documents["active_successor_review"]

    required_leaf = str(block.get("required_disposition") or "")
    leaf = str(successor.get("overall_disposition") or successor.get("status") or "")
    if not required_leaf or leaf != required_leaf:
        errors.append(f"{label} active_successor_review requires disposition "
                      f"{required_leaf!r} and the file declares {leaf!r}")

    required_handoff = block.get("required_handoff")
    handoff = successor.get("handoff")
    if not isinstance(required_handoff, dict) or not isinstance(handoff, dict):
        errors.append(f"{label} active_successor_review has no comparable handoff")
    else:
        for key in ("next_role", "readiness"):
            wanted = str(required_handoff.get(key) or "")
            actual = str(handoff.get(key) or "")
            if not wanted or wanted != actual:
                errors.append(f"{label} active_successor_review requires handoff "
                              f"{key} {wanted!r} and the file declares {actual!r}")

    reviewed = successor.get("reviewed_gup")
    reviewed_id = str((reviewed.get("id") if isinstance(reviewed, dict) else reviewed) or "")
    expected_gup = str(record["reviewed_gup"].get("id") or "")
    if reviewed_id != expected_gup:
        errors.append(f"{label} active_successor_review reviews {reviewed_id!r}, not "
                      f"the recorded {expected_gup!r}")

    # The compiler's inputs are exactly the original and the active successor. A
    # record naming the unreadable file or the bridge as an input would be asking
    # a downstream role to read what this record says cannot be read.
    inputs = record.get("exact_builder_review_inputs")
    if not isinstance(inputs, list) or len(inputs) != 2:
        errors.append(f"{label} does not record exactly two exact_builder_review_inputs")
    else:
        expected_inputs = [record["original_review"], record["active_successor_review"]]
        for position, (entry, expected) in enumerate(zip(inputs, expected_inputs)):
            found, _ = _pinned(root, f"{label} exact_builder_review_inputs[{position}]",
                               entry, must_parse=True)
            errors.extend(found)
            if not isinstance(entry, dict):
                continue
            for key in ("id", "path", "checksum"):
                if str(entry.get(key) or "") != str(expected.get(key) or ""):
                    errors.append(
                        f"{label} exact_builder_review_inputs[{position}] {key} "
                        f"{entry.get(key)!r} does not match the recorded "
                        f"{expected.get(key)!r}")
    return errors


def load_admission(root: Path, ruleset_id: str) -> Admission:
    """Resolve which unreadable Reviews queue traversal may omit.

    Called before any Review directory is walked. An empty `permitted` is the
    safe default: with no governing Decision every parse failure is fatal, which
    is what DEC-2026-0065 requires of an absent or inactive authority.

    Two delegation forms exist, each fixed. DEC-2026-0065 delegates to
    DEC-2026-0064's two-hop bridge record; DEC-2026-0069 delegates to
    DEC-2026-0068's one-step direct-predecessor record. A Decision carrying
    neither block is ignored, and neither form may name a field of its own
    choosing or point at itself.
    """
    admission = Admission()
    root = Path(root).resolve()
    decisions = _decision_documents(root, ruleset_id)
    active = _active_ids(decisions)

    for decision_id in sorted(active):
        _, document = decisions[decision_id]
        for block_key, record_key in DELEGATIONS.items():
            governing = document.get(block_key)
            if not isinstance(governing, dict):
                continue

            label = f"{decision_id} {block_key}"
            pinned = governing.get("decision_input")
            errors, _ = _pinned(root, f"{label} decision_input", pinned, must_parse=True)
            if errors:
                admission.fatal.append({
                    "code": FATAL_CODE, "severity": "error",
                    "path": str(root / str((pinned or {}).get("path") or "")),
                    "detail": "; ".join(errors) + ". No unreadable Review is admitted.",
                })
                continue

            governed_id = str(pinned["id"])
            # DEC-2026-0069: a Decision may not be its own authority. The pin is
            # a checksum of the governing file, which a file cannot contain for
            # itself, so this can only be reached by a record that is lying.
            if governed_id == decision_id:
                admission.fatal.append({
                    "code": FATAL_CODE, "severity": "error",
                    "path": str(root / str(pinned.get("path") or "")),
                    "detail": (f"{label} delegates to itself. A Decision cannot be its own "
                               "governing authority. No unreadable Review is admitted."),
                })
                continue

            if governed_id not in active:
                admission.fatal.append({
                    "code": FATAL_CODE, "severity": "error",
                    "path": str(root / str(pinned.get("path") or "")),
                    "detail": (f"{label} names {governed_id}, which is not an active "
                               "approved Decision. No unreadable Review is admitted."),
                })
                continue

            # The field name is fixed per form, not read from the Decision.
            # Honouring a declared field would let a delegation nominate any list
            # in any Decision as a repair record.
            declared_field = str(governing.get("field") or record_key)
            if declared_field != record_key:
                admission.fatal.append({
                    "code": FATAL_CODE, "severity": "error",
                    "path": str(root / str(pinned.get("path") or "")),
                    "detail": (f"{label} names field {declared_field!r}; this form admits "
                               f"only {record_key!r}. No unreadable Review is admitted."),
                })
                continue

            governed = decisions[governed_id][1]
            records = governed.get(record_key)
            index = governing.get("record_index")
            if not isinstance(records, list) or not isinstance(index, int) \
                    or not 0 <= index < len(records):
                admission.fatal.append({
                    "code": FATAL_CODE, "severity": "error",
                    "path": str(root / str(pinned.get("path") or "")),
                    "detail": (f"{label} names {record_key}[{index!r}] of {governed_id}, "
                               "which it does not carry. No unreadable Review is admitted."),
                })
                continue

            record = records[index]
            required = str(governing.get("required_disposition") or "")
            validate = (repair_record_errors if record_key == LINEAGE_REPAIR_KEY
                        else direct_predecessor_record_errors)
            problems = validate(root, governed_id, index, record, required)

            unreadable = record.get("unreadable_review") if isinstance(record, dict) else None
            target = root / str((unreadable or {}).get("path") or "")
            if problems:
                admission.fatal.append({
                    "code": FATAL_CODE, "severity": "error",
                    "path": str(target),
                    "detail": "; ".join(problems) + ". The named Review keeps its ordinary "
                              "parse failure and no bundle is offered as ready.",
                })
                continue

            admission.permitted[str(target.resolve())] = governed_id

            # Only the direct-predecessor form names a historical bundle, and
            # only a fully validated record may exclude one.
            historical = record.get("historical_bundle") if isinstance(record, dict) else None
            if record_key == DIRECT_PREDECESSOR_KEY and isinstance(historical, dict):
                manifest = (root / str(historical.get("path") or "")).resolve()
                admission.historical_bundles[str(manifest)] = governed_id
    return admission
