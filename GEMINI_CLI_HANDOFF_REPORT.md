# Gemini CLI Repository Handoff

## 1. Read This First

This is an evidence-based transfer report, not a new governance Decision, an approval, or an assignment to process packets. It describes the working tree at the snapshot time below. It does not design Antigravity orchestration. Repository artifacts and current contracts take precedence over this report after the snapshot.

The repository creates **mechanical relationship / impact-analysis graphs** from tabletop RPG source packets. It does not aim to reproduce rulebooks, store every statistic, or build a general semantic knowledge graph. The extraction test is: if a source mechanic changes, would a target mechanic need review?

**Current priority: Shadowdark. `basicdnd/rc` is owner-paused under DEC-2026-0086.** Preserve its source, claims and published history; do not process, repair, withdraw or clean it merely to clear queues. No new instruction in this report lifts that hold.

**Transfer the actual working tree, not just a fresh Git clone.** Uncommitted governance/tooling edits and published artifacts exist. Ignored scratch scripts also exist. Preserve authoritative bytes, relative paths, and line endings because artifact hashes refer to them. Do not normalize YAML, rename directories, flatten files, or reserialize published artifacts during transfer.

There are five roles, no Dispatcher. Roles are responsibilities, not model providers. Moving from Claude/Codex to Gemini does not transfer another role's authority to whichever agent happens to be available.

### Navigation

- Sections 2-4: roles, workflow, authority and directory design.
- Sections 5-7: commands, runtime dependencies, transfer hazards and validation.
- Section 8: measured status, current next work and backlog reconciliation.
- Section 9: complete project-script inventory, one entry per file.
- Section 10: complete incoming/claimed packet ledger.
- Section 11: Decision and implementation-evidence ledger.
- Section 12: diagnostics and snapshot integrity.

## 2. The Five Roles

Each agent starts from `AGENTS.md` and its own `agents/<role>/INSTRUCTIONS.md`. Resolve ruleset, book, source and packet identifiers from the actual work item and manifests. Do not invent a source or packet identifier for infrastructure/documentation tasks.

| Role       | Main input                                       | Work and ownership                                                                                                                   | Durable result                                                      | Must not do                                                     |
| ---------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------- | --------------------------------------------------------------- |
| Architect  | Complete pending ESC and its bounded evidence    | Governs ontology, prefixes, edge semantics, schemas, contracts, identity migrations, domains and general rules; defines exact        | `DEC-YYYY-NNNN.yaml` , versioned governance changes, escalation     | Extract GURs, compile ordinary GUPs, approve routine rows, edit |
|            |                                                  | implementation ownership and acceptance tests                                                                                        | disposition                                                         | canonical state                                                 |
| Analyst    | One claimed source packet, metadata and supplied | Reads the complete bounded packet, interprets mechanically load-bearing relationships, supplies citations and candidate identities   | Immutable GUR revision; ESC for architectural questions             | Mint unauthorized prefixes/types, derive owned polarity, modify |
|            | registry/neighborhood slices                     |                                                                                                                                      |                                                                     | canonical, start a second normal packet                         |
| Builder    | Active GUR or exact Review correction, current   | Deterministic normalization, validation, identity resolution, duplicate detection, derivation, compiler and common tooling within    | GUP + CSV components + validation report; IMP for assigned Decision | Decide source meaning, silently repair GURs, approve its own    |
|            | relevant registry/state, named Decisions         | assigned ownership                                                                                                                   | implementation                                                      | work, write canonical                                           |
| Reviewer   | Exact GUP and report, source evidence, governing | Independently verifies meanings, directions, citations, grain, identities and executable corrections; separately verifies            | Review, Approved bundle and checksummed components, or              | Treat Builder tests as proof of source correctness, improvise   |
|            | Decisions and relevant neighborhood              | implementation reports                                                                                                               | correction/ESC; independent IMP Review                              | ontology, alter canonical                                       |
| Integrator | Exact Approved bundle, Review, current canonical | Applies only approved operations transactionally, registers nodes, rebuilds exports/degrees/roles, validates, snapshots and rolls    | Canonical state, INT manifest, validation/diff reports, per-book    | Interpret source, invent fixes, integrate unapproved work,      |
|            | and registry baselines                           | back                                                                                                                                 | integration record; rejection when needed                           | manually edit generated JSON                                    |

### Role-Specific Operating Details

- **Architect:** incomplete ESCs are returned with a return Decision; returned is not decided. Substantive rulings specify migration impact, exact affected paths, owners and evidenceable tests. A later-role outcome must not be an impossible prerequisite for an earlier implementation report. Mutable contract tests should use minimum versions plus substantive anchors where authorized.
- **Analyst:** GUR candidate nodes use `proposed_id`, `proposed_label`, `kind`, `why_needed`, not `label`/`evidence` aliases. Relationship evidence is the production `evidence` column, not `evidence_class`. Metadata is informational, not automatically graph content.
- **Builder:** deterministic output does not mean approval-ready output. Distinguish additions, pending additions depending on node registration, updates, blocked rows and rejected rows. Existing legal prefix/kind proposals do not automatically require Architect approval. Direct Decision migrations have a different provenance root from packet GUPs.
- **Reviewer:** exact row corrections belong in row-local `exact_corrections`; ordinary correction work returns to Builder. Do not translate comments into an implicit executable directive. Validate staged YAML before publication. Current instructions require foreground work and continued bounded processing, not abandoned background tasks.
- **Integrator:** only this role writes `rulesets/<id>/canonical/`. New-ruleset genesis is an approved transaction, not a header-only baseline prepared in advance. Failure restores absence when absence was the starting state. Registered nodes may legitimately have no edges, so node-registry rows can exceed exported graph-node rows.

### Context And Token Discipline

Run `tooling/common/role_context.py verify` for role, scope and a genuinely unique persistent actor-session ID. On a miss, read every emitted stable authority path before `record`; on a same-session hit, do not reread those files merely for orientation. Receipts are checksum-bound local caches, never work evidence. A new Gemini actor cannot inherit Codex/Claude receipt trust.

Always read current task inputs separately. Receipts do not cover live GURs, Reviews, graph neighborhoods, registry state, component checksums or transaction preconditions. Do not recursively load the full corpus each packet. This report's broad audit is specifically requested transfer work, not a model for routine startup.

## 3. Workflow And Artifact Meaning

The current normal-packet contract is one repository-wide relay:

```text
Analyst --GUR--> Builder --GUP--> Reviewer --Approved bundle--> Integrator
   ^                                                              |
   +---------- successful integration + next-packet prompt --------+

Corrections: Integrator -> Reviewer -> Builder -> Analyst
Escalation: any role -> Architect -> originating role
```

Analyst selects exactly one packet. It must not claim or prepare another until terminal integration and Integrator's direct next-packet notification. When idle, use the contract's lexically smallest eligible packet ID; a scanner candidate is not automatically an executable assignment. An escalation pauses the current packet at its originator, including any necessary implementation/independent-review prerequisites. Architect returns control to that originator and additionally notifies an independently ready implementation owner when required. Decision implementation work follows its explicit sequence, not a second normal packet relay.

Current communication is `tooling/common/Send-HerdrPrompt.ps1 -Role <Role> -Message <Message>`. It is best-effort notification, not approval, artifact consumption or a second workflow database. Every next-step message identifies exact artifact/path, next role, prerequisite and reason. The wrapper adds local time and repository context. Do not resurrect the retired settled/uncertain relay or Dispatcher. Antigravity transport design is intentionally left to Gemini and the owner.

| Artifact              | Meaning                                                                                         | Where it lives                                                       |
| --------------------- | ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Packet / PKT          | Frozen bounded source and scope                                                                 | `books/<r>/<b>/packets/claimed/<packet>/`                            |
| GUR                   | Analyst's interpreted recommendations, not graph operations approved for application            | `books/<r>/<b>/artifacts/gur/`                                       |
| GUP                   | Builder's deterministic patch, proposed registrations and validation provenance                 | `books/<r>/<b>/artifacts/gup/` , with reports under `build/reports/` |
| REV-GUP               | Independent per-row judgment and exact corrections                                              | `books/<r>/<b>/artifacts/reviews/`                                   |
| APPROVED              | Exact approved GUP/Review and checksummed operation components; one logical job                 | `books/<r>/<b>/artifacts/approved/`                                  |
| INT                   | Terminal canonical transaction consuming exact bundle(s)                                        | `rulesets/<r>/manifests/` and book `artifacts/integrated/`           |
| Integration rejection | Exact failed bundle and machine-readable failures; returns work to Reviewer                     | `rulesets/<r>/reports/`                                              |
| ESC                   | Bounded architectural question with evidence and options                                        | `rulesets/<r>/escalations/{pending,returned,decided}/`               |
| DEC                   | Architect authority and assignment; approval of a Decision does not prove implementation        | `rulesets/<r>/escalations/decisions/`                                |
| IMP-DEC               | Assigned Builder/Integrator implementation with exact evidence                                  | `rulesets/<r>/decision-implementations/`                             |
| REV-IMP               | Independent implementation disposition; terminal approval consumes eligible implementation work | `rulesets/<r>/decision-implementation-reviews/`                      |

Published artifacts are immutable and append-only. A successor names `revision`, `supersedes` and `handoff`. Do not move a GUP/Review/Approved file to a `done` folder. Completion is recorded by downstream ID/checksum consumption; retained files are provenance. Packet `claimed` directories also remain after integration. The pending/returned/decided ESC directories have their own explicit lifecycle and are not a precedent for moving other artifact kinds.

`packet_update` GUPs consume a GUR; `decision_migration` GUPs consume checksummed Decisions and pinned canonical/registry baselines without a GUR. Direct migration operation models v1/v2/v3 are bounded grammars, not free-form patch permission. Unreadable or historically malformed artifacts may have exact checksummed exception Decisions: do not repair or delete them just because a generic parser complains.

### Graph And Source Semantics To Preserve

- One graph per compatible ruleset, across its books. Identical IDs in different rulesets are unrelated identities.
- The production edge has 18 columns. Assertion identity uses source ID, edge type, target ID, aspect and condition under the ruleset's normalization rules; `ALTERNATIVE_TO` is symmetric. Labels/citations are not new assertion identities.
- Store mechanically consequential relationships, not numeric magnitudes, copied descriptions or arbitrary taxonomy. Authored polarity belongs only to `MODIFIES`, `TRIGGERS`, `CONSTRAINS`; deterministic types use governed derivation.
- Current incoming/claimed source is authoritative for spelling, grammatical number, labels and marker-derived printed page. Legacy names do not overrule it.
- Packets use Pandoc Markdown. Programmatic semantic parsing must use Pandoc-compatible tooling, including tables, superscripts and subscripts.
- `{#pNNN}` at a line/block end starts that entire block on that page; in the last table cell it starts the entire row on that page; inline between words it moves following text to that page. Resolve placement before stripping markers.
- Shadowdark Constitution 1.8 admits `mstat_monster_level` for the shared monster-level rule, not per-creature numeric statistics. `CLASSIFIED_AS` is bounded to authorized mechanical classifications, not general membership. Read current Constitution for exact scope.
- Historical Shadowdark GUR version acceptance is declared by `rulesets/shadowdark/ruleset.yaml` and validated under current constraints; do not create mass version-only successors.

## 4. Directory Structure And Why

```text
dnd/
  AGENTS.md, README.md, REPOSITORY_STRUCTURE.md, CONTRIBUTING.md
  CLAUDE.md, BUILDER.MISTRAL.md, BUILDER.SKILLS.MISTRAL.md
  agents/{architect,analyst,builder,reviewer,integrator}/INSTRUCTIONS.md
  contracts/
  schemas/common/
  schemas/<ruleset>/{graph,registries,books/<book>}/
  rulesets/<ruleset>/
    ruleset.yaml, governance/, profiles/, registries/
    canonical/                     # only where actually initialized by integration
    escalations/{pending,returned,decided,decisions}/
    decision-implementations/, decision-implementation-reviews/
    manifests/, reports/, cross-book/, releases/
  books/<ruleset>/<book>/
    book.yaml, source/
    packets/{incoming,claimed,completed}/
    artifacts/{gur,gup,reviews,approved,integrated}/
    work/<role>/, reports/, archive/
  tooling/{analyst,builder,common,integrator,reviewer}/
  migrations/<ruleset>/
  build/{reports,snapshots,staging,...}/
  reports/
  .local/, .claude/, .agents/, .git/
```

This is a structural pattern, not a claim that every optional directory is populated in every ruleset/book.

| Area                                     | Why separate / source of authority                                                     | Preservation and ownership                                                                        |
| ---------------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Root instructions                        | Discoverable startup and navigation independent of model provider                      | Preserve; Architect-governed orientation, not graph data                                          |
| `agents/`                                | Five role-specific boundaries and bounded inputs                                       | Current role instructions; do not collapse roles during migration                                 |
| `contracts/`                             | Universal lifecycle, identity, source, queue and communication rules shared by systems | Architect-owned governance; versions and acceptance evidence matter                               |
| `schemas/common/`                        | Shared envelope, handoff, Review, Decision, bundle and implementation grammars         | Compose with ruleset schemas; resolve sibling `$ref` s correctly                                  |
| `schemas/<r>/graph/`                     | Ruleset-specific controlled types/IDs and artifact constraints                         | A universal envelope alone does not validate a production row                                     |
| `schemas/<r>/registries/`                | Validate books, sources, domains, races and general-rule registries                    | Distinct from extraction and canonical storage                                                    |
| `schemas/<r>/books/<b>/`                 | Book-specific extraction restrictions                                                  | Preserve separation between common mechanics and source-specific constraints                      |
| `rulesets/<r>/governance/`               | Constitution and ontology for that one combined graph                                  | Architect owns semantic changes                                                                   |
| `rulesets/<r>/registries/`               | Canonical identities, source provenance, books, domains and promoted rules             | Node registrations applied by Integrator after approval; vocabulary changes governed              |
| `rulesets/<r>/profiles/`                 | Impact and role-derivation policy                                                      | Empty bootstrap thresholds are legitimate; do not invent values                                   |
| `rulesets/<r>/canonical/`                | Authoritative edge CSV plus regenerated node/export state                              | Integrator-only mutation; graph JSON is generated, never a second editable truth                  |
| `rulesets/<r>/manifests/` and `reports/` | Audit of transactions, checksums, validation, rejection and differences                | Durable evidence, not disposable output                                                           |
| `rulesets/<r>/cross-book/`               | Explicit relationships/conflicts that span book boundaries in one ruleset              | Does not permit cross-ruleset identity merging                                                    |
| `rulesets/<r>/releases/`                 | Release packaging boundary                                                             | Not an alternative canonical graph                                                                |
| `books/<r>/<b>/source/`                  | Edition/transcription-specific preserved source                                        | Source IDs are provenance; metadata is not automatic graph content                                |
| `packets/incoming/`                      | Steward-provided bounded intake                                                        | Retained incoming files can already be claimed and integrated                                     |
| `packets/claimed/`                       | Frozen source copy, packet metadata and bounded context                                | Claim status is not completion status; retain checksum provenance                                 |
| `packets/completed/`                     | Reserved/archive organization                                                          | Not the live completion authority; do not move claimed inputs to manufacture done state           |
| `artifacts/`                             | Append-only stage outputs organized by kind and namespace                              | GUR/GUP/REV/APPROVED revisions remain even after consumption                                      |
| `work/<role>/`                           | Disposable role working space                                                          | Ignored by Git; contains historical scripts worth inventorying, not published authority           |
| `tooling/`                               | Reusable deterministic implementations and tests separated by owner                    | Common scanner semantics need governed authorization; not every helper is current/safe            |
| `migrations/adnd1e/legacy-import/`       | Preserves original inconsistent exports/documents                                      | History is not silently promoted to current artifact authority                                    |
| `build/reports/`                         | Compiler validation reports pinned by published artifacts                              | Must transfer referenced reports; the name `build` does not mean disposable                       |
| `build/snapshots/`                       | Transaction rollback evidence                                                          | Preserve relevant snapshots, including genesis absence semantics; do not run cleanup as migration |
| `build/*staging*/`                       | Publication preflight candidates                                                       | Non-authoritative drafts; inspect references before discarding                                    |
| Root `reports/`                          | Cross-repository diagnostic/report area                                                | Read each report's declared scope/date, not directory name alone                                  |
| `.local/role-context/`                   | Same-session instruction receipts                                                      | Can archive for investigation; never trust in a fresh Gemini actor session                        |
| `.local/herdr/`                          | Old communication state/requests and one-off helpers                                   | Retired transport history; not a live queue or completion database                                |
| `.claude/`                               | Local provider-specific settings                                                       | Review separately for privacy/permissions; do not automatically import as Gemini policy           |
| `.agents/`                               | Local agent integration surface; no script files discovered in this snapshot           | Not the canonical five-role instruction directory                                                 |
| `.git/`                                  | Version history and working-tree baseline                                              | Preserve history where practical; internal hooks/templates excluded from project script inventory |

### Existing System And Book Namespaces

- `adnd1e`: `phb`, `dmg`, `mm`, `ua`.
- `basicdnd`: `rc`, explicitly paused.
- `shadowdark`: `sd`, `cs1`, `cs2`, `cs3`, `shadowdome`, `western-reaches-pg`.

The actual Western Reaches slug is **`western-reaches-pg`**, not the originally suggested underscore spelling. `books/` remains the source workspace root; `rulesets/` holds combined graph state. Do not rename either root during handoff: published paths are checksummed provenance.

### Contract Index

| Contract                     | What a fresh agent needs it for                                                     |
| ---------------------------- | ----------------------------------------------------------------------------------- |
| `ARTIFACT_LIFECYCLE.md`      | Stage meanings, immutable revisions and publication requirements                    |
| `ESCALATION_CONTRACT.md`     | Complete architectural packages, returns and Decision evidence                      |
| `FILE_NAMING.md`             | Artifact IDs, revision names and Windows-safe ESC timestamps                        |
| `GRAPH_INVARIANTS.md`        | Universal machine and human validation obligations                                  |
| `HERDR_HANDOFFS.md`          | Current relay, corrections, pauses and notification semantics                       |
| `ROLE_CONTEXT_LOADING.md`    | Stable-context receipts vs always-read task inputs                                  |
| `ROLE_CONTEXT_MANIFEST.yaml` | Exact stable authority patterns per role and scope                                  |
| `SCOPE_AND_IDENTITY.md`      | Ruleset/book/source/packet namespaces and identity scope                            |
| `SOURCE_MARKDOWN.md`         | Pandoc, page markers, packet boundaries and source authority                        |
| `WORK_QUEUES.md`             | Active leaves, handoffs, consumption, legacy exceptions and implementation evidence |

## 5. Runtime And Commands

Existing runtime is Windows/PowerShell 7 plus Python and Pandoc. No project `pyproject.toml`, `requirements.txt`, package lockfile or vendored dependency tree was found in the inventory. The Python packages are run from `src` through `PYTHONPATH`, not installed project distributions. Third-party imports used are PyYAML, jsonschema and referencing; standard-library modules cover most other work. Record actual installed versions below rather than treating them as a declared minimum.

Use **`pwsh -NoProfile`** for automated shell execution. The owner's profile previously emitted `Import-Clixml` / `Import-Module` errors before commands ran. In Codex tool execution this audit used `login: false`. A new runtime must set the equivalent explicitly.

The following are examples to run only within the assigned role. Replace placeholders with exact current paths. Publication/integration commands are not startup checks.

```powershell
# Read-only queue view. JSON retains diagnostics even when console verbosity is off.
python tooling/common/scan_agent_queues.py --root . --json
.\tooling\common\scan-agent-queues.ps1 -Root . -All -Verbose false

# Context verification. A new actor uses a NEW session ID.
python tooling/common/role_context.py verify --root . --role analyst `
  --ruleset shadowdark --book sd --session-id <actor-session-id> --json
# Only after actually reading the emitted stable files:
python tooling/common/role_context.py record --root . --role analyst `
  --ruleset shadowdark --book sd --session-id <actor-session-id>

# Target-only YAML/JSON publication preflight. The path is positional, NOT --path.
python tooling/common/validate_artifact.py <staged-artifact.yaml> `
  --schema schemas/common/review.schema.json

# Builder compiler. May publish immutable output and runs its test gate.
$env:PYTHONPATH = 'tooling/builder/src'
python -m adnd1e_builder compile <gur.yaml> --repo-root . --ruleset shadowdark
python -m adnd1e_builder compile <gur.yaml> --repo-root . --ruleset shadowdark `
  --review <review.yaml> --revision <next-number> --supersedes <prior-gup-id>
python -m adnd1e_builder lint-source <source.md>
python -m adnd1e_builder verify-pages <claimed-packet-directory> --gup-dir <gup-directory>

# Integrator read-only inspection. Set BOTH ruleset and book selection.
$env:PYTHONPATH = 'tooling/integrator/src'
python -m adnd1e_integrator --repo-root . --ruleset-id shadowdark --books=sd queue
python -m adnd1e_integrator --repo-root . --ruleset-id shadowdark validate

# Integrator only, exactly one approved current bundle:
python -m adnd1e_integrator --repo-root . --ruleset-id shadowdark --books=sd `
  integrate <approved-bundle-id> --dry-run
# Actual application removes --dry-run only after all ordinary checks.

