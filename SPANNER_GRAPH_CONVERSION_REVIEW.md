# Spanner Graph Architecture Review

Reviewed: 2026-10-11, America/New_York  
Design addendum: 2026-10-12, following the owner's multi-tenant/layered-rules requirements  
Role: Architect  
Status: Architecture review and recommendations, not an implementation Decision  
Scope: Shadowdark and AD&D 1e; no RC processing or export authorized

Reviewed proposal: [SPANNER_GRAPH_CONVERSION_ASSESSMENT.md](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md).
Its measured SHA-256 is `27f7188462be1fac30fdcd9e343e29899ede60618e992823f2d6ffd7fedb327b`.

## 1. Findings First

**Verdict: useful starting sketch, but not implementation-ready.** Spanner is a plausible query backend. The proposal does not yet preserve the project's complete identity, provenance, publication, and query semantics. Its strongest idea is separating citation identifiers from display titles. Its largest mistake is treating a small set of CSV imports plus graph traversal as a complete conversion architecture.

Here, **High** means resolve before relying on the implementation, not that the current repository has suffered a production incident.

| ID | Severity | Finding and consequence | Proposal location |
|---|---|---|---|
| F01 | High | Importing `nodes_master.csv` loses **265 of 817 Shadowdark registered identities**, plus 21 AD&D identities. The derived node table is not the identity registry. | [Node ingestion, line 241](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:241) |
| F02 | High | Forward traversal across every relationship is not mechanical impact analysis. `DERIVED_FROM` has the opposite dependency direction from `FEEDS_INTO`; cross-references, exclusions, alternatives, and classifications also need different treatment. | [Impact query, line 189](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:189) |
| F03 | High | The proposed raw-string assertion hash does not implement symmetric identity or the AD&D text-normalization rule. Existing Builder and Integrator key functions also disagree; an exporter must not introduce a third definition. | [Hash transformation, line 242](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:242) |
| F04 | High | Queries omit ruleset predicates, and the Books join omits `ruleset_id`. There are already **118 node IDs shared between the two rulesets**. Results can mix unrelated mechanics; a future repeated citation code can misattribute or multiply citations. | [Citation query, line 151](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:151) |
| F05 | High | Three tables do not retain exact source-instance provenance, approval/integration lineage, secondary supporting loci, or extraction `pass`. They could serve as a deliberately limited view, not a complete replacement for repository evidence. | [DDL, line 39](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:39) |
| F06 | High | Query/API examples are not executable as written against the documented interfaces: `COLUMNS` instead of the documented `RETURN` form, inaccessible outer graph variables, Cypher-style repetition, and a nonexistent documented Python `spanner_client.batch_insert()` method. | [Queries, line 151](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:151), [ingestion, line 245](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:245) |
| F07 | High | Direct Books insertion cannot satisfy `source_authority NOT NULL` for AD&D: none of its four book records has that field. Publication status is not a substitute for source authority. | [Books DDL, line 43](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:43), [mapping, line 240](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:240) |
| F08 | High | There is no coherent snapshot, idempotency, update/removal, activation, or rollback protocol. Independent inserts can publish a partially loaded graph or retain assertions that the repository has retired. | [Ingestion section, line 235](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:235) |
| F09 | High | AD&D is not a uniformly clean production baseline: the current invariant validator reports **1,691 findings**. A schema-valid export must not silently present these rows as newly approved or resolved. | [Repository scope, line 12](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:12) |
| F10 | Medium | A core/optional flag or list of book codes is not an activation profile. Shadowdark's core book itself contains **39 optional edges**. | [Campaign filtering, line 209](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:209) |
| F11 | Medium | The proposed node labels, derived metrics, and roles lack their authority/profile context. There are 19 Shadowdark and 15 AD&D derived-node labels that differ from the registry. Graph properties also omit `roles` and `review_flag`. | [Nodes DDL, line 52](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:52), [graph definition, line 103](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:103) |
| F12 | Medium | The design has insufficient domain constraints, no adjacency-index plan, no deployment/cost case, and a citation formatter that loses section-only citations. Calling Spanner "optimal" is premature. | [Platform claim, line 22](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:22), [edge DDL, line 65](D:/analysis/dnd/SPANNER_GRAPH_CONVERSION_ASSESSMENT.md:65) |

