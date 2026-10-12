# Cloud Spanner Graph Conversion Assessment

**Date:** 2026-10-11  
**Role:** Architect  
**Repository:** Ruleset Mechanical Relationship Graph  
**Status:** Proposal / Review Ready  

---

## 1. Executive Summary

This assessment evaluates migrating or projecting the repository's ruleset mechanical relationship graph (currently Shadowdark RPG and AD&D 1e) into **Google Cloud Spanner Graph**.

The graph models mechanical dependencies between rules, classes, spells, ancestries, items, and combat mechanics to support ruleset impact analysis (e.g., *"If rule X is altered, what downstream mechanics are impacted?"*). 

The Shadowdark canonical baseline currently consists of:
- **817 Registered Concepts** (`nodes.csv` / `nodes_master.csv`)
- **1,159 Canonical Mechanical Edges** (`edges_master.csv`)
- **18 Controlled Edge Attributes** (including book, page, section, aspect, condition, polarity, evidence, and core/optional status)
- **144 Integrated Intake Packets** across the core rulebook

Cloud Spanner Graph is an optimal target because it natively implements the **ISO GQL (Graph Query Language)** standard directly on top of distributed relational tables, enabling seamless hybrid GQL + SQL queries, multi-hop traversals, and horizontal scalability without separate graph database infrastructure.

---

## 2. Core Architectural Separation: Citations vs. Display Titles

A core requirement is decoupling internal citation codes from presentation titles:
- In the graph, citations are stored as concise, deterministic codes: `book = 'SD'`, `page = 14`.
- On disk, intake files are stored in packetized paths (`books/shadowdark/sd/packets/...`), which must never leak to end users.
- In presentation, citations must resolve to real-world publication titles (e.g., `"Shadowdark RPG p. 14"`, `"Cursed Scroll 1: Diablerie p. 7"`).

In Spanner Graph, this is resolved via a relational dimension table (`Books`) joined directly with property graph queries via `GRAPH_TABLE`.

---

## 3. Relational Table Schema DDL

Spanner Graph constructs property graphs over standard Cloud Spanner relational tables. Three tables back the graph: `Books`, `Nodes`, and `Edges`.

```sql
-- 1. Books Registry (Dimension / Citation Resolution Table)
CREATE TABLE Books (
  ruleset_id STRING(32) NOT NULL,
  citation_code STRING(16) NOT NULL,
  book_id STRING(32) NOT NULL,
  title STRING(256) NOT NULL,
  source_authority STRING(64) NOT NULL,
) PRIMARY KEY (ruleset_id, citation_code);

-- 2. Nodes (Concepts & Entities)
CREATE TABLE Nodes (
  ruleset_id STRING(32) NOT NULL,
  node_id STRING(128) NOT NULL,
  label STRING(256) NOT NULL,
  kind STRING(32) NOT NULL,
  degree INT64,
  core_degree INT64,
  in_degree INT64,
  out_degree INT64,
  roles STRING(MAX),
) PRIMARY KEY (ruleset_id, node_id);

-- 3. Edges (Mechanical Dependencies & Relationships)
CREATE TABLE Edges (
  ruleset_id STRING(32) NOT NULL,
  edge_id STRING(64) NOT NULL,
  source_id STRING(128) NOT NULL,
  target_id STRING(128) NOT NULL,
  edge_type STRING(32) NOT NULL,
  aspect STRING(128) NOT NULL,
  condition STRING(256),
  polarity STRING(32),
  polarity_basis STRING(32),
  citation_code STRING(16) NOT NULL,
  page INT64,
  section STRING(128),
  evidence STRING(64),
  status STRING(32) NOT NULL,  -- 'core' vs 'optional'
  supersession_basis STRING(64),
  general_rule_id STRING(128),
  review_flag STRING(128),
  CONSTRAINT FK_Edges_Source FOREIGN KEY (ruleset_id, source_id) 
    REFERENCES Nodes (ruleset_id, node_id),
  CONSTRAINT FK_Edges_Target FOREIGN KEY (ruleset_id, target_id) 
    REFERENCES Nodes (ruleset_id, node_id),
  CONSTRAINT FK_Edges_Book FOREIGN KEY (ruleset_id, citation_code) 
    REFERENCES Books (ruleset_id, citation_code)
) PRIMARY KEY (ruleset_id, edge_id);
```

### Key Design Notes:
- **`ruleset_id` as Root Partition Key**: Multi-tenant isolation for multiple game systems (`shadowdark`, `adnd1e`, `basicdnd`).
- **`edge_id` Generation**: Deterministic SHA-256 hash or UUID derived from the canonical assertion key `(source_id, edge_type, target_id, aspect, condition)`.

---

## 4. Spanner Property Graph Definition (`CREATE PROPERTY GRAPH`)

With the relational tables defined, the property graph schema exposes the relational data to ISO GQL:

```sql
CREATE PROPERTY GRAPH DndRulesGraph
  NODE TABLES (
    Nodes
      KEY (ruleset_id, node_id)
      LABEL Concept
      PROPERTIES (
        ruleset_id,
        node_id,
        label,
        kind,
        degree,
        core_degree,
        in_degree,
        out_degree
      )
  )
  EDGE TABLES (
    Edges
      KEY (ruleset_id, edge_id)
      SOURCE KEY (ruleset_id, source_id) REFERENCES Nodes (ruleset_id, node_id)
      DESTINATION KEY (ruleset_id, target_id) REFERENCES Nodes (ruleset_id, node_id)
      LABEL Relationship
      PROPERTIES (
        ruleset_id,
        edge_id,
        edge_type,
        aspect,
        condition,
        polarity,
        polarity_basis,
        citation_code,
        page,
        section,
        evidence,
        status,
        supersession_basis,
        general_rule_id
      )
  );
```

