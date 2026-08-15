# File Naming and State

**Version 1.5.**

Use stable identifiers rather than chat titles.

```text
Packet:       PKT-<BOOK>-<START>-<END>-<slug>
GUR:          GUR-<packet-id>-rNN
GUP:          GUP-<packet-id>-rNN
Review:       REV-<gup-id>-rNN
Approved:     APPROVED-<gup-id>-rNN
Escalation:   ESC-YYYY-MM-DDTHH.mm.ss.fffZ
Decision:     DEC-YYYY-NNNN
Implementation: IMP-<decision-id>-rNN
Implementation Review: REV-<implementation-id>-rNN
Integration:  INT-YYYYMMDD-NNN
```

Examples:

```text
PKT-DMG-070-071-helpless-targets/
GUR-PKT-DMG-070-071-helpless-targets-r01.yaml
GUP-PKT-DMG-070-071-helpless-targets-r01.yaml
REV-GUP-PKT-DMG-070-071-helpless-targets-r01-r01.yaml
APPROVED-GUP-PKT-DMG-070-071-helpless-targets-r01-r01.yaml
APPROVED-GUP-PKT-DMG-070-071-helpless-targets-r01-r01.edges.csv
ESC-2026-07-30T00.57.31.482Z.yaml
DEC-2026-0042.yaml
IMP-DEC-2026-0042-r01.yaml
REV-IMP-DEC-2026-0042-r01-r01.yaml
INT-20260727-003/
```

## Escalation timestamp IDs

New escalation IDs use this exact primary form:

```text
ESC-YYYY-MM-DDTHH.mm.ss.fffZ
```

- The timestamp is the UTC instant at which the ID is allocated.
- `T` separates date and time; the terminal `Z` means UTC.
- Dots replace ISO 8601 time colons so the ID is valid in Windows filenames.
- Three fractional digits are required. They represent milliseconds.
- The filename is `<id>.yaml`; its stem must exactly equal the artifact's `id`.
- The ID is immutable after allocation. Moving an escalation between `pending/`,
  `returned/`, and `decided/` does not change it.

Epoch IDs are not used. They are less auditable for humans and do not remove the
need for collision handling.

### Collision handling

Allocate the filename atomically. If the primary filename already exists, append
the next available occurrence suffix, zero-padded to at least two digits:

```text
ESC-2026-07-30T00.57.31.482Z
ESC-2026-07-30T00.57.31.482Z-02
ESC-2026-07-30T00.57.31.482Z-03
```

Never overwrite an existing artifact, reuse an ID from another state folder, or
change the recorded time merely to evade a collision. Duplicate detection spans
the complete ruleset escalation namespace, including `pending/`, `decided/`, and
any archive.

### Legacy IDs

Existing escalation IDs are stable historical identifiers and are not renamed
solely to match this convention. This includes the earlier sequential
`ESC-YYYY-NNNN` form and timestamp IDs allocated before version 1.1. New IDs
allocated after version 1.1 must use the current form.

Never overwrite a prior revision. New work increments `rNN`, records the prior
artifact ID in `supersedes`, and follows `contracts/WORK_QUEUES.md`.

Packet intake folders represent physical intake or retention state:

- `books/<ruleset-id>/<book-id>/packets/incoming`: available
- `books/<ruleset-id>/<book-id>/packets/claimed`: claimed, immutable source
  packets retained at stable provenance paths
- `books/<ruleset-id>/<book-id>/packets/completed`: reserved for a
  manifest-backed archival migration; not evidence of Analyst completion

Artifact-kind folders do **not** represent pending work:

- `artifacts/gur`: immutable GUR revisions
- `artifacts/gup`: immutable GUP bundles and revisions
- `artifacts/reviews`: immutable Review revisions
- `artifacts/approved`: immutable Approved bundles
- `artifacts/integrated`: immutable book-scoped integration copies
- `rulesets/<ruleset-id>/decision-implementations`: immutable Builder reports
  for non-migration Architect Decisions
- `rulesets/<ruleset-id>/decision-implementation-reviews`: immutable Reviewer
  dispositions of those reports

Queue state is derived from revision and provenance lineage under
`contracts/WORK_QUEUES.md`. Do not create `pending`, `processed`, or
`superseded` subdirectories by moving published artifacts.

### Architect Decision Reissues

An Architect Decision reissue receives a new stable Decision ID, not an `-rNN`
filename suffix. It records its position in the Decision lineage using the
ordinary YAML envelope:

```yaml
id: DEC-YYYY-NNNN
revision: 2
supersedes: DEC-YYYY-NNNN
```

The predecessor file remains immutable at its original filename. See
`contracts/WORK_QUEUES.md` for the conditions under which a Decision reissue is
the active governance leaf.

## Version history

- **1.5 - 2026-08-13:** Defined new-ID naming for immutable Architect Decision
  reissues.
- **1.4 - 2026-08-04:** Added ruleset-scoped Decision Implementation Report and
  Implementation Review names and stores.
- **1.3 - 2026-07-30:** Added `returned/` to the escalation state paths while
  preserving immutable IDs across state transitions.
- **1.2 - 2026-07-30:** Added Approved bundle naming, explicit supersession, and
  append-only artifact-store semantics; delegated queue state to
  `contracts/WORK_QUEUES.md`.
- **1.1 - 2026-07-30:** Replaced sequential escalation numbers with
  Windows-safe, millisecond-resolution UTC timestamp IDs; defined collision,
  filename-stem, immutability, and legacy-ID rules.