# Existing Herdr transport only, not an Antigravity design:
.\tooling\common\Send-HerdrPrompt.ps1 -Role Builder -Message 'Exact work and prerequisite here.'
```

**Integrator argparse caution:** `--books` takes multiple values. Use `--books=sd` for this single-book invocation so it does not swallow the subcommand. That exact queue invocation was checked in this audit. Do not rely on the AD&D default book list for Shadowdark. The package names `adnd1e_builder` and `adnd1e_integrator` are historical names, not permission to omit ruleset selection.

Useful test entry points, for the corresponding tool owner/independent Reviewer:

```powershell
python -m unittest discover -s tooling/builder/tests
python -m unittest discover -s tooling/common/tests
python -m unittest discover -s tooling/integrator/tests
python -m unittest discover -s tooling/reviewer/tests
```

These are **not** instructions to run every suite each agent turn. Some tests read live artifacts and clone the repository; historical relay tests invoke fake endpoints. Scope validation to the change, then follow any exact Decision-required suite gate. Passing tests do not prove source judgments. Do not bypass normal compilation with `--skip-tests` for production merely to save time.

## 6. Transfer Hazards And Unfinished Maintenance

1. **Queue candidate inflation:** retained incoming Markdown remains offered even after its packet integrates. Reconcile `packet.yaml.original_filename`, claimed source and exact INT consumption. Never send 144 Analyst prompts because the scanner returns 144 SD candidates.
2. **Consumed blocked GUPs still displayed:** seven current scanner blocked items correspond to exact GUPs already consumed in integration manifests. They are listed with evidence later. Do not send those packets backward merely to clear the display. Scanner changes require appropriate governed ownership.
3. **AD&D validation debt:** this graph is populated but has legacy invariant findings. No empty queue or approved recent implementation erases that debt. Repair needs bounded provenance-backed work, not a mass automatic rewrite.
4. **Stale orientation text:** README/REPOSITORY_STRUCTURE contain older concurrent-work language; AGENTS and HERDR_HANDOFFS 2.4 define the current single normal-packet relay. Builder README contains old claims that proposed nodes wait for Architect; current Builder instructions permit legal unambiguous registrations through ordinary Review. Do not follow old prose over current contracts.
5. **Bootstrap metadata is not a progress meter:** AD&D ruleset metadata still says migration pending/placeholders; Shadowdark profiles/source records retain bootstrap/awaiting-intake language despite integrated data. Measured canonical and INT evidence below is more specific. Empty Shadowdark role thresholds remain legitimate configuration, not a defect to fill arbitrarily.
6. **Hardcoded transport/provider assumptions:** Send-HerdrPrompt checks Claude for Analyst/Builder/Integrator and Codex for Reviewer/Architect, defaults to `D:\analysis\dnd`, and requires `HERDR_BIN_PATH`. It will not transparently recognize Gemini. Update transport-related contracts and role instructions only as a separately authorized migration; no Antigravity implementation is included here.
7. **Retired relay is still executable code:** send-agent-handoff and three `.local/herdr` scripts contain old locks, session pins and settlement behavior. Their tests/history may still be needed to explain published evidence. Do not execute them as the new communication system.
8. **Broken broad nudge helper:** Keep-AgentsGoing sends Builder and Integrator prompts before attempting invalid `-Role agent`. `agent` is not an allowed role. It also does not select the one eligible relay step. Treat as unsafe operator scratch, not supported automation.
9. **Legacy source readers:** the three doctags readers hardcode `/home/claude/addgraph/...` and parse legacy tags using regex. They are not current Pandoc packet parsers, and can fail on import on this machine. Do not retrofit them by silently changing source meaning.
10. **Local Reviewer emitters are historical authoring aids:** their source judgments are hardcoded from past manual audits. Re-running them is not a fresh independent Review and may attempt publication. Preserve for explanation only unless explicitly revalidated.
11. **No fully pinned runtime manifest:** installed versions are evidence, not portable dependency constraints. Gemini should establish reproducible environment setup under separately assigned implementation work.
12. **Transfer is not source-completeness certification:** all currently claimed PHB packets being integrated does not mean the whole PHB/DMG/MM/UA books have been exhaustively extracted. Unpacketized preserved legacy inputs are not new queue assignments.
13. **Universal invariant wording lags vocabulary:** GRAPH_INVARIANTS 1.1 still says thirteen edge types, while Shadowdark Constitution 1.8 and its production schema explicitly authorize fourteen including CLASSIFIED_AS. Preserve the ruleset-specific authorization; flag the wording for Architect maintenance rather than removing valid rows.

## 7. Transfer Checklist And Validation Limits

- Preserve tracked modifications and untracked published artifacts along with Git history. Include referenced `build/reports`, rollback snapshots and source copies. Do not discard all ignored files without examining the inventory.
- Transfer this report and the repository. The report is self-contained; local audit JSON is supplementary evidence, not required governance.
- Keep local provider credentials/settings separate from ordinary source transfer. This report does not copy authentication secrets or recommend importing machine permissions.
- On the new service, start each role with current AGENTS, its own instructions and fresh scoped receipt verification. Do not use this report as an instruction-cache receipt.
- Preserve NO RC and the one-packet relay while Gemini designs replacement transport. No background nudge-all loop is authorized by the handoff.
- Re-run bounded queue and canonical read-only checks after transfer; compare bytes/hashes and logical counts. If work continues during transfer, take a new coherent snapshot rather than mixing timestamps.
- This audit parses and inventories code but does **not** execute historical authoring scripts, broadcast prompts, compile packets, integrate bundles or rerun the complete regression suites. It performs read-only queue and canonical checks plus report-completeness checks. Any existing test claims in artifact history remain claims of those published artifacts, not new test results from this task.



## 8. Current Status And Remaining Work

Snapshot: **2026-10-02T11:51:21.190688-04:00**. Queue scan: `2026-10-02T15:51:21.155581+00:00`. Git HEAD: `a09e0308f5af01fce7433151529f1ac0ebc47eb3`. These measurements include uncommitted working-tree content.

### Bottom Line

**Shadowdark SD: 144 incoming files, 91 claimed packets, 91 distinct claimed packets integrated, 53 unclaimed files remaining.** All 91 claimed SD packets have terminal integration evidence; there is no unintegrated claimed SD packet in this snapshot. The 92 successful SD integration manifests are transactions, not 92 distinct packets. Revisions/supplemental work can produce more than one transaction for a packet.

**Next ordinary owner: Analyst**, subject to the current Integrator-to-Analyst relay notification and fresh scope/readiness checks. The first unclaimed intake filename in sorted intake order is `091-monster-family-devils.md`. It has no claimed packet ID yet; derive that ID from its actual metadata/source rather than inventing one from this report. Follow the contract selection rule, not the filename alone. No new claim or notification was made by this audit.

Builder, Reviewer, Architect and Integrator have **zero ready items in the common scanner**. No pending ESC YAML was found. Seven blocked Reviewer displays are already-integrated GUPs, not seven new correction assignments. RC contributes the two active claims but remains paused.

**Important qualification:** completed means a successful terminal integration is recorded, not that every historical component still passes a fresh byte check. The separate Integrator queue reports five Approved edge-component checksum mismatches and one manifest with no edges component. These are real transfer-integrity follow-ups, disclosed below; they were not repaired or dismissed as harmless.

| Ruleset | Constitution | Canonical edges | Exported nodes | Registry rows | Successful INT manifests | Latest successful manifest |
| --- | --- | --- | --- | --- | --- | --- |
| adnd1e | 1.8 | 5179 | 1456 | 1477 | 21 | [rulesets/adnd1e/manifests/INT-20260905-001.json](rulesets/adnd1e/manifests/INT-20260905-001.json) |
| basicdnd | 1.0 | absent | absent | 0 | 0 | - |
| shadowdark | 1.8 | 866 | 394 | 481 | 92 | [rulesets/shadowdark/manifests/INT-20261001-005.json](rulesets/shadowdark/manifests/INT-20261001-005.json) |



Counts are parsed CSV data rows, excluding headers. Exported graph nodes need not include every registry-only identity. Basic D&D has no canonical baseline and no integrations; this is not authorization to initialize it.

| Ruleset/book | Incoming MD | Claims | Integrated claims | Unclaimed incoming | GUR YAML | GUP YAML | Review YAML | Approved manifests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| adnd1e/dmg | 0 | 1 | 1 | 0 | 5 | 7 | 6 | 3 |
| adnd1e/mm | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| adnd1e/phb | 0 | 20 | 20 | 0 | 56 | 126 | 131 | 45 |
| adnd1e/ua | 0 | 2 | 1 | 0 | 5 | 3 | 3 | 1 |
| basicdnd/rc | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| shadowdark/cs1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| shadowdark/cs2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| shadowdark/cs3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| shadowdark/sd | 144 | 91 | 91 | 53 | 108 | 133 | 132 | 107 |
| shadowdark/shadowdome | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| shadowdark/western-reaches-pg | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |



Artifact counts include revisions and historical outputs; they are not counts of pending jobs. AD&D UA has one terminal-withdrawn old Cavalier claim, not unfinished work. The other 22 AD&D claims have integration evidence. Five additional Shadowdark book workspaces are registered but have no incoming packets or claims yet.

### Raw Scanner Versus Executable Work

| Role       | Raw ready | Raw active | Raw blocked | Interpretation                                                                                   |
| ---------- | --------- | ---------- | ----------- | ------------------------------------------------------------------------------------------------ |
| Analyst    | 146       | 2          | 0           | 146 = 144 retained SD intake + 2 paused RC; actual new SD backlog is 53. Active 2 are paused RC. |
| Builder    | 0         | 0          | 0           | No ready compile/Decision item.                                                                  |
| Reviewer   | 0         | 0          | 7           | Seven consumed GUPs remain displayed as blocked; evidence below.                                 |
| Architect  | 0         | 0          | 0           | No pending ESC or ready Architect item.                                                          |
| Integrator | 0         | 0          | 0           | No ready bundle.                                                                                 |



Common scanner exit: **1** (ready candidates exist); lineage errors: **0**. ReadyCount=146, ActiveCount=2, BlockedCount=7, InformationalCount=270, diagnostics=86. Do not interpret exit 1 as a failed scan.

| Displayed blocked GUP                                  | Published terminal integration of that exact GUP                                                           | Queue blocker named                                                                       |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| GUP-PKT-SD-062-065-spells-illusion-to-magic-circle-r02 | [rulesets/shadowdark/manifests/INT-20260926-003.json](rulesets/shadowdark/manifests/INT-20260926-003.json) | Blocked GUP is waiting on: REV-GUP-PKT-SD-062-065-spells-illusion-to-magic-circle-r01-r01 |
| GUP-PKT-SD-068-070-spells-prophecy-to-shapechange-r02  | [rulesets/shadowdark/manifests/INT-20260926-005.json](rulesets/shadowdark/manifests/INT-20260926-005.json) | Blocked GUP is waiting on: REV-GUP-PKT-SD-068-070-spells-prophecy-to-shapechange-r01-r01  |
| GUP-PKT-SD-087-089-stealth-surprise-and-combat-r02     | [rulesets/shadowdark/manifests/INT-20260926-008.json](rulesets/shadowdark/manifests/INT-20260926-008.json) | Blocked GUP is waiting on: REV-GUP-PKT-SD-087-089-stealth-surprise-and-combat-r01-r01     |
| GUP-PKT-SD-096-100-example-of-play-r03                 | [rulesets/shadowdark/manifests/INT-20260926-012.json](rulesets/shadowdark/manifests/INT-20260926-012.json) | Blocked GUP is waiting on: REV-GUP-PKT-SD-096-100-example-of-play-r01-r01                 |
| GUP-PKT-SD-110-110-let-there-be-darkness-r02           | [rulesets/shadowdark/manifests/INT-20260926-014.json](rulesets/shadowdark/manifests/INT-20260926-014.json) | Blocked GUP is waiting on: REV-GUP-PKT-SD-110-110-let-there-be-darkness-r01-r01           |
| GUP-PKT-SD-111-111-optional-modes-of-play-r02          | [rulesets/shadowdark/manifests/INT-20260926-015.json](rulesets/shadowdark/manifests/INT-20260926-015.json) | Blocked GUP is waiting on: REV-GUP-PKT-SD-111-111-optional-modes-of-play-r01-r01          |
| GUP-PKT-SD-152-153-desert-r02                          | [rulesets/shadowdark/manifests/INT-20260929-005.json](rulesets/shadowdark/manifests/INT-20260929-005.json) | Blocked GUP is waiting on: REV-GUP-PKT-SD-152-153-desert-r01-r01                          |



The exact GUP IDs above match the GUP IDs inside the consuming manifests, not just similar packet names. This is a reporting/consumption inconsistency to evaluate under Architect/Builder ownership, not permission to reintegrate or rewrite history.

The Integrator's separate `--ruleset-id shadowdark --books=sd queue` returned ready=0, integrated=92, superseded=7, rejected=2, queue_integrity=0, diagnostics=6, exit=2. Its diagnostics are disclosed in section 12; this command's diagnostic exit is distinct from the common scanner's zero lineage errors.

### Completed Governance And Remaining Maintenance

Recent completed implementation lineages include DEC-0103 classification validation, DEC-0104 light-source classification, DEC-0105 blocked-GUR routing, and DEC-0107 cross-GUP Review lineage resolution. DEC-0107 is at IMP r03 with terminal approved REV-IMP r03-r01; the Angels packet has since integrated. DEC-0106 production-schema admission is also reflected in integrated Monster Attributes. These are not still waiting for a ruling merely because old conversation messages request one. The full Decision/evidence ledger follows in section 11.

Published approval evidence proves the named implementation stage, not every downstream obligation in every Decision. Preserve Decision sequences and `post_implementation_requirements`; queue absence alone is not a universal completion proof. The packet ledger verifies actual integrations for the current claimed SD corpus.

| Remaining item | Next responsible role | Scope / prerequisite |
| --- | --- | --- |
| 53 unclaimed SD intake packets | Analyst, then normal four-stage relay | Exactly one packet at a time; no RC; full list in section 10. |
| Queue intake inflation and consumed blocked GUP displays | Architect for semantic ruling if needed; Builder for assigned scanner/tests | Verify examples in this report before changing queue semantics. This audit publishes no new ESC/Decision. |
| Six Integrator discovery diagnostics | Integrator verifies historical/current bundle evidence; Architect resolves any immutable-history exception; Reviewer owns any approved successor | Five component hashes differ and one manifest lacks an edges component. See exact IDs in section 12. LF-normalizing the five files did not recover their declared checksums; do not assume a line-ending-only issue. |
| AD&D canonical conformance debt | Architect scopes; Analyst/Reviewer resolve source judgments; Builder/Integrator implement approved changes | 1691 machine findings, summarized below. Not an immediate new assignment during SD priority. |
| Transport migration to Gemini/Antigravity | Owner/Gemini with Architect contract ownership and assigned tooling owner | No implementation designed here. Existing wrapper binds Claude/Codex and Herdr. |
| Orientation/bootstrap documentation drift | Architect | Specific contradictions listed in section 6; no published history rewritten. |
| Other five Shadowdark book intakes | Source steward/user, then Analyst when authorized | Directories exist; no incoming packets measured. |
| Basic D&D RC | No worker authorized | Owner-paused. Preserve two incoming files and two claims. |



### Read-Only Graph Validation

| Ruleset    | Exit | Findings | By invariant                   | Meaning                                            |
| ---------- | ---- | -------- | ------------------------------ | -------------------------------------------------- |
| shadowdark | 0    | 0        | {}                             | Machine-checked subset only; not source re-review. |
| adnd1e     | 1    | 1691     | {"3": 10, "11": 9, "16": 1672} | Machine-checked subset only; not source re-review. |



AD&D findings: 10 prefix findings (invariant 3), 9 magnitude/grain findings (11), and 1672 unresolved authored-polarity findings (16); 1674 distinct affected edge rows. Prefix findings may refer to node identities rather than edge rows. Shadowdark: 0 findings. The validator explicitly does not machine-prove source interpretation, all direction judgments, or the entire historical provenance chain.

## 9. Complete Script Inventory

### Scope And Counting

The pre-audit workspace contains **102 project script/module/test files: 95 Python and 7 PowerShell**. Of these, 81 are under tooling, 14 are ignored PHB Reviewer work scripts, and 7 are under .local. Python `__init__.py`, `__main__.py`, internal modules and test bootstraps are included individually, not hidden behind a package entry. No additional project JS/TS, shell, batch, notebook, R, SQL, VBScript, Perl, Ruby, Lua or extensionless shebang scripts were discovered by the extension/shebang sweep.

Excluded: `.git` internals and sample hooks, bytecode, installed third-party dependency/virtual-environment trees, binaries and external PATH tools. No user answer to the optional dependency-inventory question was received during this snapshot; the default is project scripts, not third-party library internals. Inline commands in Markdown/YAML are documented entry points/evidence, not separate script files. Generated report helpers are inventoried separately at the end, making 104 script files including this audit. This is a filesystem inventory, not a claim every historical script is still used.

**Status vocabulary:** current reusable = live implementation/helper; test = regression or independent verification, not runtime work; historical = retained one-off or legacy input helper; retired = transport prohibited by current workflow; unsafe scratch = not a supported production entry point. Ownership is inferred from role boundaries and path, with common tools governed by their Decisions. All roles may consume validation results without gaining write authority.

### 9.1. `.local/architect/check_dec_0081.py`

**Role/user:** Architect. **Status:** Historical local preflight.

**Purpose:** Checks DEC-0081 Dispatcher verifier governance/schema/ownership changes against its then-current bounded authority list.

**Use / side effects:** Snapshot-specific assertions; current versions may intentionally fail. Not a standing worker gate.

**Snapshot:** 78 lines; untracked/ignored; SHA-256 `b20565394094989e917a834cdb251711f919bffddd9b5ca9774ef06ff21997a9`.

### 9.2. `.local/architect/check_dec_0082.py`

**Role/user:** Architect. **Status:** Historical local preflight.

**Purpose:** Checks Dispatcher retirement governance, role instruction changes and direct-handoff authoring requirements.

**Use / side effects:** Snapshot-specific assertions; current versions may intentionally fail. Not a standing worker gate.

**Snapshot:** 40 lines; untracked/ignored; SHA-256 `9f00297774e75efb11c5c9acc0841c94e5394dbeb84a1bcc5d963d17484278cc`.

### 9.3. `.local/architect/check_shadowdark.py`

**Role/user:** Architect. **Status:** Historical local preflight.

**Purpose:** Checks the independent Shadowdark bootstrap directory/governance/schema setup without creating production canonical state.

**Use / side effects:** Snapshot-specific assertions; current versions may intentionally fail. Not a standing worker gate.

**Snapshot:** 146 lines; untracked/ignored; SHA-256 `925545cdb034df8f5cf45d3a5efec26a88e79a9f4229d8083d00b770b3c6e2f9`.

### 9.4. `.local/architect/validate_dec0087.py`

**Role/user:** Architect. **Status:** Historical local preflight.

**Purpose:** Validates staged DEC-0087 ancestry governance, allowed identities and historical GUR compatibility against pinned Constitution 1.1 expectations.

**Use / side effects:** Snapshot-specific assertions; current versions may intentionally fail. Not a standing worker gate.

**Snapshot:** 74 lines; untracked/ignored; SHA-256 `d66fc5a2a2f35d1b17246d94653188563ae98fc694a9c8ba4a0b38ebbb631ff2`.

### 9.5. `.local/herdr/notify-shadowdark-20260919.ps1`

**Role/user:** Architect/operator. **Status:** Retired one-time transport.

**Purpose:** One-time Shadowdark workspace awareness notifications to four worker roles, serialized with old role/session bindings and acknowledgment state.

**Use / side effects:** Do not execute on new agents. Old sessions, locks, paths and state are not portable authority.

**Snapshot:** 131 lines; untracked/ignored; SHA-256 `0f2fa8701aa43b942b759e0b39e8314540bcc24de1a10654fb0d79d4856704ed`.

### 9.6. `.local/herdr/reload-roles-20260919.ps1`

**Role/user:** Architect/operator. **Status:** Retired one-time transport.

**Purpose:** One-time instruction reload notices following Dispatcher retirement; waits for role settlement and records old acknowledgment/state files.

**Use / side effects:** Do not execute on new agents. Old sessions, locks, paths and state are not portable authority.

**Snapshot:** 125 lines; untracked/ignored; SHA-256 `7bbb39115fac2f5e635fde61f0c884fb41a3a42b6099595d227fb7044797b962`.

### 9.7. `.local/herdr/stop-rc-20260921.ps1`

**Role/user:** Architect/operator. **Status:** Retired one-time transport.

**Purpose:** One-time RC stop notifications and explicit reconciliation of an old uncertain relay record using exact session/pane/evidence pins.

**Use / side effects:** Do not execute on new agents. Old sessions, locks, paths and state are not portable authority.

**Snapshot:** 157 lines; untracked/ignored; SHA-256 `6fa77527f579ed0abe80e9e04c7e23675222121ac436eca0e77a4c2661b54240`.

### 9.8. `books/adnd1e/phb/work/reviewer/audit_decision_migration_r02.py`

**Role/user:** Reviewer. **Status:** Historical read-only audit helper.

**Purpose:** Independent, read-only audit of GUP-MIG-DEC-2026-0015-0016-r02.

**Use / side effects:** Hardcoded PHB artifacts/date and manual judgments; inspect inputs before any reuse. Checks only its named historical artifacts, not the current full queue.

**Snapshot:** 317 lines; untracked/ignored; SHA-256 `3f1d6f2482d7a3a15cd2fb716559bcdbb3a6c1778bb4348355899d744827af53`.

### 9.9. `books/adnd1e/phb/work/reviewer/emit_classes_review_20260801_r02.py`

**Role/user:** Reviewer. **Status:** Historical one-off authoring helper.

**Purpose:** Supersede the classes r07 Review to state the DEC-2026-0016 page deferral precisely.

**Use / side effects:** Hardcoded PHB artifacts/date and manual judgments; inspect inputs before any reuse. May publish Reviews/Approved components; do not rerun as fresh review.

**Snapshot:** 54 lines; untracked/ignored; SHA-256 `a9433a90c1ae870583924113baa229fc201798ef212079f89439775489d2fef2`.

### 9.10. `books/adnd1e/phb/work/reviewer/emit_phb_reviews.py`

**Role/user:** Reviewer. **Status:** Historical one-off authoring helper.

**Purpose:** Emit the independent PHB GUP reviews from the completed row audit.

**Use / side effects:** Hardcoded PHB artifacts/date and manual judgments; inspect inputs before any reuse. May publish Reviews/Approved components; do not rerun as fresh review.

**Snapshot:** 1246 lines; untracked/ignored; SHA-256 `5a3181064e72bca26624a98f876eb8626cda0c64ed437d4099524d1c3d50706b`.

### 9.11. `books/adnd1e/phb/work/reviewer/emit_phb_reviews_20260731.py`

**Role/user:** Reviewer. **Status:** Historical one-off authoring helper.

**Purpose:** Emit the six independent PHB Reviews completed on 2026-07-31.

**Use / side effects:** Hardcoded PHB artifacts/date and manual judgments; inspect inputs before any reuse. May publish Reviews/Approved components; do not rerun as fresh review.

**Snapshot:** 780 lines; untracked/ignored; SHA-256 `4b852a5b5dbdb2ad8eab7c8c40f85a64f35b29d07575252c5258a2dcef9c414e`.

### 9.12. `books/adnd1e/phb/work/reviewer/emit_phb_reviews_20260731_round2.py`

**Role/user:** Reviewer. **Status:** Historical one-off authoring helper.

**Purpose:** Serialize the independent Review of the six active PHB packet GUPs.

**Use / side effects:** Hardcoded PHB artifacts/date and manual judgments; inspect inputs before any reuse. May publish Reviews/Approved components; do not rerun as fresh review.

**Snapshot:** 702 lines; untracked/ignored; SHA-256 `4bfb1c6690233de7bbb290889622f5ee31460a0129cb56543261360b5ed9e1bd`.

### 9.13. `books/adnd1e/phb/work/reviewer/emit_phb_reviews_20260801_round3.py`

**Role/user:** Reviewer. **Status:** Historical one-off authoring helper.

**Purpose:** Emit the independent Reviews for the four PHB GUPs queued on 2026-08-01.

**Use / side effects:** Hardcoded PHB artifacts/date and manual judgments; inspect inputs before any reuse. May publish Reviews/Approved components; do not rerun as fresh review.

**Snapshot:** 617 lines; untracked/ignored; SHA-256 `048968b3cc9e2e179437fe6fb210681f54d44a6ec8d77047e653839d582dfee4`.

### 9.14. `books/adnd1e/phb/work/reviewer/emit_reviewer_queue_20260730.py`

**Role/user:** Reviewer. **Status:** Historical one-off authoring helper.

**Purpose:** Emit the 2026-07-30 independent Reviews for the seven active PHB GUP leaves.

**Use / side effects:** Hardcoded PHB artifacts/date and manual judgments; inspect inputs before any reuse. May publish Reviews/Approved components; do not rerun as fresh review.

**Snapshot:** 1033 lines; untracked/ignored; SHA-256 `2eea28ba9c583f023bc86f0470ef5b88b70fdd9b30e3cbc9f2619188e8fc03c7`.

### 9.15. `books/adnd1e/phb/work/reviewer/emit_reviews_20260802_queue4.py`

**Role/user:** Reviewer. **Status:** Historical one-off authoring helper.

**Purpose:** Emit independent Reviews for the four Reviewer-ready leaves on 2026-08-02.

**Use / side effects:** Hardcoded PHB artifacts/date and manual judgments; inspect inputs before any reuse. May publish Reviews/Approved components; do not rerun as fresh review.

**Snapshot:** 715 lines; untracked/ignored; SHA-256 `6bfafe33e02e3f493986bf3dee7b189c2cdd34d723450ec4c1226c80d5413d1f`.

### 9.16. `books/adnd1e/phb/work/reviewer/emit_reviews_20260803_queue3.py`

**Role/user:** Reviewer. **Status:** Historical one-off authoring helper.

**Purpose:** Emit independent Reviews for the three Reviewer-ready leaves on 2026-08-03.

**Use / side effects:** Hardcoded PHB artifacts/date and manual judgments; inspect inputs before any reuse. May publish Reviews/Approved components; do not rerun as fresh review.

**Snapshot:** 544 lines; untracked/ignored; SHA-256 `c89dcc105d645254e904d1f1e29403740859deea7c8a31469f43abb0fe30fa41`.

### 9.17. `books/adnd1e/phb/work/reviewer/validate_phb_reviews_20260731.py`

**Role/user:** Reviewer. **Status:** Historical read-only audit helper.

**Purpose:** Independent mechanical checks for the six PHB Reviews dated 2026-07-31.

**Use / side effects:** Hardcoded PHB artifacts/date and manual judgments; inspect inputs before any reuse. Checks only its named historical artifacts, not the current full queue.

**Snapshot:** 279 lines; untracked/ignored; SHA-256 `70e40c14a623002f859f04e239c4ab0f897c2d3cdafd101292702eaa2c085af7`.

### 9.18. `books/adnd1e/phb/work/reviewer/validate_phb_reviews_20260731_round2.py`

**Role/user:** Reviewer. **Status:** Historical read-only audit helper.

**Purpose:** Read-only validation for the six PHB Reviews emitted on 2026-07-31.

**Use / side effects:** Hardcoded PHB artifacts/date and manual judgments; inspect inputs before any reuse. Checks only its named historical artifacts, not the current full queue.

**Snapshot:** 190 lines; untracked/ignored; SHA-256 `dc51c4a3f45548465dd82cb5001696eefe783e37f3919bafe42ed96a496022aa`.

### 9.19. `books/adnd1e/phb/work/reviewer/validate_phb_reviews_20260801_round3.py`

**Role/user:** Reviewer. **Status:** Historical read-only audit helper.

**Purpose:** Read-only validation for the four PHB Reviews emitted on 2026-08-01.

**Use / side effects:** Hardcoded PHB artifacts/date and manual judgments; inspect inputs before any reuse. Checks only its named historical artifacts, not the current full queue.

**Snapshot:** 288 lines; untracked/ignored; SHA-256 `82f3ff9c950717fc0eafe3f6f5b84bcb4c92572d50f033d043342fe84f2e2c3e`.

### 9.20. `books/adnd1e/phb/work/reviewer/validate_reviews_20260802_queue4.py`

**Role/user:** Reviewer. **Status:** Historical read-only audit helper.

**Purpose:** Read-only validation of the four Reviews emitted on 2026-08-02.

**Use / side effects:** Hardcoded PHB artifacts/date and manual judgments; inspect inputs before any reuse. Checks only its named historical artifacts, not the current full queue.

**Snapshot:** 198 lines; untracked/ignored; SHA-256 `6b8d690403b46a8d7fdd379ba1a712fc8aa63b4031ada7f36ef3ea0eb691f90f`.

### 9.21. `books/adnd1e/phb/work/reviewer/validate_reviews_20260803_queue3.py`

**Role/user:** Reviewer. **Status:** Historical read-only audit helper.

**Purpose:** Read-only validation for the three Reviews emitted on 2026-08-03.

**Use / side effects:** Hardcoded PHB artifacts/date and manual judgments; inspect inputs before any reuse. Checks only its named historical artifacts, not the current full queue.

**Snapshot:** 216 lines; untracked/ignored; SHA-256 `cdb8b6958b55c6729f4f2f9cc1ddf8f94e83d8b6cac54aaa21637330c7763faf`.

### 9.22. `tooling/analyst/adnd1e/dmg/doctags_reader.py`

**Role/user:** Analyst. **Status:** Historical legacy-source helper.

**Purpose:** Extracts DMG legacy doctags pages, OTSL tables and headers; offers keyword search, dehyphenation, word/table counts and a coverage-density heuristic against old edges.

**Use / side effects:** Import-time reads /home/claude/addgraph/dmg.doctags; may depend on old edges_master.csv. Not usable as a current Pandoc packet parser.

**Snapshot:** 54 lines; tracked; SHA-256 `3611c1b8d317b2ba11754f780a01481659f07c173e2833440237bbf9fc3859b9`.

### 9.23. `tooling/analyst/adnd1e/mm/doctags_reader.py`

**Role/user:** Analyst. **Status:** Historical legacy-source helper.

**Purpose:** Reconstructs Monster Manual two-column reading order from bounding boxes, extracts monster entries/stat blocks and source text from legacy doctags.

**Use / side effects:** Import-time reads /home/claude/addgraph/mm.doctags; may depend on old edges_master.csv. Not usable as a current Pandoc packet parser.

**Snapshot:** 42 lines; tracked; SHA-256 `a9af0e17a51e3244387186ce5105dbebdc99d56f41de87cdee5df3bc683d128b`.

### 9.24. `tooling/analyst/adnd1e/ua/doctags_reader.py`

**Role/user:** Analyst. **Status:** Historical legacy-source helper.

**Purpose:** Extracts UA legacy doctags page text, tables and headers and reports word/table/legacy graph coverage information.

**Use / side effects:** Import-time reads /home/claude/addgraph/ua.doctags; may depend on old edges_master.csv. Not usable as a current Pandoc packet parser.

**Snapshot:** 45 lines; tracked; SHA-256 `1e2796805288220e5d93879924972e6a3ebd3fc7ce5f6edbd0418c9ca60587a0`.

### 9.25. `tooling/builder/src/adnd1e_builder/__init__.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Package metadata/version and Builder namespace initialization; does not compile by itself.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 8 lines; tracked; SHA-256 `698716f4db90f9a304f2315df662dd0cbd1706c5ab5356d738abd763b34f1e0b`.

