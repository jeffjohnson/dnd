# Scope and Identity Contract

Every workflow artifact must declare enough identity to resolve its repository scope without conversation history.

## Required identifiers

- `ruleset_id`: compatible literature family and ontology.
- `book_id`: source work for book-scoped artifacts.
- `source_id`: exact edition, printing, scan, or transcription.
- `packet_id`: bounded work unit, when applicable.
- `schema_version`: artifact schema version.
- `constitution_version`: governing constitution version.

## Rules

1. A book belongs to exactly one ruleset namespace in a repository path.
2. One physical work may have multiple `source_id` records.
3. Book artifacts may reference ruleset-wide nodes and graph neighborhoods.
4. Cross-book artifacts must identify every participating book/source.
5. No agent may silently move an artifact between rulesets.
6. Runtime activation choices are called `activation_profile_id`, not `ruleset_id`.
