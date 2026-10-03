# Script Consolidation Review for Gemini CLI

Prepared by Architect on 2026-10-02, America/New_York.

**Status: audit and proposed implementation design, not an activated workflow contract or an implementation Decision.** No runtime scripts, worker instructions, published artifacts, registries, or canonical data were changed for this review. RC remains paused under DEC-2026-0086.

This supplements [GEMINI_CLI_HANDOFF_REPORT.md](GEMINI_CLI_HANDOFF_REPORT.md). That report is the full repository handoff, script-purpose catalog, and dated work-state inventory. This report answers a narrower question: **which operations should be combined to use fewer Gemini model requests without weakening the five roles?** It does not design Antigravity orchestration.

## 1. Recommendation

**Consolidate the commands agents use, not the source files that implement them.**

The 102-script count overstates the operational problem. Seventy-one files are imported package modules or test files. They do not each require an agent request. Much of Builder and Integrator processing is already batched inside existing commands.

The highest-value changes are:

1. Fix the recurring Builder-generated authority citation that caused six recent Shadowdark packets to need correction Reviews. Avoiding a correction cycle saves more requests than making that cycle slightly shorter.
2. Provide one local command interface with two main stages: `prepare` and `finish`, explicitly scoped to one role and one work item. Use existing implementations underneath it.
3. Make Analyst preparation and Reviewer packaging reusable operations. Those roles currently lack the general-purpose production commands that Builder and Integrator already have.
4. Batch deterministic reading, checksums, validation, publication checks, and result reporting. Do not make the model supervise these one subprocess at a time.
5. Remove historical and retired helpers from the active command menu, without deleting or relocating evidence-pinned files.

**Expected result:** approximately two routine local-tool boundaries per role stage on a warm-context, clean path, plus the model's actual authoring/review work and inter-agent notifications. This is a design target, not a measured API-request count or a promise that a packet takes eight requests.

**Do not** merge the roles, build an automatic approver, skip mandated tests, restart the retired handoff relay, or create a replacement Dispatcher.

## 2. Scope and Evidence

### What was inspected

- The 102-file inventory from the handoff audit: 95 Python files and 7 PowerShell files, totaling 65,639 lines.
- Python entrypoints, imports, public functions, subprocess boundaries, and test discovery; the implementation bodies relevant to consolidation and publication.
- All four worker instruction files, with Architect instructions and the shared lifecycle, context, source, and queue contracts.
- Recent Shadowdark GURs, GUPs, Reviews, implementation evidence, and Integration evidence where needed to check how commands are actually used.
- The prior handoff's queue and integrity snapshots. These remain dated observations, not a new work assignment.
- Current script checksums against the original inventory. All 102 matched at the final verification for this report.

The inventory included ignored project-local helpers and untracked scripts. It searched common script extensions and extensionless shebang files, excluding `.git`, virtual environments, dependency trees, and compiled caches. It is an inventory of repository-authored scripts, not every executable installed on Windows.

The handoff audit itself added two ignored local utilities, `.local/handoff-audit/report_audit.py` and `.local/handoff-audit/write_report.py`. Thus the present filesystem has those two additional audit utilities beyond the original 102. They are not worker entrypoints and are not included in the 102-file arithmetic below. This consolidation review added no executable script.

### What the count means

| Category | Files | Normal use | Disposition |
|---|---:|---|---|
| Builder package modules | 18 | Mostly imported by one compiler CLI | Keep modular; batch at the CLI boundary |
| Integrator package modules | 15 | Mostly imported by one transaction CLI | Keep modular and separately owned |
| Tests and test support | 38 | Discovered by suite commands | Keep files; aggregate suite execution locally |
| Historical helpers | 24 | Old one-off Reviews, legacy readers, local checks/messages | Exclude from routine command discovery; preserve |
| Common entrypoint files | 7 | Five current files; one retired relay; one unsafe scratch launcher | Wrap current operations; do not revive the other two |
| **Total** | **102** | **Not 102 commands per packet** | **Reduce exposed operations, not test coverage** |

The five current common files implement four operations: role context, queue scanning, staged validation, and notification. The PowerShell scanner is an alias for the Python scanner, not another independent job. Together with the Builder and Integrator CLIs, there are **six existing operational interfaces**, although each exposes multiple modes.

### What was not measured

Repository artifacts are not a complete log of model turns. Some implementation Reviews record exact commands, but normal packet artifacts often record methods and evidence without a shell transcript. I have not assigned an invented average request cost to a packet, a role, or an individual script.

No production script or old publishing helper was run merely to see what it would write. No packet was claimed or processed for this audit. No worker was awakened to perform a second audit.

## 3. The Quota Changes the Optimization Target

