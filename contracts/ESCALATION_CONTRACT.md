# Escalation Contract

**Version 1.2.**

Escalation is for architecture, not ordinary uncertainty.

## Escalate to Architect when

- no existing node ID represents the concept and a new kind or prefix may be needed;
- two canonical nodes appear ontologically equivalent and merging them could affect existing edges;
- an edge does not fit the closed vocabulary;
- a proposed interpretation changes edge semantics or direction globally;
- a candidate domain recurs and may merit promotion;
- a proposed general rule creates inherited edges;
- a Tier 3 role is proposed;
- source books conflict and current supersession categories are insufficient;
- the constitution and production data disagree in a way that cannot be fixed mechanically;
- a migration would rewrite existing approved assertions.

## Do not escalate when

- a typo can be corrected without changing identity;
- a known canonical ID exists;
- a field can be normalized under existing rules;
- a proposed node uses an approved prefix and kind, passes identity and duplicate
  checks, and can be isolated as a normal GUP registry addition;
- a citation is missing or weak;
- an edge is unsupported and should simply be rejected;
- the source packet is incomplete and should be returned for re-packetization;
- a deterministic validator can decide the issue.

## Escalation package

Every escalation must include:

1. escalation ID;
2. originating packet/GUR/GUP/review IDs;
3. exact question requiring governance;
4. smallest relevant source excerpt;
5. local graph neighborhood;
6. affected canonical IDs;
7. options considered;
8. recommended resolution;
9. expected migration impact;
10. whether the constitution, registry, or profile would change.

The escalation ID and filename must follow `contracts/FILE_NAMING.md`. New IDs
use its UTC timestamp form. The YAML `id` must equal the filename stem, and the
ID must be unique across every escalation state folder in the ruleset.

## Version history

- **1.2 - 2026-07-30:** Adopted the timestamped escalation-ID contract and
  required filename-stem equality plus ruleset-wide uniqueness.
- **1.1 - 2026-07-29:** Clarified that an otherwise valid node registration under
  an existing approved prefix and kind is normal Builder/Reviewer work, not an
  Architect escalation merely because the ID is absent from the registry.
