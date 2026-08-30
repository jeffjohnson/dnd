"""Approved-bundle discovery and Integrator queue state.

`contracts/WORK_QUEUES.md`: an Integrator job is one Approved bundle whose
approving Review is complete and whose bundle ID is not named by any Integration
manifest. Components never count as separate jobs, and consumption is recorded in
the Integration manifest -- never by moving or rewriting the published bundle.

Bundles published before WORK_QUEUES 1.0 have no manifest YAML. Legacy rule 6
groups those by filename stem and approving Review, which is exactly the case
DEC-2026-0012 flagged in its snapshot. Such a bundle is admissible, but every
inference made to reconstruct it is reported.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .admission import Admission, load_admission
from .checksums import checksum_file


#: Operation models whose Approved bundle is a manifest plus a GUP plan, with no
#: edge CSV. WORK_QUEUES rule 31 names both.
DIRECT_MIGRATION_MODELS = ("decision_migration_v1", "decision_migration_v2",
                           "decision_migration_v3")


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


@dataclass
class Bundle:
    bundle_id: str
    book_id: str
    manifest_path: Path | None
    edges_path: Path | None
    review_id: str
    review_path: Path
    gup_id: str
    gur_id: str | None
    packet_id: str
    constitution_version: str
    manifest: dict = field(default_factory=dict)
    review: dict = field(default_factory=dict)
    legacy_inferences: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    @property
    def is_legacy(self) -> bool:
        return self.manifest_path is None

    @property
    def is_direct_migration(self) -> bool:
        """A direct decision-migration bundle: the plan is a checksummed GUP YAML.

        Both narrow models take this shape and carry no edge CSV at all -- a CSV
        cannot encode registry identity replacement, retirement, exact deletion
        (v1, WORK_QUEUES 1.8) or a bounded many-to-one merge (v2, 1.9) -- so the
        operation plan is read from the GUP component instead.
        """
        return (self.manifest or {}).get("operation_model") in DIRECT_MIGRATION_MODELS

    def component_records(self, root: Path) -> list[dict]:
        records = [] if self.edges_path is None else [{
            "kind": "edges",
            "path": self.edges_path.relative_to(root).as_posix(),
            "checksum": checksum_file(self.edges_path),
        }]
        if self.manifest_path is not None:
            records.insert(0, {
                "kind": "manifest",
                "path": self.manifest_path.relative_to(root).as_posix(),
                "checksum": checksum_file(self.manifest_path),
            })
        return records


def _reviews_by_id(review_dir: Path) -> dict[str, Path]:
    found = {}
    if not review_dir.exists():
        return found
    for path in sorted(review_dir.glob("REV-*.yaml")):
        found[path.stem] = path
    return found


def discover(root: Path, ruleset_id: str, book_id: str) -> tuple[list[Bundle], list[str]]:
    """Return every Approved bundle in a book, plus discovery-level diagnostics."""
    approved_dir = root / "books" / ruleset_id / book_id / "artifacts" / "approved"
    review_dir = root / "books" / ruleset_id / book_id / "artifacts" / "reviews"
    reviews = _reviews_by_id(review_dir)
    diagnostics: list[str] = []
    bundles: list[Bundle] = []

    manifests = {p.stem: p for p in sorted(approved_dir.glob("APPROVED-*.yaml"))}
    edge_files = {p.name[: -len(".edges.csv")]: p
                  for p in sorted(approved_dir.glob("APPROVED-*.edges.csv"))}

    for stem in sorted(set(manifests) | set(edge_files)):
        manifest_path = manifests.get(stem)

        if manifest_path is None:
            # WORK_QUEUES 1.25 keeps filename inference for manifestless legacy
            # bundles alone: there is no declaration to be authoritative, so the
            # stem is the only thing left to go on.
            bundle = _from_legacy(stem, book_id, edge_files[stem], reviews, diagnostics)
            if bundle is not None:
                bundles.append(bundle)
            continue

        declared = load_yaml(manifest_path) or {}
        if declared.get("operation_model") in DIRECT_MIGRATION_MODELS:
            # Rule 31: a direct migration is a complete job with no edge CSV, and
            # rule 33 makes a colocated one evidence that the manifest and the
            # reviewed plan disagree. Both are read from the declared model.
            if stem in edge_files:
                diagnostics.append(
                    f"{stem}: decision_migration_v1 manifest carries a forbidden edge CSV")
                continue
            edges_path = None
        else:
            edges_path = declared_edges_component(root, stem, declared, diagnostics)
            if edges_path is None:
                continue

        bundle = _from_manifest(stem, book_id, manifest_path, edges_path, reviews, diagnostics)
        if bundle is not None:
            bundles.append(bundle)

    return bundles, diagnostics


def declared_edges_component(root: Path, stem: str, manifest: dict,
                             diagnostics: list[str]) -> Path | None:
    """The edge CSV a manifested bundle declares, or None with a diagnostic.

    WORK_QUEUES 1.25: for a manifested Approved bundle the manifest is the
    authority for its own components. Locating a different file by filename stem
    lets a derived convention override the artifact's explicit provenance, and
    the two only agreed while every bundle happened to ship its own CSV. The
    Bards r03 bundle deliberately re-packages the r01 component, which is the
    case that separates them.

    The checksum is verified here rather than deferred to verification, because
    a bundle whose declared component does not match its declared hash must not
    reach the queue as ready at all.
    """
    components = manifest.get("components")
    if not isinstance(components, list):
        diagnostics.append(f"{stem}: manifest declares no components list")
        return None

    edges = [c for c in components if isinstance(c, dict) and c.get("kind") == "edges"]
    if len(edges) != 1:
        diagnostics.append(
            f"{stem}: manifest declares {len(edges)} components of kind 'edges'; "
            "a packet update declares exactly one")
        return None

    relative = str(edges[0].get("path") or "")
    if not relative:
        diagnostics.append(f"{stem}: declared edges component names no path")
        return None

    root = Path(root).resolve()
    target = (root / relative).resolve()
    # A declared path is repository-relative. One that escapes the root would
    # make the queue depend on files no other role can see or check.
    if not target.is_relative_to(root):
        diagnostics.append(
            f"{stem}: declared edges component {relative!r} resolves outside the repository")
        return None
    if not target.is_file():
        diagnostics.append(
            f"{stem}: declared edges component {relative!r} does not exist")
        return None

    declared = str(edges[0].get("checksum") or "")
    actual = checksum_file(target)
    if declared != actual:
        diagnostics.append(
            f"{stem}: declared edges component {relative!r} records {declared or 'no checksum'} "
            f"but hashes to {actual}")
        return None
    return target


def _from_manifest(stem, book_id, manifest_path, edges_path, reviews, diagnostics) -> Bundle | None:
    manifest = load_yaml(manifest_path)
    if manifest.get("id") != stem:
        diagnostics.append(
            f"{stem}: manifest id {manifest.get('id')!r} does not equal its filename stem")
    approves = manifest.get("approves") or {}
    review_id = approves.get("review_id") or manifest.get("review_id")
    if review_id not in reviews:
        diagnostics.append(f"{stem}: approving Review {review_id!r} not found on disk")
        return None
    return Bundle(
        bundle_id=manifest.get("id", stem),
        book_id=book_id,
        manifest_path=manifest_path,
        edges_path=edges_path,
        review_id=review_id,
        review_path=reviews[review_id],
        gup_id=approves.get("gup_id", ""),
        gur_id=approves.get("gur_id"),
        packet_id=manifest.get("packet_id", ""),
        constitution_version=str(manifest.get("constitution_version", "")),
        manifest=manifest,
    )


def _from_legacy(stem, book_id, edges_path, reviews, diagnostics) -> Bundle | None:
    """WORK_QUEUES legacy rule 6: group by filename stem and approving Review."""
    # APPROVED-<gup-id>-rNN  ->  REV-<gup-id>-rNN
    if not stem.startswith("APPROVED-"):
        diagnostics.append(f"{stem}: not an Approved bundle name")
        return None
    review_id = "REV-" + stem[len("APPROVED-"):]
    if review_id not in reviews:
        diagnostics.append(
            f"{stem}: legacy bundle has no manifest and its approving Review "
            f"{review_id!r} cannot be identified")
        return None

    review = load_yaml(reviews[review_id])
    reviewed = review.get("reviewed_gup") or {}
    return Bundle(
        bundle_id=stem,
        book_id=book_id,
        manifest_path=None,
        edges_path=edges_path,
        review_id=review_id,
        review_path=reviews[review_id],
        gup_id=reviewed.get("id", ""),
        gur_id=((review.get("input_provenance") or {}).get("gur") or {}).get("id"),
        packet_id=review.get("packet_id", ""),
        constitution_version=str(review.get("constitution_version", "")),
        review=review,
        legacy_inferences=[
            "no Approved manifest exists; bundle reconstructed from its filename stem "
            "and approving Review under WORK_QUEUES legacy rule 6",
            f"bundle ID inferred from the edge CSV filename stem: {stem}",
            f"approving Review inferred by name substitution: {review_id}",
        ],
    )


def integrated_bundle_ids(root: Path, ruleset_id: str) -> dict[str, str]:
    """Bundle IDs already consumed, mapped to the integration that consumed them.

    Consumption is read from Integration manifests only. A bundle is never
    modified or moved to record that it was integrated.
    """
    consumed: dict[str, str] = {}
    manifests_dir = root / "rulesets" / ruleset_id / "manifests"
    if not manifests_dir.exists():
        return consumed
    for path in sorted(manifests_dir.glob("INT-*.json")):
        import json

        record = json.loads(path.read_text(encoding="utf-8"))
        for entry in record.get("approved_bundles", []):
            consumed[entry["bundle_id"]] = record.get("integration_id", path.stem)
    return consumed


def superseded_gup_ids(root: Path, ruleset_id: str, book_id: str) -> set[str]:
    """GUP ids that a later revision supersedes, per that book's GUP directory."""
    gup_dir = root / "books" / ruleset_id / book_id / "artifacts" / "gup"
    if not gup_dir.exists():
        return set()
    superseded = set()
    for path in sorted(gup_dir.glob("GUP-*.yaml")):
        data = load_yaml(path) or {}
        if data.get("supersedes"):
            superseded.add(str(data["supersedes"]))
    return superseded


