# Herdr Notifications

**Version 2.4.** Authorities: DEC-2026-0082, DEC-2026-0089, DEC-2026-0102.

## Purpose

Herdr is a best-effort notification channel. It tells a named role that work
may be ready; it does not assign authority, reserve work, record provenance,
or prove delivery, completion, review, or integration.

There is no Dispatcher. The five roles communicate directly. A missed prompt
is remedied by another direct prompt or by the user, never by modifying graph
artifacts or maintaining a second workflow system.

## Normal Packet Relay

Normal packet-update work is a single repository-wide relay, not a pool of
independently executable queue entries:

```text
Analyst -> Builder -> Reviewer -> Integrator -> Analyst
```

The Analyst selects exactly one ready packet when no packet is active. If more
than one candidate is listed, select the lexically smallest `packet_id`; all
other candidates remain discovered but are not executable. The Analyst may not
start a second packet until Integrator has successfully integrated the active
packet and sends Analyst a direct `Send-HerdrPrompt.ps1` notification to select
the next one. Publishing the Integration record alone is incomplete relay work.

Forward routing is exact: Analyst sends a ready GUR only to Builder; Builder
sends a ready GUP only to Reviewer; Reviewer sends an Approved bundle only to
Integrator; and Integrator must send a successful terminal integration only to
Analyst, explicitly directing Analyst to select the next packet. A role never
skips a stage or sends ordinary packet work to a later role.

Corrections travel only backward within the same packet lineage:

```text
Integrator -> Reviewer -> Builder -> Analyst
```

An Integrator rejection goes only to Reviewer. A Reviewer correction goes only
to Builder. When Builder cannot make the required correction without a revised
source interpretation, identity, or GUR, Builder returns the exact correction
to Analyst. A corrected artifact re-enters at its normal forward stage. Do not
start a different packet while this repair loop is active.

Any role may raise an Architect escalation. The escalating role publishes the
ESC, addresses its current artifact handoff to Architect as blocked where an
artifact exists, sends only the escalation notification, and does not forward
the packet. The entire normal packet relay pauses until Architect publishes a
ruling and directly returns control to that escalation's originating role. If
the Decision separately names an immediate implementation owner, Architect may
also notify that owner; the originating role remains responsible for rechecking
the ruling and resuming its packet stage only after its prerequisites are met.

This relay gate applies to normal `packet_update` work. Decision implementation
artifacts retain their explicit Decision sequences, but must not cause Analyst
to begin a second normal packet. Roles still respect artifact ownership,
immutable publication, active-leaf verification, current-input checksums,
approval gates, and normal revision lineage.

At completion, a role publishes and validates its own artifacts, then reports a
numbered priority list containing the one permitted relay action: next owner,
exact ID or path, prerequisite, readiness, and reason. Directly notify that
owner using `tooling/common/Send-HerdrPrompt.ps1`. Do not wait for a recipient,
infer that it acted, or make a prompt conditional on another role being idle.

A Herdr message never changes `handoff.next_role`, consumes an artifact, or
permits edits outside the recipient's authority. A receiver whose queue shows
no executable relay item reports that fact and stops; it does not manufacture
an input or begin a second packet.

## Timestamps

Every outbound Herdr notification and every role final or status message must
begin with `Local time: YYYY-MM-DD HH:mm:ss +/-HH:mm`, generated from the
sender's local system clock immediately before sending. In PowerShell 7, use
`Get-Date -Format 'yyyy-MM-dd HH:mm:ss K'`. The timestamp is message context
only; it is not artifact provenance, delivery evidence, work authority, or a
substitute for checking current repository state.

## Direct Notification

Use PowerShell 7 and `tooling/common/Send-HerdrPrompt.ps1` for every outbound
notification. Do not call `herdr agent prompt` directly. The wrapper discovers
current live names, verifies the target role's expected provider and repository,
and prefixes the timestamp and repository context. If a named role is absent,
ambiguous, attached to another repository, or uses the wrong provider, it stops
without prompting; report that exact condition and do not guess, create, or
rename an agent.

```powershell
.\tooling\common\Send-HerdrPrompt.ps1 -List
.\tooling\common\Send-HerdrPrompt.ps1 -Role Builder -Message `
  'Ready work: <path>. Run your bounded queue check.'
```

Messages are concise and bounded: repository path, exact artifact ID/path,
requested action, required prerequisite, and any pause or scope restriction.
Point to artifacts instead of pasting packets or conversation history. For a
normal packet, notify only its permitted next relay role. Architect may also
notify an immediate Decision implementation owner while returning control to an
escalation originator. Do not use `--wait`, a background relay, an operational
lock, a request record, delivery observation, settlement state, automatic retry,
or `.local/herdr` state to coordinate work.

The retired `tooling/common/send-agent-handoff.ps1`, its tests, and existing
`.local/herdr` records are historical only. Do not delete, repair, run, or
reconcile them as part of normal repository work.

## Reading Limits

Notifications do not replace scoped startup. Each receiver runs its ordinary
role-context verification and reads the current task inputs identified by its
own instructions. Do not scan a corpus, all queues, source books, graph data,
or other-role conversations merely because a prompt arrived.

Missing source remains a source-steward/user matter. A governance question uses
the ordinary Architect escalation path. Neither condition authorizes another
role to invent source text or a graph conclusion.

## Version History

- **2.4 - 2026-09-26:** Made the Integrator-to-Analyst next-packet notification
  a required completion action after every successful terminal integration.

- **2.3 - 2026-09-26:** Replaced concurrent normal packet work with the
  single Analyst -> Builder -> Reviewer -> Integrator -> Analyst relay;
  defined the backward correction path and escalation pause/return behavior.

- **2.2 - 2026-09-23:** DEC-2026-0102 made
  `tooling/common/Send-HerdrPrompt.ps1` the mandatory direct-notification
  interface for every role; the wrapper centralizes live-role, provider,
  repository, and timestamp checks.

- **2.1 - 2026-09-22:** Required local offset-bearing timestamps on every
  Herdr notification and role final or status message.
- **2.0 - 2026-09-22:** DEC-2026-0089 retired serialized relay operations and
  permitted concurrent independent role work. Herdr became notification-only.
- **1.1 - 2026-09-22:** Historical serialized relay contract, superseded by 2.0.
- **1.0 - 2026-09-21:** Historical direct-handoff bootstrap, superseded by 2.0.
