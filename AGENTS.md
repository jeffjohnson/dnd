# Repository Instructions

This repository builds ruleset-specific mechanical relationship graphs.

## Required startup

Before performing work:

1. Read `README.md`.
2. Read `REPOSITORY_STRUCTURE.md`.
3. Read all files in `contracts/`.
4. Determine the assigned role from the user's task.
5. Read the matching role instructions:
   - Architect: `agents/architect/INSTRUCTIONS.md`
   - Analyst: `agents/analyst/INSTRUCTIONS.md`
   - Builder: `agents/builder/INSTRUCTIONS.md`
   - Reviewer: `agents/reviewer/INSTRUCTIONS.md`
   - Integrator: `agents/integrator/INSTRUCTIONS.md`
6. Resolve `ruleset_id`, `book_id`, `source_id`, and `packet_id` from repository artifacts.
7. Never rely on prior conversation history as project state.

## Safety and ownership

Follow the authority hierarchy in `REPOSITORY_STRUCTURE.md` and the ownership and
prohibited-action boundaries in the matching `agents/<role>/INSTRUCTIONS.md`.

Only the Integrator may modify files under:

`rulesets/<ruleset-id>/canonical/`

Do not reinterpret legacy files as current artifacts unless they have been migrated and validated.

## Validation

Run applicable schema, graph, and repository validation before declaring work complete.
