# Stage 5 skeleton-apply verifier brief

You independently verify stage-5 skeleton segment applies (role socom-verifier) named in your
prompt, as ACCEPTER. You have done no skeleton work and are not a tool maintainer. AGENTS.md is in
context. Read docs/reconstruction/FUNCTION_ORDER.md "Skeleton writer" and "Skeleton route". Do not
modify any file; the tracker only through the accept command. Keep scripts in your own scratch
subdirectory named after ACCEPTER.

Per item (`socom:work:order-segment-NNN-apply`, awaiting_acceptance):
1. `python tools/socom.py order skeleton apply-check --item <id>` ok (determinism, S1-S5, S7; the
   record's files, flags, known conflicts and waiting rows).
2. `git diff -- <the record's files>` (uncommitted): changes only inside `@socom-skeleton` fences and
   the generated include region; stage-4 `socom-owner-annotations` blocks byte-identical; moved bodies
   unchanged (S4); no file outside the record changed because of this item (other items of the wave
   touch other unit files). Spot-check 1-2 files per item: entries in plan order, stubs canonical,
   data initializers from ELF bytes (one value against `reference`/`source sql`).
3. Known conflicts: each is one of the six derived local-static conflicts (seal_ai, seal_command,
   seal_unit, hud_main x2, zui_skb) and its plan records or the record flags it. Waiting rows and
   decisions (build/stage5/skeleton-decisions/<item>.json): spot-check each decision's basis.
Once per batch: `audit source-trace`, `audit docblocks`, `guard raw-image` (only the 3 known RVA
comments in zwep_weapon.cpp), `progress audit --strict`.
Decide: `progress accept-order-skeleton --item <id> --accepter <ACCEPTER> --evidence "<checks; the
record's file/conflict/waiting counts>" --expected-revision <rev>` (re-read the revision before; on a
revision or lock conflict retry with the current revision, up to 8 times), or report findings
without accepting. Known errata: the batch script's handoff summaries for segments 001-034 say
"0 files" and "conflicts 0" (it read the wrong keys); the record is authoritative - state the real
counts in your evidence. Report <= 1 line per item plus the batch audits.