### 9.26. `tooling/builder/src/adnd1e_builder/__main__.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Python -m entry shim that invokes the Builder CLI.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 3 lines; tracked; SHA-256 `935a1c1166b0c1ea35a82256345000bf2c73ded718d77773bc27a71ecce28f7d`.

### 9.27. `tooling/builder/src/adnd1e_builder/cli.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Dispatches compile, verify-pages, plan-migration, plan-decision-migration, audit-escalation-ids and lint-source. Compilation/planning can publish GUPs and reports and runs the suite gate.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 672 lines; tracked; SHA-256 `bef58343098b1384c3ad15108e72c6eb0fa415856b961a9e51bcc3cc9c3cd939`.

### 9.28. `tooling/builder/src/adnd1e_builder/compiler.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Orchestrates GUR compilation: identity/vocabulary/citation/conditional-field checks, node proposals, row classification, Review directives and blocked diagnostics. Produces an in-memory compile result without deciding source meaning.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 3043 lines; tracked; SHA-256 `1d5ef938d34635ef00f3aa0bdf5ee882228d5e97514cc2e64173bd0bc66f31df`.

### 9.29. `tooling/builder/src/adnd1e_builder/decision_migration.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Plans exactly Decision-enumerated canonical changes, pins before-state/authority and checks the resulting assertion keys; supports the governed direct migration path rather than inferring graph-wide edits.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 2207 lines; tracked; SHA-256 `36d1a7f5d188210f87f8603dba17bd50a495bdb2f87028d21cb9e7f8be22dfb0`.

### 9.30. `tooling/builder/src/adnd1e_builder/direction.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Validates edge direction/type against governed mechanical rules and specific Decision cases; reports reversals or inappropriate dependency forms.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 79 lines; tracked; SHA-256 `f53b258e316d97bf5cdf6d8ce9b600885cf3079bfa4b8670f48c2cf1b2d12325`.

### 9.31. `tooling/builder/src/adnd1e_builder/duplicates.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Builds normalized assertion keys and detects exact, near, intra-patch and canonical-neighborhood duplicates/conflicts, including symmetric alternatives and self-edge handling.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 214 lines; tracked; SHA-256 `891583b1d66e06cd1f1b7049089db17662b425690c22dafd605a4bdf3a85affd`.

### 9.32. `tooling/builder/src/adnd1e_builder/emit.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Serializes compile results into deterministic GUP YAML, production/pending/blocked CSV components and validation JSON; checksummed publication outputs, not canonical integration.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 353 lines; tracked; SHA-256 `7f268ed01420fa558ad74baca939bcbf2bd0d63dfe85dfdcd4f62b84d4031eb7`.

### 9.33. `tooling/builder/src/adnd1e_builder/escalation_ids.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Validates/audits Windows-safe timestamped escalation IDs and allocates conforming new IDs without reusing sequence-style names.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 183 lines; tracked; SHA-256 `acc67ba6ae081f2b9df758c9db337cd6bd13d45f4888716fe59ec53fae5bf105`.

### 9.34. `tooling/builder/src/adnd1e_builder/governance.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Loads Architect Decisions/escalation state as bounded compiler authority; distinguishes unresolved from unknown questions and applies explicit decisions without inventing resolutions.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 464 lines; tracked; SHA-256 `99eaa0fa760aed00299ee5f64f29ffbef713117fda9bbf856122ba7656905320`.

### 9.35. `tooling/builder/src/adnd1e_builder/grain.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Detects forbidden magnitudes, dice, bonuses, percentages and related grain violations in qualitative aspect/condition fields.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 150 lines; tracked; SHA-256 `c755bf825975eb202ffc1e65c4288a161a84aefd8a6e9f45f5a83ff0d8429b6e`.

### 9.36. `tooling/builder/src/adnd1e_builder/migration.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Legacy identity-merge planner rooted in DEC-0007: computes the closed incident-row migration from retired identities to survivors. Historical model use is governed; not a general merge tool.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 363 lines; tracked; SHA-256 `3c452b65505e4b52788133d6ca3faf2439e483bed5d0cb99ae29a334807771dd`.

### 9.37. `tooling/builder/src/adnd1e_builder/pagemarkers.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Invokes Pandoc and walks the AST to resolve page markers, tables, inline switches, source boundaries, heading attributes and source lint/citation helpers under SOURCE_MARKDOWN. Not a regex Markdown substitute.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 509 lines; tracked; SHA-256 `733ef8bc8eabd37d25bddb6c425fbc400e6a92b143cbf55fd36135f343b41504`.

### 9.38. `tooling/builder/src/adnd1e_builder/polarity.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Derives deterministic polarity for governed edge types and validates independently authored polarity for the three source-read types.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 176 lines; tracked; SHA-256 `005eee2f09c6611dbe571799b9965b17d5c90f8a7a71908adb66eb8fc9c4153b`.

### 9.39. `tooling/builder/src/adnd1e_builder/queues.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Shared leaf/revision resolution utility for immutable artifact chains, forks, missing predecessors and bounded legacy revision inference. Its docstring claiming the full scanner is not built is stale.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 128 lines; tracked; SHA-256 `9bda9c98104b7fa83bb89a213de1da032eab168d6d862645994bdce0743ef98e`.

### 9.40. `tooling/builder/src/adnd1e_builder/registry.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Loads the node registry and resolves exact IDs, aliases and normalized labels, surfacing ambiguity rather than merging by name.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 246 lines; tracked; SHA-256 `443aa28ccd25bc51583e3d45787306c8047572c5d9e80ae109651d31b4aa1f7f`.

### 9.41. `tooling/builder/src/adnd1e_builder/review.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Parses Review dispositions and exact row/operation corrections into compiler directives; enforces executable carrier shapes and does not infer corrections from prose.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 1206 lines; tracked; SHA-256 `40e0fd51b9dee6acca588cc5919695d7950a5cb19d81844df72b3d82832b5c7d`.

### 9.42. `tooling/builder/src/adnd1e_builder/vocab.py`

**Role/user:** Builder; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Provides AD&D compatibility constants and ruleset-scoped vocabulary loading from governance/configuration, including columns, edge types, IDs, historical GUR-version admission and bounded classifications.

**Use / side effects:** Import through adnd1e_builder; CLI commands in section 5.

**Snapshot:** 584 lines; tracked; SHA-256 `14d3f64c33951aa82144cea25779e8ae27d8cf08377ad321cf6b91838072670f`.

### 9.43. `tooling/builder/tests/_bootstrap.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Adds the builder src package and repository root to the test import path for unittest discovery; infrastructure only.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Snapshot:** 90 lines; tracked; SHA-256 `2dfc40e8755b39442e56795c2c8bbd013ea46b854ff226005d81a15055f50c27`.

### 9.44. `tooling/builder/tests/test_compiler.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** End-to-end compiler behaviour on synthetic GURs.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Test coverage anchors:** `CompilerCase`, `TestHappyPath`, `TestConditionalFields`, `TestVocabularyEnforcement`, `TestIdentity`, `TestCanonicalDuplicates`, `TestCarriedForwardCandidates`, `TestPendingRowsAreLegibleOnDisk` (additional cases in file).

**Snapshot:** 3136 lines; tracked; SHA-256 `0fb096b23cc58a7495da4b8ce39301c0a232522457cf06d3186cc0cc07fcee58`.

### 9.45. `tooling/builder/tests/test_decision_migration.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Decision-driven canonical migration — DEC-2026-0015 and DEC-2026-0016.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Test coverage anchors:** `MigrationCase`, `TestDec0015AcceptanceTests`, `TestDec0016CitationCorrections`, `TestGuards`, `TestPlanningIsReadOnly`, `TestArtifactShape`, `TestNodeIDReplacements`, `SyntheticCorpusCase` (additional cases in file).

**Snapshot:** 2776 lines; tracked; SHA-256 `0e6991b402e7f156ced4f250d2fa4607e403c8aeba6e166090f1e528bda06241`.

### 9.46. `tooling/builder/tests/test_direction.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Direction and type selection — constitution 1.4 section 4.2, DEC-2026-0011.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Test coverage anchors:** `TestClassification`, `TestInTheCompiler`, `TestAgainstTheRealGurs`.

**Snapshot:** 247 lines; tracked; SHA-256 `c3deb24af61f62ce542542f63d83b2e83d571041e07cbb2aac07bc44b433fbfd`.

### 9.47. `tooling/builder/tests/test_duplicates.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Duplicate detection and the assertion key.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Test coverage anchors:** `TestAssertionKey`, `TestIntraPatch`, `TestSelfEdges`, `TestAgainstCanonicalCorpus`.

**Snapshot:** 136 lines; tracked; SHA-256 `f68d9ca577989904ca85b65a40c6b732977b600295e9052c0b82d32e2152ca76`.

### 9.48. `tooling/builder/tests/test_edge_schema.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** DEC-2026-0014 acceptance tests for the production edge schema.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Test coverage anchors:** `TestSchemaShape`, `TestRowValidation`, `TestFullCorpus`, `TestGupBundles`, `TestAuditIsReadOnly`.

**Snapshot:** 325 lines; tracked; SHA-256 `b4563dafceed6e50e5b83e162904343faf025078070173924868961bfb6e0b4b`.

### 9.49. `tooling/builder/tests/test_escalation_ids.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Escalation identifier contract — DEC-2026-0006.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Test coverage anchors:** `TestPattern`, `TestAllocation`, `TestAudit`, `TestRealRepository`.

**Snapshot:** 148 lines; tracked; SHA-256 `64d0346c7d615f5953825ba9939c7715b63a7bf7e60bd4fa80ccd4be37d6eae6`.

### 9.50. `tooling/builder/tests/test_governance.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Architect decisions as compiler input.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Test coverage anchors:** `TestLoadedFromRepository`, `TestRoutingInTheCompiler`, `TestMigrationValidation`, `TestConstitutionVersionTolerance`.

**Snapshot:** 311 lines; tracked; SHA-256 `a7a5e96910a36a13bfeaa33dcab5c98eb78158ed1677abbfad9fde17506668ae`.

### 9.51. `tooling/builder/tests/test_grain.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** The grain rule — constitution section 2, invariant 11.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Test coverage anchors:** `TestMagnitudes`, `TestAspectLength`, `TestConstitutionExamples`.

**Snapshot:** 104 lines; tracked; SHA-256 `a5e60823abd664aeeb0e3fe29704393b2042582a2917de0e7020dceb9fd82d7b`.

### 9.52. `tooling/builder/tests/test_handoff.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Handoff metadata and revision lineage — contracts/WORK_QUEUES.md 1.0.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Test coverage anchors:** `HandoffCase`, `TestHandoffBlock`, `TestRevisionLineage`, `TestPreviousRevisionDetection`, `TestPublishedIntroBundle`, `TestVerifyPagesUsesTheLeafBundle`.

**Snapshot:** 263 lines; tracked; SHA-256 `ee50c4356e43d59463a348f9cc7e4016976b666e3e242c7d322818f4df05c58f`.

### 9.53. `tooling/builder/tests/test_migration.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Canonical identity-merge migration — DEC-2026-0007.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Test coverage anchors:** `TestGovernanceLoad`, `TestPlan`, `TestSyntheticExactDuplicate`.

**Snapshot:** 158 lines; tracked; SHA-256 `64f8fb4b916a42ccfec46ca6fc58f40ccc265cf1e81cc8d8c9f65f6ceacdb799`.

### 9.54. `tooling/builder/tests/test_pagemarkers.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Acceptance tests for the Pandoc page-marker parser.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Test coverage anchors:** `TestAcceptance`, `TestPlacementSemantics`, `TestListsAndQuotes`, `TestSourceLint`, `TestStewardFrontmatter`, `TestPageClasses`, `TestPageClassLint`, `TestClosedPageClassVocabulary` (additional cases in file).

**Snapshot:** 710 lines; tracked; SHA-256 `d2e74f8b0524243ff91fd14ddb7a4a0d3db2cf16a33c9d8e786900a771d12e82`.

### 9.55. `tooling/builder/tests/test_polarity.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Polarity derivation — constitution 6.1, invariants 13-17.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Test coverage anchors:** `TestDerivationTable`, `TestDerivedTypes`, `TestAuthoredTypes`, `TestUnknownType`, `TestRulesetScopedDerivation`.

**Snapshot:** 198 lines; tracked; SHA-256 `8df03a2ecd95f1ef4c8de8911239e0844a70fad49760a86e7d446e7eeb28abb0`.

### 9.56. `tooling/builder/tests/test_registry_and_vocab.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Node resolution and the controlled vocabularies.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Test coverage anchors:** `TestVocabulary`, `TestConstitutionVersion`, `TestIdentityHelpers`, `TestRegistry`, `TestRetiredIdentityResolution`, `TestLiveRetirementCorpus`, `TestAssertionKeyMatchesGovernance`, `TestLegacyGrainConformanceScope` (additional cases in file).

**Snapshot:** 804 lines; tracked; SHA-256 `5c36d8586dc23aa374abfcb0ba5e8fb5025081d0ddb60c31b9dee2408e76ff11`.

### 9.57. `tooling/builder/tests/test_review.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Reviewer revision requests as compiler input.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Test coverage anchors:** `ReviewCase`, `TestRevisionNumbering`, `TestDispositions`, `TestDirectedCanonicalUpdates`, `TestReviewAnsweredByANewGur`, `TestCorrections`, `TestCanonicalPageShape`, `TestBucketInstructions` (additional cases in file).

**Snapshot:** 2075 lines; tracked; SHA-256 `c914390071dd2857903a5e1eb0085f6e01e81fa85bae63c3ab724ac9300a910a`.

### 9.58. `tooling/builder/tests/test_shadowdark_ancestry.py`

**Role/user:** Builder tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Tests Shadowdark vocabulary/identity admission and historical-version compatibility introduced at ancestry bootstrap and extended by later Decisions.

**Use / side effects:** python -m unittest discover -s tooling/builder/tests (or a targeted module/class).

**Test coverage anchors:** `ShadowdarkCase`, `IsolatedShadowdarkCase`, `TestGovernanceInputs`, `TestSchemaInputs`, `TestAncestryNodeProposals`, `TestPrefixScopeIsPerRuleset`, `TestAHeldAncestryIdentityStillBlocks`, `TestUnsupportedIdentitiesStillFail` (additional cases in file).

**Snapshot:** 1575 lines; tracked; SHA-256 `054c085e8c30a763c900097a1c7de42a63a59ae7f17014f6d5b677b36c07ca22`.

### 9.59. `tooling/common/Keep-AgentsGoing.ps1`

**Role/user:** Operator; no worker should use as relay. **Status:** Unsafe scratch.

**Purpose:** Sends hardcoded keep-going prompts to Builder and Integrator, then invalid Role agent. Earlier sends can occur before the error; lacks bounded queue selection and conflicts with the single-packet relay.

**Use / side effects:** Use the documented CLI/wrapper, not private functions.

**Snapshot:** 3 lines; tracked; SHA-256 `088966fa42a9264ef054ab88cd778b07624d897b2aa2b2e36b789ff43d2d68f0`.

### 9.60. `tooling/common/Send-HerdrPrompt.ps1`

**Role/user:** All five roles / owner. **Status:** Current reusable, Herdr-specific.

**Purpose:** Lists or resolves a unique live role, checks expected provider and repository, timestamps a direct notification and calls Herdr. Requires HERDR_BIN_PATH; defaults to D:\analysis\dnd; does not execute a shell command inside the target pane.

**Use / side effects:** Use the documented CLI/wrapper, not private functions.

**Snapshot:** 149 lines; tracked; SHA-256 `18341022aec55c210e57bbfcf804d4850617483da830e44e4e04af2969173b9d`.

### 9.61. `tooling/common/role_context.py`

**Role/user:** All five roles; Builder implementation owner. **Status:** Current reusable.

**Purpose:** Resolves manifest authority paths and verifies/records exact SHA-256 receipts bound to root, actor session, role and scope. verify reads; record writes only local receipt state after actual instruction loading.

**Use / side effects:** Use the documented CLI/wrapper, not private functions.

**Snapshot:** 610 lines; tracked; SHA-256 `11aadce04390132a729575b421798d9c61865eaa8ceb1b65507654a60e5e216f`.

### 9.62. `tooling/common/scan-agent-queues.ps1`

**Role/user:** All roles / owner; common tooling. **Status:** Current reusable wrapper.

**Purpose:** PowerShell front end to scan_agent_queues.py. Forwards Root, Json, All and Verbose/-v false, and returns Python exit status unchanged; does not implement an independent queue algorithm.

**Use / side effects:** Use the documented CLI/wrapper, not private functions.

**Snapshot:** 107 lines; tracked; SHA-256 `0b221ec7de60297ec550cd14ae3e9a2506ccda31e97407b893265765bdb475bd`.

### 9.63. `tooling/common/scan_agent_queues.py`

**Role/user:** All roles / owner; Builder implementation owner. **Status:** Current reusable.

**Purpose:** Derives multi-role work from exact immutable lineage, handoff, approval, Decision/IMP and integration consumption; validates governed legacy exceptions and emits JSON/console diagnostics. Console verbosity can hide diagnostics, not change readiness. Read-only.

**Use / side effects:** Use the documented CLI/wrapper, not private functions.

**Snapshot:** 6484 lines; tracked; SHA-256 `ff1e7fb7a208f4cfc30902c4309a4d560c9c5cfa2da01562f556809f1a5862d0`.

### 9.64. `tooling/common/send-agent-handoff.ps1`

**Role/user:** Historical all-role transport; Builder implementation owner. **Status:** Retired.

**Purpose:** Old detached delivery/settlement relay with request JSON, deadlines, locks, identity pins and local delivery state. Retained for evidence/tests; forbidden as current transport under Herdr 2.x.

**Use / side effects:** Use the documented CLI/wrapper, not private functions.

**Snapshot:** 1214 lines; tracked; SHA-256 `b3d9c519fee1eb5b4549846a3f661a0edd4d309b9600b606da0c274534d0a53e`.

### 9.65. `tooling/common/tests/test_common_schemas.py`

