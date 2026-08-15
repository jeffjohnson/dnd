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

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .checksums import checksum_file


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
        """WORK_QUEUES 1.8 `decision_migration_v1`: the plan is a GUP YAML.

        This bundle shape carries no edge CSV at all -- an edge CSV cannot
        encode registry identity replacement, retirement, or exact deletion --
        so the operation plan is read from the checksummed GUP component.
        """
        return (self.manifest or {}).get("operation_model") == "decision_migration_v1"

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
        edges_path = edge_files.get(stem)

        if edges_path is None:
            # WORK_QUEUES 1.8 rule 31: a decision_migration_v1 manifest is a
            # complete job with no edge CSV. Rule 32 keeps every other manifest
            # missing its CSV a diagnostic, so the exemption is read from the
            # declared operation model rather than from the file simply being
            # absent.
            declared = load_yaml(manifest_path) if manifest_path is not None else None
            if not declared or declared.get("operation_model") != "decision_migration_v1":
                diagnostics.append(f"{stem}: manifest present with no .edges.csv component")
                continue

        if manifest_path is not None:
            bundle = _from_manifest(stem, book_id, manifest_path, edges_path, reviews, diagnostics)
            if bundle is not None and bundle.is_direct_migration and edges_path is not None:
                # Rule 33: an edge CSV in this shape means the manifest and the
                # reviewed GUP disagree about what the plan is.
                diagnostics.append(
                    f"{stem}: decision_migration_v1 manifest carries a forbidden edge CSV")
                continue
        else:
            bundle = _from_legacy(stem, book_id, edges_path, reviews, diagnostics)
        if bundle is not None:
            bundles.append(bundle)

    return bundles, diagnostics


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
    consumed = integrated_bundle_ids(root, ruleset_id)
    ready, done, superseded, diagnostics = [], [], [], []
    for book_id in book_ids:
        found, book_diagnostics = discover(root, ruleset_id, book_id)
        diagnostics.extend(book_diagnostics)
        retired = superseded_gup_ids(root, ruleset_id, book_id)
        for bundle in found:
            if bundle.bundle_id in consumed:
                done.append((bundle, consumed[bundle.bundle_id]))
            elif bundle.gup_id in retired:
                superseded.append(bundle)
            else:
                ready.append(bundle)
    return {"ready": ready, "integrated": done, "superseded": superseded,
            "diagnostics": diagnostics}
