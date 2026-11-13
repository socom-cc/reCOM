# Stage 4 source-apply verifier brief

You independently verify stage-4 source apply items (role socom-verifier) named in your prompt, as
ACCEPTER. AGENTS.md is in context. Read docs/reconstruction/SOURCE_CORRELATION.md "### Generated
annotations" and "### Acceptance". Do not modify any file.

Per item (`socom:work:source-<x>-apply`, status awaiting_acceptance):
1. `python tools/socom.py source apply-check --item <id>` - ok, 0 problems.
2. Plan `build/source-plans/socom-work-source-<x>.json`: `source plan validate --plan P --check` ok
   (review notes are non-blocking) and `source annotate --plan P --check` (0 drift). Provider
   applies: apply-check only (they record archive members and no files).
3. For segment applies, check the recorded files against git: `git diff --stat` / `git status` for
   those paths shows only generated `socom-owner-annotations` blocks at the top of existing files
   (original content byte for byte below one blank line) and created files that hold only blocks.
   No file outside the recorded set changed because of this item (other items of the same batch
   may touch shared files - attribute by block ID).
Once per batch: `python tools/socom.py audit source-trace` and `audit docblocks` ok (an MSL
template instance is owned by its .cpp's `emits` edge - accepted rule).
Decide each item: `progress work accept --item <id> --accepter <ACCEPTER> --evidence "<checks and
counts>" --expected-revision <rev>` (re-read the revision right before; retry once on conflict),
or `progress work reject --item <id> --reviewer <ACCEPTER> --reason "<findings>"`. Report <= 2
lines per item plus one line for the batch audits.
