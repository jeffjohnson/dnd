# Shadowdark Source Workspaces

Use `ruleset_id: shadowdark`. See
[the complete filesystem map](../../rulesets/shadowdark/WORKSPACE.md).

The six book workspaces are `sd`, `cs1`, `cs2`, `cs3`, `shadowdome`, and
`western-reaches-pg`. Each has a book manifest, separate steward-intake source,
packet directories, artifact stores, and book-specific extraction schemas.
The requested `western_reaches_pg` uses hyphens to meet the existing book-ID
contract. Editions/printings remain explicitly unspecified pending source intake.

Place Pandoc Markdown packets in the registered book's
`packets/incoming/`. Preserve `{#pNNN}` page markers and current source naming.
One independent Shadowdark graph will combine compatible registered books.
