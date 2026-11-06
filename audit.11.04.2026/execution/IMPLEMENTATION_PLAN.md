# Sub-Agent Implementation Plan: November 4 Rules Graph Remediation

**Date:** 2026-11-04  
**Architect:** Codex  
**Governing Authority:** [`DEC-2026-0109`](../../rulesets/shadowdark/escalations/decisions/DEC-2026-0109.yaml)  
**Execution Plan:** [`AGY_REMEDIATION_EXECUTION_PLAN.md`](../AGY_REMEDIATION_EXECUTION_PLAN.md)  
**Current Baseline:** `v1.0-audit-baseline` (732 nodes, 1,498 edges, 240 classification gaps)

---

## 1. Executive Summary & Relay Sequence

Work follows the repository-wide relay protocol:
**Analyst -> Builder -> Reviewer -> Integrator -> Analyst**

Escalations pause at their originating stage and return to the originator upon Architect ruling.
Phase 1 established architectural authority via `DEC-2026-0109`. The implementation across sub-agents is sequenced as follows:

```
+---------------------------------------------------------------------------------------+
| Phase 0: Baseline Binding & Manifest Mapping (Integrator, Analyst, Builder, Reviewer)   |
|   -> Completed: Snapshot, Packet Ledger, Component Map, Regression Crosswalk          |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| Phase 1: Minimal Shared Contracts (Architect)                                          |
|   -> Completed: DEC-2026-0109 Approved & Published                                   |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| Phase 2: Engine & Pipeline QA Gate Implementation (Builder & Reviewer)                 |
|   -> Builder: SourceEntityManifest Gate, Redirect Resolver, Retrieval Engine          |
|   -> Reviewer: 15-case Regression Test Suite Harness                                  |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| Phase 3: Shadowdark P0 Bounded Repair Batches (Analyst -> Builder -> Reviewer -> INT) |
|   -> Batch 3A: Core Spell Inventory (alarm, bless, fixed_object, fabricate)           |
|   -> Batch 3B: Control Water Identity Migration & Redirect                            |
|   -> Batch 3C: SD p.70 Layout Attribution (Sending, Shapechange, Shield of Faith)     |
|   -> Batch 3D: pp.54-62 Core Class/Tier Reconciliation                                 |
|   -> Batch 3E: Applicability Safety & Exact Passage Spans (Fatality Mode Default False)|
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| Phase 4 & 5: Regression Validation & Canonical Integration (Integrator & Reviewer)     |
|   -> Canonical Application & Master Export Regeneration (Integrator)                  |
|   -> Independent Regression Suite Run (All 15 Cases Pass) (Reviewer)                  |
|   -> Durable Tracking Ledger Updated & Release Snapshot (Integrator)                   |
+---------------------------------------------------------------------------------------+
```

---

## 2. Builder Sub-Agent: Implementation Specifications

### 2.1 Pre-Extraction Source Manifest Gate (`SD-015`, `UNIV-SRC-11`, `spec:UNIV-COV-05`)
- **Module:** `tooling/builder/src/adnd1e_builder/manifest_gate.py`
- **Specification:**
  - Ingests `SourceEntityManifest` YAML declaring `required_entities`, `optional_entities`, and `explicit_exclusions`.
  - Compares against extracted packet nodes before GUP companion compilation.
  - If any declared `required_entity` is missing from the extracted nodes, compilation terminates with an error:
    `GateError: Missing required inventory entity '<entity_id>' from source '<source_span>'`.

### 2.2 Identity Redirect Resolver (`SD-002`, `spec:SD-SPL-03`)
- **Module:** `tooling/builder/src/adnd1e_builder/redirects.py`
- **Specification:**
  - Maintains a durable registry of identity redirects (`rulesets/shadowdark/registries/identity_redirects.yaml`).
  - Contains entry: `from: spell_control_weather` -> `to: spell_control_water`, reason: "SD p.57/p.319 typo correction".
  - Resolves any incoming query or edge referencing `spell_control_weather` to `spell_control_water` without creating duplicate nodes or corrupting edge provenance.

### 2.3 Retrieval and Applicability Engine (`SD-008`, `SD-011`, `spec:SD-ITEM-05`, `spec:SD-VAR-08`)
- **Module:** `tooling/builder/src/adnd1e_builder/rules_retrieval.py`
- **Specification:**
  - **Weapon Usability:** Checks whether an entity is linked to `item_weapon`. Distinguishes category membership from class permissions. When querying "Can a wizard use a greatsword?", retrieves class permitted weapon list and identifies that greatsword is not on the permitted list.
  - **Variant Applicability:** Distinguishes `book_enabled` from `variant_opt_in`. Evaluates queries with default `fatality_mode: false`. When `fatality_mode` is false, standard dying rules are returned. When `fatality_mode: true`, the specific active override is returned with citations for both rules.
  - **Armor & Casting:** For "Can a wizard cast Sleep in plate mail?", checks wizard armor restrictions and plate mail armor classification, citing authoritative source text rather than raw edge labels.

