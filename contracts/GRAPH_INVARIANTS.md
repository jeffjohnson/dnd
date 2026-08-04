# Graph Invariants

**Version 1.0.**

These invariants are executable truths. Builder and Integrator tooling must enforce them. Reviewer verifies the subset that requires source interpretation.

## Identity

1. Every edge references existing canonical source and target nodes.
2. Every node has exactly one canonical ID.
3. Every canonical ID follows an approved prefix and `snake_case` format.
4. Labels do not determine identity; IDs do.
5. A rule and its table are separate nodes only when separately referenced.

## Edge contract

6. Every edge has exactly the production columns defined by the constitution.
7. Every edge uses one of the thirteen legal edge types.
8. Every edge direction follows the edge vocabulary.
9. Every edge has a source citation: book plus section and/or page.
10. Every edge has one evidence class.
11. No magnitude, die expression, numeric bonus, threshold value, or copied rule prose appears in `aspect` or `condition`.
12. Each ruleset constitution defines its assertion key. Two edges equal under that key are duplicate identity and cannot both enter production; tooling must not invent, omit, or widen key fields.

## Polarity

13. Derived polarity is assigned only by the build system.
14. Workers do not author polarity for deterministic edge types.
15. `MODIFIES`, `TRIGGERS`, and `CONSTRAINS` must have reviewed authored polarity before approval.
16. No Approved GUP retains `polarity_basis=heuristic` or `polarity_basis=unset`.
17. Polarity and polarity basis must agree with the constitution's derivation table.

## Provenance

18. `general_rule_id` is populated only for edges derived under an approved general rule.
19. `general_rule_id` is empty on the edge that establishes the general rule.
20. `supersession_basis` is populated only for `OVERRIDES` and is required for every `OVERRIDES` edge.
21. Every master edge retains its originating packet, GUR, GUP, review, and integration batch in the manifest or provenance ledger.

## Roles and semantics

22. Derived roles are never manually edited.
23. Tier 3 roles require an Architect decision.
24. Free-form semantic edges do not enter the mechanical graph.
25. Severity is never stored on an edge.

## Workflow

26. Analyst never mutates canonical graph files.
27. Builder never changes ontology without escalation.
28. Reviewer never approves an unresolved architectural question.
29. Integrator applies only Approved GUPs.
30. Only Integrator tooling mutates canonical graph artifacts.
31. No role requires another role's conversation history.
32. Every handoff is complete, machine-readable, and independently auditable.

## Version History

- **1.0 - 2026-08-03:** Made the active ruleset constitution authoritative for
  assertion identity and prohibited tooling from choosing a different key.
