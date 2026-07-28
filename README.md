# Mechanical Relationship Graph Agents

A repository-first, multi-agent pipeline for building mechanical relationship graphs from tabletop role-playing game literature.

The five agents are universal and stateless:

1. **Architect** — governs ontology, registries, and durable contracts.
2. **Analyst** — extracts mechanically load-bearing relationships from one bounded source packet.
3. **Builder** — compiles a GUR into a deterministic, schema-valid GUP.
4. **Reviewer** — independently verifies proposed assertions against source and constitution.
5. **Integrator** — transactionally applies approved patches to the canonical ruleset graph.

## Namespace model

Repository data is organized by compatible **ruleset**, then by source **book**:

```text
books/<ruleset-id>/<book-id>/...
schemas/<ruleset-id>/books/<book-id>/...
rulesets/<ruleset-id>/...
```

A ruleset is the graph and ontology shared by a compatible body of literature. For example, `adnd1e` may include the PHB, DMG, Monster Manual, Unearthed Arcana, and later compatible AD&D 1e publications.

A book workspace contains source files and intermediate artifacts for one work. It does not own a separate graph. Approved work from every book is integrated into the ruleset-wide canonical graph.

## Start here

1. Read `REPOSITORY_STRUCTURE.md`.
2. Initialize each console with one file under `agents/<role>/INSTRUCTIONS.md`.
3. Assign the agent a repository task containing `ruleset_id`, `book_id`, `source_id`, and `packet_id` as applicable.
4. Keep decisions and state in repository artifacts, not chat history.

## Initial ruleset

`adnd1e` is initialized with four book workspaces:

- `phb`
- `dmg`
- `mm`
- `ua`

The prior combined dump is preserved under `migrations/adnd1e/legacy-import/`. It is not yet canonical under Constitution v1.2.
