"""Integrator tooling for the AD&D 1e mechanical relationship graph.

Owned by the Integrator role (`agents/integrator/INSTRUCTIONS.md`). This package
is the only sanctioned writer of `rulesets/<ruleset-id>/canonical/`
(invariant 30).

Design rules, taken from the role instructions:

- Integration is transactional. Canonical state is snapshotted before any write
  and restored completely if any step fails. There is no partial mutation.
- Derived artifacts are never edited. `graph.json`, node degrees and node roles
  are recomputed from `edges_master.csv` on every run.
- Nothing depends on conversation history. Every input is a repository artifact
  addressed by ID and pinned by checksum.
- Identical inputs produce byte-identical canonical outputs.
"""

__version__ = "1.0.0"

TOOL_NAME = "adnd1e-integrator"