def superseded_bundle_ids(root: Path, ruleset_id: str, book_id: str) -> set[str]:
    """Approved bundle ids that a later bundle names in `supersedes`.

    WORK_QUEUES 3 and 4 make leaf-ness a property of the artifact kind itself,
    not only of the GUP it packages. A repackaging successor keeps the same GUP
    and may keep an approved Review lineage leaf, so neither
    `superseded_gup_ids` nor `withdrawn_review_ids` retires its predecessor --
    the bards r03/r04 pair is exactly that shape, and both were offered as ready
    until this read the bundles' own declaration.
    """
    approved_dir = root / "books" / ruleset_id / book_id / "artifacts" / "approved"
    if not approved_dir.exists():
        return set()
    superseded = set()
    for path in sorted(approved_dir.glob("APPROVED-*.yaml")):
        data = load_yaml(path) or {}
        if data.get("supersedes"):
            superseded.add(str(data["supersedes"]))
    return superseded


def withdrawn_review_ids(root: Path, ruleset_id: str, book_id: str,
                         admission: Admission | None = None) -> set[str]:
    """Review ids whose lineage leaf is not approved.

    An Approved bundle pins one exact Review, and only the active leaf of that
    Review's lineage says anything current (WORK_QUEUES 3 and 6). Supersession
    alone is not withdrawal: a lineage routinely goes approved -> revision_required
    -> approved again, and the re-approving leaf may endorse the very bundle the
    middle revision questioned -- which is exactly what
    REV-GUP-PKT-PHB-110-117-psionics-r06-r05 does. Treating any superseded Review
    as stale would strand such a bundle permanently.

    What must never happen is integrating on an approval the lineage has since
    withdrawn, so the test is the leaf's disposition, not its existence.
    """
    review_dir = root / "books" / ruleset_id / book_id / "artifacts" / "reviews"
    if not review_dir.exists():
        return set()

    documents, successor = {}, {}
    for path in sorted(review_dir.glob("REV-*.yaml")):
        # DEC-2026-0065: an unreadable Review is admitted only where an active
        # approved Decision pins it as historical evidence, and even then only
        # its bytes are omitted -- no content is recovered. Anything else is a
        # fatal queue-integrity diagnostic, because a Review this walk cannot
        # read may be the one that withdraws a bundle it is about to call ready.
        try:
            data = load_yaml(path) or {}
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            if admission is None:
                raise
            authority = admission.permits(path)
            if authority is None:
                admission.note_fatal(
                    path, f"{path.name} is not parseable YAML and no active approved "
                          f"Decision admits it as historical evidence: {exc}")
            else:
                admission.note_historical(path, authority)
            continue
        review_id = str(data.get("id") or path.stem)
        documents[review_id] = data
        if data.get("supersedes"):
            successor[str(data["supersedes"])] = review_id

    withdrawn = set()
    for review_id in documents:
        seen, leaf = {review_id}, review_id
        while leaf in successor and successor[leaf] not in seen:
            leaf = successor[leaf]
            seen.add(leaf)
        status = str((documents.get(leaf) or {}).get("status") or "").strip()
        if status != "approved":
            withdrawn.add(review_id)
    return withdrawn


