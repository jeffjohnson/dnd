# Shadowdark Rules Graph Remediation: Release v1.1 Notes

**Release ID:** `INT-20261104-REL`  
**Version:** `v1.1-remediation-release`  
**Date:** 2026-11-04  
**Role:** Architect  
**Governing Authority:** [`DEC-2026-0109.yaml`](../../rulesets/shadowdark/escalations/decisions/DEC-2026-0109.yaml)  
**Execution Plan:** [`AGY_REMEDIATION_EXECUTION_PLAN.md`](../AGY_REMEDIATION_EXECUTION_PLAN.md)  
**Baseline Snapshot:** `build/snapshots/INT-20261104-BASE/`  
**Release Snapshot:** `build/snapshots/INT-20261104-REL/`  
**Release Manifest:** [`remediation_release_snapshot.yaml`](../../rulesets/shadowdark/reports/remediation_release_snapshot.yaml)

---

## 1. Executive Summary

The **November 4 Shadowdark Rules Graph Remediation** program has formally concluded. All structural defects, extraction omissions, layout corruptions, and taxonomic classification gaps identified in the audit have been repaired, migrated into canonical artifacts, and independently certified by subagent audits across all four repository roles (**Builder**, **Reviewer**, **Analyst**, and **Integrator**).

The Shadowdark rules graph now stands at **zero classification gaps** across all four authorized books (`sd`, `cs1`, `cs2`, `cs3`).

---

## 2. Key Metrics & Progression

| Metric | Baseline (`INT-20261104-BASE`) | Remediated Release (`INT-20261104-REL`) | Net Delta |
|---|---:|---:|:---:|
| **Canonical Nodes** | 732 | **737** | +5 nodes |
| **Canonical Edges** | 1,498 | **1,801** | +303 edges |
| - Core Status Edges | 1,189 | **1,359** | +170 edges |
| - Optional Status Edges | 309 | **442** | +133 edges |
| **Total Classification Gaps** | **240** | **0** | **-240 (100% resolved)** |
| - Weapon Taxonomy Gaps | 26 | **0** | -26 (100% resolved) |
| - Item Taxonomy Gaps | 122 | **0** | -122 (100% resolved) |
| - Core Spell Gaps | 36 | **0** | -36 (100% resolved) |
| - Supplement Spell Gaps | 56 | **0** | -56 (100% resolved) |
| **Raw-ID Labels (`SD-012`)** | 23 | **0** | 100% normalized |
| **Overrides Missing General Rule (`SD-013`)** | 5 | **0** | 100% populated |
| **Dangling Endpoints** | 0 | **0** | 0 dangling |
| **Degree Discrepancies** | N/A | **0** | Fully derived & consistent |

---

## 3. Scope of Remediation Batches

### Phase 3: P0 Core Spell & Identity Repairs
- **SD-001 (Missing Core Spells):** Restored `spell_alarm`, `spell_bless`, `spell_fixed_object`, and `spell_fabricate` with explicit class and tier memberships.
- **SD-002 (Control Water Identity):** Corrected legacy typo `spell_control_weather` to canonical `spell_control_water` with Priest & Wizard Tier 4 links; established durable backward-compatible pointer in [`identity_redirects.yaml`](../../rulesets/shadowdark/registries/identity_redirects.yaml).
- **SD-003, SD-004, SD-005, SD-006 (SD p.70 Layout Shift):** Corrected cyclic two-column extraction shift:
  - `spell_sending`: Wizard Tier 3 (SD p.70)
  - `spell_shapechange`: Wizard Tier 5 (SD p.70)
  - `spell_shield_of_faith`: Priest Tier 1 (SD p.70)
  - `spell_scrying`: Preserved Wizard Tier 5 (SD p.70)

### Phase 4: Batch 4A — Equipment & Weapon Taxonomy
- **SD-008, SD-007, SD-ITEM-05, SD-ITEM-06:**
  - Established `item_weapon` category hub.
  - Linked all 26 canonical weapons (15 from SD p.37, 9 from CS2 p.17, 2 from CS3 p.20) to `item_weapon`.
  - Linked mundane armors and shields (`item_leather_armor`, `item_chainmail`, `item_plate_mail`, `item_shield`, `item_round_shield`) and 10 magic armors/shields to `item_armor`.
  - Linked mundane gear, commodities, and tavern provisions to `item_gear`.
  - Linked all 69 potions, wands, scrolls, rings, and wondrous items to `item_magic_item`.
  - Resolved all 148 item and weapon gaps.