**Role/user:** Builder common-tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Exercises shared envelope, GUR candidate nodes, GUP/migration, Review, Approved, Decision/IMP schemas and explicitly authorized historical exceptions.

**Use / side effects:** python -m unittest discover -s tooling/common/tests (or a targeted module/class).

**Test coverage anchors:** `TestLegacyArtifactsStayValid`, `TestSupersededExemptionIsNarrow`, `TestRevisionAndSupersedes`, `TestHandoff`, `TestApprovedBundle`, `TestSchemasAreWellFormed`, `TestImplementationArtifactsValidate`, `TestReviewDispositionVocabulary` (additional cases in file).

**Snapshot:** 1498 lines; tracked; SHA-256 `76691a7f9a1fc1025ddcd28fb5e240b286a4d865a971ff79f7d5771ee4c65398`.

### 9.66. `tooling/common/tests/test_herdr_handoff.py`

**Role/user:** Builder common-tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Fake-endpoint fixtures for the retired DEC-0082 detached relay, including timeouts, identity, locks and settlement. Historical safety regression, not recommended live orchestration.

**Use / side effects:** python -m unittest discover -s tooling/common/tests (or a targeted module/class).

**Test coverage anchors:** `RelayCase`, `TestRequestValidation`, `TestSenderSerialization`, `TestRecipientIdentity`, `TestTheGlobalLock`, `TestDuplicateAndUncertainDelivery`, `TestScheduling`, `TestTheRelayTransportsWithoutDeciding` (additional cases in file).

**Snapshot:** 1396 lines; tracked; SHA-256 `64bb495b91674ae36b8d90b33b6544618a8076e1f98c2b752e3c18d95e455b51`.

### 9.67. `tooling/common/tests/test_implementation_evidence.py`

**Role/user:** Builder common-tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Checks consistency of published implementation-report evidence and governed acceptance/retirement/contract-content semantics.

**Use / side effects:** python -m unittest discover -s tooling/common/tests (or a targeted module/class).

**Test coverage anchors:** `TestValidationEvidenceIsSelfConsistent`, `TestVerdictGrammar`, `TestPassingVerdictRejectsFailureCounters`, `TestTheRetainedReportsPass`.

**Snapshot:** 480 lines; tracked; SHA-256 `cff5e59488acf4c39ec8c4135be58cd627394c016f9ea72ea6c2b021d5e72821`.

### 9.68. `tooling/common/tests/test_role_context.py`

**Role/user:** Builder common-tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Receipt scope/session/checksum correctness, miss/hit behavior, malformed/stale receipts, manifest validation and supported role behavior.

**Use / side effects:** python -m unittest discover -s tooling/common/tests (or a targeted module/class).

**Test coverage anchors:** `RoleContextCase`, `TestColdAndWarm`, `TestInvalidation`, `TestFailsClosed`, `TestTheCacheExcludesLiveState`, `TestReceiptContent`, `TestPathSetIsDeterministic`, `TestTheLiveManifest` (additional cases in file).

**Snapshot:** 937 lines; tracked; SHA-256 `b313f030bd89b149277b0c52eb7dac53b1b726d0d25ecbc2eef5e1281ef3af8d`.

### 9.69. `tooling/common/tests/test_scan_agent_queues.py`

**Role/user:** Builder common-tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Covers multi-role lineage, exact consumers, Decision/IMP evidence, migrations, retirement exceptions, Approved linkage, blocked GUR routing, cross-GUP Review chains and Python/PowerShell parity. Broad scanner regression surface; no single packet extraction.

**Use / side effects:** python -m unittest discover -s tooling/common/tests (or a targeted module/class).

**Test coverage anchors:** `DiagnosticsConsoleFormattingTests`, `QueueScannerCase`, `MigrationFixtureMixin`, `DecisionMigrationCase`, `SupersededApprovedBundleCase`, `BlockedGupOwnershipCase`, `TestScannerParity`, `IntegratedMigrationDriftCase` (additional cases in file).

**Snapshot:** 9745 lines; tracked; SHA-256 `fae551ddfd72cf7e5132a4d37b3d1325fa34c137cc262ccc16f3018181dcb549`.

### 9.70. `tooling/common/tests/test_validate_artifact.py`

**Role/user:** Builder common-tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Proves target-only staged validation, malformed YAML rejection, schema reference handling and absence of publication side effects.

**Use / side effects:** python -m unittest discover -s tooling/common/tests (or a targeted module/class).

**Test coverage anchors:** `StagedPreflightCase`, `RealSchemaCase`.

**Snapshot:** 236 lines; tracked; SHA-256 `fa1e230569ad3c47ff630775517f319e3ae51b14941a9abd511df6f07c709681`.

### 9.71. `tooling/common/validate_artifact.py`

**Role/user:** All publishing roles; Builder implementation owner. **Status:** Current reusable.

**Purpose:** Parses one staged YAML/JSON file and validates against an explicitly named schema with sibling reference resolution. Positional artifact path. Writes no destination; exits 0 valid, 1 invalid, 2 tool failure.

**Use / side effects:** Use the documented CLI/wrapper, not private functions.

**Snapshot:** 166 lines; tracked; SHA-256 `c13f3e8a5321ca8a0b4f32d1da5c42a714f446fe21bb94b899abe2bb784538e8`.

### 9.72. `tooling/integrator/src/adnd1e_integrator/__init__.py`

**Role/user:** Integrator; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Package metadata/version and Integrator namespace initialization; no graph transaction by itself.

**Use / side effects:** Import through adnd1e_integrator; never call writer functions from other roles.

**Snapshot:** 20 lines; tracked; SHA-256 `05e9ef34ba106224b85138741ae3dca0c6687933fcc9a205e7389602d564ac13`.

### 9.73. `tooling/integrator/src/adnd1e_integrator/__main__.py`

**Role/user:** Integrator; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Python -m entry shim for the Integrator CLI.

**Use / side effects:** Import through adnd1e_integrator; never call writer functions from other roles.

**Snapshot:** 3 lines; tracked; SHA-256 `935a1c1166b0c1ea35a82256345000bf2c73ded718d77773bc27a71ecce28f7d`.

### 9.74. `tooling/integrator/src/adnd1e_integrator/admission.py`

**Role/user:** Integrator; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Validates exact Decision-governed exceptions for unreadable historical Reviews before queue discovery; malformed ungoverned input fails closed.

**Use / side effects:** Import through adnd1e_integrator; never call writer functions from other roles.

**Snapshot:** 624 lines; tracked; SHA-256 `f83d7dc15dc8c6bceeacd8f962ba60fbe9573783cc553a68aac5fee41c998da8`.

### 9.75. `tooling/integrator/src/adnd1e_integrator/bundles.py`

**Role/user:** Integrator; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Discovers Approved manifests and components, validates lineage/review linkage and classifies ready, integrated, rejected and superseded bundles, including authorized bounded legacy fallback.

**Use / side effects:** Import through adnd1e_integrator; never call writer functions from other roles.

**Snapshot:** 604 lines; tracked; SHA-256 `6d8d30a1d9a86239e35e5bdebb9c8c6335bcd7107f33061c343c276f92063e58`.

### 9.76. `tooling/integrator/src/adnd1e_integrator/canonical.py`

**Role/user:** Integrator; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Exact readers/writers and path model for canonical edge/node/export state and registry. This is an Integrator-only write surface, including genesis-state handling.

**Use / side effects:** Import through adnd1e_integrator; never call writer functions from other roles.

**Snapshot:** 267 lines; tracked; SHA-256 `31fc4055dd175f5ce578b1a380520f8a88c7589a9e4ad46c96f3032628bd92b2`.

### 9.77. `tooling/integrator/src/adnd1e_integrator/checksums.py`

**Role/user:** Integrator; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** SHA-256 file/data helpers used to verify exact immutable transaction inputs and outputs.

**Use / side effects:** Import through adnd1e_integrator; never call writer functions from other roles.

**Snapshot:** 28 lines; tracked; SHA-256 `cf47bc434a4b5ab19f738f9f33637452f05a393ce4a352f2a99177a44cd52159`.

### 9.78. `tooling/integrator/src/adnd1e_integrator/cli.py`

**Role/user:** Integrator; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Dispatches queue, validate, integrate and test. Select --ruleset-id and --books explicitly; integrate is the live transaction entry point, queue/validate are read-only.

**Use / side effects:** Import through adnd1e_integrator; never call writer functions from other roles.

**Snapshot:** 221 lines; tracked; SHA-256 `1f2df98d4d7e5a44e1ad5f2db3475c475367cfed8693bf0374897f20a626379a`.

### 9.79. `tooling/integrator/src/adnd1e_integrator/derive.py`

**Role/user:** Integrator; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Recomputes deterministic polarity, node degrees and tier-1/tier-2 roles from graph and profile; respects empty bootstrap profiles rather than borrowing another ruleset policy.

**Use / side effects:** Import through adnd1e_integrator; never call writer functions from other roles.

**Snapshot:** 243 lines; tracked; SHA-256 `92e0c6f2b49fcf6779ad35e20d889671d61edccc745d8f7b5d429514024fc9cf`.

### 9.80. `tooling/integrator/src/adnd1e_integrator/integrate.py`

**Role/user:** Integrator; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Executes the full approved-bundle transaction with preconditions, snapshot, registrations, edge operations, invariants, derived outputs, and rollback on failure; dry-run does not apply canonical writes.

**Use / side effects:** Import through adnd1e_integrator; never call writer functions from other roles.

**Snapshot:** 1220 lines; tracked; SHA-256 `74f795114cae77724c8d3929c81b40c2e5c3b237b8db54f3710569d536e00e4b`.

### 9.81. `tooling/integrator/src/adnd1e_integrator/invariants.py`

**Role/user:** Integrator; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Checks machine-verifiable graph and derived-state invariants against the active ruleset vocabulary and reports findings; cannot substitute for Reviewer source judgments.

**Use / side effects:** Import through adnd1e_integrator; never call writer functions from other roles.

**Snapshot:** 301 lines; tracked; SHA-256 `c4a1ebde1ae8f769a384f0d87cb3370e19f08bf4a64e1734eaa5a7da1315276c`.

### 9.82. `tooling/integrator/src/adnd1e_integrator/migration.py`

**Role/user:** Integrator; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Validates and executes bounded Decision migration operation models including v1/v2/v3, exact baselines, before-images, replacements/merges/repoints/removals and permitted label normalization.

**Use / side effects:** Import through adnd1e_integrator; never call writer functions from other roles.

**Snapshot:** 752 lines; tracked; SHA-256 `c496456d8fd2b452f56376e56f44f112584c95ab7de2abecc92e8622bd41ce70`.

### 9.83. `tooling/integrator/src/adnd1e_integrator/operations.py`

**Role/user:** Integrator; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Reads Approved operation indexes and node registrations; partitions row actions, enforces compare-and-swap updates and registration agreement rather than treating every CSV row as an insertion.

**Use / side effects:** Import through adnd1e_integrator; never call writer functions from other roles.

**Snapshot:** 143 lines; tracked; SHA-256 `6984de4f15aa3c155eb12b4bc6ca46a9a9a66297c0b91c59279142df46384c29`.

### 9.84. `tooling/integrator/src/adnd1e_integrator/records.py`

**Role/user:** Integrator; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Writes transaction manifests, validation reports, per-book consumption records and human-readable diffs with exact input/output provenance.

**Use / side effects:** Import through adnd1e_integrator; never call writer functions from other roles.

**Snapshot:** 546 lines; tracked; SHA-256 `283c57920d83b884f6298107b97901f8982ebe07d32736a5d4160737bd763834`.

### 9.85. `tooling/integrator/src/adnd1e_integrator/snapshot.py`

**Role/user:** Integrator; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Snapshots bytes and absence, manages transaction context and restores the exact pre-state on failure; failed genesis removes newly created canonical state.

**Use / side effects:** Import through adnd1e_integrator; never call writer functions from other roles.

**Snapshot:** 120 lines; tracked; SHA-256 `cf5c733adf917e13a003510e26fccb7f144b8b0f07c6c459258e741c3f5f9d74`.

### 9.86. `tooling/integrator/src/adnd1e_integrator/vocabulary.py`

**Role/user:** Integrator; Reviewer independently tests. **Status:** Current reusable module.

**Purpose:** Reads prefix, edge and derived-polarity tables by table structure plus citation codes from the selected ruleset; rejects absent required vocabularies instead of using AD&D assumptions.

**Use / side effects:** Import through adnd1e_integrator; never call writer functions from other roles.

**Snapshot:** 238 lines; tracked; SHA-256 `8b75a9f112f5eb33994d21ffc4edc942e0635e39cf6e873095a438d75f792b3b`.

### 9.87. `tooling/integrator/tests/_bootstrap.py`

**Role/user:** Integrator tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Adds the integrator src package and repository root to the test import path for unittest discovery; infrastructure only.

**Use / side effects:** python -m unittest discover -s tooling/integrator/tests (or a targeted module/class).

**Snapshot:** 15 lines; tracked; SHA-256 `d031906d7b09c4814cdb4112fca418e3f7eafd63761e8a7410200fbff5686857`.

### 9.88. `tooling/integrator/tests/test_admission.py`

**Role/user:** Integrator tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** DEC-2026-0065: Decision-governed admission of unreadable Reviews.

**Use / side effects:** python -m unittest discover -s tooling/integrator/tests (or a targeted module/class).

**Test coverage anchors:** `TestTheAuthorisedException`, `TestEveryConditionThatDeniesTheException`, `TestAnyOtherUnreadableReview`, `TestOrdinarySemanticsAreUnchanged`, `TestTheDirectPredecessorException`, `TestTheExclusionIsBoundedByItsRecord`.

**Snapshot:** 680 lines; tracked; SHA-256 `957bfd37d0ba228625f17d499b06c08c63bdf41e6a42d7ba23e32793ef1beb3c`.

### 9.89. `tooling/integrator/tests/test_bundles.py`

**Role/user:** Integrator tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Queue derivation against `contracts/WORK_QUEUES.md`.

**Use / side effects:** python -m unittest discover -s tooling/integrator/tests (or a targeted module/class).

**Test coverage anchors:** `TestQueue`, `TestManifestComponentAuthority`, `TestTheHistoricalBundleIsWithheld`, `TestBoundedLegacyApprovedLeafInference`, `TestTheStatsLineageIsSettledHistory`, `TestExistingClassificationsAreUnchanged`.

**Snapshot:** 565 lines; tracked; SHA-256 `fb2d546c6b08bc107de9b1bc8a5dd815bbf8387be8e274364e9b425848761f8d`.

### 9.90. `tooling/integrator/tests/test_canonical.py`

**Role/user:** Integrator tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Serialization fidelity against the real canonical corpus.

**Use / side effects:** python -m unittest discover -s tooling/integrator/tests (or a targeted module/class).

**Test coverage anchors:** `TestSerialization`.

**Snapshot:** 70 lines; tracked; SHA-256 `a790fa90fe8613639eda1a85bba0f4397d05765df6d987a60ee2b6f58271b718`.

### 9.91. `tooling/integrator/tests/test_derive.py`

**Role/user:** Integrator tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Derivation must reproduce the shipped canonical state exactly.

**Use / side effects:** python -m unittest discover -s tooling/integrator/tests (or a targeted module/class).

**Test coverage anchors:** `TestDerivation`, `TestAnEmptyBootstrapProfileDerivesNoRole`, `TestAPopulatedProfileIsUnchanged`.

**Snapshot:** 144 lines; tracked; SHA-256 `a3fa2a6a7a8f457099a8283f5c6b3861f2f7540bd2c9b76d5f769c1ac06a6023`.

### 9.92. `tooling/integrator/tests/test_genesis.py`

**Role/user:** Integrator tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** A ruleset's first integration: DEC-2026-0092.

**Use / side effects:** python -m unittest discover -s tooling/integrator/tests (or a targeted module/class).

**Test coverage anchors:** `GenesisCase`, `TestAGenesisFixtureStartsWithNothing`, `TestReadOnlyPathsCreateNoCanonicalState`, `TestASuccessfulGenesisWritesOnlyWhatWasApproved`, `TestALateGenesisFailureRestoresAbsence`.

**Snapshot:** 340 lines; tracked; SHA-256 `ae3e58fc6b82d4cf47af64b3cbbadce2988ffaeeaf53c7b2eb5b351180502e24`.

### 9.93. `tooling/integrator/tests/test_invariants.py`

**Role/user:** Integrator tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** The invariant suite, including its behaviour on the real corpus.

**Use / side effects:** python -m unittest discover -s tooling/integrator/tests (or a targeted module/class).

**Test coverage anchors:** `TestTheSuiteUsesTheActiveRulesetVocabulary`, `TestSyntheticInvariants`, `TestAgainstRealCorpus`.

**Snapshot:** 233 lines; tracked; SHA-256 `e54101bf9da44ca2c1f70eff70c016757d0429866a4a72c92cffca96ed99781b`.

### 9.94. `tooling/integrator/tests/test_migration.py`

**Role/user:** Integrator tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** `decision_migration_v1` — the direct operation model of WORK_QUEUES 1.8.

**Use / side effects:** python -m unittest discover -s tooling/integrator/tests (or a targeted module/class).

**Test coverage anchors:** `TestDiscovery`, `TestPlanParsing`, `TestPreconditionsRejectBeforeWriting`, `TestValidMigrationChangesExactlyWhatItDeclared`, `TestRollback`.

**Snapshot:** 465 lines; tracked; SHA-256 `e25e42faca908123e9f1bee868670af92361e7deab96b13369a361939bd7d51d`.

### 9.95. `tooling/integrator/tests/test_migration_v2.py`

**Role/user:** Integrator tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** `decision_migration_v2` — the bounded many-to-one merge model.

**Use / side effects:** python -m unittest discover -s tooling/integrator/tests (or a targeted module/class).

**Test coverage anchors:** `TestPlanShape`, `TestDiscoveryAndPreconditions`, `TestMergeExecution`, `TestTransactional`.

**Snapshot:** 562 lines; tracked; SHA-256 `dda86e6d9f768b281d0c219f60018eee3a0ed46a806498ea851f7d03a4f03e04`.

### 9.96. `tooling/integrator/tests/test_migration_v3.py`

**Role/user:** Integrator tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** `decision_migration_v3` — DEC-2026-0050's bounded label-normalization model.

**Use / side effects:** python -m unittest discover -s tooling/integrator/tests (or a targeted module/class).

**Test coverage anchors:** `TestPlanShape`, `TestLookupNotAuthorship`, `TestDeclaredCounts`, `TestDiscoveryAndPreconditions`, `TestTransaction`, `TestRollback`.

**Snapshot:** 511 lines; tracked; SHA-256 `f66782c1df00f1538a3e30c470505534588c2aaae792b0f61e457e614b981fbf`.

### 9.97. `tooling/integrator/tests/test_operations.py`

**Role/user:** Integrator tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Operation classification, compare-and-swap updates, and registry additions.

**Use / side effects:** python -m unittest discover -s tooling/integrator/tests (or a targeted module/class).

**Test coverage anchors:** `TestOperationIndex`, `TestCompareAndSwap`, `TestRegistryAdditions`.

**Snapshot:** 398 lines; tracked; SHA-256 `de57a66525efafb4684c1949f35dc4d2059349cad0bb571090b0565be8cfbc27`.

### 9.98. `tooling/integrator/tests/test_registration_agreement.py`

**Role/user:** Integrator tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Tests that agreeing repeated node declarations collapse to one registration while conflicting labels/kinds abort; uses rewound fixture baselines.

**Use / side effects:** python -m unittest discover -s tooling/integrator/tests (or a targeted module/class).

**Test coverage anchors:** `TestAgreeingRedeclaration`, `TestDisagreeingRedeclaration`.

**Snapshot:** 185 lines; tracked; SHA-256 `916d8c740164bf0285941caf552127444802683e2ebf022f198c2811b2c9dbf8`.

### 9.99. `tooling/integrator/tests/test_transaction.py`

**Role/user:** Integrator tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Transactional guarantees: no partial mutation, complete rollback.

**Use / side effects:** python -m unittest discover -s tooling/integrator/tests (or a targeted module/class).

**Test coverage anchors:** `TestSnapshot`, `TestIntegrationIsAtomic`, `TestPreconditions`, `TestAPartialRewindClosesOverRetiredIdentities`, `TestEveryIntegratedMigrationStaysRewindable`, `TestASnapshotRestoresAbsenceNotJustContent`.

**Snapshot:** 904 lines; tracked; SHA-256 `79a133e80fd7946f98c575a29edaabed4b0f6254379d57a8ea8cdd8520e1dc8d`.

### 9.100. `tooling/integrator/tests/test_vocabulary.py`

**Role/user:** Integrator tooling owner; Reviewer independent verification. **Status:** Test/support module.

**Purpose:** Each ruleset's vocabulary comes from its own Constitution. DEC-2026-0092.

**Use / side effects:** python -m unittest discover -s tooling/integrator/tests (or a targeted module/class).

**Test coverage anchors:** `TestTheActiveConstitutionSuppliesTheVocabulary`, `TestAMalformedConstitutionFailsClosed`.

**Snapshot:** 218 lines; tracked; SHA-256 `05d35c7bf71dc648799bb4df24796214351d1ffc7c8dcd52d0d8f4e5dd21916d`.

### 9.101. `tooling/reviewer/tests/test_dec0082_r02_acceptance.py`

**Role/user:** Reviewer. **Status:** Historical independent relay test.

**Purpose:** Additional independent r02 relay probes; no real Herdr prompt is possible. Uses fake endpoints/temp roots, not live agent prompts.

**Use / side effects:** python -m unittest discover -s tooling/reviewer/tests (or a targeted module/class).

**Test coverage anchors:** `R02Acceptance`.

**Snapshot:** 134 lines; tracked; SHA-256 `a7219e2f40ae59bdcda2d6fed7cc9644caa2f4fa4f7f3b485849cfde794b33de`.

### 9.102. `tooling/reviewer/tests/test_dec0082_relay_acceptance.py`

**Role/user:** Reviewer. **Status:** Historical independent relay test.

**Purpose:** Independent DEC-2026-0082 acceptance probes; fake endpoints and temp roots only. Uses fake endpoints/temp roots, not live agent prompts.

**Use / side effects:** python -m unittest discover -s tooling/reviewer/tests (or a targeted module/class).

**Test coverage anchors:** `IndependentRelayAcceptance`.

**Snapshot:** 145 lines; tracked; SHA-256 `b4abe87791c7ce22462669cbc03cd1e37b0265dc05b291e1b2bac12fc7900165`.

### Audit Helpers Added For This Report

- `.local/handoff-audit/report_audit.py`: Architect documentation support, not worker pipeline tooling. Read-only project-script AST/file inventory, scanner snapshot, CSV counts and artifact/Decision/packet correlation. Writes only .local/handoff-audit evidence JSON/text.

- `.local/handoff-audit/write_report.py`: Architect documentation support, not worker pipeline tooling. Combines measured snapshots and curated documentation into GEMINI_CLI_HANDOFF_REPORT.md; runs read-only graph/queue checks and report coverage checks. Does not govern normal work.

The companion report_sections.md is a Markdown template, not a third script. These two helpers are excluded from the 102 pre-existing-script count and included in the 104 post-audit total. Neither helper should become required startup context.

## 10. Packet Completion And Backlog Ledger

Each claimed item below is correlated through its packet ID to a successful INT manifest. Each SD incoming filename is correlated to `packet.yaml.original_filename`, not counted as new simply because it remains in incoming. These are lifecycle measurements, not a fresh source audit. Full paths are linked where they establish completion or the next source input.

### adnd1e/dmg

