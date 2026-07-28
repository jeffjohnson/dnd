# File Naming and State

Use stable identifiers rather than chat titles.

```text
Packet:       PKT-<BOOK>-<START>-<END>-<slug>
GUR:          GUR-<packet-id>-rNN
GUP:          GUP-<packet-id>-rNN
Review:       REV-<gup-id>-rNN
Escalation:   ESC-YYYY-NNNN
Decision:     DEC-YYYY-NNNN
Integration:  INT-YYYYMMDD-NNN
```

Examples:

```text
PKT-DMG-070-071-helpless-targets/
GUR-PKT-DMG-070-071-helpless-targets-r01.yaml
GUP-PKT-DMG-070-071-helpless-targets-r01.yaml
REV-GUP-PKT-DMG-070-071-helpless-targets-r01-r01.yaml
DEC-2026-0042.yaml
INT-20260727-003/
```

Never overwrite a prior revision. New work increments `rNN`.

Folders represent state:

- `books/<ruleset-id>/<book-id>/packets/incoming`: available
- `books/<ruleset-id>/<book-id>/packets/claimed`: assigned and immutable
- `books/<ruleset-id>/<book-id>/packets/completed`: integrated
- `work/gur`: Analyst outputs
- `work/gup`: Builder outputs
- `work/reviews`: Reviewer outputs
- `work/escalations`: pending and decided architectural issues
- `work/rejected`: preserved rejected artifacts