---

## 5. Query Patterns & Use Cases

### 5.1 Hybrid GQL + SQL: Resolving Human-Readable Real-World Citations

Spanner allows blending GQL graph pattern matching with standard SQL relational joins using the `GRAPH_TABLE` operator:

```sql
SELECT 
  src.label AS upstream_mechanic,
  r.edge_type,
  dst.label AS target_mechanic,
  r.aspect,
  r.polarity,
  -- Dynamic resolution to real-world title:
  b.title || ' p. ' || CAST(r.page AS STRING) AS citation_display
FROM GRAPH_TABLE(
  DndRulesGraph
  MATCH (src:Concept)-[r:Relationship]->(dst:Concept {node_id: 'rule_hit_points'})
  COLUMNS (
    src.label,
    r.edge_type,
    dst.label,
    r.aspect,
    r.polarity,
    r.citation_code,
    r.page
  )
)
JOIN Books b 
  ON b.citation_code = r.citation_code;
```

**Output Example:**
| upstream_mechanic | edge_type | target_mechanic | aspect | polarity | citation_display |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Stout | MODIFIES | Hit Points | starting hit points | improves | Shadowdark RPG p. 16 |
| Constitution | FEEDS_INTO | Hit Points | hit point value | neutral | Shadowdark RPG p. 14 |
| Damage | MODIFIES | Hit Points | current total | worsens | Shadowdark RPG p. 9 |

---

### 5.2 Multi-Hop Mechanical Impact Analysis

When evaluating rules changes, designers need to know all transitive dependencies within $N$ steps:

```sql
-- Find all downstream mechanics affected by changing Hit Points up to 3 hops away
SELECT DISTINCT 
  target.node_id,
  target.label,
  target.kind
FROM GRAPH_TABLE(
  DndRulesGraph
  MATCH (origin:Concept {node_id: 'rule_hit_points'})-[r:Relationship*1..3]->(target:Concept)
  COLUMNS (
    target.node_id,
    target.label,
    target.kind
  )
);
```

---

### 5.3 Filtering Core vs. Optional Rules

To support campaigns that use only core rules versus those enabling supplements like *Cursed Scroll 1: Diablerie* (`CS1`):

```sql
-- Core rules only
SELECT src.label, r.edge_type, dst.label, r.aspect
FROM GRAPH_TABLE(
  DndRulesGraph
  MATCH (src:Concept)-[r:Relationship]->(dst:Concept)
  WHERE r.status = 'core'
  COLUMNS (src.label, r.edge_type, dst.label, r.aspect)
);

-- Core + Supplement (SD + CS1)
SELECT src.label, r.edge_type, dst.label, r.aspect, r.status
FROM GRAPH_TABLE(
  DndRulesGraph
  MATCH (src:Concept)-[r:Relationship]->(dst:Concept)
  WHERE r.citation_code IN ('SD', 'CS1')
  COLUMNS (src.label, r.edge_type, dst.label, r.aspect, r.status)
);
```

---

## 6. Ingestion Pipeline from Repository Artifacts

| Source File | Spanner Table | Transformation Logic |
| :--- | :--- | :--- |
| `rulesets/<ruleset>/registries/books.yaml` | `Books` | Direct insert (`citation_code`, `title`, `source_authority`). |
| `rulesets/<ruleset>/canonical/nodes_master.csv` | `Nodes` | Map `id` $\rightarrow$ `node_id`, preserve label, kind, and degree counts. |
| `rulesets/<ruleset>/canonical/edges_master.csv` | `Edges` | Compute `edge_id = sha256(source_id + "|" + edge_type + "|" + target_id + "|" + aspect + "|" + condition)`, map `book` $\rightarrow$ `citation_code`. |

Ingestion can be handled via:
1. **Python Ingestion Script**: Using `google-cloud-spanner` and batch mutation API (`spanner_client.batch_insert()`).
2. **Cloud Storage + Dataflow / Avro**: Exporting canonical CSV/YAML to Parquet/Avro and importing directly via Spanner import jobs.

---

## 7. Architectural Questions for Codex Review

1. **Label Modeling Tradeoffs**:
   - *Option A*: Single `Relationship` label with `edge_type` as a property (as proposed above).
   - *Option B*: Discrete GQL edge labels per edge type (e.g., `LABEL Modifies`, `LABEL Gates`, `LABEL FeedsInto`) dynamically mapped using `WHERE edge_type = 'MODIFIES'`.
   - *Review question*: Does Spanner Graph query optimizer perform better on discrete edge labels versus property filtering for path traversals?
2. **Hotspotting & Primary Key Design**:
   - `(ruleset_id, node_id)` and `(ruleset_id, edge_id)` are natural primary keys. Does having sequential edge IDs or hashed UUIDs provide better write distribution during large batch ingestions?
3. **Directed vs. Undirected Edges**:
   - Spanner Graph edges are directed. `ALTERNATIVE_TO` in the ontology is symmetric. Should `ALTERNATIVE_TO` be stored as bidirectional directed edges or handled via undirected match syntax `(a)-[r:Relationship]-(b)`?
