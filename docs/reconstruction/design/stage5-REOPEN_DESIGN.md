# Stage 5 reopen, rebase and merge re-apply after a stage 4 amendment (design)

**Commands.**
- `progress reopen-order-skeleton --amendment <open stage 4 amendment> [--item <stage 5 item>]... --by --reason --evidence... --expected-revision [--dry-run]`
- `progress rebase-function-order --by --reason --evidence... --expected-revision [--graph] [--dry-run]`
- `progress apply-order-skeleton ... [--resolutions <dir under build/>]` (merge re-apply; conflict report)
- `order skeleton apply-check` verifies the item's own recorded write; later `src/` edits are drift.

**State flow.**
1. Amendment `A` open (stage 4). `reopen-order-skeleton --amendment A` selects: the order plan of each amended stage 4
   segment, the skeleton applies whose recorded files the amended stage 4 applies recorded, their plans, the prepare when
   one of its files is among them, plus `--item`. Refuses leased / in-review items, a started compile, a stale revision,
   an amendment that is not open. Each item: accepted -> blocked, review-history entry `{amendment, reopened_by, ...,
   handoff, accepted, order_skeleton}`; stage 5 row `reopenings[]` `{id socom:order-reopening:NNN, amendment, items,
   status open, ancestors}`. Before the mutation it renders the tree from the still-current inputs and stores every file
   whose render equals a skeleton record's write in the blob store (the merge ancestors).
2. Stage 4 re-applies `A` (`apply-source-plan` now accepts files of skeleton items reopened for `A`, refuses others).
3. `accept-source-amendment` -> new stage 4 baseline B'.
4. `rebase-function-order` (no open amendment; B' reached from stage 5's baseline only through accepted amendments):
   builds the order target over B'; records `decomposition.rebases[]` (previous digests, amendments, reopened/carried
   segments, base delta); updates the decomposition digests and every order item's cited digests; for changed segments
   updates units, target digest, directories and unit files; reopens (history entry) any accepted plan the new target
   no longer validates, its apply, and the link plan when the link order changed; advances the frozen base (current
   stage 4 blocks onto the base's authored content, new stage 4 files as block-only); marks the reopenings `absorbed`.
   A path a skeleton record deleted that a current stage 4 record creates (`recreated_paths`: a new unit file named
   after the orphan) is released from the deleting item to the segment apply (`released`); the deletion stays in the
   record as history (not retired for stage 4, not a skeleton write, not a merge ancestor), the base takes the file as
   blocks only, and stage 4 contradiction rows on it are checked against the deleted file's frozen copy (by digest:
   base, base-history, blobs). The ancestor capture is `skipped` while held plans keep the manifest unreadable.
   The manifest/writer read a recreated path's authored content from the deleted file's frozen copy
   (`provisional_overlays`: bodies keep `path:line` and render, never stubs; the new unit file drops the rest), and the
   rebase re-seals the body snapshot's `src_sha256` over the advanced base (blocks-only delta, recorded in
   `base.snapshot`).
5. Planners re-draft / validate / hand off; reviewers accept. A plan built on an absorbed earlier baseline whose
   segment target digest is unchanged stays valid ("carried": the global digests become notes). Rebuild the manifest.
6. Re-apply the reopened skeleton items (the prepare first if reopened): merge, check, hand off, accept.

**Merge inputs (per file).** ancestor = the previous render of the file (record row `rendered_sha256`, else
`after_sha256`; content from `build/stage5/skeleton-route/blobs`, else a fresh render with that digest), or the base
content for a file never written; ours = live `src/`; theirs = the new render. theirs == ancestor -> ours; ours ==
ancestor -> theirs; ours == theirs -> ours; else a pure-Python line merge3 (difflib, deterministic). Any conflict: nothing
is written for the item, `build/stage5/skeleton-route/conflicts/<item>.json` lists the hunks (lines and both sides) and
`conflicts/<item>/src/...` holds marker files; a worker copies a resolved file to `<dir>/src/...` and passes
`--resolutions <dir>`; the report's digests must still be current. Merged/resolved files must keep the render's fence
lines (same sequence) and stage 4 blocks; S1-S7 run on the pure render as before.

**Recorded per file.** path, action, `before_sha256` (live), `ancestor_sha256`, `rendered_sha256`, `after_sha256`
(written), `merge` (`render`|`kept`|`clean`|`resolved`), `resolution`, stage 4 block digests; record `amendments`.
Blobs of ancestor, before, render and after are stored so `apply-check` re-runs the merge deterministically.

**Fence-keyed carry (before the per-file merge).** Entries (top-level stub/body fences, decl regions) are matched by
fence identity (same file, else a name unique in the tree, else the held body id the write manifest gives a moved body).
An entry the render moved across files or names takes `merge3(ancestor, live, render)` at the render's place; its old
place takes back the ancestor text (or loses it). Across items: `pending` on the source record (texts in the blob store),
`merged` (`via`) on the destination's, `carried-by` when the destination carried it first. Unowned port fences become
`/* port: <kind> <name> (no owner in the render) */`. A still-conflicting file is retried entry by entry (preamble and
edited entries merged alone). Kind `carried` (row `carry`: inner kind, effective input digests), record `carried[]`,
`carried_by_state`. A clean merge failing check_merged is a conflict; a render-deleted file resolves via
`<dir>/<path>.socom-deleted` or fence-free content.