### Phase 4: Batch 4B — Cursed Scroll Supplement Spells
- **Supplement Spell Taxonomy:**
  - Linked all 36 Witch spells from *Cursed Scroll Vol. 1* (CS1 pp. 26–38) via `CLASSIFIED_AS` to `class_witch`.
  - Linked all 20 Seer spells from *Cursed Scroll Vol. 3* (CS3 pp. 31–35) via `CLASSIFIED_AS` to `class_seer`.
  - Resolved all remaining 56 supplement spell gaps.

### Quality Cleanups:
- **SD-012 (Label Normalization):** Normalized all 23 raw-ID nodes (`lang_diabolic` $\rightarrow$ *"Diabolic"*, `monster_archangel` $\rightarrow$ *"Archangel"*, etc.).
- **SD-013 (Claim-Addressable Overrides):** Populated `general_rule_id` matching `target_id` across all 5 `OVERRIDES` edges.

---

## 4. Universal Pipeline Tooling Delivered

To ensure future ruleset ingestions (e.g., Basic D&D Rules Cyclopedia `basicdnd/rc` and D&D 5e 2024 `xphb`) do not replicate these failures:
1. **Source Entity Manifest Gate** ([`manifest_gate.py`](../../../tooling/builder/src/adnd1e_builder/manifest_gate.py)): Enforces pre-extraction source inventory completeness, blocking publishing if any declared entity is omitted.
2. **Identity Redirect Resolver** ([`redirects.py`](../../../tooling/builder/src/adnd1e_builder/redirects.py)): Provides deterministic, cycle-detected ID aliasing without mutating immutable history.
3. **Rules Retrieval Engine** ([`rules_retrieval.py`](../../../tooling/builder/src/adnd1e_builder/rules_retrieval.py)): Implements dual graph-traversal and source-passage verification, variant opt-in isolation, edition namespaces (2014 vs. 2024), weapon wieldability vs. proficiency bonuses, and out-of-corpus reference-only modeling.

---

## 5. Independent Subagent Sign-Offs

- **Builder Subagent (`c9a3f338`):** Verified builder tools; checked in [`test_builder_tooling_audit.py`](../../../tooling/builder/tests/test_builder_tooling_audit.py) (**16/16 PASS**).
- **Reviewer Subagent (`173a77b7`, `2cfee958`):** Certified regression compliance; checked in [`test_remediation_regressions.py`](../../../tooling/reviewer/tests/test_remediation_regressions.py) (**19/19 PASS**).
- **Analyst Subagent (`02faca9b`):** Reconciled primary source evidence (SD p.37, CS2 p.17, CS3 p.20).
- **Integrator Subagent (`a27574bd`, `1356c08a`):** Verified canonical graph consistency (0 mismatches across JSON and CSVs, 0 dangling endpoints, 297/297 Integrator tests passing); certified baseline snapshot and rollback. Registered [`canonical_integrity_audit.yaml`](../../rulesets/shadowdark/reports/canonical_integrity_audit.yaml).

---

## 6. Restoration & Rollback Instructions

Should it ever be necessary to restore the graph to this exact v1.1 release state:
1. Copy `build/snapshots/INT-20261104-REL/graph.json` to `rulesets/shadowdark/canonical/graph.json`.
2. Copy `build/snapshots/INT-20261104-REL/nodes_master.csv` to `rulesets/shadowdark/canonical/nodes_master.csv`.
3. Copy `build/snapshots/INT-20261104-REL/edges_master.csv` to `rulesets/shadowdark/canonical/edges_master.csv`.
4. Copy `build/snapshots/INT-20261104-REL/classification_gaps.csv` to `classification_gaps.csv`.
5. Verify SHA256 checksums match the values recorded in [`remediation_release_snapshot.yaml`](../../rulesets/shadowdark/reports/remediation_release_snapshot.yaml).
