# Legacy Import

This directory preserves the exact pre-ruleset repository dump.

- `original/edges_master.csv` contains 3,851 rows spanning PHB, DMG, MM, and UA.
- `original/addnd_graph.json` contains 3,613 edges and is stale by 238 rows.
- Both use the legacy 13-field schema rather than Constitution v1.2's production schema.

Do not edit these files. Builder must create a migration plan and deterministic transformed artifacts. Reviewer must review non-deterministic mappings. Integrator establishes canonical state only after validation and approval.

The `by-book/` CSV files are generated convenience partitions of the original CSV, not canonical data.