#: DEC-2026-0043 authorizes one already-published record by exact ID pair; every
#: other record must pin the bundle, its Review and its GUP.
LEGACY_AUTHORIZED_REJECTIONS = {
    ("INT-20260815-002",
     "APPROVED-GUP-PKT-PHB-094-100-illusionist-spells-r04-r01"),
}


def rejected_bundle_ids(root: Path, ruleset_id: str) -> dict[str, str]:
    """Bundle IDs a current, valid Integration rejection withdraws from the queue.

    DEC-2026-0043 makes a rejection a first-class queue signal: it suppresses the
    bundle's Integrator item and routes remediation to the Reviewer instead. A
    record that cannot be trusted suppresses nothing -- otherwise a stale record
    would keep a re-issued bundle unqueued *and* unrejected, which is the exact
    failure this rule exists to end. So each entry must pin the bundle, the
    Review that approved it and the GUP it carries, to the bytes on disk.
    """
    directory = root / "rulesets" / ruleset_id / "reports"
    if not directory.exists():
        return {}

    approved = root / "books" / ruleset_id
    def artifact(artifact_id: str) -> Path | None:
        for pattern in (f"*/artifacts/approved/{artifact_id}.yaml",
                        f"*/artifacts/reviews/{artifact_id}.yaml",
                        f"*/artifacts/gup/{artifact_id}.yaml"):
            for found in approved.glob(pattern):
                return found
        return None

    documents = []
    for path in sorted(directory.glob("*.rejected.json")):
        try:
            documents.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue

    # A rejection can be wrong. Without honouring `supersedes` an over-broad
    # record would suppress its bundles forever, because the only way to correct
    # one is to publish a successor -- editing a published record is prohibited.
    # A superseded record stays on disk as immutable history; it just stops
    # deriving queue state.
    retired = {str(d.get("supersedes")).strip()
               for d in documents
               if str(d.get("status") or "").strip() == "rejected" and d.get("supersedes")}

    suppressed: dict[str, str] = {}
    for document in documents:
        if str(document.get("status") or "").strip() != "rejected":
            continue
        if str(document.get("id") or "").strip() in retired:
            continue
        record_id = str(document.get("id") or "")
        for entry in document.get("rejected_bundles") or []:
            bundle_id = str(entry.get("bundle_id") or "").strip()
            if not bundle_id or not (entry.get("blocking_failures") or []):
                continue
            if (record_id, bundle_id) not in LEGACY_AUTHORIZED_REJECTIONS:
                pinned = True
                for id_field, sum_field in (("bundle_id", "bundle_checksum"),
                                            ("review_id", "review_checksum"),
                                            ("gup_id", "gup_checksum")):
                    declared_id = str(entry.get(id_field) or "").strip()
                    declared_sum = str(entry.get(sum_field) or "").strip()
                    target = artifact(declared_id) if declared_id else None
                    if target is None or checksum_file(target) != declared_sum:
                        pinned = False
                        break
                if not pinned:
                    continue
            suppressed[bundle_id] = record_id
    return suppressed


