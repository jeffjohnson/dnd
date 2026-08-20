# Repository Instructions

This repository builds ruleset-specific mechanical relationship graphs.

## Required startup

Before performing work:

1. Determine the assigned role from the user's task.
2. Resolve `ruleset_id`, `book_id`, `source_id`, and `packet_id` from the work
   item and its repository manifest.
3. Run `tooling/common/role_context.py verify` for that role and scope, as
   specified by `contracts/ROLE_CONTEXT_LOADING.md` and
   `contracts/ROLE_CONTEXT_MANIFEST.yaml`. Until the verifier is installed,
   read the manifest and treat startup as a cache miss; do not manufacture or
   trust a receipt.
4. On a cache miss, read every stable authority file emitted by the verifier,
   then record the verified context receipt. On a same-session cache hit, do not
   reload those files merely for orientation.
5. Always read the current task inputs named in the matching role instructions;
   their content, checksums, and current baselines are never supplied by the
   stable context cache.
6. Never rely on prior conversation history or a receipt from another actor
   session as project state. A missing, malformed, stale, or different-session
   receipt is a cache miss.

## Safety and ownership

Follow the authority hierarchy in `REPOSITORY_STRUCTURE.md` and the ownership and
prohibited-action boundaries in the matching `agents/<role>/INSTRUCTIONS.md`.

Only the Integrator may modify files under:

`rulesets/<ruleset-id>/canonical/`

Do not reinterpret legacy files as current artifacts unless they have been migrated and validated.

## Validation

Run applicable schema, graph, and repository validation before declaring work complete.
