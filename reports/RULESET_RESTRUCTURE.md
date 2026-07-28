# Ruleset-First Restructure

The original package assumed one source collection. This revision introduces a ruleset-first namespace:

- universal agents and contracts remain at repository root;
- graph ontology and canonical state live under `rulesets/<ruleset-id>/`;
- source and workflow artifacts live under `books/<ruleset-id>/<book-id>/`;
- book-specific extraction schemas live under `schemas/<ruleset-id>/books/<book-id>/`;
- the legacy multi-book AD&D dump is preserved under `migrations/adnd1e/legacy-import/`.

No legacy artifact has been declared canonical or silently rewritten.
