"""
Source Entity Manifest Gate.

Enforces pre-extraction source inventory completeness (SD-015, UNIV-SRC-11, spec:UNIV-COV-05).
Prevents publication if any declared defined entity is omitted from packet output.
"""

from typing import Dict, List, Set, Any, Optional


class ManifestGateError(Exception):
    def __init__(self, message: str, missing_entities: List[str], source_span: Optional[str] = None):
        super().__init__(message)
        self.missing_entities = missing_entities
        self.source_span = source_span


class SourceEntityManifestGate:
    """Validates extracted packet entities against a pre-extraction source manifest."""

    def __init__(self, manifest_data: Optional[Dict[str, Any]] = None):
        self.manifest_data = manifest_data or {}

    def validate_packet_entities(
        self,
        extracted_node_ids: Set[str],
        manifest: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Validates that all required entities in the manifest are present in extracted_node_ids.
        Raises ManifestGateError if any required entity is omitted.
        """
        active_manifest = manifest or self.manifest_data
        required_entities = active_manifest.get("required_entities", [])
        source_span = active_manifest.get("source_span", "unknown")

        missing = []
        for entity in required_entities:
            entity_id = entity if isinstance(entity, str) else entity.get("id")
            if entity_id not in extracted_node_ids:
                missing.append(entity_id)

        if missing:
            raise ManifestGateError(
                f"Completeness gate failure: {len(missing)} required entity(ies) omitted from packet: {', '.join(missing)}. "
                f"Source span: {source_span}",
                missing_entities=missing,
                source_span=source_span,
            )

        return True


def verify_packet_manifest_completeness(
    packet_id: str,
    expected_ids: List[str],
    extracted_ids: List[str],
    source_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Helper to check completeness without necessarily throwing an exception."""
    gate = SourceEntityManifestGate({
        "packet_id": packet_id,
        "required_entities": expected_ids,
        "source_span": source_file or "unknown",
    })
    try:
        gate.validate_packet_entities(set(extracted_ids))
        return {
            "valid": True,
            "packet_id": packet_id,
            "missing_ids": [],
            "source_file": source_file,
        }
    except ManifestGateError as e:
        return {
            "valid": False,
            "packet_id": packet_id,
            "missing_ids": e.missing_entities,
            "source_file": e.source_span,
        }
