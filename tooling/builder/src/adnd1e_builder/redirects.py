"""
Identity Redirect Resolver.

Handles entity identity redirects (SD-002, spec:SD-SPL-03).
Resolves renamed or corrected identifiers to their canonical successors.
"""

from typing import Dict, Optional, Any
import os
import yaml


class IdentityRedirectResolver:
    """Resolves node IDs through registered redirects."""

    def __init__(self, redirects_path: Optional[str] = None):
        self.redirects: Dict[str, str] = {}
        if redirects_path and os.path.exists(redirects_path):
            self.load_from_yaml(redirects_path)

    def load_from_yaml(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for entry in data.get("redirects", []):
            from_id = entry.get("from_id")
            to_id = entry.get("to_id")
            if from_id and to_id:
                self.redirects[from_id] = to_id

    def resolve(self, node_id: str) -> str:
        """Returns the canonical node_id following redirects, or the original node_id if no redirect exists."""
        current = node_id
        visited = set()
        while current in self.redirects:
            if current in visited:
                raise ValueError(f"Circular redirect detected at node_id: {current}")
            visited.add(current)
            current = self.redirects[current]
        return current


IdentityRedirectRegistry = IdentityRedirectResolver