The owner clarified that the allowance counts model/API requests, not local subprocesses. One shell-tool invocation can run several local operations without a model decision between each one. Google's documentation likewise distinguishes prompts from model requests and notes that a prompt can cause several requests. The exact quota depends on the account; the owner's stated planning budget here is 1,500 per day. [Official quota documentation](https://docs.cloud.google.com/gemini/docs/quotas)

The shell tool executes a local command and returns its result to the agent. Combining deterministic work within that invocation reduces intervening model/tool exchanges; simply concatenating source files does not. [Official shell-tool documentation](https://geminicli.com/docs/tools/shell/)

For example:

| Approach | Agent-visible tool boundaries | Local work |
|---|---:|---|
| Ask the model to run schema validation, then hashes, then output preflight, then publication verification separately | 4 | The four operations |
| One local publication command performs those checks in order and reports the result | 1 | The same four operations |
| Move those implementations into one large Python file but still ask the model to invoke four modes separately | 4 | Still the same four operations |

This table counts **tool boundaries**, not billing events. Authentication, model behavior, reasoning/authoring turns, errors, and notification handling also contribute to actual request usage.

Local execution time is not itself a model request. Nevertheless, a long-running tool can require extra polling turns if the host detaches it. Use supported foreground execution and concise progress output, especially for Reviewer work. Do not implement a background agent-waiting system to solve this.

## 4. Highest-Value Findings

### 4.1 Eliminate a repeated correction cycle before optimizing its commands

The compiler still generates this ordinary-node-registration basis:

```text
DEC-2026-0003: approved prefix and kind, valid ID, no duplicate
```

The two generation sites are in [compiler.py](tooling/builder/src/adnd1e_builder/compiler.py), around lines 1374-1381 and 1523-1527. Related generated diagnostic prose also cites the same Decision. DEC-2026-0003 is AD&D authority; there is no corresponding Shadowdark Decision with that ID.

Six recent Shadowdark first Reviews required node-local `routing_basis` corrections for this generated text:

| Packet | Correction Review | Affected node entries |
|---|---|---:|
| Monster Family Angels | [Angels r01-r01](books/shadowdark/sd/artifacts/reviews/REV-GUP-PKT-SD-195-195-monster-family-angels-r01-r01.yaml) | 4 |
| Animated Armor to Bat, Giant | [196-198 r01-r01](books/shadowdark/sd/artifacts/reviews/REV-GUP-PKT-SD-196-198-monsters-animated-armor-to-bat-giant-r01-r01.yaml) | 12 |
| Bat Swarm to Cave Brute | [198-200 r01-r01](books/shadowdark/sd/artifacts/reviews/REV-GUP-PKT-SD-198-200-monsters-bat-swarm-to-cave-brute-r01-r01.yaml) | 12 |
| Cave Creeper to Cultist | [200-203 r01-r01](books/shadowdark/sd/artifacts/reviews/REV-GUP-PKT-SD-200-203-monsters-cave-creeper-to-cultist-r01-r01.yaml) | 12 |
| Cyclops to Deep One | [203-203 r01-r01](books/shadowdark/sd/artifacts/reviews/REV-GUP-PKT-SD-203-203-monsters-cyclops-to-deep-one-r01-r01.yaml) | 3 |
| Monster Family Demons | [Demons r01-r01](books/shadowdark/sd/artifacts/reviews/REV-GUP-PKT-SD-204-205-monster-family-demons-r01-r01.yaml) | 5 |
| **Total** | **Six correction Reviews** | **48 entries** |

This is a repeated compiler-output problem, not six independent ontology questions. The source-supported corrected basis points to Shadowdark Constitution section 2 and the ordinary GUR/GUP/Review workflow.

**Recommendation:** authorize Builder to make ordinary-registration authority text ruleset-aware, including the corresponding diagnostic prose, and add focused AD&D/Shadowdark regressions. Reviewer independently verifies the change. Do not fix it by supplying hand corrections on every future packet, importing the AD&D Decision into Shadowdark, or rewriting the 48 historical entries.

This is a separate narrow improvement from the batch-command interface. Its exact governance wording and implementation scope should be fixed in an Architect Decision before implementation.

### 4.2 Builder already runs its suite inside compilation

[Builder CLI](tooling/builder/src/adnd1e_builder/cli.py), `run_tests` and the compile branch, discovers and runs the Builder suite in-process before emitting the patch. Compilation, deterministic row processing, serialization, and test-result provenance already occur in one CLI invocation.

Consequences:

- Do not routinely ask Builder to run the same full suite as a separate preparatory model step and then invoke the compile command that runs it again, unless the task has a distinct reason for both.
- Do not recommend `--skip-tests` as the quota optimization. Tests are local work; preserve the existing gate.
- Independent Reviewer reruns required by a Decision remain independent evidence. They can be locally batched with other Reviewer checks, not replaced by Builder's result.
- A multi-input compile option is not permission to start multiple normal packets. The current relay authorizes one packet at a time.

### 4.3 Reviewer has the largest missing reusable publication interface

[Reviewer instructions](agents/reviewer/INSTRUCTIONS.md) explicitly permit review tooling. However, the reusable `tooling/reviewer/` files in this inventory are two old relay acceptance tests, not a general current Review/Approved publisher.

The fourteen PHB scratch scripts combine hardcoded judgments, old paths, and publication logic for particular historical jobs. They are not a safe Shadowdark publisher. Some import another historical emitter by filename, so deleting or moving them can also break their own retained reproducibility.

A reusable Reviewer-owned publisher could take the Reviewer's **already-authored decisions** and mechanically perform:

1. Parse and schema-check the staged Review and the exact reviewed GUP inputs.
2. Resolve ref coverage, operation placement, legal disposition terms, and row-local corrections.
3. Materialize only the approved row set and the sanctioned pending-row packaging, excluding blocked rows.
4. Calculate component hashes, row counts, operation indexes, provenance, and the Approved manifest.
5. Validate all staged outputs, check every final and companion path, and publish create-only.
6. Report the exact next artifact and permitted next owner; optionally send the existing notification in the same local invocation.

The tool must not decide whether a source supports an edge, invent an identity or label, turn every row into `approved`, or accept Builder's assertions as independent review. It consolidates clerical work, not judgment.

### 4.4 Analyst needs preparation support, not a legacy-reader merger

[Analyst instructions](agents/analyst/INSTRUCTIONS.md) require the full claimed packet, supplied slices, scoped identity context, and source-supported extraction. There is no general current Analyst preparation command in the 102-file inventory. The three `doctags_reader.py` files are legacy AD&D readers and are not the required Pandoc Markdown ingestion path.

The useful new operation is a bounded input package: exact scope and claim status, complete source content, Pandoc-derived page context, supplied graph/registry slices, and applicable current constraints. Follow that with a common staged publication operation for the Analyst-authored GUR.

Do not substitute regex extraction or a synopsis for the complete source reading. Do not require the model to rebuild filesystem paths, schema resolution, and SHA-256 boilerplate on every packet.

### 4.5 Integrator already performs many of the checks a wrapper might duplicate

[Integrator CLI](tooling/integrator/src/adnd1e_integrator/cli.py) resolves ready bundles before integration. [integrate.py](tooling/integrator/src/adnd1e_integrator/integrate.py) verifies inputs, validates the baseline and proposed result, rebuilds derived outputs, and uses the transaction machinery.

A default sequence of separate model calls for queue, dry run, integrate, validate, and another queue scan repeats some work. Retain every required check, but execute the necessary sequence locally and return one result. A separate dry run is useful when someone will inspect a proposed plan; it is not inherently necessary as another model turn when the next action is already authorized and deterministic.

There is an important boundary: `cmd_integrate` calls `integrate(...)`, then separately calls `write_records(...)`. The canonical transaction and publication of its manifests/reports are not one call. A future wrapper must require successful record publication and exact terminal evidence before it tells Analyst to start another packet. If record publication fails after canonical application, do not blindly retry the apply step or describe the packet as untouched.

The CLI also selects every ready bundle if no explicit IDs are given. A single-packet interface must always name the one authorized bundle. It must preserve the Integrator's own queue-integrity gate; a filtered common-scanner display is not an authorization bypass.

### 4.6 Similar-looking code is not necessarily interchangeable

Several modules duplicate hashes, vocabulary parsing, or lineage concepts. Some consolidation is reasonable maintenance work, but it does not directly save model requests.

A concrete caution: [Builder assertion identity](tooling/builder/src/adnd1e_builder/duplicates.py) normalizes `aspect` and `condition`, while [Integrator assertion identity](tooling/integrator/src/adnd1e_integrator/invariants.py) returns their raw strings. The helper functions therefore differ for case/punctuation variants. This audit does not assert that an invalid packet has reached production; it establishes that replacing one implementation with the other is not a behavior-neutral refactor.

Resolve expected behavior against the active ruleset contract, add parity fixtures, and retain independent validation coverage before consolidating shared semantic logic. The same caution applies to vocabulary fallbacks and queue eligibility. Do not remove an independent check merely because two functions have the same name.

### 4.7 A blind shell chain is not a reliable batch interface

Current commands do not share one exit-code meaning:

| Command | Relevant outcome |
|---|---|
| `role_context.py verify` | `1` means reload required; it is not permission to continue with unread context |
| `scan_agent_queues.py` | `1` means ready work exists; `2` means lineage errors |
| Builder `compile` | `1` can mean a blocked patch was produced; `2` can mean suite failure |
| Integrator commands | Distinguish ready work, rejection, and tooling/lineage failure |
| `validate_artifact.py` | Nonzero prevents publication |

A wrapper must interpret each operation's structured result and exit code deliberately. A universal `command_a && command_b` policy would stop on legitimate queue results and could mishandle blocked outputs. Shell batching saves requests only when its control flow is correct.

## 5. What Each Worker Would Use

The following table is a proposed interface arrangement. It does not transfer ownership or replace the current role instructions.

| Role | Existing work and tools | Combine into `prepare` | Combine into `finish` | Keep as model judgment |
|---|---|---|---|---|
| Analyst | Context verifier, queue selection, file/Pandoc reads, staged validation, ad hoc GUR publication, notification | Context status; one eligible packet or exact correction; source and supplied slices; current IDs and page evidence | Validate the authored GUR; preflight all outputs; publish; report exact Builder/Architect handoff | Read the complete packet; choose assertions and identities within authority; decide whether an ESC is necessary |
| Builder | Context verifier; `adnd1e_builder compile`; staged validator; scanner; notification | Exact GUR and Review chain; Decisions; registry/neighborhood; source-marker dependencies | Existing suite gate and compilation; staged envelope/ruleset checks; create-only outputs; exact result and next owner | Resolve implementation issues within authority; escalate policy questions; return source defects to Analyst |
| Reviewer | Context verifier; independent source/GUP checks; suite runs when required; ad hoc Review/Approved construction; staged validator; notification | Independently collect exact source/GUR/GUP/components, hashes, local neighborhood, required tests, and previous directives | Validate Reviewer-authored dispositions; package approved rows; generate hashes/manifests; publish; report correction or approval | Independently judge every required assertion, identity, correction, and acceptance criterion |
| Integrator | Context verifier; `adnd1e_integrator queue/validate/integrate`; terminal records; notification | Exact Approved bundle and Review; integrity/readiness; baseline and transaction inputs | Apply only that bundle through Integrator tooling; verify terminal records; notify Analyst after success, or Reviewer on rejection | Attribute a failed precondition; recognize governance questions; do not reinterpret source |

Architect can use the same context/preflight utilities for a named ESC and staged Decision, but there is no reason to invoke Architect for every clean packet. Routine work should not become five-role work merely because the shared command supports five roles.

### Normal and correction routing remains unchanged

```text
Analyst -> Builder -> Reviewer -> Integrator -> Analyst selects the next packet

Integrator -> Reviewer -> Builder -> Analyst  (only as far back as needed)

Any role -> Architect -> that same originating role  (escalation pause)
```

No normal stage advances while its escalation remains unresolved. A command must not select another packet to hide that pause. Decision implementation follows its own explicit prerequisites without starting a second normal packet.

## 6. Proposed Small Local Interface

Use one Python entrypoint, provisionally `tooling/common/agent_task.py`, backed by existing role-owned code. Python is already required by the compiler, schema validation, and integration packages. A second new PowerShell implementation of the same logic would add maintenance without reducing requests.

**The following commands are a proposed interface only. `agent_task.py` does not exist yet.**

```text
python tooling/common/agent_task.py prepare --role <role> --ruleset <id> --book <id> --session-id <session> --input <exact-artifact-or-packet>
python tooling/common/agent_task.py finish --role <role> --input <exact-input> --staged <role-authored-output-or-plan>
```

The role determines the permitted finish operation. Builder uses its existing compile inputs; Integrator names an exact Approved bundle rather than a new user-authored canonical plan. The final argument design should be kept as small as these differences allow. Do not make a new general-purpose workflow language or duplicate GUR/GUP/Review artifact formats in an authoritative task file.

### Preparation rules

1. Resolve real scope from the input and repository manifests. Fail on disagreement; do not invent identifiers.
2. Verify the existing context receipt. A cache hit avoids rereading stable files. On a miss, emit the required complete authority content or its explicit readable chunks and stop for the agent to read it. Never silently truncate required source or stable authority.
3. Only after that reading may the role attest through the existing `record` operation, which can be included in its next local call. Do not manufacture a receipt because the wrapper itself opened or hashed the files.
4. Revalidate exact current task evidence and baselines every time. A receipt is not a cached task approval.
5. Return the bounded input set together, not a series of instructions that makes the agent ask for each checksum and adjacent file separately.
6. An exact-assignment fast path must still apply required lineage, readiness, pause, and integrity checks. It does not mean trust the notification text.

### Finish rules

1. Keep semantic authoring separate: Analyst authors extraction; Reviewer authors judgment; Architect authors rulings.
2. Perform all deterministic checks locally. Collect related validation findings into one actionable result instead of requiring a new model turn for each missing field.
3. Validate staged bytes before publication, including applicable common and ruleset schemas with the repository's reference resolver.
4. Preflight all durable destinations and same-ID companion paths before the first write. Do not introduce an overwrite option.
5. Recheck mutable inputs at the write/transaction boundary. An earlier prepare result is not a reservation of the current baseline.
6. Publish through the owning role's implementation. Only Integrator may write canonical state.
7. Return exact published IDs, paths, checksums, phase outcome, findings, blockers, and the next permitted role in one concise result. Keep full logs locally for failures or deliberate audits.
8. Notification may be the final local operation, after successful durable publication and verified routing. Under the current platform it must call `Send-HerdrPrompt.ps1`, never the retired relay or raw Herdr prompt command.
9. Notification failure does not erase completed artifact work or trigger a duplicate publication. Report it separately, without claiming receipt, agent execution, or settlement.

### Publication cannot be bolted on after the current writer

[validate_artifact.py](tooling/common/validate_artifact.py) already exposes `validate_staged(...)`, so a batch command can call the shared validator without spawning one process per YAML file.

However, [Builder `emit.write_all`](tooling/builder/src/adnd1e_builder/emit.py) currently performs its create-only check and writes rendered output directly. Its pure renderers can be reused, but a new wrapper must validate those staged bytes **before** calling a durable write path. Calling the current compiler, then validating already-published YAML, does not implement the existing prepublication contract. This integration belongs in Builder-owned publication code, not in an Architect scratch script.

Likewise, a Reviewer publisher must stage the complete linked set before final publication; an Approved manifest cannot be fully checked until its derived component bytes and checksums are known.

Multi-file failure handling must be explicit. The implementation must not claim filesystem-wide atomicity that it does not provide. A partial write must be reported precisely, never silently overwritten on retry.

### Keep transport migration separate

[Send-HerdrPrompt.ps1](tooling/common/Send-HerdrPrompt.ps1) intentionally pins the present provider mapping: Analyst/Builder/Integrator are Claude, Reviewer/Architect are Codex. It also requires Herdr's environment and verifies the live repository. It is not already a Gemini transport adapter.

The batch command should produce a transport-independent next-action result. Gemini can decide how that result becomes an Antigravity notification. Until a separately authorized migration replaces the transport rule, all actual Herdr messages still use the existing wrapper. No Antigravity orchestration, pane registry, settlement store, or delivery polling is proposed here.

## 7. Specific Consolidation Decisions to Make

| Candidate | Recommendation | Reason and boundary |
|---|---|---|
| Context verification plus bounded input reads | Batch | Same tool call can verify and load required content; agent still attests only after reading |
| Queue scan plus role/scope projection | Batch output first | Reuse the current scanner and show bounded work; filtering its result is safer initially than inventing a partial scan |
| YAML parsing, schema resolution, checksums, publication preflight | Consolidate repeated mechanics | Shared pure utilities plus owner-specific writers; preserve exact UTF-8 bytes and provenance |
| Builder suite, compile, output validation, result summary | Batch existing compiler path | Much is already combined; add staged validation and avoid redundant model-supervised calls |
| Reviewer disposition checks, CSV assembly, manifest hashing, publication | Build reusable Reviewer publisher | Replaces manual packaging and one-off emitters, not source judgment |
| Analyst claim/input preparation | Build reusable bounded helper | One packet only; preserve immutable claimed paths; never select paused RC |
| Integrator verification, application, record checks, next action | Batch through Integrator API/CLI | Exact bundle; preserve own integrity gate and transaction semantics |
| Multiple test suites | Aggregate invocation, not files | Run suites in isolated subprocesses within one local command; preserve module discovery and exit reporting |
| Python and PowerShell queue entrypoints | Keep one implementation and thin alias | Already this arrangement; deleting the alias saves no model requests |
| SHA-256 implementations | Defer low-risk shared utility extraction | Preserve raw-hex versus `sha256:` conventions; maintenance benefit, little request benefit |
| Builder/Integrator vocabulary loaders | Consider shared table parsing later | Different contracts and fallback behavior; require cross-ruleset fixtures first |
| Builder/Integrator assertion identity | Do not blindly merge | Observed normalization differences need a contract-backed parity decision |
| Common scanner and Integrator readiness | Keep independent responsibility | Work discovery is not admission authority; do not let display filtering bypass integrity |
| Migration planners | Keep separate modes | Merge/repoint/row-migration operation models and authority differ |
| Pandoc page-marker parser and legacy doctags readers | Use the Pandoc path for current packets | Old readers are not substitutes for the page-marker contract |
| Historical Review emitters | Exclude from active interface | Hardcoded source judgments and paths; preserve immutable history and imports |
| Retired relay and blanket keep-going launcher | Never include in the new interface | Violates the intended simple notification and exact-routing model |

### Why not one giant test file or one universal discovery command?

Tests do not each cost a request when one command discovers them. Builder and Integrator also contain identically named test modules, including `test_migration.py`, with different bootstraps. A naive shared import namespace can collide or change fixture resolution. Running their existing suite commands as separate local subprocesses within one batch is both simpler and cheaper in model requests than asking the model to run each separately.

Do not silently stop running a suite that an active Decision requires. Do not cache a green result merely by source-code checksum: several suites inspect current corpus, registry, schemas, and contracts. A correct test-cache dependency model would be separate work, and is not necessary for the first request-saving improvement.

## 8. Request-Budget Model and Pilot

### Count only boundaries that actually disappear

| Mechanical sequence | Possible separate calls today | Proposed local calls | Qualification |
|---|---:|---:|---|
| Context verify, exact-input reads, dependency hashes, scoped work display | 4 | 1 | Warm receipt; cold context can require an additional read/attestation exchange |
| Multiple staged YAML/schema checks, component hashes, destination checks | 3-5 | 1 | Complete local preparation; no model judgment needed between checks |
| Builder full suite followed by compile | 2 | 1 | Compile already includes the suite; not a saving if the role already invokes only compile |
| Reviewer-generated component, hash, manifest, schema check, final-path checks | 5 | 1 | After Reviewer authors the actual decisions |
| Integrator queue, verification/apply, terminal-record check, notification | 4 | 1 | Only with exact authorized input and correct local failure handling |

These are illustrative decompositions, not reconstructed transcripts. The same operation must not be counted twice in a claimed total saving. A source ambiguity or failed invariant still needs a reasoning turn.

### Measure a small real pilot

After implementation approval, measure several representative authorized Shadowdark packets through the ordinary single-packet relay. Include a clean packet, a registration-heavy packet, and a correction path if one naturally occurs; do not invent graph work to manufacture a benchmark.

Record:

- Model-request counter at the start and end, using the target service's actual accounting.
- Per-role shell calls, source/authoring turns, notifications, and correction/escalation turns.
- Local command duration, exit outcome, and whether an extra poll was needed.
- Number of repeat validations, full queue dumps, and unchanged instruction reloads avoided.
- Published artifact counts and independent correctness outcomes, so fewer requests cannot hide skipped work.

Use `daily packet capacity = floor((1500 - reserve - unrelated requests) / measured requests per completed packet)`. Select the reserve based on actual escalation/error traffic. Do not promise a daily packet count from file count alone.

The goal is fewer model-supervised procedures and fewer avoidable correction cycles, not fewer useful tests or unread source pages.

## 9. Constraints the Implementation Must Preserve

1. **One normal packet.** Starting another packet before terminal integration remains forbidden. Batching operations is not batching packet assignments.
2. **NO RC.** Paused incoming files and existing RC claims are not executable selections.
3. **Role authority.** Shared code does not let Builder approve, Reviewer write canonical, or Integrator interpret source.
4. **Context truth.** Missing, malformed, stale, or different-session receipts miss. No wrapper reads-and-records on behalf of an agent that has not loaded the content.
5. **Current evidence.** Never replace current source, checksums, active lineage, or canonical preconditions with a prior run's summary.
6. **Pandoc syntax and pages.** Current source parsing must use the sanctioned Pandoc-compatible path and all three page-marker positions.
7. **Create-only publication.** Every companion and validation report is checked. Malformed output stays staged, not published and later patched.
8. **Explicit outcomes.** Ready, blocked, revision-required, approved, rejected, and integrated remain distinct. Process success alone is not graph completion.
9. **Independent review.** Mechanical automation cannot choose dispositions or accept an implementation owner's tests as the Reviewer's entire evidence.
10. **Transaction safety.** Preserve baseline rechecks, rollback, deterministic serialization, and new-ruleset genesis behavior.
11. **Complete terminal records.** Canonical application without complete records is not a successful relay step. No blind reapply on a record-publication error.
12. **Immutable history.** Keep old scripts where named by evidence, and keep old artifacts byte-unchanged. Archive status in documentation does not authorize relocation.
13. **No message state machine.** No pending/settled lock store, recipient wait loop, auto-resend, or blanket keep-going broadcast.
14. **Useful output.** Summaries include all actionable failures and exact evidence paths. Full logs are optional to read, not necessary for discovering whether a run succeeded.

### Current queue discrepancies need their own treatment

The handoff snapshot showed raw incoming counts that include already-claimed source files, paused RC candidates, and differences between common-scanner output and the Integrator's own evidence. A new command must not blindly equate a raw ready count with permission to start work.

Initially, project the existing complete scan into a smaller display while preserving relevant diagnostics. That reduces output and follow-up calls, not scanner CPU time. Any later optimization that changes which stores are read, suppresses historical evidence, or redefines consumption is a queue-semantics change requiring Architect authority and focused regressions. Do not create an incomplete temporary repository and call its clean queue authoritative.

Likewise, changing claimed/completed folder behavior is not a script-count optimization. Current [FILE_NAMING](contracts/FILE_NAMING.md) and [WORK_QUEUES](contracts/WORK_QUEUES.md) preserve claimed paths for provenance. Give the owner a terminal-state view rather than moving source directories to make a display look tidy.

## 10. Implementation Sequence and Ownership

These are proposed work packages. They are not new queue items until authorized and assigned through the repository's normal governance.

| Priority | Work package | Primary implementer | Independent check | Dependencies |
|---|---|---|---|---|
| 0 | Ruleset-correct node-registration authority text and focused regressions | Builder | Reviewer | Architect pins allowed authority behavior; no dependency on the batch interface |
| 1 | Read-only `prepare` facade, structured results, role/scope projection, reuse of context verifier | Builder, for common tooling | Reviewer | Architect defines exact bounds and current-input requirements |
| 2 | Common staged publication plumbing and Builder compile integration | Builder | Reviewer | Approved prepare/result contract; preserve the existing suite gate |
| 3 | Reviewer-specific deterministic Review/Approved publisher | Reviewer on its tooling surface | Separate fresh verification of implementation against approved tests, with no self-approval shortcut | Architect explicitly assigns code and implementation-review ownership; common staging primitives available |
| 3 | Analyst packet preparation/claim helper and GUR finish adapter | Analyst on its tooling surface, Builder only for assigned shared plumbing | Reviewer | Single-packet selection and pause rules unchanged; Pandoc path reused |
| 4 | Exact-bundle finish adapter with record-completion checks | Integrator | Reviewer | Existing transactional integration preserved; failure-boundary tests added |
| 5 | Update all five role instructions and active command documentation to the approved interface | Architect | Verify named commands and substantive anchors after implementation approval | Only activate implemented and reviewed commands |
| Later | Deduplicate pure utilities or remove active-menu references to historical helpers | Owning role for each path | Reviewer as assigned | Measured benefit and behavior-preserving tests; no evidence-path deletions |

For a Reviewer-authored tooling implementation, the Architect must explicitly designate an independent verification path before coding; a Reviewer cannot treat its own publishing tool as self-approved. Alternatively, an Architect Decision can assign the deterministic implementation to Builder while reserving all actual review judgment and artifact publication to Reviewer. Do not leave that ownership choice implicit.

### Likely paths for an eventual exact-diff authorization

| Owner | Existing surfaces | Possible new surface |
|---|---|---|
| Architect | `AGENTS.md`; the five `agents/*/INSTRUCTIONS.md` files; applicable contracts and schema definitions | A short batched-command contract only if existing contracts cannot express the interface cleanly |
| Builder | `tooling/common/role_context.py`, `validate_artifact.py`, `scan_agent_queues.py`, their focused tests; Builder `cli.py`, `compiler.py`, `emit.py`, and focused tests | `tooling/common/agent_task.py` and its tests; owner-scoped adapters as needed |
| Analyst | Current Analyst tooling surface and source-preparation behavior | A reusable `tooling/analyst/` preparation adapter, rather than another packet-specific scratch emitter |
| Reviewer | Current Reviewer tooling surface and Review/Approved construction | A reusable `tooling/reviewer/` publisher and tests, under explicitly assigned implementation/review ownership |
| Integrator | Integrator `cli.py`, `integrate.py`, `records.py`, and transaction/record tests where required | Only a thin adapter if the current CLI cannot provide the required structured result |

This table is a planning map, not an `exact_diff` record. Each authorized increment should list only the exact files needed for that increment, assign each once, and use the normal implementation report and independent Review process.

### Required acceptance coverage

- Warm same-session preparation hits; cold/stale/malformed/different-session preparation does not attest unread context.
- Exact assignment rejects scope mismatch, missing provenance, blocked readiness, and inactive lineage.
- RC is never selected and no second normal packet starts during an active relay or escalation.
- Required full source content is returned or explicitly segmented, never silently replaced by a summary.
- YAML parse/schema failures, unresolved references, missing components, and stale hashes prevent durable writes.
- One existing same-ID companion prevents every output from being modified.
- Caller-selected scope and paths cannot escape the repository or gain another role's write authority.
- Ordinary Builder compilation keeps its suite gate and matches existing artifact semantics.
- Existing entrypoints remain compatible while role instructions migrate.
- Reviewer decisions remain explicit input; blocked rows cannot become approved components through packaging convenience.
- Ref coverage, operation indexes, source provenance, and registration fields agree across Review and bundle.
- Zero-edge and node-only cases, source/GUR corrections, packaging-only corrections, and escalation outcomes are represented correctly.
- Integrator rejects stale baseline/approval data and preserves rollback, including genesis rollback to absence.
- Failure to publish terminal records cannot trigger another packet or an automatic reapplication.
- Notification errors are reported separately from publication success; no retry creates a duplicate artifact.
- Exit-code adapters distinguish queue-ready, blocked, reload-required, rejection, and tooling failure.
- AD&D behavior stays covered; Shadowdark authority text does not cite an invented local Decision.
- Foreground execution returns a concise complete result; local suite aggregation does not introduce Python test-module collisions.
- A measured pilot reduces local-tool/model boundaries without reducing independent verification or mandated coverage.

## 11. Every Original Script: Recommended Disposition

The following index accounts for all 102 original scripts exactly once. It is intentionally shorter than the full purpose catalog in the handoff report.

Actions mean:

- **Batch:** keep the implementation/path, expose its operation through the small role interface.
- **Keep:** retain the module/test boundary; invoke it through its package or suite rather than individually.
- **History:** retain in place for evidence/compatibility; do not offer it as routine work.
- **Hold:** do not execute as a normal workflow helper; preserve until separately authorized cleanup.

### Common entrypoints: 7

| Script | User/owner and purpose | Action |
|---|---|---|
| [tooling/common/Keep-AgentsGoing.ps1](tooling/common/Keep-AgentsGoing.ps1) | Owner scratch broadcast: prompts Builder/Integrator and an invalid `agent` role, without exact work selection | Hold; never put behind the new interface |
| [tooling/common/Send-HerdrPrompt.ps1](tooling/common/Send-HerdrPrompt.ps1) | All roles; verifies live Herdr target/provider/root and sends timestamped notification | Batch as the final permitted operation while Herdr is active |
| [tooling/common/role_context.py](tooling/common/role_context.py) | All roles; Builder-owned scope/session/checksum receipt verifier | Batch verification, preserve explicit read attestation |
| [tooling/common/scan-agent-queues.ps1](tooling/common/scan-agent-queues.ps1) | Owner/all roles; PowerShell front end to Python scanner | Keep as a thin compatibility alias; do not call both scanners |
| [tooling/common/scan_agent_queues.py](tooling/common/scan_agent_queues.py) | All roles; Builder-owned lineage-derived work discovery | Batch and project output; no admission shortcut |
| [tooling/common/send-agent-handoff.ps1](tooling/common/send-agent-handoff.ps1) | Retired lock/settlement relay with historical tests/evidence | History; do not reuse its state machinery |
| [tooling/common/validate_artifact.py](tooling/common/validate_artifact.py) | All artifact publishers; target-only YAML/schema validation | Batch its API over staged outputs |

### Builder package: 18

| Script | User/owner and purpose | Action |
|---|---|---|
| [tooling/builder/src/adnd1e_builder/__init__.py](tooling/builder/src/adnd1e_builder/__init__.py) | Builder; package identity/exports | Keep |
| [tooling/builder/src/adnd1e_builder/__main__.py](tooling/builder/src/adnd1e_builder/__main__.py) | Builder; module execution shim | Keep compatibility |
| [tooling/builder/src/adnd1e_builder/cli.py](tooling/builder/src/adnd1e_builder/cli.py) | Builder; compile/page checks/migration command dispatch and suite gate | Batch, without another redundant suite invocation |
| [tooling/builder/src/adnd1e_builder/compiler.py](tooling/builder/src/adnd1e_builder/compiler.py) | Builder; deterministic GUR compilation and routing | Keep; correct repeated ruleset authority output first |
| [tooling/builder/src/adnd1e_builder/decision_migration.py](tooling/builder/src/adnd1e_builder/decision_migration.py) | Builder; Decision-authorized migration planning | Keep distinct from ordinary packet compilation |
| [tooling/builder/src/adnd1e_builder/direction.py](tooling/builder/src/adnd1e_builder/direction.py) | Builder; directional edge checks | Keep imported validator |
| [tooling/builder/src/adnd1e_builder/duplicates.py](tooling/builder/src/adnd1e_builder/duplicates.py) | Builder; assertion identity and canonical-neighborhood comparison | Keep; parity-check before any cross-role merger |
| [tooling/builder/src/adnd1e_builder/emit.py](tooling/builder/src/adnd1e_builder/emit.py) | Builder; GUP/CSV/report rendering and create-only writes | Batch with pre-write staged validation |
| [tooling/builder/src/adnd1e_builder/escalation_ids.py](tooling/builder/src/adnd1e_builder/escalation_ids.py) | Builder; escalation identity handling | Keep reusable logic, not a model step |
| [tooling/builder/src/adnd1e_builder/governance.py](tooling/builder/src/adnd1e_builder/governance.py) | Builder; governed Decisions, escalation state, identity authority | Keep separate from source interpretation |
| [tooling/builder/src/adnd1e_builder/grain.py](tooling/builder/src/adnd1e_builder/grain.py) | Builder; relationship-grain/value leakage checks | Keep imported validator |
| [tooling/builder/src/adnd1e_builder/migration.py](tooling/builder/src/adnd1e_builder/migration.py) | Builder; identity-merge migration planning | Keep its distinct operation semantics |
| [tooling/builder/src/adnd1e_builder/pagemarkers.py](tooling/builder/src/adnd1e_builder/pagemarkers.py) | Builder and source-checking tools; Pandoc-backed page resolution | Reuse from preparation; do not replace with doctags readers |
| [tooling/builder/src/adnd1e_builder/polarity.py](tooling/builder/src/adnd1e_builder/polarity.py) | Builder; derived/authored polarity checks | Keep imported validator |
| [tooling/builder/src/adnd1e_builder/queues.py](tooling/builder/src/adnd1e_builder/queues.py) | Builder; build-relevant artifact leaf/queue handling | Keep scope-specific behavior; test against shared contract |
| [tooling/builder/src/adnd1e_builder/registry.py](tooling/builder/src/adnd1e_builder/registry.py) | Builder; node registry lookup and resolution | Keep read-only role boundary |
| [tooling/builder/src/adnd1e_builder/review.py](tooling/builder/src/adnd1e_builder/review.py) | Builder; executable Review corrections and operation directives | Keep; never replace with prose inference |
| [tooling/builder/src/adnd1e_builder/vocab.py](tooling/builder/src/adnd1e_builder/vocab.py) | Builder; ruleset vocabulary and version acceptance | Keep; consider pure parser sharing only after parity tests |

### Integrator package: 15

| Script | User/owner and purpose | Action |
|---|---|---|
| [tooling/integrator/src/adnd1e_integrator/__init__.py](tooling/integrator/src/adnd1e_integrator/__init__.py) | Integrator; package metadata/exports | Keep |
| [tooling/integrator/src/adnd1e_integrator/__main__.py](tooling/integrator/src/adnd1e_integrator/__main__.py) | Integrator; module execution shim | Keep compatibility |
| [tooling/integrator/src/adnd1e_integrator/admission.py](tooling/integrator/src/adnd1e_integrator/admission.py) | Integrator; schema/lineage/repair-record admission checks | Keep independent of display scanner |
| [tooling/integrator/src/adnd1e_integrator/bundles.py](tooling/integrator/src/adnd1e_integrator/bundles.py) | Integrator; exact Approved bundle discovery and readiness | Batch through integration entrypoint, not common-scan inference |
| [tooling/integrator/src/adnd1e_integrator/canonical.py](tooling/integrator/src/adnd1e_integrator/canonical.py) | Integrator; canonical/registry readers and deterministic writers | Keep exclusively Integrator-owned |
| [tooling/integrator/src/adnd1e_integrator/checksums.py](tooling/integrator/src/adnd1e_integrator/checksums.py) | Integrator; checksum utilities | Keep now; possible later pure shared utility |
| [tooling/integrator/src/adnd1e_integrator/cli.py](tooling/integrator/src/adnd1e_integrator/cli.py) | Integrator; queue/validate/integrate/test commands | Batch with exact one-bundle selection and terminal-result checks |
| [tooling/integrator/src/adnd1e_integrator/derive.py](tooling/integrator/src/adnd1e_integrator/derive.py) | Integrator; roles, polarity, degree and graph derivation | Keep imported module |
| [tooling/integrator/src/adnd1e_integrator/integrate.py](tooling/integrator/src/adnd1e_integrator/integrate.py) | Integrator; transaction orchestration and checks | Keep transaction boundary explicit |
| [tooling/integrator/src/adnd1e_integrator/invariants.py](tooling/integrator/src/adnd1e_integrator/invariants.py) | Integrator; production invariant verification | Keep independent coverage; resolve identity parity before sharing |
| [tooling/integrator/src/adnd1e_integrator/migration.py](tooling/integrator/src/adnd1e_integrator/migration.py) | Integrator; approved direct-migration preconditions and application | Keep separate from Builder planning |
| [tooling/integrator/src/adnd1e_integrator/operations.py](tooling/integrator/src/adnd1e_integrator/operations.py) | Integrator; approved operation-index/registration interpretation | Keep imported module |
| [tooling/integrator/src/adnd1e_integrator/records.py](tooling/integrator/src/adnd1e_integrator/records.py) | Integrator; immutable manifests, validation reports, diffs, book copies | Batch and require successful completion before next-packet message |
| [tooling/integrator/src/adnd1e_integrator/snapshot.py](tooling/integrator/src/adnd1e_integrator/snapshot.py) | Integrator; snapshot/rollback transaction machinery | Keep; not common publisher logic |
| [tooling/integrator/src/adnd1e_integrator/vocabulary.py](tooling/integrator/src/adnd1e_integrator/vocabulary.py) | Integrator; ruleset-specific ontology/profile parsing | Keep; share only proven pure parsing later |

### Builder tests and support: 16

All are Builder-maintained tests and Reviewer evidence when applicable. Run through existing suite discovery; no individual model invocation is required.

| Script | Coverage | Action |
|---|---|---|
| [tooling/builder/tests/_bootstrap.py](tooling/builder/tests/_bootstrap.py) | Test import/fixture setup | Keep |
| [tooling/builder/tests/test_compiler.py](tooling/builder/tests/test_compiler.py) | Compiler and live compilation regressions | Keep |
| [tooling/builder/tests/test_decision_migration.py](tooling/builder/tests/test_decision_migration.py) | Decision-migration planning | Keep |
| [tooling/builder/tests/test_direction.py](tooling/builder/tests/test_direction.py) | Directional semantics | Keep |
| [tooling/builder/tests/test_duplicates.py](tooling/builder/tests/test_duplicates.py) | Duplicate and neighborhood behavior | Keep |
| [tooling/builder/tests/test_edge_schema.py](tooling/builder/tests/test_edge_schema.py) | Production edge schema/corpus checks | Keep |
| [tooling/builder/tests/test_escalation_ids.py](tooling/builder/tests/test_escalation_ids.py) | Escalation identity validation | Keep |
| [tooling/builder/tests/test_governance.py](tooling/builder/tests/test_governance.py) | Governance and escalation resolution | Keep |
| [tooling/builder/tests/test_grain.py](tooling/builder/tests/test_grain.py) | Grain/value-leakage checks | Keep |
| [tooling/builder/tests/test_handoff.py](tooling/builder/tests/test_handoff.py) | Build handoff behavior | Keep |
| [tooling/builder/tests/test_migration.py](tooling/builder/tests/test_migration.py) | Identity-merge planner | Keep |
| [tooling/builder/tests/test_pagemarkers.py](tooling/builder/tests/test_pagemarkers.py) | Pandoc page-marker semantics | Keep |
| [tooling/builder/tests/test_polarity.py](tooling/builder/tests/test_polarity.py) | Derived/authored polarity | Keep |
| [tooling/builder/tests/test_registry_and_vocab.py](tooling/builder/tests/test_registry_and_vocab.py) | Registry and ruleset vocabulary | Keep |
| [tooling/builder/tests/test_review.py](tooling/builder/tests/test_review.py) | Review directive interpretation | Keep |
| [tooling/builder/tests/test_shadowdark_ancestry.py](tooling/builder/tests/test_shadowdark_ancestry.py) | Shadowdark-specific schema/vocabulary/compiler cases | Keep |

### Common tests: 6

Builder owns common implementation maintenance; Reviewer independently verifies required outcomes.

| Script | Coverage | Action |
|---|---|---|
| [tooling/common/tests/test_common_schemas.py](tooling/common/tests/test_common_schemas.py) | Artifact schemas and authorized historical exceptions | Keep |
| [tooling/common/tests/test_herdr_handoff.py](tooling/common/tests/test_herdr_handoff.py) | Historical relay implementation/authority evidence | Keep test history; never infer relay activation from passing tests |
| [tooling/common/tests/test_implementation_evidence.py](tooling/common/tests/test_implementation_evidence.py) | Decision implementation evidence and ownership | Keep |
| [tooling/common/tests/test_role_context.py](tooling/common/tests/test_role_context.py) | Context manifest/receipt/session behavior | Keep |
| [tooling/common/tests/test_scan_agent_queues.py](tooling/common/tests/test_scan_agent_queues.py) | Queue and lineage contract regressions | Keep; do not merge 9,745 lines just to lower file count |
| [tooling/common/tests/test_validate_artifact.py](tooling/common/tests/test_validate_artifact.py) | Exact staged YAML/schema validation | Keep |

### Integrator tests and support: 14

Integrator owns this implementation suite; Reviewer uses it for independent evidence when required.

| Script | Coverage | Action |
|---|---|---|
| [tooling/integrator/tests/_bootstrap.py](tooling/integrator/tests/_bootstrap.py) | Test import/fixture setup | Keep |
| [tooling/integrator/tests/test_admission.py](tooling/integrator/tests/test_admission.py) | Admission and authorized historical repair cases | Keep |
| [tooling/integrator/tests/test_bundles.py](tooling/integrator/tests/test_bundles.py) | Approved-bundle discovery and lineage | Keep |
| [tooling/integrator/tests/test_canonical.py](tooling/integrator/tests/test_canonical.py) | Canonical serialization round trips | Keep |
| [tooling/integrator/tests/test_derive.py](tooling/integrator/tests/test_derive.py) | Deterministic derived fields | Keep |
| [tooling/integrator/tests/test_genesis.py](tooling/integrator/tests/test_genesis.py) | First-integration creation and rollback to absence | Keep |
| [tooling/integrator/tests/test_invariants.py](tooling/integrator/tests/test_invariants.py) | Production graph invariants | Keep |
| [tooling/integrator/tests/test_migration.py](tooling/integrator/tests/test_migration.py) | Migration application and verification | Keep |
| [tooling/integrator/tests/test_migration_v2.py](tooling/integrator/tests/test_migration_v2.py) | Version-two migration operations | Keep |
| [tooling/integrator/tests/test_migration_v3.py](tooling/integrator/tests/test_migration_v3.py) | Version-three migration operations | Keep |
| [tooling/integrator/tests/test_operations.py](tooling/integrator/tests/test_operations.py) | Operation-index handling | Keep |
| [tooling/integrator/tests/test_registration_agreement.py](tooling/integrator/tests/test_registration_agreement.py) | Approved registration agreement | Keep |
| [tooling/integrator/tests/test_transaction.py](tooling/integrator/tests/test_transaction.py) | Transactional application, failures, determinism | Keep |
| [tooling/integrator/tests/test_vocabulary.py](tooling/integrator/tests/test_vocabulary.py) | Active-ruleset vocabulary parsing | Keep |

### Reviewer tests: 2

| Script | User/owner and purpose | Action |
|---|---|---|
| [tooling/reviewer/tests/test_dec0082_r02_acceptance.py](tooling/reviewer/tests/test_dec0082_r02_acceptance.py) | Reviewer; historical DEC-0082 relay revision acceptance | Keep evidence, not routine packet processing |
| [tooling/reviewer/tests/test_dec0082_relay_acceptance.py](tooling/reviewer/tests/test_dec0082_relay_acceptance.py) | Reviewer; historical DEC-0082 relay acceptance | Keep evidence, not a current transport specification |

### Historical Analyst readers: 3

| Script | User/owner and purpose | Action |
|---|---|---|
| [tooling/analyst/adnd1e/dmg/doctags_reader.py](tooling/analyst/adnd1e/dmg/doctags_reader.py) | Analyst; legacy DMG doctags inspection | History; not current Markdown ingestion |
| [tooling/analyst/adnd1e/mm/doctags_reader.py](tooling/analyst/adnd1e/mm/doctags_reader.py) | Analyst; legacy Monster Manual doctags inspection | History; do not combine into a new live parser |
| [tooling/analyst/adnd1e/ua/doctags_reader.py](tooling/analyst/adnd1e/ua/doctags_reader.py) | Analyst; legacy UA doctags inspection | History; retain exact format assumptions |

### Historical PHB Reviewer helpers: 14

These are Reviewer-owned, job-specific scratch tools. Reuse ideas from their packaging checks only after separating them from hardcoded judgments. Do not run them against current output paths during migration.

| Script | Original purpose | Action |
|---|---|---|
| [books/adnd1e/phb/work/reviewer/audit_decision_migration_r02.py](books/adnd1e/phb/work/reviewer/audit_decision_migration_r02.py) | Audit a specific migration revision | History |
| [books/adnd1e/phb/work/reviewer/emit_classes_review_20260801_r02.py](books/adnd1e/phb/work/reviewer/emit_classes_review_20260801_r02.py) | Emit a specific classes Review successor using an earlier emitter | History |
| [books/adnd1e/phb/work/reviewer/emit_phb_reviews.py](books/adnd1e/phb/work/reviewer/emit_phb_reviews.py) | Emit a hardcoded PHB Review set | History |
| [books/adnd1e/phb/work/reviewer/emit_phb_reviews_20260731.py](books/adnd1e/phb/work/reviewer/emit_phb_reviews_20260731.py) | Emit the July 31 Review set | History |
| [books/adnd1e/phb/work/reviewer/emit_phb_reviews_20260731_round2.py](books/adnd1e/phb/work/reviewer/emit_phb_reviews_20260731_round2.py) | Emit the second July 31 set; imported by later scratch scripts | History; preserve its path |
| [books/adnd1e/phb/work/reviewer/emit_phb_reviews_20260801_round3.py](books/adnd1e/phb/work/reviewer/emit_phb_reviews_20260801_round3.py) | Emit the third historical Review round | History |
| [books/adnd1e/phb/work/reviewer/emit_reviewer_queue_20260730.py](books/adnd1e/phb/work/reviewer/emit_reviewer_queue_20260730.py) | Emit a dated Review queue's results | History |
| [books/adnd1e/phb/work/reviewer/emit_reviews_20260802_queue4.py](books/adnd1e/phb/work/reviewer/emit_reviews_20260802_queue4.py) | Emit a specific August 2 set | History |
| [books/adnd1e/phb/work/reviewer/emit_reviews_20260803_queue3.py](books/adnd1e/phb/work/reviewer/emit_reviews_20260803_queue3.py) | Emit a specific August 3 set | History |
| [books/adnd1e/phb/work/reviewer/validate_phb_reviews_20260731.py](books/adnd1e/phb/work/reviewer/validate_phb_reviews_20260731.py) | Validate a dated Review set | History |
| [books/adnd1e/phb/work/reviewer/validate_phb_reviews_20260731_round2.py](books/adnd1e/phb/work/reviewer/validate_phb_reviews_20260731_round2.py) | Validate the second July 31 set | History |
| [books/adnd1e/phb/work/reviewer/validate_phb_reviews_20260801_round3.py](books/adnd1e/phb/work/reviewer/validate_phb_reviews_20260801_round3.py) | Validate the third historical round | History |
| [books/adnd1e/phb/work/reviewer/validate_reviews_20260802_queue4.py](books/adnd1e/phb/work/reviewer/validate_reviews_20260802_queue4.py) | Validate the August 2 set | History |
| [books/adnd1e/phb/work/reviewer/validate_reviews_20260803_queue3.py](books/adnd1e/phb/work/reviewer/validate_reviews_20260803_queue3.py) | Validate the August 3 set | History |

### Local Architect/Herdr helpers: 7

These are ignored local historical checks or messages. They are not portable startup requirements and may contain machine/session-specific assumptions.

| Script | Original user and purpose | Action |
|---|---|---|
| [.local/architect/check_dec_0081.py](.local/architect/check_dec_0081.py) | Architect; targeted Dispatcher-era Decision preflight | History |
| [.local/architect/check_dec_0082.py](.local/architect/check_dec_0082.py) | Architect; Dispatcher-retirement preflight | History |
| [.local/architect/check_shadowdark.py](.local/architect/check_shadowdark.py) | Architect; bounded Shadowdark bootstrap checks | History |
| [.local/architect/validate_dec0087.py](.local/architect/validate_dec0087.py) | Architect; targeted DEC-0087 validation | History |
| [.local/herdr/notify-shadowdark-20260919.ps1](.local/herdr/notify-shadowdark-20260919.ps1) | Architect/owner; dated Shadowdark notification | History; never replay old assignments |
| [.local/herdr/reload-roles-20260919.ps1](.local/herdr/reload-roles-20260919.ps1) | Architect/owner; dated role-reload operation | History |
| [.local/herdr/stop-rc-20260921.ps1](.local/herdr/stop-rc-20260921.ps1) | Architect/owner; dated RC stop notification | History; current RC hold comes from authority, not replaying this script |

**Index total: 7 + 18 + 15 + 16 + 6 + 14 + 2 + 3 + 14 + 7 = 102.**

## 12. Bottom Line

There is no useful goal of turning 102 source files into ten giant files. There is a useful goal of giving each role **one predictable preparation call and one completion call**, backed by existing tested code and explicit judgment boundaries.

Start with the recurring generated-authority defect, then the common read-only preparation interface and staged publication support. Build a reusable Reviewer publisher instead of more job-specific emitters. Keep Integrator's transaction and independent Review intact. Preserve the historical scripts without teaching a fresh Gemini agent to run them.

The likely reduction is in model-supervised plumbing, avoidable correction rounds, and repeated discovery. The actual request saving must be measured on the target service after implementation; this audit does not claim that the implementation already exists.

### Verification of this deliverable

- All 102 inventory paths occur exactly once in section 11; no missing, duplicate, or extra entries.
- All 122 local Markdown links resolve in this workspace.
- All 102 current script SHA-256 values still match the handoff inventory.
- The six cited Reviews parse successfully and contain exactly 48 node-local `routing_basis` corrections in total.
- This is a static architecture audit, not a runtime change. The production test suites were not rerun, and no new implementation is represented as tested or approved.
- No Decision, packet assignment, Herdr notification, or normal processing work was issued by this audit.
