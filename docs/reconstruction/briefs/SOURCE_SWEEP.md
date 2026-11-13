# Stage 4 sweep brief (fix listed rows in existing plans)

You fix the stage-4 plans named in your prompt, as OWNER (role socom-source-owner-mapper). Follow
build/batch-helpers/SOURCE_PLANNER.md for tools, rules and the cycle (claim, edit, validate,
handoff); this brief only narrows the work. Do NOT redraft: edit the existing plan in place.

Inputs:
- build/stage4/emit-check.json (`source plan emit-check --all` output; authoritative for header
  emits: missing_emits with suggested header+line, missing_notes, wrong_citations per plan) and the
  older build/stage4/sweep-list.json: per plan item, `emit` rows (owned inline/WEAK/13 copies whose
  referencing artifacts belong to two or more units and that have no header emit; with class,
  referencing units and the class's DWARF header units if any) and `dref` rows (drafted
  D-referenced GLOBAL data with position flanks). Treat it as a checklist, re-verify each row
  with `source sql` before acting (some rows may already be handled by a note).
- Prior review findings quoted in your prompt (do them too).
- The pre-sweep copy of each plan is build/stage4/pre-sweep/<file> (reviewers diff against it).

Per emit row (ODR rule): confirm >= 2 referencing units with the current plan decisions. Header:
the class's DWARF header unit if any (map Z:\dev\... to the repo path), else the provisional
header under src/ that declares the class (`class|struct <Name>`; cite file:line), else no emit
and add one plan note "<artifact> <name>: used by N units; no header declares <Class>". Every `decide` needs
`--lease-owner <OWNER>`. Record
emits with `source plan decide --plan P --artifact X --header-emit <path|<name>> --reason inline
(or template for MSL) --emit-evidence "<header:line>; <referencing units>"`; add every new
header directory to the reservation (hand edit, json.load/json.dump, raw strings).
Per dref row: only rows the prompt names as OUT OF ORDER change: `decide --override --evidence`
to the unit whose data run contains it in link order, or `--unresolved` with the reason. Edge
rows (next to their own unit's run, link order consistent) stay.

Then `source plan emit-check --plan P` must be clean (0 missing emits/notes, 0 wrong citations;
`undetermined` rows are fine), then `source plan validate --plan P --check --fill-annotations`, `--check`, `source plan draft
--check P`, and `progress work handoff` with summary "sweep: +E emits, +N notes, D data
overrides, other fixes ..." and evidence citing the new sha256. No src/, Ghidra, memory or issue
ledger. Report <= 2 lines per plan.
