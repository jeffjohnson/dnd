# Candidate Batched Workflow

Status: owner-requested implementation in an isolated candidate copy. This is
not a published Architect Decision or independent Reviewer approval. Do not
copy the candidate graph, packets, receipts, or historical artifacts back to
the live repository. A separately reviewed code-only rollout is required.

## Purpose

Use one foreground local command for preparation and one for mechanical
completion. The wrapper imports the existing role engines; it does not merge
their ownership, approve assertions, reinterpret source, or invent identities.
Local subprocesses do not require additional model turns. The number of source
files is not the number of model requests.

`agent_task.py` is the routine interface. `artifact_io.py`, Analyst
`packet_inputs.py`, and Reviewer `publish_review.py` are imported helpers, not
additional commands an agent should run in sequence. Existing specialized
commands remain available for migrations, historical repairs, and diagnostics.

## Prepare

Run from the repository root with a real actor-session identifier:

```powershell
python tooling/common/agent_task.py prepare --root . --role builder --ruleset shadowdark --book sd --session-id ACTOR_SESSION --input books/shadowdark/sd/artifacts/gur/GUR-EXACT-ID.yaml
```

On a context miss, the command returns every stable authority document and a
`context_token`, then stops. Read those documents before repeating the command
with `--context-read <context_token>`. That explicit attestation records the
ordinary role-context receipt. A warm receipt avoids rereading unchanged
authorities. Tokens bind the session, role, scope and exact checksums.
The candidate manifest includes this guide in the stable checksum set. Neither
the manifest schema version nor receipt format changes. If a shell tool truncates
the cold-start output, read the missing documents before attesting; a token does
not certify that an unread or truncated document was seen.

Preparation performs one complete common scan and emits a role/scope projection,
all error diagnostics, supported explicit checksum/ID dependencies, and a
bounded registry/neighborhood slice. For a packet it includes full source text,
Pandoc-derived pages/classes and supplied slices; missing slices are explicit.
It does not replace source reading or independent judgment.
References stated only in prose, nonstandard metadata keys and task-specific
authorities still require the actor's scoped reading; this helper is not a
semantic relevance detector and never claims those unparsed references were read.

Save the returned `preparation_file` path as a command argument, not as an
authoritative task artifact. It lives in `.local/agent-task/prepared/` and binds
the observed bytes to this session. It is not a lock, queue or settlement state.
Finish refuses changed inputs. `--inspect`
permits read-only historical inspection but does not issue a preparation file
that can authorize completion.

An Analyst may add `--claim-manifest <staged-packet.yaml>` for an exact eligible
incoming Markdown path. The agent must author the packet ID and registered
source ID; the tool does not infer them. It copies source bytes, never moves or
deletes intake, refuses duplicate claims, and refuses a second active packet.
Claimed paths remain immutable. Integration records, not a completed directory,
record completion.

## Finish

Reuse the exact role, scope, session and input from preparation:

```powershell
python tooling/common/agent_task.py finish --root . --role reviewer --ruleset shadowdark --book sd --session-id ACTOR_SESSION --input books/shadowdark/sd/artifacts/gup/GUP-EXACT-ID.yaml --prepared .local/agent-task/prepared/EXACT.json --staged .local/staged/review.yaml --notify
```

| Role | Completion input and operation | Permitted next action |
|---|---|---|
| Analyst | Authored `--staged` GUR or complete ESC; schema and exact lineage preflight, create-only publication | Builder, or Architect for ESC |
| Builder | Exact GUR; optional repeated `--review` correction inputs, `--revision`, `--supersedes`; full existing suite, compilation, staged schemas, create-only companion set | Reviewer, Analyst for corrections, Architect only with a complete published ESC |
| Reviewer | Authored Review 1.3 in `--staged`; validates explicit dispositions and mechanically packages eligible rows/registrations | Builder for correction, Integrator for approval, Architect for ESC |
| Integrator | Exact Approved manifest, without `--staged`; own readiness/integrity gate, transaction, complete terminal records | Analyst after successful integration; Reviewer for authored rejection; Architect for ESC |
| Architect | Authored Decision in `--staged` for the exact pending ESC | Original escalation sender |

`--preview` validates staged output plans without publishing or notifying. For
Integrator it invokes the existing dry run. Builder preview is preparation;
the publishing compile always retains its existing full test gate. No
`--skip-tests` option is offered by this facade.

The Reviewer publisher never creates judgments. It requires independently
authored approval and explicit dispositions, compares GUP YAML with companion
CSVs, pins the validation report, excludes blocked rows, and checks node labels
and kinds. Corrections that have not been applied require a Builder successor.
An Approved bundle is produced only with an approved Review; all files are
validated before any exclusive final write. Zero-edge, node-only bundles work.

Integrator terminal-record publication runs within its transaction. Ordinary
record write/validation failures roll back canonical and registry state. A
successful return requires the manifest, validation, diff, and book-scoped
terminal record. Hard process crashes are not a multi-file atomic transaction;
preserve partial evidence and use the existing snapshot recovery process.

## Errors And Boundaries

- NO RC. The facade refuses `basicdnd/rc` and excludes paused RC from claims.
- A pending ESC pauses its packet. Architect may inspect/rule on an assigned
  ESC even when the defect being escalated causes lineage errors; ordinary
  stages cannot advance through those errors.
- Finish refuses stale preparation, wrong owner/scope, invalid schema,
  existing outputs, malformed lineage and illegal notification routes.
- A compiler block that needs architecture does not send an incomplete request.
  Publish the complete ESC first. An integration failure returns its log and
  required Reviewer route but does not invent a rejection judgment: author a
  schema-valid rejection and finish with that staged record before notifying.
- Decisions return to their originator. If the immutable Decision publishes
  but its ESC lifecycle move fails, the result explicitly reports
  `published_lifecycle_incomplete`; never republish or resend blindly.
- New ordinary packet Reviews reuse the common scanner's cross-GUP lineage
  semantics. Historical exceptions, direct migrations and opaque legacy
  provenance retain their specialized workflows. The wrapper does not guess
  a missing predecessor, alias, authority, or retrospective checksum.
- The existing scanner's already-claimed incoming entries and historical
  blocked-GUP entries are not silently reclassified. If these prevent a claim,
  resolve queue semantics through governance; do not invent an override. Use
  read-only inspection to document the exact terminal evidence.

## Notifications

Without `--notify`, return the transport-independent `next_role` and artifact
paths/checksums for a future orchestration adapter. With `--notify`, call only
`Send-HerdrPrompt.ps1 -Role ... -Message ...`, via `pwsh -NoProfile`. One attempt,
no relay, no settlement loop, no blanket wake-up and no automatic resend after
an unknown outcome. Notification failure does not roll back a valid published
artifact or repeat integration. Gemini owns any later Antigravity adaptation.

## Tests And Logs

```powershell
python tooling/common/agent_task.py test --root . --suites builder common integrator reviewer
```

Each suite runs in a separate local Python process to avoid module-name
collisions. The command retains full logs and returns bounded summaries, exit
codes and duration. It removes live Herdr endpoint environment variables from
test subprocesses. Test fixtures may use RC names in temporary directories;
that does not authorize any live RC packet work. Run foreground and wait for
completion; do not treat a started test as a passed test.

The old queue Python/PowerShell pair remains one implementation plus a thin
alias. Historical per-packet emitters and retired relays remain evidence, not
part of this command menu. `Keep-AgentsGoing.ps1` now refuses broad dispatch.
No test modules are merged, no cached green result substitutes for a required
suite, and no graph semantics change merely to reduce request count.