def ready_queue(root: Path, ruleset_id: str, book_ids: list[str]) -> dict:
    """The Integrator queue: ready bundles, already-integrated bundles, diagnostics.

    WORK_QUEUES 3 and 6: only the active leaf creates work. A bundle inherits
    that from the GUP it packages, so a bundle whose GUP a later revision
    supersedes is history, not a job -- the same rule the common queue scanner
    applies.

    Without this, "not yet integrated" was read as "ready", and a superseded
    bundle stayed in the batch permanently. Its preconditions can never be
    satisfied once its successor ships, so a single retired bundle with drifted
    provenance would block every future integration of the whole ruleset.
    """
    # DEC-2026-0065: admission is resolved before any Review directory is walked,
    # so the queue knows which unreadable bytes an active Decision pins before it
    # meets one. With no such Decision `permitted` is empty and every parse
    # failure below is fatal, which is the required fail-closed default.
    admission = load_admission(root, ruleset_id)

    consumed = integrated_bundle_ids(root, ruleset_id)
    rejected = rejected_bundle_ids(root, ruleset_id)
    ready, done, superseded, refused, diagnostics = [], [], [], [], []
    for book_id in book_ids:
        found, book_diagnostics = discover(root, ruleset_id, book_id)
        diagnostics.extend(book_diagnostics)
        retired = superseded_gup_ids(root, ruleset_id, book_id)
        repackaged = superseded_bundle_ids(root, ruleset_id, book_id)
        stale_reviews = withdrawn_review_ids(root, ruleset_id, book_id, admission)
        for bundle in found:
            # DEC-2026-0070: a validated direct-predecessor record names exactly
            # one historical bundle. It is withheld from every bucket, not just
            # from ready: its approving Review is the unreadable file, so there
            # is no readable approval to classify it against, and letting it fall
            # through to "not integrated, not rejected" would offer it as ready.
            authority = (bundle.manifest_path is not None
                         and admission.excludes_bundle(bundle.manifest_path))
            if authority:
                admission.note_historical_bundle(
                    bundle.bundle_id, bundle.manifest_path, authority)
                continue
            if bundle.bundle_id in consumed:
                done.append((bundle, consumed[bundle.bundle_id]))
            elif bundle.bundle_id in rejected:
                # A refusal outranks both history buckets. A rejected bundle
                # usually *does* acquire a successor Review -- that is the
                # remediation -- so classifying supersession first would hide the
                # one signal the Reviewer still has to act on.
                refused.append((bundle, rejected[bundle.bundle_id]))
            elif bundle.bundle_id in repackaged:
                # A repackaging successor shares its predecessor's GUP and may
                # leave its Review lineage approved, so this is the only signal
                # that the earlier bundle is history.
                superseded.append(bundle)
            elif bundle.gup_id in retired:
                superseded.append(bundle)
            elif bundle.review_id in stale_reviews:
                superseded.append(bundle)
            else:
                ready.append(bundle)

    # A fatal queue-integrity failure means no reported bundle is trustworthy,
    # not that this particular one is bad. DEC-2026-0065: return no ready bundles
    # and let the caller refuse the transaction. History buckets stay visible so
    # the failure is diagnosable without a second, unguarded run.
    if admission.fails_closed:
        ready = []
    return {"ready": ready, "integrated": done, "superseded": superseded,
            "rejected": refused, "diagnostics": diagnostics,
            "queue_integrity": admission.fatal,
            "informational": admission.informational}