The SQL findings are based on current official documentation, not an executed Spanner deployment. Google's documented graph-within-SQL interface uses a GQL query ending in `RETURN`; scalar projections need explicit output names for outer SQL. Its quantified edge syntax is different from the proposal's Cypher-like example. The Python batch interface belongs to a database object. See [graphs within SQL](https://docs.cloud.google.com/spanner/docs/reference/standard-sql/graph-sql-queries), [GQL patterns](https://docs.cloud.google.com/spanner/docs/reference/standard-sql/graph-patterns), and [Python batch usage](https://docs.cloud.google.com/python/docs/reference/spanner/latest/batch-usage).

## 2. What I Actually Verified

I read the scoped Architect authorities, both rulesets' relevant constitutions and schemas, registries, canonical tables, profiles, and the actual Builder/Integrator identity and derivation implementations. I checked every current canonical edge against its production JSON schema and ran the existing Integrator invariant validator read-only for both rulesets.

The local, reproducible inspection is [audit.py](D:/analysis/dnd/.local/spanner-review/audit.py), with detailed results and input checksums in [audit.json](D:/analysis/dnd/.local/spanner-review/audit.json). These are review scratch artifacts under ignored `.local/`, not new production tooling. Preserve them separately if transferring this evidence through Git alone.

| Measurement | Shadowdark | AD&D 1e |
|---|---:|---:|
| Registered identities in `registries/nodes.csv` | 817 | 1,477 |
| Incident nodes in `canonical/nodes_master.csv` | 552 | 1,456 |
| Registry-only identities absent from derived node table | **265** | **21** |
| Canonical edges | 1,159 | 5,179 |
| Per-row production JSON-schema errors | 0 | 0 |
| Integrator invariant findings | 0 | **1,691** |
| Duplicate assertion-key groups, using Builder implementation | 0 | 0 |
| Duplicate assertion-key groups, using Integrator implementation | 0 | 0 |
| Rows whose Builder key differs from Integrator key | 8 | 339 |
| `ALTERNATIVE_TO` rows | 10 | 89 |
| `ALTERNATIVE_TO` rows stored in descending endpoint order | 2 | 52 |
| Self-edges | 0 | 86 |
| Derived-node labels differing from registry label | 19 | 15 |
| Blank page fields, with section-based citation available | 0 | 7 |

The descending endpoint counts are **not proof of invalid stored assertions**. They demonstrate why a raw directional hash is not the symmetric comparison key. Likewise, different computed key tuples do not mean duplicate assertions exist: both duplicate checks found zero current groups.

Other checks:

- All current edge endpoints and cited book codes resolve to their respective registries.
- All measured edge-string and node-string values fit the proposal's corresponding length limits. There is no demonstrated truncation incident. Future limits still need an explicit validation policy because the source schemas do not promise those maxima.
- No current five-field assertion key contains the proposed `|` separator. Ambiguous delimiter serialization is a future robustness issue, not a collision observed in this corpus.
- The three illustrative Shadowdark rows concerning Stout, Constitution, and Damage really exist. The problem is the query and scope, not invented sample facts.
- The 144 Shadowdark incoming Markdown packets have 144 distinct packet IDs represented in terminal integration records. There are 145 terminal records, including 47 zero-row integrations. This supports completed processing, not a claim that every possible source assertion has been independently re-extracted during this review.
- Across 145 Shadowdark integration manifests, every current edge matches exactly one primary addition entry and every registered identity matches exactly one registration entry. All **290 recorded approved-bundle component checksums** and **145 recorded Review checksums** match current files.
- The latest Shadowdark integration, `INT-20261010-002`, pins after-checksums matching all four current canonical/registry outputs. No audited input drift was detected.

This review did **not** run a cloud database, create billable resources, deploy a loader, benchmark Spanner, or independently rereview every source packet. Neither `gcloud` nor `docker` was available on the inspected PATH. No canonical data, registry, proposal, or governance file was changed.

## 3. Preserve the Repository's Actual Architecture

The repository deliberately separates several things that the proposal compresses together:

| Repository layer | Meaning | Database consequence |
|---|---|---|
| Ruleset constitution and production schemas | Which identities and assertions are legal in that ruleset | Pin authority/schema versions and content hashes for every exported release. Do not impose one ruleset's vocabulary on another. |
| `registries/nodes.csv` | Accepted identities and their display labels, including zero-edge identities | This is the source of the complete concept population. |
| `canonical/edges_master.csv` | Current integrated mechanical assertions, in 18 controlled columns | This is the source of current relationship facts, not every proposed GUR/GUP row. |
| `canonical/nodes_master.csv` | Derived incident-node metrics and roles | Join this to the registry; do not use it as the whole identity catalog. |
| `canonical/graph.json` | Derived graph presentation of the canonical tables | Do not independently merge it as another source of facts. |
| Book and source registries | Publication identity versus exact edition/printing/transcription identity | Model both; one book can have multiple source instances. |
| Approved bundles and integration records | Authority, exact consumed inputs, changes, checksums, and lineage | Retain resolvable, checksum-bound evidence for the projection. |
| Activation and impact profiles | Query-time choices and analytical interpretation | Do not turn these into unapproved production edges or stored severity. |
| Packet claims and published artifacts | Workflow history | Do not move, delete, or reinterpret these as database completion flags. |

This follows [Scope and Identity](D:/analysis/dnd/contracts/SCOPE_AND_IDENTITY.md:7), [Graph Invariants](D:/analysis/dnd/contracts/GRAPH_INVARIANTS.md:23), and the [Integrator's record construction](D:/analysis/dnd/tooling/integrator/src/adnd1e_integrator/records.py:37).

**Recommendation: a rebuildable, read-only projection of approved repository state.** The repository remains the write authority. Spanner serves queries. Deleting and rebuilding the projection must not lose the ability to reconstruct or govern the graph.

Do not introduce a second path where an application or ingestion script independently decides which GUPs are approved, which optional rules override others, or which IDs should merge. Direct Decision migrations also exist and need not have an ordinary packet/GUR chain. Preserve the Integrator's actual operation records, including compare-and-swap changes, identity replacements, and removals.

The title-resolution feature does not require a platform migration. It can be implemented over the existing book registry and query/API layer independently.

## 4. Tables: What I Would Keep and Change

### 4.1 Identity and Release Context

There are three different notions of identity:

1. **Concept identity:** `(ruleset_id, node_id)`. The same string in another ruleset is a different identity.
2. **Assertion identity:** the ruleset's governed five-field key, after its authorized comparison rules.
3. **Projection occurrence:** a concept or assertion as represented in one immutable exported release.

Do not confuse a release identifier with a new ruleset or new concept identity. Do not confuse a content checksum with an assertion ID. A citation correction changes row content without necessarily changing the assertion. An endpoint repoint can change assertion identity and must retire the old projected assertion in the new release.

For an initial implementation I favor release-scoped snapshots. At this size, that is simpler to verify than a new incremental change-data-capture system.

Suggested logical tables:

| Table | Suggested key | Purpose and principal constraint |
|---|---|---|
| `ProjectionReleases` | `(ruleset_id, release_id)` | Immutable export manifest: input hashes, integration anchor, exporter/key-codec versions, profiles, conformance result, expected counts and row-set digests. |
| `ActiveProjections` | `(ruleset_id)` | Pointer to one completely validated release, changed atomically after loading succeeds. |
| `Books` | `(ruleset_id, release_id, book_id)` | Source-work metadata; unique citation code within the same context. |
| `Sources` | `(ruleset_id, release_id, source_instance_id)` | Exact source-instance metadata, linked to its book; explicit unknown edition/printing remains unknown. |
| `Nodes` | `(ruleset_id, release_id, node_id)` | All registry identities; registry labels/kinds plus optional version-bound derived metrics. |
| `Assertions` | `(ruleset_id, release_id, assertion_id)` | One current assertion per governed key, full canonical payload or losslessly recoverable raw payload. |
| `AssertionEvidence` | `(ruleset_id, release_id, assertion_id, evidence_id)` | Primary and corroborating loci, source-instance links, and approval/integration evidence pointers. |

These are logical responsibilities, not a demand for a large new workflow database. Node-registration provenance can initially be stored as structured, checksum-bound references on Nodes or in the release evidence manifest. Separate `NodeEvidence`, `ArtifactReferences`, or `NodeMetrics` tables are optional if actual query needs justify them. Keep packet queues, escalation routing, and role instructions out of the graph database.

Every snapshot relationship and foreign key includes the same ruleset **and release**. A query chooses its release once; it must not accidentally join today's Books or Nodes to yesterday's Assertions. The property graph exposes this release context as well as the semantic IDs.

### 4.2 Books

Keep the distinction between:

- `book_id`: repository work identity, such as `sd`.
- `citation_code`: controlled citation token, such as `SD`.
- `title`: display text, now `Shadowdark RPG` in the current registry.
- `source_authority`: publication authority assessment, where supplied.
- Publication classification and campaign activation: different concepts, not aliases for source authority.

I prefer keying Books on `book_id` with a unique `(ruleset_id, release_id, citation_code)` lookup, but the proposal's code-based key can also work if code stability is explicitly promised. Either way, all joins include the full context.

AD&D book records lack `source_authority`. Preserve that as absent/unknown or obtain an authorized mapping; do not convert `status: core` to `source_authority: canonical` by inference. Shadowdark supplement entries marked `pending_source_review` must stay that way. A suggestive title is not authority to activate a supplement.

Display-title changes should not change node or assertion IDs. Preserve the title used in a historical release while allowing a newly exported metadata release to show a corrected title. Internal paths may be retained for audit, but presentation should return structured book/page/section data rather than expose workspace paths.

### 4.3 Sources and Source Loci

The repository's workflow `source_id` means edition, printing, scan, or transcription. The edge CSV's `source_id` means the **source endpoint node**. These are not interchangeable.

Use unambiguous database names such as `source_node_id` and `source_instance_id`. AD&D DMG and UA already have both legacy-unspecified and steward-intake source records. Joining an edge's book to an arbitrary single source record would invent provenance.

An evidence record should be able to identify:

- The assertion and whether this is its primary or an additional supporting locus.
- Book, exact source instance when established, printed page or section locator, and evidence class.
- Packet/GUR/GUP/Review/Approved/Integration identifiers **where applicable**, plus exact artifact checksums and paths or stable audit URIs.
- The Decision and reviewed operation for a decision-driven migration, instead of manufacturing a packet chain.
- An explicit limitation where historical provenance does not establish an exact source instance.

One assertion can have multiple supporting loci. It must not become multiple mechanical edges merely because two books repeat it. The [AD&D citation and identity rules](D:/analysis/dnd/rulesets/adnd1e/governance/constitution.md:211) say this explicitly.

For query convenience, retaining the primary citation fields directly on Assertions is reasonable. If AssertionEvidence also contains that primary locus, validate that exactly one primary record exists and that its values agree with the canonical payload. Additional evidence is not a second assertion. Avoid joins that multiply edge counts merely because an assertion has several supporting records.

### 4.4 Nodes

Start with every row in `registries/nodes.csv`, then left-join the derived node table on ID within the ruleset/release.

Examples of why this matters:

- [Registry line 182](D:/analysis/dnd/rulesets/shadowdark/registries/nodes.csv:182) contains `lang_common`, label `Common`, at degree zero. It is absent from `nodes_master.csv`.
- [Derived-node line 334](D:/analysis/dnd/rulesets/shadowdark/canonical/nodes_master.csv:334) labels `lang_diabolic` with the ID itself; [registry line 183](D:/analysis/dnd/rulesets/shadowdark/registries/nodes.csv:183) supplies `Diabolic`.
- [Derived-node line 511](D:/analysis/dnd/rulesets/shadowdark/canonical/nodes_master.csv:511) similarly uses `monster_archangel` where the registry label is `Archangel`.

These do not justify rewriting canonical files during export. They justify choosing the correct authority for database display labels and preserving the raw imported artifacts for comparison.

Derived fields need defined semantics:

- Total degree is incoming plus outgoing incidence, not the number of distinct neighboring identities. A self-edge contributes to both directions in the current implementation; AD&D has 86 self-edges.
- `core_degree` is based on canonical `status: core`, not the active campaign profile.
- Registry-only identities have zero incident degree; do not drop them or leave their existence ambiguous.
- Roles are a derived collection. Prefer an array or a small bridge relation over an opaque pipe-delimited string if querying roles matters. Preserve the exact original representation in audit evidence.
- Shadowdark's empty role profile is an approved bootstrap state, not permission to apply AD&D thresholds. Empty roles are not evidence that a complete Shadowdark role classifier found no roles.

The relevant implementation is [derive.py](D:/analysis/dnd/tooling/integrator/src/adnd1e_integrator/derive.py:219). Pin its version and the role-profile hash if storing its outputs. Do not add creature hit points, spell magnitudes, or other excluded stat-block properties just because a property graph can hold them.

### 4.5 Assertions and Stable Keys

Use one row per governed assertion, not one row per endpoint pair. Parallel assertions with the same endpoints/type but distinct source-supported aspects or conditions are intentional.

The proposed `sha256(source + "|" + type + "|" + target + "|" + aspect + "|" + condition)` needs a formal codec before use:

1. Resolve the active ruleset and its identity policy.
2. Preserve canonical endpoint IDs and the controlled edge type without inventing aliases.
3. Sort endpoints for `ALTERNATIVE_TO` when constructing the comparison key. Do not add a second stored edge.
4. Apply only the authorized aspect/condition comparison normalization.
5. Define empty-string versus NULL handling once. Empty condition is a real, currently common representation, not a second identity when converted to SQL NULL.
6. Serialize a fixed ordered structure with a specified encoding, escaping, and algorithm version. A JSON array with fixed serializer settings or a length-prefixed encoding is safer than an unescaped delimiter join.
7. Hash a namespaced payload containing ruleset and codec version. Choose one representation, for example 64 lowercase hexadecimal characters; do not leave random UUID versus deterministic hash unresolved.
8. Retain the normalized key and compare it when an existing hash is encountered. A hash collision or incompatible existing payload must be a hard error, not an upsert that erases evidence.

Keep a **separate row-content digest** over all canonical fields. Do not include citations or labels in semantic assertion identity. Retain the original source file checksum for byte-level reproducibility; a normalized row digest is not the CSV file's byte checksum.

There is a pre-existing implementation issue to resolve first: [Builder `assertion_key`](D:/analysis/dnd/tooling/builder/src/adnd1e_builder/duplicates.py:38) normalizes aspect/condition text, while [Integrator `assertion_key`](D:/analysis/dnd/tooling/integrator/src/adnd1e_integrator/invariants.py:118) preserves the raw strings. Both sort symmetric endpoints. AD&D [section 5.1](D:/analysis/dnd/rulesets/adnd1e/governance/constitution.md:223) expressly requires normalization. Shadowdark's shorter identity clause should be made unambiguous about its policy before freezing a cross-tool codec. This review is not silently selecting a new policy.

Do not use CSV row number as a durable ID. It is a valid locator only together with the exact file checksum. Do not treat labels as identity. Do not make `book` part of assertion identity to avoid deciding a provenance conflict.

### 4.6 Lossless Mapping of All 18 Edge Columns

| Canonical column | Projection treatment |
|---|---|
| `source_id` | `source_node_id`; scoped FK to Nodes. |
| `source_label` | Retain as raw assertion/audit payload; query display normally uses the registry label. |
| `edge_type` | Controlled property, optionally also exposed through a mapped graph label. |
| `target_id` | `target_node_id`; scoped FK to Nodes. |
| `target_label` | Same preservation rule as source label. |
| `aspect` | Preserve raw text and separately derive the governed comparison form for identity. |
| `condition` | Preserve raw text; explicitly map empty/NULL for comparison and round-trip export. Not executable Boolean code. |
| `polarity` | Preserve controlled value; do not reinterpret `neutral` as "no impact". |
| `polarity_basis` | Preserve `read`, `derived`, and any disclosed legacy unresolved values. |
| `book` | `citation_code`, resolving to the scoped Books record. |
| `page` | Positive integer or NULL for the source's empty value; preserve section-based citations. |
| `section` | Preserve; it is substantive citation information, not merely display decoration. |
| `evidence` | Controlled evidence class, not a numeric confidence score. |
| `pass` | Preserve as `extraction_pass` or in the lossless raw payload. It is a string, not always a number. |
| `status` | Core/optional publication classification, not workflow state or campaign activation. |
| `supersession_basis` | Preserve and validate the `OVERRIDES` gating rule. |
| `general_rule_id` | Validate against the separate general-rule registry, not against node IDs. |
| `review_flag` | Preserve and expose when consumers need caveats; the proposed graph definition omits it. |

The proposal removes three original columns: both endpoint labels and `pass`. Normalizing display labels can be an intentional projection choice, but it is not a lossless conversion without retaining the originals elsewhere. AD&D currently has 3,123 nonempty endpoint-label occurrences differing from registry labels; these can include aliases or context-specific wording and are not automatically 3,123 invalid assertions.

`pass` has 11 distinct AD&D values, including nonnumeric values such as `page-sweep` and `spell-scan`. Four AD&D rows reference general rules; three carry `class_level_conflation` review flags. Those fields are not all empty historical decoration.

Add importer checks and database constraints where appropriate: legal per-ruleset vocabulary, valid endpoints, book resolution, nonempty required fields, positive page or a section locator, legal evidence/status, and conditional supersession/general-rule requirements. The current nullable SQL columns alone do not enforce these contracts. Do not allow silent truncation to fit a SQL column.

Preserving legacy data and rejecting newly introduced defects are separate policies. Hardening constraints must not silently delete the existing AD&D exceptions or falsely mark them repaired.

## 5. The Hardest Part Is Query Meaning, Not SQL

### 5.1 Reachability Is Not Yet Impact Analysis

The graph stores evidence-bearing mechanical relationships. It is not a complete executable rules engine: it intentionally excludes many numeric values, individual creature statistics, and unsupported inferences. Conditions are source-grounded text, not compiled predicates. A graph database cannot fill those gaps merely by walking more edges.

A concrete counterexample is [Shadowdark edge CSV line 2](D:/analysis/dnd/rulesets/shadowdark/canonical/edges_master.csv:2):

```text
abil_charisma --DERIVED_FROM--> rule_stat_generation
```

Changing stat generation potentially affects the derived ability. Discovering that dependency starts at `rule_stat_generation` and follows this relationship **backward**. The proposed outgoing-only traversal misses it. In contrast, the recorded Constitution-to-Hit-Points `FEEDS_INTO` relationship points input-to-result. Neither stored edge should be reversed merely to make one generic traversal work.

The [Shadowdark vocabulary](D:/analysis/dnd/rulesets/shadowdark/governance/constitution.md:207) requires the following distinctions. The last column describes questions an impact policy must answer, not a newly ratified propagation algorithm.

| Edge type | Authored relationship | Required query treatment |
|---|---|---|
| `MODIFIES` | Modifier to modified mechanic | Forward influence is plausible, but preserve aspect, condition, and polarity; a different change question may need reverse contextual discovery. |
| `DERIVED_FROM` | Derived value to its source | Source-change dependency discovery follows the reverse direction. |
| `GATES` | Gate to gated mechanic | Preserve prerequisites and conditional availability rather than assuming unconditional propagation. |
| `TRIGGERS` | Cause to effect | Preserve triggering conditions; an asserted trigger is not a universal outcome. |
| `ALTERNATIVE_TO` | Symmetric substitutability or mutual exclusion | Discover either endpoint, but do not automatically activate both alternatives. |
| `CONSUMES` | Consumer to resource | A resource change can affect consumers, requiring reverse dependency discovery. |
| `CONSTRAINS` | Constrainer to constrained mechanic | Preserve limiting semantics; not simply another positive input. |
| `OVERRIDES` | Overrider to overridden rule | Resolve activation and supersession before deciding which rule participates. |
| `FEEDS_INTO` | Input to process | Forward dependency discovery is appropriate for input changes. |
| `RESOLVED_BY` | Thing resolved to procedure | A procedure change can affect the things resolved by it, requiring reverse discovery. |
| `CROSS_REFERENCES` | Explicit textual reference | Useful navigation/evidence context, not proof of mechanical propagation. |
| `EXCLUDES` | Active prevention | Retain as a negative mechanical constraint. Do not discard it or treat it as an enabling edge. |
| `EXCLUDED_FROM` | Not an input/member of the named mechanic | Preserve the asserted non-connection. It is not a reverse spelling of `EXCLUDES`. |
| `CLASSIFIED_AS` | Individual to mechanically operative classification | Apply only the approved classification semantics. Do not create general taxonomy or universal inheritance. |

The practical API should distinguish:

1. **Neighborhood:** these assertions touch this identity.
2. **Dependency candidates:** these paths match an explicit, versioned relationship/direction policy.
3. **Assessed impact:** these candidate paths remain relevant under the chosen activation profile, assumptions, conditions, and change description.

Each result should retain the path's assertion IDs, directions of traversal, citations, conditions, and exclusion/override caveats. `SELECT DISTINCT target` alone discards the explanation and can hide several contradictory or conditional paths to the same node.

Specify cycle handling, self-edge behavior, repeated-node/edge policy, path limits, and pagination. AD&D's 86 self-edges make these real test cases. A path-length cap is a resource bound, not a definition of mechanical severity. Different aspects on parallel edges must not collapse into one unexplained neighbor.

Both [Shadowdark's impact profile](D:/analysis/dnd/rulesets/shadowdark/profiles/impact.yaml) and [AD&D's profile](D:/analysis/dnd/rulesets/adnd1e/profiles/impact.yaml) retain query-time policy rather than a complete implemented impact algorithm. Do not present placeholder profile files as an already validated scoring engine. Do not infer that `neutral` polarity means harmless or that two negative relationships multiply into a positive effect.

### 5.2 Activation Is a Separate Input

Use `activation_profile_id` for campaign choices, as required by [Scope and Identity](D:/analysis/dnd/contracts/SCOPE_AND_IDENTITY.md:21). A ruleset namespace identifies a compatible literature/ontology family; it is not a campaign configuration.

Observed Shadowdark facts:

- All 1,159 edges currently cite `SD`.
- 1,120 are `core`; 39 are `optional`.
- Therefore `book = 'SD'` and `status = 'core'` are already different selections.

The proposal's `SD + CS1` query includes every optional SD assertion, whether a campaign selected it or not. It also assumes a future CS1 import/authority policy that the current pending-source registry entries do not establish.

Start with clearly named filters such as "all assertions from selected publications" or "publication-classified core assertions." Do not call either an active campaign graph until rules for optional inclusion, conflicts, overriding procedures, and exclusion are specified and tested. Activation should select existing assertions, not invent new canonical ones or rewrite their publication status.

## 6. Spanner-Specific Review

### 6.1 Platform Choice and Cost

Spanner Graph does support relational/property-graph interoperability through an **ISO GQL-compatible** interface. It currently requires a GoogleSQL-dialect database and Enterprise or Enterprise Plus edition; it does not support the PostgreSQL interface. Those are deployment prerequisites missing from the proposal, not implementation details to discover after choosing a database. [Official Spanner Graph overview](https://docs.cloud.google.com/spanner/docs/graph/overview?hl=en).

The current combined dataset is **6,338 edges and 2,294 ruleset-scoped registered identities**. This is small enough that distribution and horizontal scale are not, by themselves, a demonstrated requirement. That does not make Spanner wrong: managed operation, an existing Google Cloud environment, concurrency requirements, or planned product integration could justify it. None of those has been measured in this assessment.

Before approving production infrastructure, define expected query rate, latency, path depth, users, availability, region, data residency, growth, and monthly budget. Compare the same correctly specified queries against a local read model as a baseline. This is a benchmark recommendation, not a claim that an untested alternative will outperform Spanner.

Budget compute capacity, replicas/configuration, storage, backups, network, and any Dataflow or specialized analysis services. A tiny graph does not imply a zero-cost always-on deployment. Use the selected configuration's current pricing rather than a generic per-node estimate. [Spanner pricing](https://cloud.google.com/spanner/pricing).

Do not conflate this database decision with the choice of Gemini/Antigravity as the agent interface. One does not require the other.

### 6.2 Generic Versus Typed Graph Labels

**My starting choice: one generic relationship table with the governed `edge_type` retained as a property.** It is easy to compare with the canonical CSV and works with the unified vocabulary per ruleset. Introduce label-specific access only when it improves a measured query or makes a reviewed query contract clearer.

There are three implementable approaches to investigate:

| Approach | Advantage | Constraint or tradeoff |
|---|---|---|
| Generic `Relationship` with `edge_type` property | Simplest lossless mapping and one edge population | Queries must explicitly filter eligible types; index/query-plan testing still matters. |
| Typed labels over filtered SQL views | Explicit edge-type patterns without duplicating canonical rows | Views must actually filter rows and preserve unique keys; do not label every row with every edge type. |
| Dynamic labels from a mapped column | One relational edge population with type-driven graph labels | Maintain an explicit mapping and comply with Spanner's dynamic-label rules. |

Current Spanner supports property graphs over suitable SQL views, including filtering a single table while retaining its primary key. Views are not materialized. Keep element-key uniqueness validation enabled; do not bypass it to hide a many-to-many provenance join or an ambiguous current-release view. [Graphs from SQL views](https://docs.cloud.google.com/spanner/docs/graph/graph-with-views-overview).

Current dynamic labels are also an option, not something requiring one physical table per type. Their label values must be lowercase, so retain the uppercase canonical `edge_type` and derive a separate presentation/mapping column. For each element kind using dynamic labels, only one input table of that kind is permitted: a dynamic edge label restricts edge tables, and a dynamic node label restricts node tables. Check this against any planned additional graph relationships. [Schemaless/dynamic graph data](https://docs.cloud.google.com/spanner/docs/graph/manage-schemaless-data), [graph schema reference](https://docs.cloud.google.com/spanner/docs/reference/standard-sql/graph-schema-statements).

There is no justified universal answer that typed labels are faster than property filtering. Compare execution plans and latency for the actual traversal mix, data distribution, indexes, and path bounds. A typed view may improve clarity without improving speed; a unified shape may simplify mixed-type paths. Do not infer a performance guarantee from label syntax.

### 6.3 Primary Keys, Adjacency Indexes, and Isolation

`ruleset_id` is a namespace component. Calling it a "root partition key" overstates what the DDL guarantees. Spanner distributes ordered key ranges; a leading ruleset value is not a promise of one physical partition per ruleset. Sequential insertion patterns can create hotspots, while hash distribution has locality tradeoffs. [Schema design guidance](https://docs.cloud.google.com/spanner/docs/schema-design).

For this dataset, deterministic identity and reproducibility matter more than speculative large-scale sharding. Keep the deterministic assertion hash; do not switch to random IDs just to pursue write distribution. Avoid row-number or timestamp-only edge IDs. Benchmark a larger workload before adding shards or restructuring keys.

The assertion primary key alone does not describe adjacency access. Evaluate indexes beginning with:

```text
(ruleset_id, release_id, source_node_id, edge_type, target_node_id, assertion_id)
(ruleset_id, release_id, target_node_id, edge_type, source_node_id, assertion_id)
```

These are candidate index shapes, not tested DDL. Include only properties worth covering; do not copy the entire provenance payload into every index. Compare outgoing, incoming, type-filtered, citation, and bounded-path queries. Spanner's graph schema guidance specifically discusses traversal locality and reverse access. [Graph schema best practices](https://docs.cloud.google.com/spanner/docs/graph/best-practices-designing-schema).

Keep enforced endpoint and book foreign keys. Spanner can create managed backing indexes for them, so inspect actual indexes and plans before adding redundant structures. Their existence is not proof that every traversal has the desired covering access path. [Foreign keys and backing indexes](https://docs.cloud.google.com/spanner/docs/foreign-keys/overview?hl=en).

Neither a composite key nor a query parameter is an authorization system. Application queries must bind a permitted ruleset/release; arbitrary user queries must not gain write access or access to unauthorized source material. Use a read-only application identity distinct from the projection writer, and evaluate IAM/database-role permissions explicitly. [Spanner IAM](https://docs.cloud.google.com/spanner/docs/iam).

### 6.4 Symmetric Relationships

**Store `ALTERNATIVE_TO` once.** Preserve the existing canonical row and normalize endpoint order only when constructing its comparison key. Use an undirected match restricted to that edge type when finding alternatives. Do not query every relationship undirected and pretend the ontology has become symmetric.

An undirected query can produce both orientations when both ends are unconstrained; deduplicate by the scoped assertion ID when the requested result is a set of assertions. Distinguish that from a query intentionally returning endpoint orientations. The documented undirected pattern supports this without adding reciprocal canonical rows. [GQL edge patterns](https://docs.cloud.google.com/spanner/docs/reference/standard-sql/graph-patterns).

If a future analytical engine requires two traversal arcs, derive them in a separate analytical view and retain their one originating assertion ID. They are not two facts and must not double citations, confidence, degree metrics, or integration counts.

### 6.5 Corrected Citation Query Shape

The following is an **illustrative, unexecuted** query for the recommended release-scoped model, assuming `DndRulesGraph` exposes its context and primary-citation properties. It is not a migration script or a claim of server validation. It asks for incoming assertions about a node, not a full impact result.

```sql
SELECT
  q.source_node_id,
  q.source_label,
  q.edge_type,
  q.target_label,
  q.aspect,
  q.condition,
  q.polarity,
  b.title,
  q.page,
  q.section,
  b.title
    || CASE WHEN q.page IS NULL THEN ''
            ELSE ' p. ' || CAST(q.page AS STRING) END
    || CASE WHEN q.section IS NULL OR q.section = '' THEN ''
            ELSE ' / ' || q.section END AS citation_display
FROM GRAPH_TABLE(
  DndRulesGraph
  MATCH (src:Concept)-[r:Relationship]->(dst:Concept)
  WHERE src.ruleset_id = @ruleset_id
    AND src.release_id = @release_id
    AND r.ruleset_id = @ruleset_id
    AND r.release_id = @release_id
    AND dst.ruleset_id = @ruleset_id
    AND dst.release_id = @release_id
    AND dst.node_id = @node_id
  RETURN
    r.ruleset_id AS ruleset_id,
    r.release_id AS release_id,
    src.node_id AS source_node_id,
    src.label AS source_label,
    dst.label AS target_label,
    r.edge_type AS edge_type,
    r.aspect AS aspect,
    r.condition AS condition,
    r.polarity AS polarity,
    r.citation_code AS citation_code,
    r.page AS page,
    r.section AS section
) AS q
JOIN Books AS b
  ON b.ruleset_id = q.ruleset_id
 AND b.release_id = q.release_id
 AND b.citation_code = q.citation_code;
```

The key corrections are named outputs, full context, and section-aware formatting. The original proposal's outer `src`, `dst`, and `r` references are not supplied by its scalar projection. The documented interface can return graph variables themselves, but that is a different return shape. [Graphs within SQL reference](https://docs.cloud.google.com/spanner/docs/reference/standard-sql/graph-sql-queries), [GQL query statements](https://docs.cloud.google.com/spanner/docs/reference/standard-sql/graph-query-statements).

For bounded repetition, the documented pattern uses a quantifier such as `-[r:Relationship]->{1,3}`, not `-[r:Relationship*1..3]->`. Correct syntax still does not supply the missing impact semantics; filters must apply to each repeated step, not merely the final edge or endpoint. Define a path mode and preserve explanations rather than only returning distinct targets. [GQL quantified paths](https://docs.cloud.google.com/spanner/docs/reference/standard-sql/graph-patterns).

### 6.6 Loading API and Import Format

Replace the invented `spanner_client.batch_insert()` call with the documented client-library batch/transaction APIs. For example, the Python database object exposes a batch context with insert operations. An insert-or-update convenience method does not by itself enforce immutable-release equivalence or safely handle removed rows. Pin a client version and test retry behavior. [Python batch usage](https://docs.cloud.google.com/python/docs/reference/spanner/latest/batch-usage).

For a graph this small, a deterministic Python loader with bounded local validation is the sensible first implementation to evaluate. Dataflow is not necessary merely because Spanner is distributed.

Google documents CSV and Avro import/export workflows, including a CSV import manifest and Cloud Storage/Dataflow plumbing. Do not promise a direct Parquet import merely by writing "Parquet/Avro"; identify and test the exact supported conversion/job path. [Import/export overview](https://docs.cloud.google.com/spanner/docs/import-export-overview?hl=en), [CSV import](https://docs.cloud.google.com/spanner/docs/import-export-csv?hl=en).

## 7. Publication, Recovery, and Reconciliation

The database projection must not become another fragile agent-to-agent handoff protocol. One deterministic local command can collect inputs, validate, build a release, load it, verify it, and report a compact outcome. Agent/model round trips are unnecessary between those mechanical steps.

Recommended release protocol:

1. **Select explicit scope.** Start with Shadowdark only. Do not scan or export owner-paused RC material. An AD&D projection is a separate, explicitly qualified release.
2. **Select a coherent repository snapshot.** Use the completed Integrator transaction as the canonical anchor. Copy/read its matching canonical files and registry plus the exact book/source registries, profiles, schemas, and relevant authority. Detect concurrent changes; never combine independently read before/after versions.
3. **Record all inputs.** A Git commit alone is insufficient when the worktree is dirty or metadata was amended separately. Record exact content hashes, declared versions, exporter version, key-codec version, and every lineage input needed for reconstruction.
4. **Validate locally before uploading.** Check schema, identity, endpoint/book references, provenance, conformance policy, raw-to-projection equivalence, and complete node coverage. Produce deterministic counts and row-set digests.
5. **Create an inactive release.** Load its Books, Sources, Nodes, Assertions, and evidence in dependency order, with bounded transactions and retries. Existing active queries continue using the previous release.
6. **Treat repeated submission as replay.** Same release ID plus identical manifest/data is a no-op or a verifiably resumable load. Same release ID plus different content is an error. A blind upsert is not adequate proof of equivalence.
7. **Verify the database independently.** Reconcile every expected identity/assertion and required field, not just total row counts. Check constraints, evidence links, canonical digests, and representative query results.
8. **Activate atomically.** Compare the expected prior active release and update the pointer only after the new release passes. A delayed exporter must not overwrite a newer active release. Return the selected release ID in API responses for reproducibility.
9. **Retain rollback capability.** A projection rollback switches the pointer to a previously validated release. It does not undo a valid repository integration. Retain old releases until no active readers or retention requirements depend on them.
10. **Report lag and failures explicitly.** If the cloud write fails after repository integration succeeds, canonical work remains integrated; the projection is stale, not the packet. Retry/reconcile the export without rerunning packet integration or asking agents to recreate immutable artifacts.

Readers should capture the active release once and consistently use it throughout their query/request. Release IDs must appear in cache keys and pagination tokens, along with ruleset, activation profile, query-policy version, and parameters where applicable. Otherwise a title edit, integration, or profile change can leave a cache returning mismatched facts and citations.

Full snapshots naturally handle removals: an assertion absent from the new canonical state is absent from the new active release. If incremental loading is later necessary, use the Integrator's recorded additions, before/after updates, merges, repoints, and removals. Do not infer deletion merely from a skipped row, and do not ignore it because an insert-only loader is easier.

The exporter needs a coherent snapshot mechanism; this is not permission to reinstate a repository-wide lock that waits for another agent to finish an arbitrary turn. File snapshot consistency and agent orchestration are different concerns.

## 8. Existing Repository Debt This Review Exposed

These points predate Gemini's proposal. They should not be blamed on the database, nor hidden by changing representation.

### 8.1 Assertion Comparison Has Two Implementations

The Builder/Integrator normalization difference is real. Freeze one authorized, ruleset-aware comparison contract and test its implementation across both tools and the exporter. Do not repair canonical rows, renumber assertions, or merge identities as a side effect of consolidating a helper.

Current data is duplicate-free under both implementations. That is reassuring about this snapshot, but it does not make the implementations equivalent or protect future inputs. Tests need examples where punctuation/case and symmetric direction vary, not only examples where current rows happen to agree.

### 8.2 Derived Display Labels Are Not Always the Registry Labels

The 19/15 derived-node label differences are an existing derivation/display issue. The registry is still the right source for accepted identity labels. A projection can use it without editing history. Whether to change the canonical derivation is a separate, owned repair with regressions.

The registry being a superset of incident graph nodes is **intentional**, not an error to fix by deleting isolated identities or inventing membership edges for them.

### 8.3 AD&D Has Explicit Legacy Quality Debt

The current invariant findings break down as:

| Finding | Count |
|---|---:|
| Prefix not admitted by the current constitution | 10 |
| Magnitude/grain findings in aspect or condition | 9 |
| Unresolved authored polarity basis | 1,672 |
| **Total** | **1,691** |

They affect 1,674 rows; findings can overlap. The current JSON production schemas accept all rows, so a schema-only test will not detect this quality boundary. The [legacy baseline note](D:/analysis/dnd/rulesets/adnd1e/canonical/BASELINE.md) itself retains `verification_status: pending`, while [integration reporting](D:/analysis/dnd/tooling/integrator/src/adnd1e_integrator/records.py:218) distinguishes retained findings from newly introduced regressions.

For an initial trusted demonstration, use Shadowdark. For AD&D, either expose an expressly labeled legacy/nonconforming projection with exact diagnostics, or define a separately authorized clean subset with clear omissions. Do not silently filter rows, change `heuristic` to `read`, add placeholder prefixes, or claim the import validates source truth. A quality field/report is a conformance disclosure, not a new confidence score attached to each rule.

### 8.4 Shared Documentation and Profiles Need Careful Interpretation

[GRAPH_INVARIANTS.md](D:/analysis/dnd/contracts/GRAPH_INVARIANTS.md) still contains the old fixed 13-edge-type wording, while Shadowdark has 14 governed types including `CLASSIFIED_AS`. The ruleset-aware executable vocabulary handles this; a new exporter must not copy the stale number as a universal whitelist.

Some profile/constitution prose records the original empty bootstrap. Current canonical data and later amendments show that initialization is complete. Conversely, the intentionally empty Shadowdark role profile does not become a finished analytical model merely because many packets are now integrated.

The architectural boundaries originally established in this repository remain useful: evidence before assertions, registry identity separate from graph incidence, explicit ownership, immutable publication history, and query-time interpretation. What needs improvement is consistency and a deliberate read-model contract, not bypassing those boundaries with three convenient tables.

## 9. Acceptance Tests Before Production Use

These are proposed acceptance criteria, not tests I claim to have run against Spanner.

| Area | Required test and expected result |
|---|---|
| Full node population | Export 817 Shadowdark identities, including all 265 without incident edges; export 1,159 assertions for this pinned snapshot. |
| AD&D population | If enabled, export 1,477 registered identities and 5,179 assertions with the chosen explicit legacy-quality policy; no silent omissions. |
| Display authority | `lang_common` exists; `lang_diabolic` displays `Diabolic`; `monster_archangel` displays `Archangel`. Original artifacts remain unchanged. |
| Namespace isolation | Seed the same node ID and citation code in two rulesets. Every scoped graph query and citation join returns only the requested ruleset. |
| Release isolation | Two releases contain different labels/citations/edges. A single request cannot mix them. |
| Assertion identity | Governed normalization and reversed `ALTERNATIVE_TO` endpoints produce the same key; distinct supported aspects/conditions remain distinct. |
| Codec boundaries | Delimiters, quotes, Unicode, empty strings, and NULL conversion are deterministic and follow the authorized policy. No ambiguous serialization or unreviewed normalization. |
| Hash defense | Simulated hash collision or conflicting replay fails instead of overwriting an assertion. |
| Content versus identity | A citation-only correction changes content digest but not semantic identity. Endpoint repoint/identity-changing updates retire the prior assertion in the new release. |
| Lossless payload | Round-trip all 18 canonical columns, including endpoint-label variants, string-valued `pass`, review flags, and empty values. File checksums remain a separate byte-level check. |
| Evidence multiplicity | Two supporting loci produce one assertion, two evidence records, one primary locus, and no inflated edge count. |
| Source instances | Multiple sources for one book do not result in arbitrary edition/printing assignment. Unknown historical source stays explicitly unknown. |
| Citation formatting | Page-only, page-plus-section, and section-only citations render without NULL collapse or workspace paths. |
| Non-packet migrations | A Decision-driven update with no normal packet/GUR retains its valid authority chain. |
| Node-only integration | A zero-edge approved integration can add registered concepts without invented mechanical relationships. |
| Domain constraints | Invalid endpoint, unknown book, illegal type/evidence/status, and invalid supersession/general-rule combinations are rejected before activation. |
| Lengths | Over-limit future text is explicitly rejected or handled by an approved schema change; it is never silently truncated. |
| Derived metrics | Degree/in/out/core values agree with the pinned implementation, including self-edges, parallel assertions, and registry-only identities. |
| Role profile | Shadowdark does not inherit AD&D thresholds; profile changes invalidate derived caches, not immutable source artifacts. |
| Graph property exposure | Expected properties, including caveats and roles where required, are actually queryable, not merely stored in SQL. |
| Dependency direction | Stat-generation changes find the derived abilities through reverse `DERIVED_FROM`; input-to-process discovery follows `FEEDS_INTO` forward. |
| Negative relationships | `EXCLUDES` and `EXCLUDED_FROM` remain distinct and do not become positive propagation paths. |
| Nonmechanical navigation | A cross-reference-only path is not reported as established mechanical impact. |
| Conditional explanation | Conditions and assumptions appear with paths; no unsupported Boolean evaluation or polarity arithmetic. |
| Symmetry | One stored alternative assertion is discoverable from either endpoint without doubled fact or degree counts. |
| Activation | The 39 optional SD assertions are not automatically enabled by selecting the SD publication. Overrides/alternatives follow the reviewed profile. |
| Cycles and bounds | Self-edges/cycles terminate within defined budgets; path explanations, truncation, and pagination remain reproducible. |
| Failed load | Interrupt loading after Nodes and midway through Assertions. The previous active release remains unchanged; a failed first load remains explicitly unpublished, not a successfully published empty graph. |
| Replay | Rerun identical release: no duplicate rows or evidence. Resume a partial release without changing immutable content. |
| Stale activation | A delayed older export cannot replace a newer active release. |
| Canonical removal | A removed or merged-away assertion/identity cannot remain active because the importer only inserts. |
| Snapshot consistency | Concurrent repository changes are detected; mixed-checksum input sets cannot activate. |
| Reconciliation | Compare IDs and full payload digests, not counts alone; equal counts with substituted rows must fail. |
| Rollback | Switching to a retained release restores prior query results without modifying repository canonical state. |
| Ownership and access | The read-only app cannot alter graph data, authority metadata, or active-release pointers. |
| Operational budget | Representative queries meet an agreed latency/cost budget on the intended service configuration. |
| Scope hold | No exporter or test discovers/claims/processes live `basicdnd/rc` inputs. Synthetic fixtures remain isolated. |

Local/emulator tests are useful but not a substitute for validating the target service. The current emulator supports GQL; its graph-algorithm support has limitations, including mocked algorithm results documented by the emulator project. Do not accept an empty analytical result as correctness proof. [Emulator documentation](https://docs.cloud.google.com/spanner/docs/emulator?hl=en), [official emulator repository](https://github.com/GoogleCloudPlatform/cloud-spanner-emulator).

## 10. Recommended Sequence and Ownership

This is a proposed implementation sequence for review, not authorization to begin cloud work or a change to the packet relay.

1. **Architect:** revise the assessment into an explicit read-only projection contract; settle the identity codec, lossless mapping, conformance policy, and exact file ownership. Separate this from an unproven full-impact engine.
2. **Builder, within assigned scope:** implement one deterministic exporter/validator over a frozen Shadowdark snapshot. Reuse established structured readers and validation logic; do not add a separate mini-script for every field or agent step.
3. **Reviewer:** independently verify row/identity completeness, provenance, failure cases, and generated schema/query behavior against the pinned snapshot and acceptance criteria.
4. **Integrator, within assigned scope:** provide the coherent post-integration snapshot/publication hook and verify that projection failure never changes canonical completion or repeats integration.
5. **Owner/Architect:** select deployment configuration and budget after a measured proof of concept. Approve cloud deployment separately from schema review.
6. **Architect plus implementation owner and Reviewer:** define and test activation/impact policy as a second feature, using explained dependency candidates before claiming complete mechanical impact.

The Analyst should not have to republish otherwise valid GURs merely to suit a database backend. The Reviewer should not rereview every already integrated assertion just because it moved into a projection. Replay and validate existing approval evidence; request source/authority work only for a demonstrated semantic gap. The Integrator remains the only canonical writer.

The export manifest should distinguish current projection authority from each historical artifact's originally declared constitution/schema version. A new projection version must not rewrite old artifact declarations or recreate the prior version-churn problems.

## 11. Decisions Still Needed From the Owner

These questions do not prevent the findings above, but they determine the next design iteration:

1. **Partially answered on 2026-10-12:** the target supports multiple users, reusable settings, and campaign-specific layered rules. Section 12 records these requirements. The remaining question is how far rule queries go beyond browsing and explained dependencies into executable rules or numeric calculation.
2. Is Spanner a firm platform choice for an existing Google Cloud deployment, or a candidate to compare on cost and query behavior? What monthly budget and availability are acceptable?
3. Should the first release contain only clean Shadowdark, or also an explicitly disclosed AD&D legacy baseline?
4. Is retaining historical queryable releases useful, or is a current-only view plus reproducible offline snapshots sufficient? The latter can simplify retention but still needs atomic publication and rollback.

My default recommendation is **Shadowdark first; a read-only, versioned query projection; no workflow migration; no new extraction; no invented mechanics; and no claim of a finished impact engine.**

## 12. Multi-Tenant, Four-Layer Rules Design

Added 2026-10-12 to preserve the owner's requirements and the subsequent architectural discussion for a separate Codex session. **Owner requirements below are explicit; implementation choices are recommendations unless marked otherwise.** This is not a published Decision, a schema amendment, or permission to deploy cloud resources.

### 12.1 Owner Requirements

The owner specified:

- Multiple users will query the graph, each with a campaign associated with their current application instance or query context.
- Rules have four precedence layers: **core, optional, setting, campaign**. Each higher layer supersedes lower layers where the applicable rules overlap.
- A user who has access to a setting, such as Forgotten Realms, can use that setting's rules and add campaign rules above them.
- Users can create their own settings.
- Users should be able to start from an existing base setting, customize it, and reuse their customized setting across multiple campaigns. The owner suggested copying as the user-facing model; physical duplication was not required.
- Rules remain associated with their layers; one campaign's changes must not become changes to every user's underlying ruleset.

The earlier proposal supports a shared published graph, **not yet this complete multi-tenant feature set**. Finalizing only its original tables and adding `tenant_id` later would miss ownership, permissions, stable override targets, and versioned campaign composition. Those concepts belong in the design now, even if implementation starts with read-only Shadowdark browsing.

### 12.2 Precedence and Activation

The owner-defined precedence, highest first, is:

```text
Campaign overrides
Setting rules
Selected optional rules
Core rules
```

Recommended interpretation: **the highest authorized, selected, applicable layer wins for an explicitly identified conflict/replacement scope; all unaffected lower-layer behavior remains inherited.** Availability is not activation. Access to several optional packages does not enable all their rules automatically.

Do not overload existing edge `status: core/optional` with these four values. Keep these independent dimensions:

| Dimension | Meaning |
|---|---|
| `ruleset_id` | Compatible rules literature and ontology; not a tenant or campaign. |
| Publication classification | Whether a source assertion is core or optional under the existing contract. |
| Owner/tenant | Who owns a custom resource and can manage it. |
| Resource access | Who may view, use, edit, fork, or share a resource. |
| Activation profile | Which exact packages and versions the campaign selects. |
| Precedence layer | Core, optional, setting, or campaign position in resolution. |
| Provenance | Where an assertion or custom rule came from, independently of whether it currently wins. |

The source graph keeps valid assertions and their evidence. An effective campaign graph selects or derives the active representation without overwriting published source truth.

### 12.3 Copy a Setting as a Versioned Fork

**Recommendation: implement the user's "copy setting" action as a versioned fork with local changes, rather than eagerly copying the whole base graph.**

```text
Published Forgotten Realms setting v3
  -> Jeff's customized setting v1
       -> Campaign A: its own campaign overrides
       -> Campaign B: different campaign overrides
```

Store the exact parent setting version and the user's changes. Campaigns can share the customized setting while retaining independent campaign layers. This is copy-on-write behavior: inherited data stays shared; customization creates owned records.

Recommended invariants:

1. Editing Campaign A does not alter Campaign B, Jeff's shared setting, or the published base setting.
2. Publishing Jeff's setting v2 does not silently upgrade campaigns pinned to v1.
3. Adopting a new parent version is an explicit upgrade with conflict detection. Parent changes must not silently overwrite local customizations.
4. A setting can start without a parent. Parent chains must be acyclic and resolve to existing, accessible, compatible versions.
5. Each setting declares its compatible ruleset. A setting title alone does not establish compatibility across rules editions.
6. A fork retains ancestry and provenance. It does not automatically grant permission to redistribute its parent content or bypass later authorization checks.
7. Parent/fork ancestry does not introduce a fifth precedence layer. Resolve inherited setting content and its local changes within the setting layer, then apply campaign rules above it.

Version pinning is an Architect recommendation, not a separately answered owner preference. It avoids a campaign's rules changing merely because someone else edited a shared setting.

### 12.4 Define Overlap Explicitly

The five-field assertion key answers whether two graph assertions are the same assertion. It does **not** necessarily identify which alternative rules compete for the same mechanical purpose. A change to condition, aspect, or endpoint can create a different assertion while still replacing the same rule behavior.

Introduce a stable rule identity and a precisely defined replacement scope, separate from the content hash of a particular assertion. Never infer conflict solely from matching node labels, a shared endpoint, a shared prefix, or textual similarity.

Recommended authored operations:

| Operation | Meaning |
|---|---|
| Add | Introduce behavior without replacing inherited rules. |
| Replace | Substitute an explicitly identified rule, variant, or assertion bundle within a defined scope. |
| Suppress | Disable inherited behavior in that scope without deleting its history. |
| Inherit | Leave lower-layer behavior unchanged. |

An override should identify its target, replacement coverage, applicability, and replacement payload. Where one rule produces several graph assertions, replace or regenerate the affected bundle consistently. Changing the displayed rule text while leaving the original dependency edges active would make graph queries incorrect.

A conditional campaign override leaves the lower rule applicable outside that condition. Source condition prose is not automatically executable code: machine-resolved conditions need an approved representation, or the response must expose the unresolved applicability rather than pretend it has been evaluated.

Conflicting selections **within one layer** need an explicit choice or governed ordering. Layer precedence alone does not resolve two incompatible optional packages or two contradictory campaign edits. Do not default to last-write-wins, filename order, or an arbitrary traversal order.

Custom rule authoring also needs a representation for the rule definition itself and its authored provenance. The current mechanical relationship graph deliberately is not a complete rules-text, numeric parameter, or creature-stat-block database. Do not silently expand the canonical edge vocabulary or store excluded mechanics merely to support the new UI. Define the authoring representation and its graph projection separately.

### 12.5 Additional Logical Tables

These extend the earlier published projection model. Names and keys remain proposed, not deployed DDL.

| Entity | Responsibility |
|---|---|
| `Tenants`, `Memberships` | Ownership boundaries and their users; a tenant can begin as a personal workspace and later support a group. |
| `Settings`, `SettingVersions` | Stable setting identity, immutable published versions, compatible ruleset, exact parent version, and customization history. |
| `Campaigns`, `CampaignMembers` | Campaign ownership, participating users, member roles, and its selected activation profile/version. |
| `RulePackages`, `PackageVersions` | Versioned rule collections contributing to the selected core, optional, setting, or campaign layer. |
| `RuleVariants`, `RuleOverrides` | Authored rule definitions, graph assertion bundles, explicit replacement/suppression targets, and applicability. |
| `ResourceGrants` | Permission to view, use, edit, fork, or share a setting/package; resource access is not the same as tenant membership. |
| `ActivationProfiles` | Campaign-specific composition: exact source releases, selected package/setting/campaign versions, precedence, and same-layer conflict choices. |
| `EffectiveGraphBuilds` | Rebuildable resolved graph outputs, their input/version digest, resolver version, and explanations of winning and shadowed rules. |

A user, tenant, campaign, setting, and ruleset are separate identities. Do not key every resource only by user ID: several users can participate in a campaign, and one user can participate in several ownership contexts.

Published nodes/assertions remain shared. Custom identities need an ownership-qualified namespace so two users independently creating the same local node name cannot collide. References to published identities remain references to those identities; do not create per-user copies just to attach an override. Cross-resource references must resolve to compatible, authorized resources.

The exact physical split between authoring storage and Spanner's query projection remains open. Multi-user custom-rule writes need a separately scoped, validated publication path; they must not become direct writes to the repository's shared canonical files. The existing Integrator-only canonical ownership boundary remains intact.

### 12.6 Query and Permission Context

Every request follows this conceptual resolution:

```text
Authenticated user
  -> authorized tenant/campaign membership
  -> pinned activation profile and accessible resource versions
  -> resolved effective campaign graph
  -> query result with provenance and override explanation
```

The active campaign can be remembered in an application session, but the server must validate it on every request. A client-provided campaign or tenant ID is a selection, not proof of authorization. A missing or invalid campaign context must not silently select another campaign's private graph.

Resolve precedence and suppression **before graph traversal**. Filtering only the final result can still let an inactive or inaccessible rule create an intermediate path. Access boundaries apply to nodes, assertions, explanations, provenance, and cached results.

Return enough evidence to explain the result, for example: "Campaign rule X replaces setting rule Y for this scope; the original core assertion remains available in authorized history." Query access does not imply edit, fork, or redistribution access.

Materializing a resolved campaign graph is an optimization, not a second canonical authority. Reuse it across authorized campaign members when their visible rule sets are identical. Cache identity must include the campaign/profile composition, exact input versions, and resolver policy. Always recheck authorization; a cached build must not preserve access after a grant is revoked. Where member visibility differs, shared caches must not expose otherwise hidden rules or explanations.

Spanner supports multi-tenant storage patterns, but tenant-aware application authorization is still necessary; a primary-key prefix is not access control. Appropriate graph views and database permissions can reinforce the boundary. No deployment/security configuration is approved by this design note. [Spanner multi-tenancy guidance](https://docs.cloud.google.com/spanner/docs/implement-multi-tenancy), [graph views and access control](https://docs.cloud.google.com/spanner/docs/graph/graph-with-views-how-to).

### 12.7 Unanswered Product Decisions

The following must remain questions, not assumptions silently filled by a new session:

1. **Campaign sharing:** when the owner has access to a setting, do campaign members gain campaign-scoped access to its rules, or must each member independently have access? The owner has not answered this question.
2. **Same-layer conflicts:** how should users resolve conflicting optional packages or setting components? The recommendation is explicit selection/order, not last-write-wins.
3. **Setting composition:** is there one selected setting, or can several setting packages compose? Parent/fork ancestry is supported by the recommendation; arbitrary multiple-setting composition is not yet specified.
4. **Version adoption:** confirm pinned versions and explicit upgrades versus any requested automatic-update behavior.
5. **Authoring depth:** will queries return rule text and dependencies, or execute conditions/formulas? This controls how much structured rule authoring is necessary.
6. **Access changes:** define campaign behavior after the owner loses access, a shared setting is withdrawn, or a parent resource is deleted. Pinning data does not itself settle access rights.

### 12.8 Additional Acceptance Criteria

- The same core rule can resolve differently in two campaigns without changing the shared source graph.
- A campaign override wins over setting, optional, and core rules for its explicit applicable scope; unrelated lower-layer rules remain inherited.
- An unselected optional package never activates merely because the user can access it.
- A setting fork changes only its local customization records; siblings and its published parent stay unchanged.
- A parent update does not alter pinned campaigns; explicit upgrade reports conflicts with local edits.
- Add, replace, suppress, and inherit behavior is deterministic; suppression cannot leave stale dependency paths active.
- Same-layer ambiguity prevents an unexplained effective-graph publication.
- A partial/conditional override preserves lower-layer behavior outside its coverage, or explicitly reports applicability that the system cannot determine.
- Tenant-owned identities do not collide, and guessed campaign/resource IDs do not bypass authorization.
- Unauthorized intermediate nodes, evidence, and cache entries cannot influence or leak through query results.
- A custom rule update changes its relevant assertion bundle and invalidates affected effective-graph caches.
- Results record the profile, versions, resolver policy, selected rule origin, and explanation for an override.
- None of these application features rewrites published source assertions, bypasses canonical ownership, or resumes RC work.

## 13. Handoff to a Separate Codex Session

This document now contains the Spanner review, the owner's four-layer/multi-user requirements, the recommended design, and unresolved questions. It is a **curated architecture handoff, not a verbatim transcript of the entire conversation**.

For a fresh session on another computer:

1. Make this report and the original assessment available in the destination repository, normally through the owner's commit and normal repository synchronization. This editing task does not itself make a commit or push.
2. Read the destination repository's startup instructions and perform its normal scoped Architect startup with a new actor-session receipt. Do not copy or reuse this session's context receipt as authority.
3. Read this report, emphasizing sections 11 and 12, then inspect only the current files necessary for the next assigned design question. Historical counts/checksums are dated evidence, not a claim that the destination has identical current bytes.
4. Keep explicit owner requirements separate from recommendations and unanswered questions. Do not treat the report as a production Decision or assume implementation already exists.
5. Preserve NO RC and canonical ownership. Do not recreate extraction or packet work merely to prepare the database design.

The earlier absolute links refer to the review machine's `D:/analysis/dnd/` checkout. On another machine, resolve their repository-relative suffixes against that machine's checkout. The `.local/spanner-review/` audit files are ignored scratch artifacts and **will not travel in a normal Git commit**. The report embeds the key measurements and hashes, but independent reruns require transferring the audit harness separately or recreating the bounded read-only checks; do not claim an unavailable harness was run.

Suggested opening prompt for a new session:

```text
You are Architect for this repository. Follow AGENTS.md and normal scoped
Architect startup. Read SPANNER_GRAPH_CONVERSION_REVIEW.md and the original
SPANNER_GRAPH_CONVERSION_ASSESSMENT.md. The review's section 12 records the
owner's multi-user, four-layer requirements: campaign > setting > selected
optional > core. Treat its implementation details as recommendations, not
published Decisions. The campaign-member setting-access question is unanswered.
Continue architecture discussion from this document; first summarize the
remaining decisions and propose the next bounded design step. Do not deploy,
change canonical data, resume RC, or start implementation without assignment.
Resolve document paths against this checkout and verify current inputs rather
than borrowing a prior session's receipt or relying on old conversation state.
```

### Continuing the Actual Conversation Elsewhere

As documented on 2026-10-12, the desktop app supports handing a chat and its Git state to a connected host with a matching saved repository project. Choose the current run location in the chat footer, select the destination, and review **Hand off**. This is distinct from remotely accessing the original host, where execution and local resources remain on that host. Feature availability and workspace policy can vary. [Official remote connections and chat handoff documentation](https://learn.chatgpt.com/docs/remote-connections#hand-off-a-chat-between-hosts).

For CLI use, `codex resume` continues an existing available session, and `codex fork` creates a separate conversation from existing history. These commands alone are not a promise of automatic history synchronization to a new computer or a merge into an unrelated existing chat. [Official CLI reference](https://learn.chatgpt.com/docs/cli/reference).

The supported handoff/remote features were researched, not configured or executed in this task. No conversation store, credentials, host settings, or remote connection was changed. The Markdown handoff remains the straightforward alternative for a clean independent session.

## Appendix A. Evidence and Reproduction

The evidence harness was rerun successfully at **2026-10-11 23:39:10 -04:00**, expanding the evidence to **755 pinned input files** with no detected drift. This includes the additional 145 Review checksum checks. The preceding 23:30 recheck had also found all 610 original pinned inputs unchanged.

To reproduce the local evidence only, from the repository root:

```powershell
python .local/spanner-review/audit.py
```

It reads only the named Shadowdark/AD&D inputs and writes its own scratch JSON report. It does not load cloud data, alter canonical files, or select packet work. It requires the repository's existing Python/YAML/JSON-schema dependencies. Its process exit status detects input drift; the embedded per-ruleset validator results must also be inspected. AD&D's nonzero invariant result is intentionally reported rather than hidden.

Selected pinned SHA-256 values:

| Input | SHA-256 |
|---|---|
| Assessment | `27f7188462be1fac30fdcd9e343e29899ede60618e992823f2d6ffd7fedb327b` |
| Shadowdark edges | `2cbd0d165517ed1b958a1f7079919e001b652d9367f9d6029eae358d43211c11` |
| Shadowdark derived nodes | `b0d3bb3e60494733d3a61a07227c00be247553752d0dec5173538a267916f6d4` |
| Shadowdark identity registry | `bf2e5013fcf229a7cbc336eda1fbce57b68d9f6bf07e335bfae1366040cdb9b4` |
| Shadowdark book registry | `b6801509f8ddbad75924829c13f70c8a286c4a38f0651f64ad1450494ea10a33` |
| AD&D edges | `e321666ea303ab65c1303bb1c120ccc8fb80a176c6dc2f45147532495dce549b` |
| AD&D identity registry | `86fb45e10781aa578606cad95bc36ca02d03d2dfe171d0e3276b345b12cd7bef` |

The Shadowdark book-title edits were already present and uncommitted when this review began. The report uses those current bytes and pins their hash; it does not assume they are part of the last integration or silently approve unrelated metadata changes. The original assessment remains untouched. Official Spanner documentation was checked during the review, but all proposed SQL still requires execution tests on the chosen database/client versions.

## Appendix B. Direct Answers to Gemini's Questions

**Discrete labels or property filtering?** Start with the generic table/property representation. Filtered views or dynamic labels are valid alternatives under the current product, but a performance winner requires representative plans and measurements. Neither option repairs undefined impact semantics.

**Sequential IDs or hashes?** Use deterministic, governed assertion IDs for reproducibility. A hash is appropriate once the codec is settled. Do not introduce sequential row IDs or random-per-import UUIDs. At this scale, solve correctness and adjacency access first; measure before adding sharding.

**Two stored directions for `ALTERNATIVE_TO`?** No. Store one assertion and use a type-restricted undirected query. Any doubled traversal representation must be explicitly derived, preserve the originating assertion ID, and never double-count facts.

## 14. Peer Architect Appraisal and Owner Resolutions (2026-10-12)

**Author:** Architect (Gemini)  
**Date:** 2026-10-12, America/New_York  
**Status:** Architecture consensus and owner-approved scope  

### 14.1 Peer Review & Architectural Endorsement

Codex's review in Sections 1–13 is endorsed in full. The empirical verification against the repository's canonical artifacts identified vital architectural boundaries that were absent or oversimplified in the initial assessment:

1. **Identity Completeness (`registries/nodes.csv` vs. `canonical/nodes_master.csv` - F01):**
   - The initial proposal's plan to import `nodes_master.csv` would have dropped **265 registered identities** (leaving only the 552 incident nodes).
   - Ingestion must populate `Nodes` from `registries/nodes.csv` (all 817 concepts) and left-join `nodes_master.csv` solely for incident metrics (degree, core degree, roles). Zero-edge identities (e.g. languages, reference tables) are intentional registry citizens.
2. **Mechanical Impact Directionality (F02):**
   - Unrestricted forward graph traversal (`MATCH (a)-[r]->*(b)`) is not rules impact analysis.
   - Certain edge types flow opposite to dependency propagation: `DERIVED_FROM` points from derived value to source (`abil_charisma --DERIVED_FROM--> rule_stat_generation`), meaning a stat generation change impacts charisma *in reverse*. `CONSUMES` and `RESOLVED_BY` also require reverse dependency discovery.
   - The projection query layer must implement an edge-type-aware traversal policy rather than raw topological reachability.
3. **Exact Cloud Spanner GQL / SQL Syntax (F06):**
   - Spanner's `GRAPH_TABLE` implementation conforms to ISO GQL: scalar outputs require `RETURN` (with explicit aliases for outer SQL), path repetition uses quantified syntax (`-[r:Relationship]->{1,3}` rather than Cypher-style `*1..3`), and client batching uses `database.batch()`.
4. **Namespace and Release Isolation (F04, F08):**
   - With 118 shared concept IDs across rulesets, all compound keys and queries must strictly enforce `(ruleset_id, release_id)`.
   - Release management uses immutable snapshots (`ProjectionReleases`) and atomic pointer activation (`ActiveProjections`), preventing dirty or partial loads from being queried.
5. **Multi-Tenant Layering & Copy-on-Write Setting Forks (Section 12):**
   - The 4-layer precedence model (`Campaign > Setting > Selected Optional > Core`) and the four explicit operations (`Add`, `Replace`, `Suppress`, `Inherit`) provide a robust conceptual model.
   - The "copy setting" user action is modeled as a versioned copy-on-write fork (`SettingVersions` with `parent_version_id` and local diffs), avoiding massive redundant graph cloning while pinning versions so upstream changes never break live campaigns.

---

### 14.2 Owner Decisions and Resolution of Open Questions

On 2026-10-12, the owner provided direct decisions resolving key questions from Sections 11 and 12.7:

| Open Question | Owner Decision | Architectural Consequence |
|---|---|---|
| **1. Campaign-scoped setting access** (Section 12.7, Question 1) | **Players have access for free.** They will not be querying the raw rules graph directly, but they have access to the active rules in the campaign. | Access to setting rules is inherited via `CampaignMembers` and the campaign's active profile. Players do not require independent setting licenses to consume rules during play. Out-of-campaign customization and forking remain bounded by tenant/setting ownership. |
| **2. Initial release corpus** (Section 11, Question 3) | **Focus first on Shadowdark. No AD&D right now.** | Phase 1 is strictly scoped to Shadowdark (817 concepts, 1,159 edges, 0 invariant findings). AD&D 1e (1,691 historical invariant findings) and Rules Cyclopedia (paused under DEC-2026-0086) are completely excluded from initial export tooling. |

---

### 14.3 Next Step: Phase 1 Local Shadowdark Exporter

Per the agreed sequence in Section 10:
1. Construct a deterministic Python exporter/validator (`tooling/spanner/`) operating strictly on a frozen local Shadowdark snapshot.
2. Ingest 100% of registry concepts (817) and canonical edges (1,159) lossless across all 18 columns.
3. Compute governed assertion hashes and output release manifests with row-set digests.
4. Run 100% locally with zero billable cloud infrastructure until local verification is complete.