| Source filename | Packet ID | Status | Evidence |
| --- | --- | --- | --- |
| dmg-p64.md | PKT-DMG-064-064-missile-discharge | Integrated | [INT-20260905-001](rulesets/adnd1e/manifests/INT-20260905-001.json); GUP-PKT-DMG-064-064-missile-discharge-r03 |



### adnd1e/mm

Workspace exists; no incoming Markdown or claimed packet manifest found. Preserved source/legacy material, if any, is not an automatically assigned packet.

### adnd1e/phb

| Source filename | Packet ID | Status | Evidence |
| --- | --- | --- | --- |
| phb.01.preamble.md | PKT-PHB-001-006-preamble | Integrated | [INT-20260730-001](rulesets/adnd1e/manifests/INT-20260730-001.json); GUP-PKT-PHB-001-006-preamble-r02 |
| phb.02.intro.md | PKT-PHB-007-008-intro | Integrated | [INT-20260730-001](rulesets/adnd1e/manifests/INT-20260730-001.json); GUP-PKT-PHB-007-008-intro-r05 |
| phb.03.ability_scores.md | PKT-PHB-009-013-ability-scores | Integrated | [INT-20260801-001](rulesets/adnd1e/manifests/INT-20260801-001.json); GUP-PKT-PHB-009-013-ability-scores-r06 |
| phb.04.races.md | PKT-PHB-013-018-races | Integrated | [INT-20260801-001](rulesets/adnd1e/manifests/INT-20260801-001.json); GUP-PKT-PHB-013-018-races-r09 |
| phb.05.classes.md | PKT-PHB-018-033-classes | Integrated | [INT-20260803-001](rulesets/adnd1e/manifests/INT-20260803-001.json); GUP-PKT-PHB-018-033-classes-r09 |
| phb.06.additional_character_info.md | PKT-PHB-033-035-alignment-hp-languages | Integrated | [INT-20260804-001](rulesets/adnd1e/manifests/INT-20260804-001.json); GUP-PKT-PHB-033-035-alignment-hp-languages-r06 |
| phb.07.equipment.md | PKT-PHB-035-038-money-equipment | Integrated | [INT-20260804-001](rulesets/adnd1e/manifests/INT-20260804-001.json); GUP-PKT-PHB-035-038-money-equipment-r07 |
| phb.08.additional_concepts.md | PKT-PHB-039-040-hirelings-time-distance | Integrated | [INT-20260801-002](rulesets/adnd1e/manifests/INT-20260801-002.json); GUP-PKT-PHB-039-040-hirelings-time-distance-r05 |
| phb.09.spells_intro.md | PKT-PHB-040-042-spells-intro | Integrated | [INT-20260801-001](rulesets/adnd1e/manifests/INT-20260801-001.json); GUP-PKT-PHB-040-042-spells-intro-r04 |
| phb.10.cleric_spells.md | PKT-PHB-043-054-cleric-spells | Integrated | [INT-20260804-001](rulesets/adnd1e/manifests/INT-20260804-001.json); GUP-PKT-PHB-043-054-cleric-spells-r06 |
| phb.11.druid_spells.md | PKT-PHB-054-064-druid-spells | Integrated | [INT-20260830-003](rulesets/adnd1e/manifests/INT-20260830-003.json); GUP-PKT-PHB-054-064-druid-spells-r03 |
| phb.12.mu_spells_1-4.md | PKT-PHB-064-079-magic-user-spells-1-4 | Integrated | [INT-20260826-001](rulesets/adnd1e/manifests/INT-20260826-001.json); GUP-PKT-PHB-064-079-magic-user-spells-1-4-r08 |
| phb.13.mu_spells_5-9.md | PKT-PHB-079-094-magic-user-spells-5-9 | Integrated | [INT-20260826-001](rulesets/adnd1e/manifests/INT-20260826-001.json); GUP-PKT-PHB-079-094-magic-user-spells-5-9-r07 |
| phb.14.illusionist_spells.md | PKT-PHB-094-100-illusionist-spells | Integrated | [INT-20260825-001](rulesets/adnd1e/manifests/INT-20260825-001.json); GUP-PKT-PHB-094-100-illusionist-spells-r08 |
| phb.15.playing_the_game.md | PKT-PHB-100-109-playing-the-game | Integrated | [INT-20260815-001](rulesets/adnd1e/manifests/INT-20260815-001.json); GUP-PKT-PHB-100-109-playing-the-game-r06 |
| phb.16.appendix1.psionics.md | PKT-PHB-110-117-psionics | Integrated | [INT-20260819-003](rulesets/adnd1e/manifests/INT-20260819-003.json); GUP-PKT-PHB-110-117-psionics-r06 |
| phb.17.appendix2.bards.md | PKT-PHB-117-119-bards | Integrated | [INT-20260830-001](rulesets/adnd1e/manifests/INT-20260830-001.json); GUP-PKT-PHB-117-119-bards-r04 |
| phb.18.appendix3.alignment_graph.md | PKT-PHB-119-119-alignment-graph | Integrated | [INT-20260812-001](rulesets/adnd1e/manifests/INT-20260812-001.json); GUP-PKT-PHB-119-119-alignment-graph-r03 |
| phb.19.appendix4.planes.md | PKT-PHB-120-120-planes-of-existence | Integrated | [INT-20260814-002](rulesets/adnd1e/manifests/INT-20260814-002.json); GUP-PKT-PHB-120-120-planes-of-existence-r06 |
| phb.20.appendix5.division_of_treasure.md | PKT-PHB-122-122-division-of-treasure | Integrated | [INT-20260812-001](rulesets/adnd1e/manifests/INT-20260812-001.json); GUP-PKT-PHB-122-122-division-of-treasure-r04 |



### adnd1e/ua

| Source filename | Packet ID | Status | Evidence |
| --- | --- | --- | --- |
| ua-class-cavalier.md | PKT-UA-014-016-cavalier | Integrated | [INT-20260819-004](rulesets/adnd1e/manifests/INT-20260819-004.json); GUP-PKT-UA-014-016-cavalier-r03 |
| ua-p15.md | PKT-UA-015-015-cavaliers | Terminal withdrawal | [GUR-PKT-UA-015-015-cavaliers-r03](books/adnd1e/ua/artifacts/gur/GUR-PKT-UA-015-015-cavaliers-r03.yaml) |



### basicdnd/rc

| Source filename | Packet ID | Status | Evidence |
| --- | --- | --- | --- |
| [RC_pages_1-5.md](books/basicdnd/rc/packets/incoming/RC_pages_1-5.md) | PKT-RC-001-005-front-matter-and-introduction | OWNER-PAUSED; do not act | [claim only](books/basicdnd/rc/packets/claimed/PKT-RC-001-005-front-matter-and-introduction/packet.yaml) |
| [RC_pages_6-12.md](books/basicdnd/rc/packets/incoming/RC_pages_6-12.md) | PKT-RC-006-012-steps-in-character-creation | OWNER-PAUSED; do not act | [claim only](books/basicdnd/rc/packets/claimed/PKT-RC-006-012-steps-in-character-creation/packet.yaml) |



### shadowdark/cs1

Workspace exists; no incoming Markdown or claimed packet manifest found. Preserved source/legacy material, if any, is not an automatically assigned packet.

### shadowdark/cs2

Workspace exists; no incoming Markdown or claimed packet manifest found. Preserved source/legacy material, if any, is not an automatically assigned packet.

### shadowdark/cs3

Workspace exists; no incoming Markdown or claimed packet manifest found. Preserved source/legacy material, if any, is not an automatically assigned packet.

### shadowdark/sd

