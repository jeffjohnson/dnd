# Tooling

Tooling is universal unless a ruleset adapter is explicitly required.

- Builder owns deterministic normalization, migration, schema validation, and GUP compilation.
- Reviewer owns inspection aids and review-schema validation, not automated source interpretation.
- Integrator owns transactional patch application, exports, manifests, and rollback.

Ruleset-specific adapters should live under `tooling/<role>/src/adapters/<ruleset-id>/`, with tests proving that universal behavior remains unchanged.
