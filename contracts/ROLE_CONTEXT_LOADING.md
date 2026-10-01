# Role Context Loading

**Version 1.3.**

This contract limits repeated role-context loading without weakening the
repository as the source of authority. It distinguishes stable governance
context from current task evidence and mutable repository state.

## Stable Authority Context

`contracts/ROLE_CONTEXT_MANIFEST.yaml` declares the stable authority files for
each role. The manifest itself, its schema, and every resolved file are hashed
with SHA-256. The resolved path list is deterministic for a role, ruleset, and
book scope; paths outside the repository root, missing literal paths, duplicate
paths, and an unrecognized role are verifier errors.

The Builder-owned verifier interface is:

```text
python tooling/common/role_context.py verify \
  --root . --role <architect|analyst|builder|reviewer|integrator> \
  --ruleset <ruleset-id> [--book <book-id>] --session-id <opaque-session-id>

python tooling/common/role_context.py record \
  --root . --role <role> --ruleset <ruleset-id> [--book <book-id>] \
  --session-id <opaque-session-id>
```

`verify` emits `reload_required` and the exact stable authority paths on a cache
miss. The role reads those files before calling `record`. It emits `cache_hit`
only when the current session's receipt has the same repository root, role,
scope, manifest checksum, manifest-schema checksum, and checksum for every
resolved authority file.

Until `tooling/common/role_context.py` is installed and passes its Decision
Implementation review, every role treats the verifier as unavailable and follows
the cache-miss path directly from the manifest. No role may create a receipt by
hand or treat a missing verifier as a cache hit.

Receipts live under `.local/role-context/`, which is ignored by Git. They are
operational cache records, never provenance, an artifact input, an approval, or
authority to edit data. A receipt contains only cache format version, repository
root, role, scope, manifest and schema checksums, and the exact resolved
path/checksum set.

## Five-Role Operation

DEC-2026-0082 retires Dispatcher and cancels DEC-2026-0081's activation step.
There is no manual Dispatcher startup and no authorized Dispatcher work.
The live manifest deliberately selects the existing supported five-role
schema language `1.0`; this is not a rollback of published Decisions or an
in-place receipt upgrade. Schema language `1.1` may remain readable as historical
compatibility, but it cannot reactivate the retired role. Receipt format stays 1.

All five roles inherit `contracts/HERDR_HANDOFFS.md` through common_patterns.
They retain ruleset/book-scoped receipts and bounded current task inputs.
Herdr names and panes identify notification targets, not cached actor context.
Notifications may arrive while other roles work; each receiver independently
checks its queue and current inputs before acting. Never borrow another role's
receipt or invent source/scope IDs for a reload. An instruction-only notification
reads the named changed instructions and common handoff contract; it does not
authorize a corpus scan, graph task, or scope claim.
Before the next actual task, perform the ordinary scoped verifier startup.

## Session Boundary

A cache hit is permitted only for the same persistent actor session identified by
`--session-id`. A fresh agent, a changed session ID, a missing receipt, a changed
authority file, a changed manifest, or an unverifiable checksum is a cache miss.
No role may reuse another actor's receipt or infer instructions from a checksum
list alone. This preserves the repository's stateless-agent rule while avoiding
repeated loading by a continuing actor.

Hashing a file to verify the receipt is allowed and expected. A hash check does
not place the file's contents in the role's working context. `record` is an
attestation that the role loaded the stable authority set after the matching
`verify` result; it must not be called on a miss to bypass loading.

## Always-Read Inputs

The cache never covers a task's live evidence or mutable state. Each role reads
the exact current inputs in its role instructions every task and verifies their
artifact-level checksums or transaction preconditions where required. In
particular:

- Architect reads the pending escalation and only its named evidence and local
  graph slice.
- Analyst reads the complete claimed packet and its supplied slices.
- Builder reads the active GUR or revision request, current registry and local
  neighborhood, and named Decisions.
- Reviewer independently reads the current GUP, validation report, cited source
  evidence, and named governed records.
- Integrator reads the Approved bundle, Review, current canonical and registry
  state, authority Decisions, and transaction inputs.
- Every role reads the exact incoming herdr assignment and live routing evidence
  under `contracts/HERDR_HANDOFFS.md`; message text never replaces source evidence.

No role may recursively enumerate a book, an artifact store, the full graph, or
the whole codebase merely to establish context. The queue scanner, manifest, or
the task's explicit provenance must first identify the bounded inputs.

## Failure Behavior

The verifier fails closed. A cache-verification error requires a stable-context
reload and emits no `cache_hit`. It must never silently fall back to a previous
receipt, a file modification time, a different scope, or an unverified summary.
The role may continue only after reading the emitted stable set and recording a
new receipt.

## Version History

- **1.3 - 2026-09-22:** DEC-2026-0089 made Herdr notifications best effort and
  permitted concurrent independent role work without changing receipt scope.

- **1.2 - 2026-09-19:** Retired Dispatcher under DEC-2026-0082 without activating
  DEC-2026-0081; restored the supported five-role manifest and direct handoffs.

- **1.1 - 2026-09-07:** Defined bounded Dispatcher startup before verifier
  support, without borrowing receipts or changing existing-role startup.

- **1.0 - 2026-08-17:** Introduced checksum-verified, same-session role context
  receipts and bounded always-read task inputs.
