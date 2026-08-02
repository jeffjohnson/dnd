**ChatGPT:**

The current run indicates that your **folder lifecycle is not aligned with role completion**.

`PKT-PHB-001-006-preamble` is still under `packets/claimed/`, even though it already produced GURs, GUPs, and an approved artifact. That means it is finished from the Analyst’s perspective, but the packet directory was never moved to `packets/completed/`.

The key distinction should be:

* `packets/completed/` means **Analyst work is complete**
* `artifacts/approved/` means **Reviewer approved the GUP**
* `artifacts/integrated/` means **Integrator merged it into canonical**
* “fully done” is pipeline state, not packet location

## What should happen to the packet

For the preamble:

```
books/adnd1e/phb/packets/claimed/PKT-PHB-001-006-preamble
```

should already have been moved to:

```
books/adnd1e/phb/packets/completed/PKT-PHB-001-006-preamble
```

as soon as the Analyst produced the accepted GUR.

The Analyst should not wait for Builder, Reviewer, or Integrator.

The packet’s lifecycle is:

```
incoming
   ↓ Analyst claims
claimed
   ↓ Analyst emits GUR
completed
```

The overall graph-update lifecycle continues separately:

```
GUR
 ↓
GUP
 ↓
Review
 ↓
Approved
 ↓
Integrated
```

## Your scanner is overcounting work

The scan reports:

* 19 GUR files
* 22 GUP files
* 9 claimed packets

But many of those are old revisions, not genuinely pending items.

For example, the preamble has:

```
GUR-PKT-PHB-001-006-preamble-r01.yaml
GUR-PKT-PHB-001-006-preamble-r02.yaml
```

and:

```
GUP-PKT-PHB-001-006-preamble-r02.yaml
GUP-PKT-PHB-001-006-preamble-r02.edges.csv
```

plus an approved output. The scanner currently treats all of those as active queue entries merely because they remain inside `artifacts/gur/` and `artifacts/gup/`.

That folder structure cannot distinguish:

* awaiting processing;
* processed;
* superseded revision;
* rejected revision;
* approved revision;
* integrated revision.

## Recommended folder change

Each artifact type needs explicit queue states.

```
artifacts/
├── gur/
│   ├── pending/
│   ├── processing/
│   ├── completed/
│   ├── superseded/
│   └── failed/
│
├── gup/
│   ├── pending/
│   ├── processing/
│   ├── completed/
│   ├── superseded/
│   └── failed/
│
├── reviews/
│   ├── pending/
│   └── completed/
│
├── approved/
│   ├── pending-integration/
│   └── integrated/
│
└── integrated/
```

You could simplify slightly:

```
artifacts/
├── gur/
│   ├── pending/
│   └── processed/
├── gup/
│   ├── pending/
│   └── processed/
├── reviews/
├── approved/
└── integrated/
```

But revision-heavy workflows benefit from `superseded/`.

## Correct handoffs

### Analyst → Builder

The Analyst should write the final GUR into:

```
artifacts/gur/pending/
```

Then move the packet:

```
packets/claimed/
→ packets/completed/
```

The Builder scans only:

```
artifacts/gur/pending/
```

After successfully producing a GUP:

```
artifacts/gur/pending/GUR-...yaml
→ artifacts/gur/completed/GUR-...yaml
```

and writes:

```
artifacts/gup/pending/GUP-...yaml
artifacts/gup/pending/GUP-...edges.csv
```

### Builder → Reviewer

The Reviewer scans only:

```
artifacts/gup/pending/
```

After review, the GUP moves to one of:

```
artifacts/gup/completed/
artifacts/gup/superseded/
artifacts/gup/failed/
```

The Reviewer writes a review artifact.

If approved, it also creates or moves an integration-ready bundle into:

```
artifacts/approved/pending-integration/
```

### Reviewer → Integrator

The Integrator scans only:

```
artifacts/approved/pending-integration/
```

After successful integration:

```
artifacts/approved/pending-integration/
→ artifacts/approved/integrated/
```

or copies the finalized integration record into:

```
artifacts/integrated/
```

## How roles know work is complete

They should **not scan the entire repository and infer state from filenames**.

Each role should have exactly one inbox:

| Role       | Inbox                                     |
| ---------- | ----------------------------------------- |
| Analyst    | `packets/incoming/`                       |
| Builder    | `artifacts/gur/pending/`                  |
| Reviewer   | `artifacts/gup/pending/`                  |
| Architect  | `rulesets/adnd1e/escalations/pending/`    |
| Integrator | `artifacts/approved/pending-integration/` |

Each role processes only entries in its inbox.

That makes the filesystem itself a queue.

## What the current files imply

For `PKT-PHB-001-006-preamble`, based on the output:

* packet is incorrectly still `claimed`;
* GUR files are incorrectly still sitting in the Builder input directory;
* GUP files are incorrectly still sitting in the Reviewer input directory;
* an approved integration artifact exists;
* the approved artifact has not yet been integrated.

The likely corrected state should be:

```
packets/completed/
    PKT-PHB-001-006-preamble/

artifacts/gur/completed/
    GUR-PKT-PHB-001-006-preamble-r02.yaml

artifacts/gur/superseded/
    GUR-PKT-PHB-001-006-preamble-r01.yaml

artifacts/gup/completed/
    GUP-PKT-PHB-001-006-preamble-r02.yaml
    GUP-PKT-PHB-001-006-preamble-r02.edges.csv

artifacts/approved/pending-integration/
    APPROVED-GUP-PKT-PHB-001-006-preamble-r02-r01.edges.csv
```

## One more important issue

Your GUP count is counting the YAML and CSV components separately. A single GUP commonly consists of:

```
GUP-....yaml
GUP-....edges.csv
```

The scanner reports those as two pending items. That is why 22 GUP files does not necessarily mean 22 GUP jobs.

The scanner should group by artifact base ID:

```
GUP-PKT-PHB-001-006-preamble-r02
```

and report one package containing two files.

The same applies to approved bundles if they gain manifests, edge files, node files, and reports.

## Recommended invariant

Add this to the lifecycle contract:

```Markdown
A role input directory contains only artifacts awaiting that role.

When a role successfully completes an artifact, it must atomically move the
input artifact out of the input directory before publishing the downstream
artifact.

Historical, superseded, rejected, completed, or integrated artifacts must never
remain in a role's input directory.
```

So, yes: the Analyst appears to have failed to perform the final packet move, but the larger issue is that the current `gur/` and `gup/` folders are acting as both **archive and queue**. Those two purposes need to be separated.