| Source filename | Packet ID | Status | Evidence |
| --- | --- | --- | --- |
| [001-credits-and-contents.md](books/shadowdark/sd/packets/incoming/001-credits-and-contents.md) | PKT-SD-001-004-credits-and-contents | Integrated | [INT-20260923-004](rulesets/shadowdark/manifests/INT-20260923-004.json); GUP-PKT-SD-001-004-credits-and-contents-r01 |
| [002-introduction-and-the-basics.md](books/shadowdark/sd/packets/incoming/002-introduction-and-the-basics.md) | PKT-SD-005-010-introduction-and-the-basics | Integrated | [INT-20260923-005](rulesets/shadowdark/manifests/INT-20260923-005.json); GUP-PKT-SD-005-010-introduction-and-the-basics-r02 |
| [003-character-overview-and-starting-level.md](books/shadowdark/sd/packets/incoming/003-character-overview-and-starting-level.md) | PKT-SD-011-014-character-overview-and-starting-level | Integrated | [INT-20260923-002](rulesets/shadowdark/manifests/INT-20260923-002.json); GUP-PKT-SD-011-014-character-overview-and-starting-level-r03 |
| [004-stats-and-stat-modifiers.md](books/shadowdark/sd/packets/incoming/004-stats-and-stat-modifiers.md) | PKT-SD-015-015-stats-and-stat-modifiers | Integrated | [INT-20260922-002](rulesets/shadowdark/manifests/INT-20260922-002.json); GUP-PKT-SD-015-015-stats-and-stat-modifiers-r05 |
| [005-ancestries.md](books/shadowdark/sd/packets/incoming/005-ancestries.md) | PKT-SD-016-017-ancestries | Integrated | [INT-20260922-003](rulesets/shadowdark/manifests/INT-20260922-003.json); GUP-PKT-SD-016-017-ancestries-r02 |
| [006-fighter-class.md](books/shadowdark/sd/packets/incoming/006-fighter-class.md) | PKT-SD-018-019-fighter-class | Integrated | [INT-20260924-001](rulesets/shadowdark/manifests/INT-20260924-001.json); GUP-PKT-SD-018-019-fighter-class-r02 |
| [007-priest-class.md](books/shadowdark/sd/packets/incoming/007-priest-class.md) | PKT-SD-020-021-priest-class | Integrated | [INT-20260924-002](rulesets/shadowdark/manifests/INT-20260924-002.json); GUP-PKT-SD-020-021-priest-class-r02 |
| [008-thief-class.md](books/shadowdark/sd/packets/incoming/008-thief-class.md) | PKT-SD-022-023-thief-class | Integrated | [INT-20260924-003](rulesets/shadowdark/manifests/INT-20260924-003.json); GUP-PKT-SD-022-023-thief-class-r03 |
| [009-wizard-class.md](books/shadowdark/sd/packets/incoming/009-wizard-class.md) | PKT-SD-024-025-wizard-class | Integrated | [INT-20260924-006](rulesets/shadowdark/manifests/INT-20260924-006.json); GUP-PKT-SD-024-025-wizard-class-r02 |
| [010-background.md](books/shadowdark/sd/packets/incoming/010-background.md) | PKT-SD-026-026-background | Integrated | [INT-20260924-007](rulesets/shadowdark/manifests/INT-20260924-007.json); GUP-PKT-SD-026-026-background-r02 |
| [011-alignment-and-deities.md](books/shadowdark/sd/packets/incoming/011-alignment-and-deities.md) | PKT-SD-027-029-alignment-and-deities | Integrated | [INT-20260924-009](rulesets/shadowdark/manifests/INT-20260924-009.json); GUP-PKT-SD-027-029-alignment-and-deities-r03 |
| [012-titles.md](books/shadowdark/sd/packets/incoming/012-titles.md) | PKT-SD-030-031-titles | Integrated | [INT-20260924-008](rulesets/shadowdark/manifests/INT-20260924-008.json); GUP-PKT-SD-030-031-titles-r02 |
| [013-languages.md](books/shadowdark/sd/packets/incoming/013-languages.md) | PKT-SD-032-032-languages | Integrated | [INT-20260924-004](rulesets/shadowdark/manifests/INT-20260924-004.json); GUP-PKT-SD-032-032-languages-r01 |
| [014-starting-gear-armor-class-and-equipment.md](books/shadowdark/sd/packets/incoming/014-starting-gear-armor-class-and-equipment.md) | PKT-SD-033-037-starting-gear-armor-class-and-equipment | Integrated | [INT-20260924-010](rulesets/shadowdark/manifests/INT-20260924-010.json); GUP-PKT-SD-033-037-starting-gear-armor-class-and-equipment-r02 |
| [015-character-names.md](books/shadowdark/sd/packets/incoming/015-character-names.md) | PKT-SD-038-038-character-names | Integrated | [INT-20260924-005](rulesets/shadowdark/manifests/INT-20260924-005.json); GUP-PKT-SD-038-038-character-names-r01 |
| [016-level-advancement.md](books/shadowdark/sd/packets/incoming/016-level-advancement.md) | PKT-SD-039-039-level-advancement | Integrated | [INT-20260924-011](rulesets/shadowdark/manifests/INT-20260924-011.json); GUP-PKT-SD-039-039-level-advancement-r02 |
| [017-random-characters.md](books/shadowdark/sd/packets/incoming/017-random-characters.md) | PKT-SD-040-042-random-characters | Integrated | [INT-20260926-001](rulesets/shadowdark/manifests/INT-20260926-001.json); GUP-PKT-SD-040-042-random-characters-r02 |
| [018-magic-rules-mishaps-scrolls-wands-and-focus.md](books/shadowdark/sd/packets/incoming/018-magic-rules-mishaps-scrolls-wands-and-focus.md) | PKT-SD-043-050-magic-rules-mishaps-scrolls-wands-and-focus | Integrated | [INT-20260926-002](rulesets/shadowdark/manifests/INT-20260926-002.json); GUP-PKT-SD-043-050-magic-rules-mishaps-scrolls-wands-and-focus-r02 |
| [019-priest-and-wizard-spell-lists.md](books/shadowdark/sd/packets/incoming/019-priest-and-wizard-spell-lists.md) | PKT-SD-051-053-priest-and-wizard-spell-lists | Integrated | [INT-20260924-013](rulesets/shadowdark/manifests/INT-20260924-013.json); GUP-PKT-SD-051-053-priest-and-wizard-spell-lists-r01 |
| [020-spells-acid-arrow-to-burning-hands.md](books/shadowdark/sd/packets/incoming/020-spells-acid-arrow-to-burning-hands.md) | PKT-SD-054-056-spells-acid-arrow-to-burning-hands | Integrated | [INT-20260924-014](rulesets/shadowdark/manifests/INT-20260924-014.json); GUP-PKT-SD-054-056-spells-acid-arrow-to-burning-hands-r01 |
| [021-spells-charm-person-to-detect-magic.md](books/shadowdark/sd/packets/incoming/021-spells-charm-person-to-detect-magic.md) | PKT-SD-057-058-spells-charm-person-to-detect-magic | Integrated | [INT-20260925-004](rulesets/shadowdark/manifests/INT-20260925-004.json); GUP-PKT-SD-057-058-spells-charm-person-to-detect-magic-r02 |
| [022-spells-detect-thoughts-to-fireball.md](books/shadowdark/sd/packets/incoming/022-spells-detect-thoughts-to-fireball.md) | PKT-SD-059-060-spells-detect-thoughts-to-fireball | Integrated | [INT-20260925-005](rulesets/shadowdark/manifests/INT-20260925-005.json); GUP-PKT-SD-059-060-spells-detect-thoughts-to-fireball-r02 |
| [023-spells-fixed-object-to-holy-weapon.md](books/shadowdark/sd/packets/incoming/023-spells-fixed-object-to-holy-weapon.md) | PKT-SD-061-062-spells-fixed-object-to-holy-weapon | Integrated | [INT-20260924-015](rulesets/shadowdark/manifests/INT-20260924-015.json); GUP-PKT-SD-061-062-spells-fixed-object-to-holy-weapon-r01 |
| [024-spells-illusion-to-magic-circle.md](books/shadowdark/sd/packets/incoming/024-spells-illusion-to-magic-circle.md) | PKT-SD-062-065-spells-illusion-to-magic-circle | Integrated | [INT-20260926-003](rulesets/shadowdark/manifests/INT-20260926-003.json); GUP-PKT-SD-062-065-spells-illusion-to-magic-circle-r02 |
| [025-spells-magic-missile-to-prismatic-orb.md](books/shadowdark/sd/packets/incoming/025-spells-magic-missile-to-prismatic-orb.md) | PKT-SD-065-067-spells-magic-missile-to-prismatic-orb | Integrated | [INT-20260926-004](rulesets/shadowdark/manifests/INT-20260926-004.json); GUP-PKT-SD-065-067-spells-magic-missile-to-prismatic-orb-r02 |
| [026-spells-prophecy-to-shapechange.md](books/shadowdark/sd/packets/incoming/026-spells-prophecy-to-shapechange.md) | PKT-SD-068-070-spells-prophecy-to-shapechange | Integrated | [INT-20260926-005](rulesets/shadowdark/manifests/INT-20260926-005.json); GUP-PKT-SD-068-070-spells-prophecy-to-shapechange-r02 |
| [027-spells-shield-of-faith-to-turn-undead.md](books/shadowdark/sd/packets/incoming/027-spells-shield-of-faith-to-turn-undead.md) | PKT-SD-070-072-spells-shield-of-faith-to-turn-undead | Integrated | [INT-20260926-006](rulesets/shadowdark/manifests/INT-20260926-006.json); GUP-PKT-SD-070-072-spells-shield-of-faith-to-turn-undead-r01 |
| [028-spells-wall-of-force-to-zone-of-truth.md](books/shadowdark/sd/packets/incoming/028-spells-wall-of-force-to-zone-of-truth.md) | PKT-SD-073-074-spells-wall-of-force-to-zone-of-truth | Integrated | [INT-20260926-007](rulesets/shadowdark/manifests/INT-20260926-007.json); GUP-PKT-SD-073-074-spells-wall-of-force-to-zone-of-truth-r01 |
| [029-gameplay-introduction-and-adventuring.md](books/shadowdark/sd/packets/incoming/029-gameplay-introduction-and-adventuring.md) | PKT-SD-075-077-gameplay-introduction-and-adventuring | Integrated | [INT-20260925-001](rulesets/shadowdark/manifests/INT-20260925-001.json); GUP-PKT-SD-075-077-gameplay-introduction-and-adventuring-r01 |
| [030-dice-luck-stats-and-checks.md](books/shadowdark/sd/packets/incoming/030-dice-luck-stats-and-checks.md) | PKT-SD-078-081-dice-luck-stats-and-checks | Integrated | [INT-20260925-002](rulesets/shadowdark/manifests/INT-20260925-002.json); GUP-PKT-SD-078-081-dice-luck-stats-and-checks-r01 |
| [031-time-and-turn-order.md](books/shadowdark/sd/packets/incoming/031-time-and-turn-order.md) | PKT-SD-082-083-time-and-turn-order | Integrated | [INT-20260925-003](rulesets/shadowdark/manifests/INT-20260925-003.json); GUP-PKT-SD-082-083-time-and-turn-order-r01 |
| [032-crawling-light-and-movement.md](books/shadowdark/sd/packets/incoming/032-crawling-light-and-movement.md) | PKT-SD-084-085-crawling-light-and-movement | Integrated | [INT-20260925-006](rulesets/shadowdark/manifests/INT-20260925-006.json); GUP-PKT-SD-084-085-crawling-light-and-movement-r01 |
| [033-resting.md](books/shadowdark/sd/packets/incoming/033-resting.md) | PKT-SD-086-086-resting | Integrated | [INT-20260925-007](rulesets/shadowdark/manifests/INT-20260925-007.json); GUP-PKT-SD-086-086-resting-r01 |
| [034-stealth-surprise-and-combat.md](books/shadowdark/sd/packets/incoming/034-stealth-surprise-and-combat.md) | PKT-SD-087-089-stealth-surprise-and-combat | Integrated | [INT-20260926-008](rulesets/shadowdark/manifests/INT-20260926-008.json); GUP-PKT-SD-087-089-stealth-surprise-and-combat-r02 |
| [035-overland-travel.md](books/shadowdark/sd/packets/incoming/035-overland-travel.md) | PKT-SD-090-090-overland-travel | Integrated | [INT-20260926-009](rulesets/shadowdark/manifests/INT-20260926-009.json); GUP-PKT-SD-090-090-overland-travel-r02 |
| [036-downtime-and-carousing.md](books/shadowdark/sd/packets/incoming/036-downtime-and-carousing.md) | PKT-SD-091-093-downtime-and-carousing | Integrated | [INT-20260926-010](rulesets/shadowdark/manifests/INT-20260926-010.json); GUP-PKT-SD-091-093-downtime-and-carousing-r02 |
| [037-wizards-and-thieves.md](books/shadowdark/sd/packets/incoming/037-wizards-and-thieves.md) | PKT-SD-094-095-wizards-and-thieves | Integrated | [INT-20260926-011](rulesets/shadowdark/manifests/INT-20260926-011.json); GUP-PKT-SD-094-095-wizards-and-thieves-r01 |
| [038-example-of-play.md](books/shadowdark/sd/packets/incoming/038-example-of-play.md) | PKT-SD-096-100-example-of-play | Integrated | [INT-20260926-012](rulesets/shadowdark/manifests/INT-20260926-012.json); GUP-PKT-SD-096-100-example-of-play-r03 |
| [039-game-master-guidance.md](books/shadowdark/sd/packets/incoming/039-game-master-guidance.md) | PKT-SD-101-109-game-master-guidance | Integrated | [INT-20260926-013](rulesets/shadowdark/manifests/INT-20260926-013.json); GUP-PKT-SD-101-109-game-master-guidance-r01 |
| [040-let-there-be-darkness.md](books/shadowdark/sd/packets/incoming/040-let-there-be-darkness.md) | PKT-SD-110-110-let-there-be-darkness | Integrated | [INT-20260926-014](rulesets/shadowdark/manifests/INT-20260926-014.json); GUP-PKT-SD-110-110-let-there-be-darkness-r02 |
| [041-optional-modes-of-play.md](books/shadowdark/sd/packets/incoming/041-optional-modes-of-play.md) | PKT-SD-111-111-optional-modes-of-play | Integrated | [INT-20260926-015](rulesets/shadowdark/manifests/INT-20260926-015.json); GUP-PKT-SD-111-111-optional-modes-of-play-r02 |
| [042-random-encounters.md](books/shadowdark/sd/packets/incoming/042-random-encounters.md) | PKT-SD-112-113-random-encounters | Integrated | [INT-20260926-016](rulesets/shadowdark/manifests/INT-20260926-016.json); GUP-PKT-SD-112-113-random-encounters-r01 |
| [043-traps.md](books/shadowdark/sd/packets/incoming/043-traps.md) | PKT-SD-114-114-traps | Integrated | [INT-20260926-017](rulesets/shadowdark/manifests/INT-20260926-017.json); GUP-PKT-SD-114-114-traps-r01 |
| [044-hazards.md](books/shadowdark/sd/packets/incoming/044-hazards.md) | PKT-SD-115-115-hazards | Integrated | [INT-20260926-018](rulesets/shadowdark/manifests/INT-20260926-018.json); GUP-PKT-SD-115-115-hazards-r01 |
| [045-the-gauntlet.md](books/shadowdark/sd/packets/incoming/045-the-gauntlet.md) | PKT-SD-116-116-the-gauntlet | Integrated | [INT-20260926-019](rulesets/shadowdark/manifests/INT-20260926-019.json); GUP-PKT-SD-116-116-the-gauntlet-r01 |
| [046-awarding-xp.md](books/shadowdark/sd/packets/incoming/046-awarding-xp.md) | PKT-SD-117-117-awarding-xp | Integrated | [INT-20260926-020](rulesets/shadowdark/manifests/INT-20260926-020.json); GUP-PKT-SD-117-117-awarding-xp-r01 |
| [047-something-happens.md](books/shadowdark/sd/packets/incoming/047-something-happens.md) | PKT-SD-118-119-something-happens | Integrated | [INT-20260926-021](rulesets/shadowdark/manifests/INT-20260926-021.json); GUP-PKT-SD-118-119-something-happens-r01 |
| [048-rumors.md](books/shadowdark/sd/packets/incoming/048-rumors.md) | PKT-SD-120-121-rumors | Integrated | [INT-20260927-001](rulesets/shadowdark/manifests/INT-20260927-001.json); GUP-PKT-SD-120-121-rumors-r01 |
| [049-adventures.md](books/shadowdark/sd/packets/incoming/049-adventures.md) | PKT-SD-122-123-adventures | Integrated | [INT-20260927-002](rulesets/shadowdark/manifests/INT-20260927-002.json); GUP-PKT-SD-122-123-adventures-r01 |
| [050-npcs.md](books/shadowdark/sd/packets/incoming/050-npcs.md) | PKT-SD-124-125-npcs | Integrated | [INT-20260928-001](rulesets/shadowdark/manifests/INT-20260928-001.json); GUP-PKT-SD-124-125-npcs-r01 |
| [051-rival-crawlers.md](books/shadowdark/sd/packets/incoming/051-rival-crawlers.md) | PKT-SD-126-127-rival-crawlers | Integrated | [INT-20260928-002](rulesets/shadowdark/manifests/INT-20260928-002.json); GUP-PKT-SD-126-127-rival-crawlers-r01 |
| [052-npc-names.md](books/shadowdark/sd/packets/incoming/052-npc-names.md) | PKT-SD-128-129-npc-names | Integrated | [INT-20260928-003](rulesets/shadowdark/manifests/INT-20260928-003.json); GUP-PKT-SD-128-129-npc-names-r01 |
| [053-shadowdark-maps.md](books/shadowdark/sd/packets/incoming/053-shadowdark-maps.md) | PKT-SD-130-131-shadowdark-maps | Integrated | [INT-20260928-004](rulesets/shadowdark/manifests/INT-20260928-004.json); GUP-PKT-SD-130-131-shadowdark-maps-r01 |
| [054-overland-hex-maps.md](books/shadowdark/sd/packets/incoming/054-overland-hex-maps.md) | PKT-SD-132-133-overland-hex-maps | Integrated | [INT-20260928-005](rulesets/shadowdark/manifests/INT-20260928-005.json); GUP-PKT-SD-132-133-overland-hex-maps-r01 |
| [055-settlement-maps.md](books/shadowdark/sd/packets/incoming/055-settlement-maps.md) | PKT-SD-134-135-settlement-maps | Integrated | [INT-20260928-006](rulesets/shadowdark/manifests/INT-20260928-006.json); GUP-PKT-SD-134-135-settlement-maps-r01 |
| [056-taverns.md](books/shadowdark/sd/packets/incoming/056-taverns.md) | PKT-SD-136-137-taverns | Integrated | [INT-20260928-007](rulesets/shadowdark/manifests/INT-20260928-007.json); GUP-PKT-SD-136-137-taverns-r02 |
| [057-shop.md](books/shadowdark/sd/packets/incoming/057-shop.md) | PKT-SD-138-141-shop | Integrated | [INT-20260928-008](rulesets/shadowdark/manifests/INT-20260928-008.json); GUP-PKT-SD-138-141-shop-r01 |
| [058-encounters-arctic.md](books/shadowdark/sd/packets/incoming/058-encounters-arctic.md) | PKT-SD-142-143-arctic | Integrated | [INT-20260928-009](rulesets/shadowdark/manifests/INT-20260928-009.json); GUP-PKT-SD-142-143-arctic-r01 |
| [059-encounters-artisan-district.md](books/shadowdark/sd/packets/incoming/059-encounters-artisan-district.md) | PKT-SD-144-145-artisan-district | Integrated | [INT-20260929-001](rulesets/shadowdark/manifests/INT-20260929-001.json); GUP-PKT-SD-144-145-artisan-district-r01 |
| [060-encounters-castle-district.md](books/shadowdark/sd/packets/incoming/060-encounters-castle-district.md) | PKT-SD-146-147-castle-district | Integrated | [INT-20260929-002](rulesets/shadowdark/manifests/INT-20260929-002.json); GUP-PKT-SD-146-147-castle-district-r01 |
| [061-encounters-cave-encounters.md](books/shadowdark/sd/packets/incoming/061-encounters-cave-encounters.md) | PKT-SD-148-149-cave-encounters | Integrated | [INT-20260929-003](rulesets/shadowdark/manifests/INT-20260929-003.json); GUP-PKT-SD-148-149-cave-encounters-r01 |
| [062-encounters-deep-tunnels.md](books/shadowdark/sd/packets/incoming/062-encounters-deep-tunnels.md) | PKT-SD-150-151-deep-tunnels | Integrated | [INT-20260929-004](rulesets/shadowdark/manifests/INT-20260929-004.json); GUP-PKT-SD-150-151-deep-tunnels-r01 |
| [063-encounters-desert.md](books/shadowdark/sd/packets/incoming/063-encounters-desert.md) | PKT-SD-152-153-desert | Integrated | [INT-20260929-005](rulesets/shadowdark/manifests/INT-20260929-005.json); GUP-PKT-SD-152-153-desert-r02 |
| [064-encounters-forest.md](books/shadowdark/sd/packets/incoming/064-encounters-forest.md) | PKT-SD-154-155-forest | Integrated | [INT-20260929-006](rulesets/shadowdark/manifests/INT-20260929-006.json); GUP-PKT-SD-154-155-forest-r01 |
| [065-encounters-grassland.md](books/shadowdark/sd/packets/incoming/065-encounters-grassland.md) | PKT-SD-156-157-grassland | Integrated | [INT-20260929-007](rulesets/shadowdark/manifests/INT-20260929-007.json); GUP-PKT-SD-156-157-grassland-r01 |
| [066-encounters-high-district.md](books/shadowdark/sd/packets/incoming/066-encounters-high-district.md) | PKT-SD-158-159-high-district | Integrated | [INT-20260929-008](rulesets/shadowdark/manifests/INT-20260929-008.json); GUP-PKT-SD-158-159-high-district-r01 |
| [067-encounters-jungle.md](books/shadowdark/sd/packets/incoming/067-encounters-jungle.md) | PKT-SD-160-161-jungle | Integrated | [INT-20260929-009](rulesets/shadowdark/manifests/INT-20260929-009.json); GUP-PKT-SD-160-161-jungle-r01 |
| [068-encounters-low-district.md](books/shadowdark/sd/packets/incoming/068-encounters-low-district.md) | PKT-SD-162-163-low-district | Integrated | [INT-20260929-010](rulesets/shadowdark/manifests/INT-20260929-010.json); GUP-PKT-SD-162-163-low-district-r01 |
| [069-encounters-market.md](books/shadowdark/sd/packets/incoming/069-encounters-market.md) | PKT-SD-164-165-market | Integrated | [INT-20260929-011](rulesets/shadowdark/manifests/INT-20260929-011.json); GUP-PKT-SD-164-165-market-r01 |
| [070-encounters-mountain.md](books/shadowdark/sd/packets/incoming/070-encounters-mountain.md) | PKT-SD-166-167-mountain | Integrated | [INT-20260929-012](rulesets/shadowdark/manifests/INT-20260929-012.json); GUP-PKT-SD-166-167-mountain-r01 |
| [071-encounters-ocean.md](books/shadowdark/sd/packets/incoming/071-encounters-ocean.md) | PKT-SD-168-169-ocean | Integrated | [INT-20260929-013](rulesets/shadowdark/manifests/INT-20260929-013.json); GUP-PKT-SD-168-169-ocean-r01 |
| [072-encounters-river-and-coast.md](books/shadowdark/sd/packets/incoming/072-encounters-river-and-coast.md) | PKT-SD-170-171-river-and-coast | Integrated | [INT-20260929-014](rulesets/shadowdark/manifests/INT-20260929-014.json); GUP-PKT-SD-170-171-river-and-coast-r01 |
| [073-encounters-ruins.md](books/shadowdark/sd/packets/incoming/073-encounters-ruins.md) | PKT-SD-172-173-ruins | Integrated | [INT-20260929-015](rulesets/shadowdark/manifests/INT-20260929-015.json); GUP-PKT-SD-172-173-ruins-r01 |
| [074-encounters-slums.md](books/shadowdark/sd/packets/incoming/074-encounters-slums.md) | PKT-SD-174-175-slums | Integrated | [INT-20260929-016](rulesets/shadowdark/manifests/INT-20260929-016.json); GUP-PKT-SD-174-175-slums-r01 |
| [075-encounters-swamp.md](books/shadowdark/sd/packets/incoming/075-encounters-swamp.md) | PKT-SD-176-177-swamp | Integrated | [INT-20260929-017](rulesets/shadowdark/manifests/INT-20260929-017.json); GUP-PKT-SD-176-177-swamp-r01 |
| [076-encounters-tavern.md](books/shadowdark/sd/packets/incoming/076-encounters-tavern.md) | PKT-SD-178-179-tavern | Integrated | [INT-20260930-001](rulesets/shadowdark/manifests/INT-20260930-001.json); GUP-PKT-SD-178-179-tavern-r01 |
| [077-encounters-temple-district.md](books/shadowdark/sd/packets/incoming/077-encounters-temple-district.md) | PKT-SD-180-181-temple-district | Integrated | [INT-20260930-002](rulesets/shadowdark/manifests/INT-20260930-002.json); GUP-PKT-SD-180-181-temple-district-r01 |
| [078-encounters-tomb.md](books/shadowdark/sd/packets/incoming/078-encounters-tomb.md) | PKT-SD-182-183-tomb | Integrated | [INT-20260930-003](rulesets/shadowdark/manifests/INT-20260930-003.json); GUP-PKT-SD-182-183-tomb-r01 |
| [079-encounters-university-district.md](books/shadowdark/sd/packets/incoming/079-encounters-university-district.md) | PKT-SD-184-186-university-district | Integrated | [INT-20260930-004](rulesets/shadowdark/manifests/INT-20260930-004.json); GUP-PKT-SD-184-186-university-district-r01 |
| [080-monsters-introduction.md](books/shadowdark/sd/packets/incoming/080-monsters-introduction.md) | PKT-SD-187-188-monsters-introduction | Integrated | [INT-20260930-005](rulesets/shadowdark/manifests/INT-20260930-005.json); GUP-PKT-SD-187-188-monsters-introduction-r01 |
| [081-monster-attributes.md](books/shadowdark/sd/packets/incoming/081-monster-attributes.md) | PKT-SD-189-189-monster-attributes | Integrated | [INT-20260930-006](rulesets/shadowdark/manifests/INT-20260930-006.json); GUP-PKT-SD-189-189-monster-attributes-r01 |
| [082-monster-generator-and-mutations.md](books/shadowdark/sd/packets/incoming/082-monster-generator-and-mutations.md) | PKT-SD-190-191-monster-generator-and-mutations | Integrated | [INT-20260930-007](rulesets/shadowdark/manifests/INT-20260930-007.json); GUP-PKT-SD-190-191-monster-generator-and-mutations-r01 |
| [083-designing-monsters.md](books/shadowdark/sd/packets/incoming/083-designing-monsters.md) | PKT-SD-192-193-designing-monsters | Integrated | [INT-20260930-008](rulesets/shadowdark/manifests/INT-20260930-008.json); GUP-PKT-SD-192-193-designing-monsters-r01 |
| [084-monsters-aboleth-to-acolyte.md](books/shadowdark/sd/packets/incoming/084-monsters-aboleth-to-acolyte.md) | PKT-SD-194-194-monsters-aboleth-to-acolyte | Integrated | [INT-20260930-009](rulesets/shadowdark/manifests/INT-20260930-009.json); GUP-PKT-SD-194-194-monsters-aboleth-to-acolyte-r01 |
| [085-monster-family-angels.md](books/shadowdark/sd/packets/incoming/085-monster-family-angels.md) | PKT-SD-195-195-monster-family-angels | Integrated | [INT-20260930-010](rulesets/shadowdark/manifests/INT-20260930-010.json); GUP-PKT-SD-195-195-monster-family-angels-r03 |
| [086-monsters-animated-armor-to-bat-giant.md](books/shadowdark/sd/packets/incoming/086-monsters-animated-armor-to-bat-giant.md) | PKT-SD-196-198-monsters-animated-armor-to-bat-giant | Integrated | [INT-20261001-001](rulesets/shadowdark/manifests/INT-20261001-001.json); GUP-PKT-SD-196-198-monsters-animated-armor-to-bat-giant-r02 |
| [087-monsters-bat-swarm-to-cave-brute.md](books/shadowdark/sd/packets/incoming/087-monsters-bat-swarm-to-cave-brute.md) | PKT-SD-198-200-monsters-bat-swarm-to-cave-brute | Integrated | [INT-20261001-002](rulesets/shadowdark/manifests/INT-20261001-002.json); GUP-PKT-SD-198-200-monsters-bat-swarm-to-cave-brute-r02 |
| [088-monsters-cave-creeper-to-cultist.md](books/shadowdark/sd/packets/incoming/088-monsters-cave-creeper-to-cultist.md) | PKT-SD-200-203-monsters-cave-creeper-to-cultist | Integrated | [INT-20261001-003](rulesets/shadowdark/manifests/INT-20261001-003.json); GUP-PKT-SD-200-203-monsters-cave-creeper-to-cultist-r02 |
| [089-monsters-cyclops-to-deep-one.md](books/shadowdark/sd/packets/incoming/089-monsters-cyclops-to-deep-one.md) | PKT-SD-203-203-monsters-cyclops-to-deep-one | Integrated | [INT-20261001-004](rulesets/shadowdark/manifests/INT-20261001-004.json); GUP-PKT-SD-203-203-monsters-cyclops-to-deep-one-r02 |
| [090-monster-family-demons.md](books/shadowdark/sd/packets/incoming/090-monster-family-demons.md) | PKT-SD-204-205-monster-family-demons | Integrated | [INT-20261001-005](rulesets/shadowdark/manifests/INT-20261001-005.json); GUP-PKT-SD-204-205-monster-family-demons-r02 |
| [091-monster-family-devils.md](books/shadowdark/sd/packets/incoming/091-monster-family-devils.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [092-monster-family-dinosaurs.md](books/shadowdark/sd/packets/incoming/092-monster-family-dinosaurs.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [093-monsters-djinni-to-doppelganger.md](books/shadowdark/sd/packets/incoming/093-monsters-djinni-to-doppelganger.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [094-monster-family-dragons.md](books/shadowdark/sd/packets/incoming/094-monster-family-dragons.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [095-monster-family-drow.md](books/shadowdark/sd/packets/incoming/095-monster-family-drow.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [096-monsters-druid-to-efreeti.md](books/shadowdark/sd/packets/incoming/096-monsters-druid-to-efreeti.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [097-monster-family-elementals.md](books/shadowdark/sd/packets/incoming/097-monster-family-elementals.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [098-monsters-elephant-to-ghoul.md](books/shadowdark/sd/packets/incoming/098-monsters-elephant-to-ghoul.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [099-monster-family-giants.md](books/shadowdark/sd/packets/incoming/099-monster-family-giants.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [100-monsters-gibbering-mouther-to-gnome-deep.md](books/shadowdark/sd/packets/incoming/100-monsters-gibbering-mouther-to-gnome-deep.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [101-monster-family-goblins.md](books/shadowdark/sd/packets/incoming/101-monster-family-goblins.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [102-monster-family-golems.md](books/shadowdark/sd/packets/incoming/102-monster-family-golems.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [103-monsters-gorgon-to-guard.md](books/shadowdark/sd/packets/incoming/103-monsters-gorgon-to-guard.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [104-monster-family-hags.md](books/shadowdark/sd/packets/incoming/104-monster-family-hags.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [105-monsters-harpy-to-kobold-sorcerer.md](books/shadowdark/sd/packets/incoming/105-monsters-harpy-to-kobold-sorcerer.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [106-monsters-kraken-to-medusa.md](books/shadowdark/sd/packets/incoming/106-monsters-kraken-to-medusa.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [107-monsters-merfolk-to-ochre-jelly.md](books/shadowdark/sd/packets/incoming/107-monsters-merfolk-to-ochre-jelly.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [108-monsters-octopus-giant-to-otyugh.md](books/shadowdark/sd/packets/incoming/108-monsters-octopus-giant-to-otyugh.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [109-monster-family-outsiders.md](books/shadowdark/sd/packets/incoming/109-monster-family-outsiders.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [110-monsters-owlbear-to-rat-dire.md](books/shadowdark/sd/packets/incoming/110-monsters-owlbear-to-rat-dire.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [111-monsters-rat-giant-to-salamander.md](books/shadowdark/sd/packets/incoming/111-monsters-rat-giant-to-salamander.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [112-monsters-scarab-swarm-to-snake-cobra.md](books/shadowdark/sd/packets/incoming/112-monsters-scarab-swarm-to-snake-cobra.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [113-monsters-snake-giant-to-the-wandering-merchant.md](books/shadowdark/sd/packets/incoming/113-monsters-snake-giant-to-the-wandering-merchant.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [114-monsters-thief-to-violet-fungus.md](books/shadowdark/sd/packets/incoming/114-monsters-thief-to-violet-fungus.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [115-monster-family-viperians.md](books/shadowdark/sd/packets/incoming/115-monster-family-viperians.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [116-monsters-vulture-to-wyvern.md](books/shadowdark/sd/packets/incoming/116-monsters-vulture-to-wyvern.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [117-monsters-zombie-to-zombie.md](books/shadowdark/sd/packets/incoming/117-monsters-zombie-to-zombie.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [118-treasure-introduction.md](books/shadowdark/sd/packets/incoming/118-treasure-introduction.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [119-treasure-overview.md](books/shadowdark/sd/packets/incoming/119-treasure-overview.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [120-treasure-table-levels-0-to-3.md](books/shadowdark/sd/packets/incoming/120-treasure-table-levels-0-to-3.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [121-treasure-table-levels-4-to-6.md](books/shadowdark/sd/packets/incoming/121-treasure-table-levels-4-to-6.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [122-treasure-table-levels-7-to-9.md](books/shadowdark/sd/packets/incoming/122-treasure-table-levels-7-to-9.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [123-treasure-table-levels-10-and-above.md](books/shadowdark/sd/packets/incoming/123-treasure-table-levels-10-and-above.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [124-mundane-items.md](books/shadowdark/sd/packets/incoming/124-mundane-items.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [125-boons.md](books/shadowdark/sd/packets/incoming/125-boons.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [126-magic-item-attributes.md](books/shadowdark/sd/packets/incoming/126-magic-item-attributes.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [127-magic-armor-generator.md](books/shadowdark/sd/packets/incoming/127-magic-armor-generator.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [128-potions-and-mixing-potions.md](books/shadowdark/sd/packets/incoming/128-potions-and-mixing-potions.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [129-scroll-and-wand-generator.md](books/shadowdark/sd/packets/incoming/129-scroll-and-wand-generator.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [130-utility-item-generator.md](books/shadowdark/sd/packets/incoming/130-utility-item-generator.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [131-magic-weapon-generator.md](books/shadowdark/sd/packets/incoming/131-magic-weapon-generator.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [132-item-personality.md](books/shadowdark/sd/packets/incoming/132-item-personality.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [133-designing-magic-items.md](books/shadowdark/sd/packets/incoming/133-designing-magic-items.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [134-magic-items-alabaster-destrier-to-boots-of-hovering.md](books/shadowdark/sd/packets/incoming/134-magic-items-alabaster-destrier-to-boots-of-hovering.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [135-magic-items-boots-of-the-cat-to-flying-carpet.md](books/shadowdark/sd/packets/incoming/135-magic-items-boots-of-the-cat-to-flying-carpet.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [136-magic-items-gauntlets-of-might-to-jewel-of-barbalt.md](books/shadowdark/sd/packets/incoming/136-magic-items-gauntlets-of-might-to-jewel-of-barbalt.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [137-magic-items-kytherian-cog-to-obsidian-witchknife.md](books/shadowdark/sd/packets/incoming/137-magic-items-kytherian-cog-to-obsidian-witchknife.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [138-magic-items-onyx-destrier-to-potion-of-invisibility.md](books/shadowdark/sd/packets/incoming/138-magic-items-onyx-destrier-to-potion-of-invisibility.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [139-magic-items-potion-of-legendary-deeds-to-ring-of-fireballs.md](books/shadowdark/sd/packets/incoming/139-magic-items-potion-of-legendary-deeds-to-ring-of-fireballs.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [140-magic-item-ring-of-invisibility.md](books/shadowdark/sd/packets/incoming/140-magic-item-ring-of-invisibility.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [141-magic-items-ring-of-ramlaat-to-sphere-of-annihilation.md](books/shadowdark/sd/packets/incoming/141-magic-items-ring-of-ramlaat-to-sphere-of-annihilation.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [142-magic-items-spyglass-of-true-sight-to-trident-of-the-seas.md](books/shadowdark/sd/packets/incoming/142-magic-items-spyglass-of-true-sight-to-trident-of-the-seas.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [143-magic-items-true-name-to-wraith-chain.md](books/shadowdark/sd/packets/incoming/143-magic-items-true-name-to-wraith-chain.md) | Not yet claimed | Unclaimed intake; Analyst candidate | No packet/GUR/INT inferred |
| [144-community-credits-and-licensing.md](books/shadowdark/sd/packets/incoming/144-community-credits-and-licensing.md) | PKT-SD-322-325-community-credits-and-licensing | Integrated | [INT-20260923-003](rulesets/shadowdark/manifests/INT-20260923-003.json); GUP-PKT-SD-322-325-community-credits-and-licensing-r01 |



### shadowdark/shadowdome

Workspace exists; no incoming Markdown or claimed packet manifest found. Preserved source/legacy material, if any, is not an automatically assigned packet.

### shadowdark/western-reaches-pg

Workspace exists; no incoming Markdown or claimed packet manifest found. Preserved source/legacy material, if any, is not an automatically assigned packet.

## 11. Decision And Implementation Evidence Ledger

This index covers every Decision YAML discovered under current ruleset escalation/decisions stores. Approved is the Decision disposition, not automatic proof of all work being done. The evidence column gives active implementation leaves and their independent Review dispositions when present. A Decision with no IMP may be a direct governance edit, a migrated packet, a replaced authorization, a return, or ordinary worker work; do not invent a missing-report job. Common scanner offers no ready Decision work in this snapshot. Exact post-implementation sequences still govern future work.

### adnd1e

| Decision | Disposition | Question / scope | Authored handoff (not live assignment) | Implementation evidence |
| --- | --- | --- | --- | --- |
| [DEC-2026-0001](rulesets/adnd1e/escalations/decisions/DEC-2026-0001.yaml) | approved | Should race_human be added to the node registry, and should the explicit human default case be represented by a node rather than by the absence of edges? | -/- | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0002](rulesets/adnd1e/escalations/decisions/DEC-2026-0002.yaml) | approved | How should the seven playable character races be represented as one controlled set, how should human and demihuman classification be recorded, and what identity should replace race_any where legacy rows mean demihuman? | -/- | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0003](rulesets/adnd1e/escalations/decisions/DEC-2026-0003.yaml) | approved | Does every absent canonical node ID require Architect approval, or may the normal Builder and Reviewer workflow approve a registry addition under an already-approved prefix and kind? | -/- | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0004](rulesets/adnd1e/escalations/decisions/DEC-2026-0004.yaml) | approved | Which of the node prefixes used by existing AD&D 1e production data should be added to the closed prefix vocabulary, and which identities should instead be migrated to approved kinds? | -/- | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0005](rulesets/adnd1e/escalations/decisions/DEC-2026-0005.yaml) | approved | After DEC-2026-0003 returned incomplete architectural placeholders, which role must supply each standalone escalation package, and what interim precedence applies to the PHB and UA subrace-infravision assertions? | -/- | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0006](rulesets/adnd1e/escalations/decisions/DEC-2026-0006.yaml) | approved | What Windows-safe escalation ID format should replace ESC-YYYY-NNNN, how should same-instant collisions be handled, and must existing IDs be migrated? | -/- | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0007](rulesets/adnd1e/escalations/decisions/DEC-2026-0007.yaml) | approved | Which canonical identity survives for the duplicate Loyalty Base and Maximum Henchmen node pairs, and what migration controls are required? | -/- | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0008](rulesets/adnd1e/escalations/decisions/DEC-2026-0008.yaml) | approved | May one production edge carry several page and section loci, and how should repeated or multi-page support be preserved? | -/- | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0009](rulesets/adnd1e/escalations/decisions/DEC-2026-0009.yaml) | approved | Should the dwarf, gnome, and halfling underground-detection assertions reuse rule_detection, create rule_racial_detection, or be split further? | -/- | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0010](rulesets/adnd1e/escalations/decisions/DEC-2026-0010.yaml) | approved | How should the PHB halfling-subrace infravision assertion coexist with the broader optional UA assertion without false deduplication or provenance loss? | -/- | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0011](rulesets/adnd1e/escalations/decisions/DEC-2026-0011.yaml) | approved | When an ability score, class, or other input determines a mechanic through a table, should the graph use input MODIFIES mechanic or mechanic DERIVED_FROM input? | -/- | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0012](rulesets/adnd1e/escalations/decisions/DEC-2026-0012.yaml) | approved | How must repository work queues represent role-ready jobs while preserving immutable artifact paths, revision history, component grouping, and provenance? | -/- | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0013](rulesets/adnd1e/escalations/decisions/DEC-2026-0013.yaml) | returned_incomplete | Does the current spell-node identity contract require specific-spell IDs to govern over broader or contradictory registry labels, and which existing spell nodes would require relabeling, splitting, renaming, or edge migration? | -/- | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0014](rulesets/adnd1e/escalations/decisions/DEC-2026-0014.yaml) | approved | Which production edge field set governs when the adnd1e edge schema requires per-row ruleset_id and book_id and rejects book, while Constitution v1.4, canonical data, Builder, and Integrator use the same 18-column row? | -/- | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0015](rulesets/adnd1e/escalations/decisions/DEC-2026-0015.yaml) | approved | When a legacy spell_ node's ID names one spell but its registry label and incident assertions name a broader spell category, a condition, or another spell, which identity survives and what exact split or migration is required? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0016](rulesets/adnd1e/escalations/decisions/DEC-2026-0016.yaml) | approved | When page attribution derived from a current claimed packet conflicts with a legacy canonical citation, which value governs and should the nine supplied canonical disagreements be corrected? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0017](rulesets/adnd1e/escalations/decisions/DEC-2026-0017.yaml) | approved | When individual spell descriptions explicitly scale effects with caster experience level, are those dependencies represented per spell or only through a spell aggregate? | analyst/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0018](rulesets/adnd1e/escalations/decisions/DEC-2026-0018.yaml) | approved | How does a GUP produced directly from approved Architect Decisions enter the Builder and Reviewer queues when it intentionally has no GUR lineage? | builder/ready | [IMP-DEC-2026-0018-r15](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0018-r15.yaml): [REV-IMP-DEC-2026-0018-r15-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0018-r15-r01.yaml) approved |
| [DEC-2026-0019](rulesets/adnd1e/escalations/decisions/DEC-2026-0019.yaml) | approved | How must the DEC-2026-0015/0016 migration proceed when one label directive names the wrong endpoint field and 20 touched authored-polarity assertions retain bases that an Approved patch may not contain? | analyst/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0020](rulesets/adnd1e/escalations/decisions/DEC-2026-0020.yaml) | approved | Which fields define one production-edge assertion, and may tooling choose that identity when the constitution is silent? | builder/ready | [IMP-DEC-2026-0020-r06](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0020-r06.yaml): [REV-IMP-DEC-2026-0020-r06-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0020-r06-r01.yaml) approved |
| [DEC-2026-0021](rulesets/adnd1e/escalations/decisions/DEC-2026-0021.yaml) | approved | How does the DEC-2026-0015/0016 migration proceed when four required PHB polarity readings are complete but the repository contains no claimed Markdown packet or Markdown source for the sixteen required DMG and UA readings? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0022](rulesets/adnd1e/escalations/decisions/DEC-2026-0022.yaml) | approved | When an approved Architect Decision resolves an escalation and changes the responsible role or readiness, may the scanner continue reporting the immutable originating artifact's older handoff as ready work? | builder/ready | [IMP-DEC-2026-0022-r13](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0022-r13.yaml): [REV-IMP-DEC-2026-0022-r13-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0022-r13-r01.yaml) approved |
| [DEC-2026-0023](rulesets/adnd1e/escalations/decisions/DEC-2026-0023.yaml) | approved | What durable artifact consumes an approved Architect Decision when its ready Builder handoff changes schemas, documentation, tests, or tooling but requires no canonical decision-migration GUP? | builder/ready | [IMP-DEC-2026-0023-r15](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0023-r15.yaml): [REV-IMP-DEC-2026-0023-r15-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0023-r15-r01.yaml) approved |
| [DEC-2026-0024](rulesets/adnd1e/escalations/decisions/DEC-2026-0024.yaml) | approved | Should the PHB concept be registered as rule_mistletoe and canonical CSV row 1502 be migrated from the class_druid endpoint labelled "Druid Mistletoe", or does druidic mistletoe require a different identity or representation? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0025](rulesets/adnd1e/escalations/decisions/DEC-2026-0025.yaml) | approved | When the current PHB druid-spells packet directly names the spell "Call Woodland Beings," does its plural source identity control over the legacy canonical singular spell_call_woodland_being and the Review instruction to reuse that singular ID? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0026](rulesets/adnd1e/escalations/decisions/DEC-2026-0026.yaml) | approved | Does the canonical/default component identity directed by DEC-2026-0024 remain rule_mistletoe / Mistletoe, or must it be rule_greater_mistletoe / Greater Mistletoe given the PHB distinctions and the stated default? May the exact DEC-2026-0025 identity migration preserve neutral/unset polarity bases on legacy rows 2665 and 2666? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0027](rulesets/adnd1e/escalations/decisions/DEC-2026-0027.yaml) | approved | How is the ready Analyst handoff in REV-GUP-MIG-DEC-2026-0015-0016-r03-r01 retired after DEC-2026-0021 barred its remaining sixteen source readings, and who owns the absent DMG and UA source required to resume that work? | none/terminal | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0028](rulesets/adnd1e/escalations/decisions/DEC-2026-0028.yaml) | approved | How can an approved Decision's implementation report truthfully discharge an acceptance test that names a live queue artifact after that artifact has completed ordinary Approval and Integration, making the literal snapshot false solely because the pipeline succeeded? | builder/ready | [IMP-DEC-2026-0028-r09](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0028-r09.yaml): [REV-IMP-DEC-2026-0028-r09-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0028-r09-r01.yaml) approved |
| [DEC-2026-0029](rulesets/adnd1e/escalations/decisions/DEC-2026-0029.yaml) | approved | Does the one-to-four-word aspect cap and the prohibition on copied rule prose retroactively invalidate the legacy 13-field migrated canonical rows that predate Reviewer-governed source work, and how should the two candidate assertion-key collisions be handled? | builder/ready | [IMP-DEC-2026-0029-r03](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0029-r03.yaml): [REV-IMP-DEC-2026-0029-r03-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0029-r03-r01.yaml) approved |
| [DEC-2026-0030](rulesets/adnd1e/escalations/decisions/DEC-2026-0030.yaml) | approved | When the current claimed PHB packet directly names the item "Pipes of the Sewer," does that source identity govern over legacy item_pipes_sewers / "Pipes of the Sewers," and what exact migration is required? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0031](rulesets/adnd1e/escalations/decisions/DEC-2026-0031.yaml) | approved | How must the approved Pipes of the Sewer identity migration be expressed when DEC-2026-0030 uses operation keys the Builder's migration planner does not read, while published Decisions must remain immutable? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle; Supersedes DEC-2026-0030 |
| [DEC-2026-0032](rulesets/adnd1e/escalations/decisions/DEC-2026-0032.yaml) | approved | Which identity survives for each duplicated ability-adjustment mechanic, and how can two retired node IDs be merged into that identity without permitting the Builder to infer an unbounded canonical rewrite? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0033](rulesets/adnd1e/escalations/decisions/DEC-2026-0033.yaml) | approved | How are ordinary weapons represented without widening the magic-item namespace, and can a class identity distinguish a class-specific flat hit-point progression without carrying a prohibited magnitude? | builder/ready | [IMP-DEC-2026-0033-r01](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0033-r01.yaml): no matching leaf IMP Review found |
| [DEC-2026-0034](rulesets/adnd1e/escalations/decisions/DEC-2026-0034.yaml) | approved | How is the registry to record fresh packets supplied by the repository source steward when the only existing per-book source IDs truthfully describe legacy graph-dump provenance? | -/- | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0035](rulesets/adnd1e/escalations/decisions/DEC-2026-0035.yaml) | approved | What Approved-bundle operation model may authorize the Integrator to apply the already reviewed combined migration of one registry addition, two node identity replacements, five endpoint repoints, and one canonical-row removal when no edge CSV can represent the complete operation set? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0036](rulesets/adnd1e/escalations/decisions/DEC-2026-0036.yaml) | approved | How must DEC-2026-0032 be reissued after the integrated r05 migration shifted its physical canonical and registry locators, and which direct operation model may execute its already decided two-retired-IDs-to-one-new-ID merges? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle; Supersedes DEC-2026-0032 |
| [DEC-2026-0037](rulesets/adnd1e/escalations/decisions/DEC-2026-0037.yaml) | approved | Does the PHB Bards packet's secondary mention of Pipes of the Sewer control the identity of the DMG item's defining entry, and what canonical identity should replace the already integrated singular form? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle; Supersedes DEC-2026-0031 |
| [DEC-2026-0038](rulesets/adnd1e/escalations/decisions/DEC-2026-0038.yaml) | approved | How must the DEC-2026-0032 ability-merge lineage proceed after an unrelated registry insertion moved str_exceptional from its declared physical row while every identity and every closed canonical incident set remained exact? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle; Supersedes DEC-2026-0036 |
| [DEC-2026-0039](rulesets/adnd1e/escalations/decisions/DEC-2026-0039.yaml) | approved | How does the repository withdraw a GUR whose source scope is wholly superseded by a later packet, and who repairs a published active GUR whose attempted terminal handoff is schema-invalid and therefore mis-routed to Builder? | builder/ready | [IMP-DEC-2026-0039-r04](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0039-r04.yaml): [REV-IMP-DEC-2026-0039-r04-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0039-r04-r01.yaml) approved |
| [DEC-2026-0040](rulesets/adnd1e/escalations/decisions/DEC-2026-0040.yaml) | approved | How may a persistent role avoid repeatedly loading unchanged repository instructions while preserving fresh evidence review, mutable-state validation, and the repository-first stateless-agent model? | builder/ready | [IMP-DEC-2026-0040-r02](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0040-r02.yaml): [REV-IMP-DEC-2026-0040-r02-r03](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0040-r02-r03.yaml) approved |
| [DEC-2026-0041](rulesets/adnd1e/escalations/decisions/DEC-2026-0041.yaml) | approved | How can repository-wide envelope validation remain strict when a published, immutable predecessor has only invalid queue-handoff metadata and a fully valid successor has already repaired that metadata? | builder/ready | [IMP-DEC-2026-0041-r01](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0041-r01.yaml): [REV-IMP-DEC-2026-0041-r01-r03](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0041-r01-r03.yaml) approved |
| [DEC-2026-0042](rulesets/adnd1e/escalations/decisions/DEC-2026-0042.yaml) | approved | May a non-migration Decision Implementation Report be required to prove an artifact that a later role in the same Decision has not yet created? | builder/ready | [IMP-DEC-2026-0042-r01](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0042-r01.yaml): [REV-IMP-DEC-2026-0042-r01-r03](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0042-r01-r03.yaml) approved; Supersedes DEC-2026-0033 |
| [DEC-2026-0043](rulesets/adnd1e/escalations/decisions/DEC-2026-0043.yaml) | approved | How does an Integrator rejection of an otherwise approved bundle return exact, repairable work to the workflow instead of re-queuing the same rejected bundle indefinitely? | builder/ready | [IMP-DEC-2026-0043-r08](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0043-r08.yaml): [REV-IMP-DEC-2026-0043-r08-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0043-r08-r01.yaml) approved |
| [DEC-2026-0044](rulesets/adnd1e/escalations/decisions/DEC-2026-0044.yaml) | approved | What release path applies when DEC-2026-0038 requires a no-edge-CSV `decision_migration_v2` bundle but the installed Integrator recognizes only v1 bundles? | integrator/ready | [IMP-DEC-2026-0044-r03](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0044-r03.yaml): [REV-IMP-DEC-2026-0044-r03-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0044-r03-r01.yaml) approved |
| [DEC-2026-0045](rulesets/adnd1e/escalations/decisions/DEC-2026-0045.yaml) | approved | Who owns a file named by an Architect Decision's exact_diff when the Decision assigned it to no role, and how is that omission prevented before approval? | builder/ready | [IMP-DEC-2026-0045-r10](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0045-r10.yaml): [REV-IMP-DEC-2026-0045-r10-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0045-r10-r01.yaml) approved |
| [DEC-2026-0046](rulesets/adnd1e/escalations/decisions/DEC-2026-0046.yaml) | approved | Does later drift in a shared implementation file reopen a Decision after an exact Approved Decision Implementation Review has already consumed its report? | builder/ready | [IMP-DEC-2026-0046-r11](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0046-r11.yaml): [REV-IMP-DEC-2026-0046-r11-r02](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0046-r11-r02.yaml) approved |
| [DEC-2026-0047](rulesets/adnd1e/escalations/decisions/DEC-2026-0047.yaml) | approved | When an Approved bundle's only defect is an incomplete edge component, what is Builder's revision and which role publishes the corrected bundle? | reviewer/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0048](rulesets/adnd1e/escalations/decisions/DEC-2026-0048.yaml) | approved | How can an acceptance test prove a mutable contract's required content without becoming permanently false merely because a later approved Decision advances that contract's version? | builder/ready | [IMP-DEC-2026-0048-r04](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0048-r04.yaml): [REV-IMP-DEC-2026-0048-r04-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0048-r04-r01.yaml) approved |
| [DEC-2026-0049](rulesets/adnd1e/escalations/decisions/DEC-2026-0049.yaml) | approved | Which identity key governs duplicate rejection for AD&D 1e production assertions: the five-field Constitution 5.1 key or a three-field source/type/target shortcut? | none/terminal | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0050](rulesets/adnd1e/escalations/decisions/DEC-2026-0050.yaml) | approved | May source-supported ordinary work enlarge the DEC-2026-0014 legacy endpoint debt, and how must the already decided comeliness, fatigue, and training replacements plus the remaining blank endpoint labels be completed? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0051](rulesets/adnd1e/escalations/decisions/DEC-2026-0051.yaml) | approved | Is `approved_but_excluded_from_bundle` a legal per-edge Review disposition, and how must the active Illusionist Review lineage recover without rewriting immutable Reviews or causing Builder to infer a disposition? | builder/ready | [IMP-DEC-2026-0051-r01](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0051-r01.yaml): no matching leaf IMP Review found |
| [DEC-2026-0052](rulesets/adnd1e/escalations/decisions/DEC-2026-0052.yaml) | approved | How may the Review 1.1 direct implementation be independently approved when DEC-2026-0051 makes the later Reviewer r06 successor both an acceptance test and conditional on that prior approval? | builder/ready | [IMP-DEC-2026-0052-r03](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0052-r03.yaml): [REV-IMP-DEC-2026-0052-r03-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0052-r03-r01.yaml) approved; Supersedes DEC-2026-0051 |
| [DEC-2026-0053](rulesets/adnd1e/escalations/decisions/DEC-2026-0053.yaml) | approved | How must the repository record a consumed GUP that was overwritten in place, leaving its Review's published checksum unrecoverable, and how must Builder publication paths prevent recurrence? | builder/ready | [IMP-DEC-2026-0053-r03](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0053-r03.yaml): [REV-IMP-DEC-2026-0053-r03-r03](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0053-r03-r03.yaml) approved |
| [DEC-2026-0054](rulesets/adnd1e/escalations/decisions/DEC-2026-0054.yaml) | approved | When an active revision-required Review has a ready Builder handoff, does a later GUP revision consume that handoff merely by superseding the reviewed GUP, and should an already integrated approved bundle be rediscovered as Integrator work? | builder/ready | [IMP-DEC-2026-0054-r06](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0054-r06.yaml): [REV-IMP-DEC-2026-0054-r06-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0054-r06-r01.yaml) approved |
| [DEC-2026-0055](rulesets/adnd1e/escalations/decisions/DEC-2026-0055.yaml) | approved | How should queue derivation classify a stale decision-migration leaf when its Decision work was integrated through another lineage, or when a later Decision explicitly retires the leaf pending a separately governed source prerequisite? | builder/ready | [IMP-DEC-2026-0055-r03](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0055-r03.yaml): [REV-IMP-DEC-2026-0055-r03-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0055-r03-r01.yaml) approved |
| [DEC-2026-0056](rulesets/adnd1e/escalations/decisions/DEC-2026-0056.yaml) | approved | Should the eight historical Analyst handoffs that predate usable provenance.review_id remain ready work after their same-lineage corrections received a later independently approved Review? | builder/ready | [IMP-DEC-2026-0056-r03](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0056-r03.yaml): [REV-IMP-DEC-2026-0056-r03-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0056-r03-r01.yaml) approved |
| [DEC-2026-0057](rulesets/adnd1e/escalations/decisions/DEC-2026-0057.yaml) | approved | Once an exact Approved Decision Implementation Review has independently verified checksummed versioned-contract-content evidence, should a later contract version or content change reopen that completed Decision? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0058](rulesets/adnd1e/escalations/decisions/DEC-2026-0058.yaml) | approved | Does the intentionally invalid, superseded r02 GUR require another Analyst repair after DEC-2026-0039's valid r03 successor exists? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle; Supersedes DEC-2026-0057 |
| [DEC-2026-0059](rulesets/adnd1e/escalations/decisions/DEC-2026-0059.yaml) | approved | In what order must the three malformed implementation-Review lineages be repaired so the Builder can again produce passing implementation evidence? | builder/ready | [IMP-DEC-2026-0059-r02](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0059-r02.yaml): [REV-IMP-DEC-2026-0059-r02-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0059-r02-r01.yaml) approved; Supersedes DEC-2026-0058 |
| [DEC-2026-0060](rulesets/adnd1e/escalations/decisions/DEC-2026-0060.yaml) | approved | How must current-state validation distinguish immutable historical artifacts from current canonical state, and how must queue derivation represent the one already-ratified r02 handoff-only GUR exemption? | builder/ready | [IMP-DEC-2026-0060-r01](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0060-r01.yaml): [REV-IMP-DEC-2026-0060-r01-r02](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0060-r01-r02.yaml) approved |
| [DEC-2026-0061](rulesets/adnd1e/escalations/decisions/DEC-2026-0061.yaml) | approved | How must immutable Decision Implementation Report evidence recognize standard unittest success output, and may a schema-invalid Decision Implementation Review consume a Decision in queue derivation? | builder/ready | [IMP-DEC-2026-0061-r01](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0061-r01.yaml): [REV-IMP-DEC-2026-0061-r01-r02](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0061-r01-r02.yaml) approved |
| [DEC-2026-0062](rulesets/adnd1e/escalations/decisions/DEC-2026-0062.yaml) | approved | Which key is normative for a Reviewer row correction, what must the compiler do when an `approved_with_revision` row carries a correction it cannot read, and how are already-integrated rows whose corrections never applied reconciled? | builder/ready | [IMP-DEC-2026-0062-r01](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0062-r01.yaml): [REV-IMP-DEC-2026-0062-r01-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0062-r01-r01.yaml) approved |
| [DEC-2026-0063](rulesets/adnd1e/escalations/decisions/DEC-2026-0063.yaml) | approved | Which artifact records the outcome of an Integrator-assigned check that is neither an integration nor a rejection, and does a passing result discharge the Integrator handoff on its own, or must the Reviewer publish approving successors first? | builder/ready | [IMP-DEC-2026-0063-r01](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0063-r01.yaml): [REV-IMP-DEC-2026-0063-r01-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0063-r01-r01.yaml) approved |
| [DEC-2026-0064](rulesets/adnd1e/escalations/decisions/DEC-2026-0064.yaml) | approved | How may queue derivation reach a schema-valid active Druid Review when its immutable immediate ancestry crosses one YAML-unreadable historical Review? | builder/ready | [IMP-DEC-2026-0064-r01](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0064-r01.yaml): [REV-IMP-DEC-2026-0064-r01-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0064-r01-r01.yaml) approved |
| [DEC-2026-0065](rulesets/adnd1e/escalations/decisions/DEC-2026-0065.yaml) | approved | How must Integrator queue traversal handle the exact immutable unreadable Druid Review bridge already authorized by DEC-2026-0064, while remaining fail-closed for every unrecognized malformed artifact? | integrator/ready | [IMP-DEC-2026-0065-r05](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0065-r05.yaml): [REV-IMP-DEC-2026-0065-r05-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0065-r05-r01.yaml) approved |
| [DEC-2026-0066](rulesets/adnd1e/escalations/decisions/DEC-2026-0066.yaml) | returned_incomplete | May Architect decide an escalation package that cannot itself be parsed as YAML? | reviewer/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0067](rulesets/adnd1e/escalations/decisions/DEC-2026-0067.yaml) | approved | What immutable lineage permits the Bards packaging correction to continue when its direct r02 Review is YAML-unreadable, while preserving all reviewed assertions and source decisions? | reviewer/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0068](rulesets/adnd1e/escalations/decisions/DEC-2026-0068.yaml) | approved | May the checksummed Bards r03 Review and r03 Approved bundle be routed after their direct r02 predecessor remains permanently YAML-unreadable? | builder/ready | [IMP-DEC-2026-0068-r03](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0068-r03.yaml): [REV-IMP-DEC-2026-0068-r03-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0068-r03-r01.yaml) approved |
| [DEC-2026-0069](rulesets/adnd1e/escalations/decisions/DEC-2026-0069.yaml) | approved | How must Integrator admit only the checksummed Bards r03 bundle when its r02 Review is immutable unreadable direct-predecessor history? | integrator/ready | [IMP-DEC-2026-0069-r02](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0069-r02.yaml): no matching leaf IMP Review found |
| [DEC-2026-0070](rulesets/adnd1e/escalations/decisions/DEC-2026-0070.yaml) | approved | How must Integrator discover the Bards r03 bundle's declared shared edge component while preventing the same discovery rule from offering the unreadable r02 predecessor bundle? | integrator/ready | [IMP-DEC-2026-0070-r02](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0070-r02.yaml): [REV-IMP-DEC-2026-0070-r02-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0070-r02-r01.yaml) approved; Supersedes DEC-2026-0069 |
| [DEC-2026-0071](rulesets/adnd1e/escalations/decisions/DEC-2026-0071.yaml) | approved | May Bards r03 receive one ordinary Review and Approved-bundle successor that restores its omitted node-registration decisions and Integrator handoff without invalidating the exact r02 unreadable-predecessor repair? | reviewer/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0072](rulesets/adnd1e/escalations/decisions/DEC-2026-0072.yaml) | approved | How is the immutable, unreadable DEC-2026-0065 r01 implementation Review handled, and how must the repository prevent free-text YAML serialization defects from reaching durable publication? | builder/ready | [IMP-DEC-2026-0072-r05](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0072-r05.yaml): [REV-IMP-DEC-2026-0072-r05-r02](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0072-r05-r02.yaml) approved |
| [DEC-2026-0073](rulesets/adnd1e/escalations/decisions/DEC-2026-0073.yaml) | approved | Can the immutable Bards r03 Review's checksummed integration_rejection_input record consume INT-20260827-001 for queue derivation after the single r04 successor authorized by DEC-2026-0071, or must Reviewer publish a further successor solely to use a scanner-recognized field name? | builder/ready | [IMP-DEC-2026-0073-r01](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0073-r01.yaml): [REV-IMP-DEC-2026-0073-r01-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0073-r01-r01.yaml) approved |
| [DEC-2026-0074](rulesets/adnd1e/escalations/decisions/DEC-2026-0074.yaml) | approved | Must Decision handoff replacement stop emitting a Decision job once an Approved Decision Implementation Review has consumed that Decision, just as the ordinary direct-Decision queue rule already does? | builder/ready | [IMP-DEC-2026-0074-r02](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0074-r02.yaml): [REV-IMP-DEC-2026-0074-r02-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0074-r02-r01.yaml) approved |
| [DEC-2026-0075](rulesets/adnd1e/escalations/decisions/DEC-2026-0075.yaml) | approved | Is the disclosed Bards fixture repair a sufficient durable record for an Integrator-owned test-only correction, and what standing guard must prevent a fixture from passing only because it assumes a transient corpus state? | integrator/ready | [IMP-DEC-2026-0075-r02](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0075-r02.yaml): [REV-IMP-DEC-2026-0075-r02-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0075-r02-r01.yaml) approved |
| [DEC-2026-0076](rulesets/adnd1e/escalations/decisions/DEC-2026-0076.yaml) | approved | Does DMG 64's giant-humanoid subject warrant the broad monster_giant identity, or must the packet reuse generic monster_special and encode the distinction only in a row-level field? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0077](rulesets/adnd1e/escalations/decisions/DEC-2026-0077.yaml) | approved | Must the authorized monster_giant registry addition be stated under the direct-v1 planner's top-level new_nodes_authorized field, or may Builder infer an alternate node-addition location? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle; Supersedes DEC-2026-0076 |
| [DEC-2026-0078](rulesets/adnd1e/escalations/decisions/DEC-2026-0078.yaml) | approved | Does DEC-2026-0075's live-corpus invariant requirement authorize the disclosed test-only rewind guard, or must each such guard have a separate Decision Implementation Report and independent Review? | none/terminal | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0079](rulesets/adnd1e/escalations/decisions/DEC-2026-0079.yaml) | approved | Where is a confirmed no-graph-content printed page recorded when it falls outside every immutable claimed packet span? | none/terminal | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0081](rulesets/adnd1e/escalations/decisions/DEC-2026-0081.yaml) | approved | How does Dispatcher obtain exactly its bounded routing authority context without common-pattern inheritance or invented ruleset identifiers, and how is its verifier activated without changing the five existing roles? | builder/ready | [IMP-DEC-2026-0081-r01](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0081-r01.yaml): no matching leaf IMP Review found |
| [DEC-2026-0082](rulesets/adnd1e/escalations/decisions/DEC-2026-0082.yaml) | approved | How is the unactivated Dispatcher implementation retired without rewriting history, while five workers take responsibility for direct, serial handoffs? | builder/ready | [IMP-DEC-2026-0082-r03](rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0082-r03.yaml): [REV-IMP-DEC-2026-0082-r03-r01](rulesets/adnd1e/decision-implementation-reviews/REV-IMP-DEC-2026-0082-r03-r01.yaml) approved; Supersedes DEC-2026-0081 |



### basicdnd

| Decision | Disposition | Question / scope | Authored handoff (not live assignment) | Implementation evidence |
| --- | --- | --- | --- | --- |
| [DEC-2026-0080](rulesets/basicdnd/escalations/decisions/DEC-2026-0080.yaml) | approved | What minimum independent governance and tooling must exist before Basic D&D Rules Cyclopedia packets are claimed, and how does the repository admit the steward's Pandoc frontmatter and full-page-artwork page classification? | builder/ready | [IMP-DEC-2026-0080-r04](rulesets/basicdnd/decision-implementations/IMP-DEC-2026-0080-r04.yaml): [REV-IMP-DEC-2026-0080-r04-r01](rulesets/basicdnd/decision-implementation-reviews/REV-IMP-DEC-2026-0080-r04-r01.yaml) approved |
| [DEC-2026-0085](rulesets/basicdnd/escalations/decisions/DEC-2026-0085.yaml) | approved | What remains of DEC-2026-0080 when its two unclaimed Rules Cyclopedia source inputs have been withdrawn, and may the tooling implementation be reviewed without recreating those inputs? | none/terminal | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0086](rulesets/basicdnd/escalations/decisions/DEC-2026-0086.yaml) | approved | How is the owner's explicit RC stop applied despite existing incoming and claimed packets? | none/terminal | No direct IMP leaf; inspect Decision-specific lifecycle |



### shadowdark

| Decision | Disposition | Question / scope | Authored handoff (not live assignment) | Implementation evidence |
| --- | --- | --- | --- | --- |
| [DEC-2026-0083](rulesets/shadowdark/escalations/decisions/DEC-2026-0083.yaml) | approved | How should Shadowdark and its six books enter this repository without inheriting another system's data, guessing editions, or bypassing ownership? | none/terminal | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0084](rulesets/shadowdark/escalations/decisions/DEC-2026-0084.yaml) | approved | Admit page-intentionally-ignored and blank-page as closed, steward-authored page classifications without making metadata into graph content or hiding source coverage, and without invalidating an in-progress implementation Review. | builder/ready | [IMP-DEC-2026-0084-r01](rulesets/shadowdark/decision-implementations/IMP-DEC-2026-0084-r01.yaml): [REV-IMP-DEC-2026-0084-r01-r01](rulesets/shadowdark/decision-implementation-reviews/REV-IMP-DEC-2026-0084-r01-r01.yaml) approved |
| [DEC-2026-0087](rulesets/shadowdark/escalations/decisions/DEC-2026-0087.yaml) | approved | How are Shadowdark's six source-defined playable ancestries and their named benefits identified without conflating ancestry, class, subsystem or creature? | builder/ready | [IMP-DEC-2026-0087-r02](rulesets/shadowdark/decision-implementations/IMP-DEC-2026-0087-r02.yaml): [REV-IMP-DEC-2026-0087-r02-r01](rulesets/shadowdark/decision-implementation-reviews/REV-IMP-DEC-2026-0087-r02-r01.yaml) approved |
| [DEC-2026-0088](rulesets/shadowdark/escalations/decisions/DEC-2026-0088.yaml) | approved | When a direct Herdr handoff is demonstrably delivered but its recipient is still working, what ends the relay's transport lifecycle without weakening single-agent execution, and how are busy-peer deferral and genuine uncertainty recovered without editing local relay state by hand? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0089](rulesets/shadowdark/escalations/decisions/DEC-2026-0089.yaml) | approved | How should the repository notify roles of ready work without turning delivery observation into a second workflow engine or preventing independent roles from progressing concurrently? | none/terminal | No direct IMP leaf; inspect Decision-specific lifecycle; Supersedes DEC-2026-0088 |
| [DEC-2026-0090](rulesets/shadowdark/escalations/decisions/DEC-2026-0090.yaml) | approved | How must the Builder validate a previously published Shadowdark GUR that declares Constitution 1.1 after the ruleset has advanced to 1.2? | builder/ready | [IMP-DEC-2026-0090-r01](rulesets/shadowdark/decision-implementations/IMP-DEC-2026-0090-r01.yaml): [REV-IMP-DEC-2026-0090-r01-r01](rulesets/shadowdark/decision-implementation-reviews/REV-IMP-DEC-2026-0090-r01-r01.yaml) approved |
| [DEC-2026-0091](rulesets/shadowdark/escalations/decisions/DEC-2026-0091.yaml) | approved | Which GUR candidate-node fields and Review per-row decision forms are executable repository inputs, and how are the observed Shadowdark artifacts corrected without silently aliasing or rewriting published history? | builder/ready | [IMP-DEC-2026-0091-r01](rulesets/shadowdark/decision-implementations/IMP-DEC-2026-0091-r01.yaml): [REV-IMP-DEC-2026-0091-r01-r02](rulesets/shadowdark/decision-implementation-reviews/REV-IMP-DEC-2026-0091-r01-r02.yaml) approved |
| [DEC-2026-0092](rulesets/shadowdark/escalations/decisions/DEC-2026-0092.yaml) | approved | Who implements and independently verifies new-ruleset canonical initialization support, and what must a first Shadowdark transaction prove before it may create canonical state? | integrator/ready | [IMP-DEC-2026-0092-r01](rulesets/shadowdark/decision-implementations/IMP-DEC-2026-0092-r01.yaml): [REV-IMP-DEC-2026-0092-r01-r01](rulesets/shadowdark/decision-implementation-reviews/REV-IMP-DEC-2026-0092-r01-r01.yaml) approved |
| [DEC-2026-0093](rulesets/shadowdark/escalations/decisions/DEC-2026-0093.yaml) | approved | Which individual alignment and deity identities may the Shadowdark graph represent, and how are the source-named collective groupings and the explicitly unnamed Lost handled? | architect/blocked | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0094](rulesets/shadowdark/escalations/decisions/DEC-2026-0094.yaml) | approved | How must queue derivation treat the stale Stats Approved manifests after their resolved successor was integrated, and which manifest fields control Review linkage and active-leaf selection? | builder/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0095](rulesets/shadowdark/escalations/decisions/DEC-2026-0095.yaml) | approved | What must queue derivation treat as authoritative for an Approved bundle's Review, active leaf, and integration consumption, including the legacy Stats lineage with incomplete manifest revision metadata? | builder/ready | [IMP-DEC-2026-0095-r03](rulesets/shadowdark/decision-implementations/IMP-DEC-2026-0095-r03.yaml): [REV-IMP-DEC-2026-0095-r03-r01](rulesets/shadowdark/decision-implementation-reviews/REV-IMP-DEC-2026-0095-r03-r01.yaml) approved |
| [DEC-2026-0096](rulesets/shadowdark/escalations/decisions/DEC-2026-0096.yaml) | approved | Must Integrator bundle discovery apply the existing bounded legacy rNN leaf-resolution rule to manifested Approved bundles that lack complete revision metadata, and who owns that implementation? | integrator/ready | [IMP-DEC-2026-0096-r01](rulesets/shadowdark/decision-implementations/IMP-DEC-2026-0096-r01.yaml): [REV-IMP-DEC-2026-0096-r01-r01](rulesets/shadowdark/decision-implementation-reviews/REV-IMP-DEC-2026-0096-r01-r01.yaml) approved |
| [DEC-2026-0097](rulesets/shadowdark/escalations/decisions/DEC-2026-0097.yaml) | approved | How must Shadowdark compiler tests retain coverage of both an approved fresh ancestry proposal and a subsequently registered canonical ancestry without making the Builder suite depend on the mutable live registry baseline? | builder/ready | [IMP-DEC-2026-0097-r01](rulesets/shadowdark/decision-implementations/IMP-DEC-2026-0097-r01.yaml): [REV-IMP-DEC-2026-0097-r01-r01](rulesets/shadowdark/decision-implementation-reviews/REV-IMP-DEC-2026-0097-r01-r01.yaml) approved |
| [DEC-2026-0098](rulesets/shadowdark/escalations/decisions/DEC-2026-0098.yaml) | approved | Which source-defined language identities and language-table distinctions may the Shadowdark graph represent from the defining languages packet? | analyst/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0099](rulesets/shadowdark/escalations/decisions/DEC-2026-0099.yaml) | approved | How is the already-replaced DEC-2026-0094 Builder handoff retired without a duplicate implementation report or any Stats artifact repair? | none/terminal | No direct IMP leaf; inspect Decision-specific lifecycle; Supersedes DEC-2026-0094 |
| [DEC-2026-0100](rulesets/shadowdark/escalations/decisions/DEC-2026-0100.yaml) | approved | Which constitution versions may an immutable incoming Shadowdark GUR declare, and how is that compatibility governed without repeatedly transcribing it into Builder code? | builder/ready | [IMP-DEC-2026-0100-r01](rulesets/shadowdark/decision-implementations/IMP-DEC-2026-0100-r01.yaml): no matching leaf IMP Review found |
| [DEC-2026-0101](rulesets/shadowdark/escalations/decisions/DEC-2026-0101.yaml) | approved | How is DEC-2026-0100's stale Decision-input evidence corrected without rewriting immutable history or repeating unchanged Builder implementation? | builder/ready | [IMP-DEC-2026-0101-r01](rulesets/shadowdark/decision-implementations/IMP-DEC-2026-0101-r01.yaml): [REV-IMP-DEC-2026-0101-r01-r01](rulesets/shadowdark/decision-implementation-reviews/REV-IMP-DEC-2026-0101-r01-r01.yaml) approved; Supersedes DEC-2026-0100 |
| [DEC-2026-0102](rulesets/shadowdark/escalations/decisions/DEC-2026-0102.yaml) | approved | What is the mandatory outbound Herdr interface for the five repository roles? | none/terminal | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0103](rulesets/shadowdark/escalations/decisions/DEC-2026-0103.yaml) | approved | Which source-declared category facts are graph relationships, and how are mechanically operative spell casting class and spell tier represented without converting the impact graph into a general taxonomy? | builder/ready | [IMP-DEC-2026-0103-r01](rulesets/shadowdark/decision-implementations/IMP-DEC-2026-0103-r01.yaml): [REV-IMP-DEC-2026-0103-r01-r01](rulesets/shadowdark/decision-implementation-reviews/REV-IMP-DEC-2026-0103-r01-r01.yaml) approved |
| [DEC-2026-0104](rulesets/shadowdark/escalations/decisions/DEC-2026-0104.yaml) | approved | May a source-explicit item be represented as a mechanically operative Light Source without widening Shadowdark CLASSIFIED_AS into general item taxonomy? | builder/ready | [IMP-DEC-2026-0104-r01](rulesets/shadowdark/decision-implementations/IMP-DEC-2026-0104-r01.yaml): [REV-IMP-DEC-2026-0104-r01-r01](rulesets/shadowdark/decision-implementation-reviews/REV-IMP-DEC-2026-0104-r01-r01.yaml) approved |
| [DEC-2026-0105](rulesets/shadowdark/escalations/decisions/DEC-2026-0105.yaml) | approved | How does Shadowdark represent the shared monster-level mechanic without conflating it with character advancement or converting per-creature stat-block values into graph data; and how must queue tooling route an active blocked GUR? | builder/ready | [IMP-DEC-2026-0105-r02](rulesets/shadowdark/decision-implementations/IMP-DEC-2026-0105-r02.yaml): [REV-IMP-DEC-2026-0105-r02-r01](rulesets/shadowdark/decision-implementation-reviews/REV-IMP-DEC-2026-0105-r02-r01.yaml) approved |
| [DEC-2026-0106](rulesets/shadowdark/escalations/decisions/DEC-2026-0106.yaml) | approved | May the Shadowdark production edge schema admit the already authorized `mstat_` prefix in both endpoint positions so the Monster Attributes GUP can proceed through its ordinary Review and integration lifecycle? | reviewer/ready | No direct IMP leaf; inspect Decision-specific lifecycle |
| [DEC-2026-0107](rulesets/shadowdark/escalations/decisions/DEC-2026-0107.yaml) | approved | How should the scanner resolve an explicit packet-update Review supersedes link when the successor reviews a later GUP revision than its predecessor, while keeping unrelated Review roots and migration Reviews independent? | builder/ready | [IMP-DEC-2026-0107-r03](rulesets/shadowdark/decision-implementations/IMP-DEC-2026-0107-r03.yaml): [REV-IMP-DEC-2026-0107-r03-r01](rulesets/shadowdark/decision-implementation-reviews/REV-IMP-DEC-2026-0107-r03-r01.yaml) approved |



### Escalation Store State

| State | Files |
| --- | --- |
| decided | 90 |
| returned | 2 |



Pending count is zero. Two returned files remain as history; retained returned files do not prove a still-open task. One is deliberately unreadable historical YAML. No repair was attempted and the common scanner reported no lineage errors. Recheck governing successor/exception Decisions before any action on them.

| Returned artifact | Observed condition |
| --- | --- |
| [ESC-2026-07-30T15.16.18.973Z](rulesets/adnd1e/escalations/returned/ESC-2026-07-30T15.16.18.973Z.yaml) | Twenty-seven of the 183 canonical spell_ nodes carry a label that contradicts their own ID, and several are aggregates wearing a specific spell's ID. Constitution 3.1 says labels do not determine identity and IDs do. Applied literally that makes spell_cure_light_wounds the Cure Light Wounds spell, but its label reads "Curative Spells" and its existing edges were presumably written against that broader meaning. Which reading governs, and what should an Analyst attach a specific spell's mechanics to? |
| [ESC-2026-08-28T00.41.24.104Z](rulesets/adnd1e/escalations/returned/ESC-2026-08-28T00.41.24.104Z.yaml) | Unparseable historical YAML; preserved |



## 12. Snapshot Integrity, Diagnostics And Audit Results

### Runtime Observed

| Component | Observed version |
| --- | --- |
| Python | 3.14.6 |
| PowerShell | 7.6.6 |
| Pandoc | 3.10 |
| PyYAML | 6.0.3 |
| jsonschema | 4.26.0 |
| referencing | 0.37.0 |



### Common Scanner Diagnostic Classes

| Severity | Code | Count |
| --- | --- | --- |
| info | gur_handoff_historical_exemption | 1 |
| info | implementation_files_drifted_after_approval | 46 |
| info | implementation_review_unreadable_predecessor_repaired | 1 |
| info | integration_rejection_remediation_recognised | 1 |
| info | legacy_revision_inference | 1 |
| info | migration_lineage_retired | 2 |
| info | review_contract_content_drifted_after_approval | 18 |
| info | review_handoff_retired | 8 |
| info | review_malformed_lineage_repaired | 1 |
| info | review_unreadable_direct_predecessor_repaired | 1 |
| warning | approved_review_inferred_or_missing | 1 |
| warning | legacy_migration_spelling | 1 |
| warning | legacy_revision_inference | 4 |



Post-approval implementation/contract drift notices are intentionally governed historical evidence, not automatic instructions to reissue every approved report. Keep exact exception/retirement records; do not suppress diagnostics by deleting artifacts.

### Integrator Queue Diagnostics

- APPROVED-GUP-PKT-SD-018-019-fighter-class-r02-r01: declared edges component 'books/shadowdark/sd/artifacts/approved/APPROVED-GUP-PKT-SD-018-019-fighter-class-r02-r01.edges.csv' records sha256:232678289ab54c9f5fdd4d3671895d3672b3f04eb52c1b640940055d9787fa4c but hashes to sha256:987a13b521864563fac0a1935d370149c43af9a0ee705204c1847db9cb3cdecc

- APPROVED-GUP-PKT-SD-020-021-priest-class-r02-r01: declared edges component 'books/shadowdark/sd/artifacts/approved/APPROVED-GUP-PKT-SD-020-021-priest-class-r02-r01.edges.csv' records sha256:e3e5404f90540f2a6cdc4a7ed09c0f1b78b9b0c16725a49eb358180bec9cd85c but hashes to sha256:89ca9b0a43c3187c4653e9931b00f9608d1380520d0e24defede109d7222c166

- APPROVED-GUP-PKT-SD-022-023-thief-class-r03-r01: declared edges component 'books/shadowdark/sd/artifacts/approved/APPROVED-GUP-PKT-SD-022-023-thief-class-r03-r01.edges.csv' records sha256:60b5b7b1bc4a416ca3d54549b0ea2ea152e9a4afecb7650c00a7d1f4ad6acc2c but hashes to sha256:49a23c80bc78700e41779c33563754a6dcc2da506b07b9276b0a2799fdd5ca3c

- APPROVED-GUP-PKT-SD-032-032-languages-r01-r01: declared edges component 'books/shadowdark/sd/artifacts/approved/APPROVED-GUP-PKT-SD-032-032-languages-r01-r01.edges.csv' records sha256:0fa94297f85977bb52d120ca01bcd42822b247b77241c1aded19de48c6227f8c but hashes to sha256:5885440b3d1357e8d011f5d79f1db71321ac992e1ce32a62ac4895ede08775a3

- APPROVED-GUP-PKT-SD-038-038-character-names-r01-r01: declared edges component 'books/shadowdark/sd/artifacts/approved/APPROVED-GUP-PKT-SD-038-038-character-names-r01-r01.edges.csv' records sha256:0fa94297f85977bb52d120ca01bcd42822b247b77241c1aded19de48c6227f8c but hashes to sha256:5885440b3d1357e8d011f5d79f1db71321ac992e1ce32a62ac4895ede08775a3

- APPROVED-GUP-PKT-SD-322-325-community-credits-and-licensing-r01-r01: manifest declares 0 components of kind 'edges'; a packet update declares exactly one

The five checksum mismatches were also tested against LF-normalized bytes and still did not match. This audit does not establish when or why they diverged. These diagnostics require provenance investigation before reusing those exact inputs; a zero-finding current graph does not validate every historical component. No repair, deletion or re-integration is authorized by this report.

### Transfer-Sensitive Working Tree

At the captured snapshot, git status listed **106** changed/untracked entries (Git may aggregate untracked directories). This count excludes ignored local/work scripts. The existing modified tracked paths were:

- ` M contracts/WORK_QUEUES.md`

- ` M rulesets/shadowdark/registries/nodes.csv`

- ` M tooling/common/scan_agent_queues.py`

- ` M tooling/common/tests/test_scan_agent_queues.py`

Untracked entries include recent packet artifacts, integrations/reports and Decision implementation evidence; their status as untracked does not make them unpublished or disposable. A fresh clone at HEAD is not this working tree. Full machine-readable status was retained at `.local/handoff-audit/state.json` without changing it.

### Inventory Coverage Checks

- 102 distinct pre-existing script paths inventoried, with specific purpose, role/user, status and checksum for each.

- Extension/shebang sweep included hidden and ignored project paths. No installed dependency scripts or .git hooks were treated as project work.

- SD intake reconciled as 91 claimed/integrated + 53 unclaimed = 144 incoming files; no claim is inferred from filename similarity.

- All 91 claimed SD source files were compared with their named incoming files after CRLF-to-LF normalization: 91 matches, no missing source files. This confirms the filename-based intake reconciliation without asserting raw-byte equality across line endings.

- All 481 Markdown evidence links resolved locally, and all 102 pre-existing script hashes remained unchanged between inventory and report generation.

- Read-only common queue scan and both populated-ruleset canonical validators were run. Integrator SD queue was independently inspected; no integration command was run.

- No complete regression suite was rerun. Historical emitters/relay scripts were not executed. No source packet was claimed, no published artifact rewritten, no graph edited, and no Herdr prompt sent.

- Audit outputs live in `.local/handoff-audit/`; the deliverable is the root Markdown report. Those outputs are snapshot evidence, not new workflow authority.

### Verify After Transfer

Check authoritative file bytes against their existing artifact checksums, then re-run the read-only commands in section 5 with correct ruleset/book scope. Compare counts to this dated snapshot only if no later work has occurred. Preserve local cache files as history if desired, but always start a new actor-session receipt. Gemini may then propose transport changes separately without reopening completed packet lineages.