---

## 3. Analyst Sub-Agent: Data & Packet Specifications

### 3.1 Batch 3A: Core Spell Inventory (`SD-001`, `spec:SD-INV-01`)
- **Source:** SD pp. 54-62 (lists), pp. 63-95 (descriptions).
- **Additions:**
  - `spell_alarm`: Wizard Tier 1, SD p. 63.
  - `spell_bless`: Priest Tier 2, SD p. 64.
  - `spell_fabricate`: Wizard Tier 3, SD p. 69.
  - `spell_fixed_object`: Wizard Tier 2, SD p. 69.
- **Passage Joins:** Exact character span, page marker, and class list offerings.

### 3.2 Batch 3B: Control Water Migration (`SD-002`, `spec:SD-SPL-03`)
- **Source:** SD p. 57 (Priest tier 4, Wizard tier 4), p. 66 (spell description), p. 319 (Trident of the Seas).
- **Identity:** `spell_control_water`.
- **Links:**
  - `class_priest` -> `PROVIDES` -> `spell_control_water` (tier 4)
  - `class_wizard` -> `PROVIDES` -> `spell_control_water` (tier 4)
  - `item_trident_of_the_seas` -> `CASTS` -> `spell_control_water`

### 3.3 Batch 3C: SD p. 70 Packet (`SD-003`, `SD-004`, `SD-005`, `spec:SD-SPL-02`)
- **Source:** SD p. 70.
- **Corrections:**
  - `spell_sending`: Wizard Tier 3 (was Wizard Tier 5).
  - `spell_shapechange`: Wizard Tier 5 (was Priest Tier 5).
  - `spell_shield_of_faith`: Priest Tier 1 (was Wizard Tier 1).
  - `spell_scrying`: Wizard Tier 5 (preserved unchanged).

### 3.4 Batch 3D & 3E: Reconciled Offerings & Applicability
- Reconcile 240 classification gaps in `classification_gaps.csv`.
- Add weapon taxonomy for 26 weapons under `item_weapon`.
- Explicitly set `fatality_mode` as optional rule with default state `disabled`.

---

## 4. Integrator Sub-Agent: Canonical & Transaction Specifications

### 4.1 Canonical Graph Migration
- **Artifact:** Canonical integration patch updating `rulesets/shadowdark/canonical/graph.json`.
- **Integrity:**
  - Replace `spell_control_weather` with `spell_control_water`.
  - Add missing 4 spells with complete node metadata and offering edges.
  - Update edge targets and source attributes for p.70 spells.
  - Re-derive `rulesets/shadowdark/canonical/nodes_master.csv` and `edges_master.csv`.
- **Rollback Test:** Validate that restoring from `build/snapshots/INT-20261104-BASE/` restores exact baseline byte-for-byte.

---

## 5. Reviewer Sub-Agent: Verification & Regression Specifications

### 5.1 Automated Regression Test Suite
- **Script:** `tooling/reviewer/tests/test_remediation_regressions.py`
- **Execution Scope:** Runs all 15 test cases defined in `audit.11.04.2026/rules_graph_regression_cases.json`.
- **Success Criteria:**
  - `SD-INV-01`: Core spell inventory contains all 4 omitted spells and correct Control Water.
  - `SD-SPL-02`: SD p.70 spells match verified class and tier.
  - `SD-SPL-03`: Control Water has dual list (Priest 4, Wizard 4) and old ID redirect.
  - `SD-SPL-04`: Wizard Sleep in plate mail retrieves authoritative armor rule with citation.
  - `SD-ITEM-05`: Wizard greatsword query distinguishes class rule from weapon taxonomy.
  - `SD-REL-06`: Damage trigger for focus spellcasters retrieves correct relationships.
  - `SD-VAR-07` & `SD-VAR-08`: Fatality Mode disabled vs enabled retrieves correct active rules.
  - `SD-SPL-09`: Priest Burning Hands checks authoritative list without negative edge inference.
  - `SD-QUAL-10`: Deterministic replay produces identical results with no duplicates.
  - `UNIV-SRC-11`: Missing manifest entry triggers gate failure.
  - `UNIV-TBL-12`: Multi-column table preserves row and header context.
  - `D5-ED-13` & `D5-PROF-14`: Edition isolation and proficiency vs weapon use readiness.
  - `UNIV-REF-15`: Reference-only entries marked without fake definitions.
