# Repository Instructions

This repository builds ruleset-specific mechanical relationship graphs.

## Required startup

Before performing work

1. Read `README.md`.
2. Read `REPOSITORY_STRUCTURE.md`.
3. Read all files in `contracts`.
4. Determine the assigned role from the user's task.
5. Read the matching role instructions under `agents/<role>/INSTRUCTIONS.md`.
6. Resolve `ruleset_id`, `book_id`, `source_id`, and `packet_id` from repository artifacts.
7. Treat the repository, not chat history, as project memory.

## Ownership

Ownership is defined by the authority hierarchy in `REPOSITORY_STRUCTURE.md` and by the
"Prohibited actions" section of each role's `agents/<role>/INSTRUCTIONS.md`.

Only the Integrator may modify

`rulesets/<ruleset-id>/canonical/`

## Validation

Run all applicable validations before completing work.