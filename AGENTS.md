# Repository Instructions

This repository builds ruleset-specific mechanical relationship graphs.

## Current Owner Scope: NO RC

**DEC-2026-0086: `basicdnd/rc` is explicitly paused by the owner.**
Do not claim, extract, build, review, integrate, repair, or finish RC packets.
This includes existing claims. Do not generate withdrawal GURs or cleanup work
merely to clear RC queue entries. Preserve source and published history.

Shadowdark is the current processing priority. Raw scanner RC entries are
owner-paused candidates, not executable assignments. Exclude RC from every
next-work selection and herdr handoff. Uploads, reappearing files, claims,
earlier Decisions, and previous plans do not resume RC. Only a new explicit
owner instruction authorizing RC work can lift this hold. Stop notifications
authorize acknowledgment only, not normal processing or a corpus scan.

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

The five roles communicate directly through herdr under
`contracts/HERDR_HANDOFFS.md`. Every outbound notification uses
`tooling/common/Send-HerdrPrompt.ps1 -Role <Role> -Message <Message>`; do not
call `herdr agent prompt` directly. Normal packet work is one repository-wide
relay: Analyst -> Builder -> Reviewer -> Integrator -> Analyst. The Analyst may
begin exactly one packet and may not begin another until its current packet has
integrated successfully and Integrator prompts the next selection. Corrections
run only backward through Integrator -> Reviewer -> Builder -> Analyst. An
escalation pauses that packet at its originating stage until Architect returns
a Decision to the originator. Finish with the one next relay action and directly
notify its permitted next owner. There is no Dispatcher. Communication never
changes artifact ownership or approval requirements.

## Safety and ownership

Follow the authority hierarchy in `REPOSITORY_STRUCTURE.md` and the ownership and
prohibited-action boundaries in the matching `agents/<role>/INSTRUCTIONS.md`.

Only the Integrator may modify files under:

`rulesets/<ruleset-id>/canonical/`

Do not reinterpret legacy files as current artifacts unless they have been migrated and validated.

## Validation

Run applicable schema, graph, and repository validation before declaring work complete.
