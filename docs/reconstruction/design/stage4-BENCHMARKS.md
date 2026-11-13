# Stage 4 benchmarks

Measured with `python build/batch-helpers/bench.py ~/.claude/projects/<project>/<session>/subagents
--filter SOURCE_`. Cost is turns x context, so cumulative context per item (cumM) is the target.
Quality signal: first-pass review outcome and the kind of findings.

## Baseline (2026-10-31)

| Run | Items | cumM/item | Turns | Notes | First-pass review |
| --- | --- | --- | --- | --- | --- |
| s001 (no drafter) | seg 001 | 10.6 | 100 | | superseded by refresh |
| s017 (no drafter) | seg 017 | 16.8 | 143 | | superseded |
| pmw (no drafter) | mw-runtime | 10.4 | 96 | | superseded |
| s001b (drafter v1) | seg 001, 017 | 3.2 | 77 | 232/236 drafted | 017 accepted; 001 rejected (corrupted strings only) |
| pmw2 (drafter v1) | mw-runtime, crt0 | 5.1 | 116 | 64 MW member rows by hand | both accepted |
| p02 (drafter v1) | newlib, libgcc | 9.7 | 132 | 450-artifact slice, peak 243k, out 291k | held (graph fix) |
| p03 (drafter v1) | 989snd, lgaud | 9.1 | 139 | 84 hand rows (989snd) | 989snd in review; lgaud held |
| x1 reviewer | seg 001, 017 | 4.4 | 98 | | |
| x2 reviewer | mw-runtime, crt0 | 4.1 | 93 | | |

Maintainer rounds: ~59 M cumulative context per round (m7-m13). m14 (11 fixes): 139 M, 358 turns,
peak 585k, 74 min - scope too wide for one round; keep rounds to 3-5 related fixes.

## Draft coverage after m14 (v3 rules, graph 7bd4e540, 2026-10-31)

- Authored segments 013-027, 039, 040 (16 plans, 6902 rows): 1287 open (19%). Open rows: ~700
  "boundary function between A and B" (GLOBAL/weak/inline functions in an unanchored run between two
  units), ~350 data waiting on those functions. A LOCAL-reference rule would decide ~0 of them (844
  reference only GLOBAL symbols). Mangled class matches exactly one flanking unit for 404/926.
- Providers (10 plans): 136 open, 122 of them Medius; libgcc, lgaud, rsa, speech middleware 0.
- Wave 1 (6 planners) measures whether boundary rows dominate planner cost (027, 040 carry a
  benchmark report line) before any "suggested cut" tool is built.

## Sinks and planned fixes

1. Provider plans with Metrowerks-compiled members: no provider-scope draft rules -> hand rows
   (989snd 84). Fix: provider A-local-block / A-between / D-referenced rules (round m14).
2. Large slices: planners load/rewrite the full plan JSON via scripts (peak 243k). Fix:
   `source plan open` (print open rows compactly) + `source plan decide` (record one decision)
   (round m14).
3. Graph mis-slices forcing holds/replans (Sid object -> lgAud, GOFAST -> unidentified,
   .rodata gaps spanning two objects). Fix: graph rules + partial refresh (round m14).
4. Maintainer rounds are the most expensive runs: batch fixes into few rounds with exact file
   pointers.

## Wave 1 results

| Run | Items | Result | cumM/item | Notes |
| --- | --- | --- | --- | --- |
| w1c | speech-middleware, medius | both handed off | 6.0 | speech 0 hand rows; medius 122 open decided in 9 `decide` calls (119 COMMON unresolved) |
| w1e | seg 015, 018 | both handed off | 9.2 | 20+28 hand rows (medium); boundary evidence: per-object order non-template code then WEAK template copies (non-WEAK after a WEAK block starts a new object), vtable key function, WEAK callee order; gap: `plan open` lacks binding/WEAK order |
| w1b | sce, unidentified, libptt, rsa | all handed off | 4.0 | 4+2+0+0 hand rows; gaps: P-gnu-section misses .rodata run also referenced by the object's own .data; C-fill skips alignment fill >= 16 bytes; 7 unidentified objects look like SCE libkernl patch members (note only) |
| w1a | msl, newlib, libgcc, lgaud | all handed off | 5.5 | 4+2+0+0 hand rows; gaps: SCE .sdata run overruns to 0x47560c; locale.o no .data run |
| w1d | seg 013, 019, 023 | all handed off | 6.9 | 3+5+21 hand rows; found kept-copy rule (0/1276 counterexamples) + vtable key function |
| w1f | seg 027, 040 | both handed off | 11.5 | 6+18 hand, 37+25 unresolved (unnamed objects: user decided 2026-10-31 to own them -> revise after m15c); boundary evidence: WEAK closes its object (139/139), sole referencer, LOCAL blocks, class match |

## Queued for m15 (graph slicing, keep to these)

1. COMMON .bss tail: SCE 0x425ea0's .bss run ends at 0x5e7f00 ("next section symbol") and swallows
   the COMMON tail (250 GLOBAL vars 0x5b17c0-0x5e7e94); end the run at its own last symbol and tag
   COMMON artifacts (no slice change).
2. Gaps inside a moved object move with it: Sid 0x3b7248's 7 alignment gaps (0x3b7284..0x3b7818)
   are in the lgaud slice, its functions in speech middleware.
3. Data inside an object's section goes to the object's library slice: 0x468af2
   RT_MSG_CLIENT_MAX_AGGREGATION_LEN (inside 0x40c000 .rodata) is in source-data-rodata, not medius.
4. `source plan open --output`.
Reviews of lgaud, speech-middleware, medius held until m15 + refresh (their slices change).

Wave-1 split: m15a (graph slicing items 1-3 + locale.o cluster; running) and m15b (draft rules v4 for
boundary runs: kept-copy, vtable key function, contiguity cascade as rules; WEAK-order and class
match as reviewed suggestions; P-gnu-section/C-fill gaps; `plan open --output`) after w1f reports.
Authored planning costs 7-11.5 M/item vs providers 4-6 M; boundary rows are the sink.

m15 split final: m15a graph slicing; m15b draft v4 (R1 kept-copy, R3 key function, R4 contiguity as
rules; R2/sole-referencer/class as `suggest`); m15c plan open/decide/validate (unnamed-object
name_basis, cross-plan unit paths, decide contradictions/header_emits, open --output + WEAK order,
--accept-suggestion). Wave 2 (014 016 020 021 022 024 025 026 039) waits for m15b/c.

## Wave 1 reviews (first pass)

| Reviewer | Plans | Outcome | Finding kind |
| --- | --- | --- | --- |
| x4 | sce, unidentified, libptt, rsa | 3 accepted; sce rejected -> fixed (6 tools) -> accepted | unevidenced archive names (3 rows) |
| x7 | msl, newlib, libgcc | 2 accepted; msl rejected -> fixed (6 tools) -> accepted | wrong member list in one basis line |
| x5 | seg 013, 019, 023 | all rejected | missing MSL template header emits only (boundary decisions all held; kept-copy re-verified 0/1277) -> H-template-family rule sent to m15b; replan after m15b |
| x6 | seg 015, 018 | both rejected | one missing MSL <vector> emit each (+015: CAiMapLocVec implicit ctor/dtor header to argue); key-function rule re-verified (no exceptions), WEAK-closes re-verified |

Resuming the original planner/reviewer for a fix costs ~6 tool calls (context reuse) vs a fresh agent.

Convention (brief, already a rule): every owned MSL template instance gets an MSL header emit;
accepted 001 complies (7/7). All 5 authored rejections are this one gap -> fixed by v4 drafting.

## m15 rounds (parallel worktrees, 2026-10-31)

| Round | Scope | cumM | Turns | Peak k | Min | Result |
| --- | --- | --- | --- | --- | --- | --- |
| m15a | 4 graph slicing fixes | 101 | 372 | 382 | 61 | graph c79d76e6; slices changed only lgaud/speech/medius/rodata |
| m15b | draft v4 + H-template-family | 86 | 351 | 362 | 52 | open 2604 -> 2285 (46 segs), 1043 suggestions (30 right, 0 wrong), 605 MSL emits; 0 disagreements over 8369 planned rows |
| m15c | plan open/decide/validate | 45 | 216 | 301 | 52 | name_basis, cross-plan unit check, decide contradictions/header emits/accept-suggestion |

Splitting by file kept the wall clock at ~1 h for 3 rounds but did not cut cost per fix: graph rounds
are expensive (whole-graph rebuilds + accepted-slice dry runs; peaks 300-380k). Next rounds: tell
maintainers to write large outputs to build/ files and print only counts; one graph rebuild per
verification cycle.
Reviewer cost per plan: x4 2.5, x7 2.4, x5 3.7, x6 8.3 M.

## Rules v5 (parent, 2f7d013)

COMMON variables: v4 D-referenced / P-gnu-data "referenced only by" gave 89 Medius COMMON vars medium
owners (unsound: one reader is not the definer). v5 leaves them open with the reason (+ suggestion in
authored plans). Small parent fix (one condition x3, one reference test), no maintainer round.

## Queued small tool gaps (next round, keep to these)

1. `decide` silently drops an empty hand-added owner row when another `decide` runs first (w1f).
2. S-weak-order ignores unit-less clusters between the flanks (points past unnamed objects; w1f).
3. H-template-family skips LOCAL MSL copies (find, find_if, swap) and rows still open at draft time (023: 7 __list_deleter) (w1e, w1d).
4. `source plan validate` has no --format/--output (w1e).
5. SCE libmc 0x171070 .data run covers authored gopt 0x438750 / team_table 0x438770 (m15a; slices ok).
6. Mapper role toml / skills do not mention the new decide options (m15c).
7. `decide` cannot replace or remove a contradiction row (rewording needs hand JSON; w1f).
8. `source sql` has no --output (w2a).
9. Cross-plan header coordination: a new header created in one plan (zmath_matrix.h, 021) is not visible to others (022, 026) - validate could list header paths other plans create (w2a).

## Replan reviews

| Reviewer | Plans | Outcome |
| --- | --- | --- |
| x5 (resumed) | 013, 019, 023 | all accepted (9 tools total) |
| x8 | lgaud, speech, medius | all accepted - all 13 provider plans done |
| x9 | 015, 018, 027, 040 | 018 accepted; 015 two implicit-ctor emits; 027 cut on R2 alone stated as fact; 040 owned provisional file's contradictions unrecorded |

Quality signal: rejections are now narrow (1-3 rows each), boundary placements hold.

## Wave 2/3 reviews: one recurring gap

Of 21 wave-2/3 first reviews so far, 11 were rejected and every rejection was missing header emits
(LOCAL MSL copies; implicit/inline members of cross-unit classes) - placements held in all. Rule
now in both briefs as the ODR rule (inline copy referenced by >= 2 units => class header). The
drafter could suggest these emits (open-emit suggestion from the class's header unit or provisional
declaring header); m16b reports the gap across accepted plans (build/stage4/v6-emit-report.json).

## Sweep (2026-10-31)

Consolidated fix lists (v6 reports) given to fresh sweep agents instead of resuming 300-450k-context
planners: sw2 fixed 5 plans in 47 tools / 118k tokens. Reviewers diff against build/stage4/pre-sweep/.
10. H-template-family misses MSL friend operators (std::operator!= of __tree::iterator 0x3a3670, classified authored) (w3h).
11. No rule/suggestion for this-adjusting thunks of a vtable read by several units (0x394ad0) (w3h).
12. .rodata @N label-number restart (same-unit drops <= 51; 0/4550) is used by planners by hand - candidate rule/evidence column (w2d, w3h, x12).
13. `progress work packet` has no --output (w3h).
14. `source plan decide` edits a plan without checking that the caller holds the item lease (two sweep edits landed seconds before a re-claim after a revision race); add an --owner/lease check.
15. `decide` does not copy `draft.open_row_header_emits` for a row it owns (29 re-entered by hand in 043; they then count as hand rows) (w3e).
16. `source sql` rejects any ';' even inside a string literal; `draft --check` has no --output (w3e).
17. No drafter rule anchors an object via its vtable's key function when the RTTI sits in a unit-less LOCAL block (caused 78 wrong S-weak-order suggestions in 043) (w3e).
18. FINAL CONSISTENCY CHECK before data reconciles (tool, validate review note + one sweep over all plans): (a) inline copy kept in unit A referenced by another unit B without emit/note; (b) implicit special member of a class a header declares (DWARF header unit or provisional declaration) without emit; (c) emit rows citing a line that does not declare the class. x20 found (a)/(b) missed by the v6 emit report (013 CNodeVector, 016 Contains, 017 CZAnimZAR).
19. H-dwarf-header does not map Z:\dev\Apps\FTS\hud.h to src/Apps/FTS/hud/hud.h (every hud segment needs hand emits); plan open lists drafted emits as outside reservation after the reservation row is corrected; decide --header-emit cannot change a hand row reason without --override (w3i).
20. Shell/heredoc layers eat backslashes (\\ -> \ produced a TAB in 044); planners need a Write-tool or chr(92) path for Windows paths; --accept-suggestion cannot append evidence to the copied basis (w3f).
21. Template static DATA members (binding 13, e.g. std::deque default_bufsize_s 0x4684d8 in 068, a sibling in 042) get no header emit; emit-check covers functions only - decide whether MSL template data emits from its header (x22).
22. emit-check note matching: counts only addresses a note spells out (no range expansion) and ties each address to "no header declares" within one ;-clause (fs3).
23. (PRIORITY before gate) emit-check classifies a binding-13 __dt__ without a DWARF subprogram as implicit even when its body is user-written (021 0x1df000 deletes elements); implicit-ness heuristic needs the body shape or an "unknown" state (fs4).
24. `decide` has no option to remove a header-emit row (x28).
25. Symbol-order test (any LOCAL label pair reversed against another object => separate objects; 6970/6970 shared pairs keep order) settles object splits - candidate draft rule / evidence column (x26).
26. (fixed 8bbd563) emit-check counted header lines including the generated ownership blocks, so the
    stage-4 applies made 250 citations read as wrong; citations now count authored lines only.
27. `source plan draft --check` flags an O-path owner row once its own apply created the file (014
    aidemo.cpp); the amendment turned it into a hand row - draft should treat apply-created files as
    the plan's own (am1).
28. (stage 5) `order plan draft` raises `out-of-rule` only for a DWARF-lined member off the longest
    reverse chain; an in-class member that happens to fit the chain (hud_linemap Advance, line 36,
    vtable-only references) is drafted out-of-line. Candidate check: a lined function whose line lies
    inside a file-local class body, or referenced only through a vtable. Only hud_linemap is affected
    among DWARF units (planner p2).
29. (stage 5, reviewer r3) static-initializer rank counts reads of initialized inputs and address
    loads (035, 064, 065); rank by the first store into each object - and treat it as weak evidence
    (store scheduling: 026, 032, 064 IMAGE_*). Calibrate in Phase C (C2).
30. (stage 5, reviewer r3) local-static counter credits a function with a static that has >1 guard
    site (031 k_fudge) or with statics straddling another function's counters (036); flag those as
    inlined-helper statics. Calibrate in Phase C (C2). Also see 28 (in-class candidates by class-body
    line runs).
31. (stage 5 route) `order skeleton decide` re-decides a type row only by its mangled key
    (Q210ActionItem5EVENT); the readable `ActionItem::EVENT` is still "not a waiting row" for a decided
    row (the re-added row's name is the last component only). Cosmetic; worker w0.
32. (stage 5 skeleton) 10 data rows typed `unsigned char X[N]` (no DWARF/stage-3 record, no direct
    access) hold relocated pointer words, so no initializer can be rendered and the rows stay unwritten
    (UICommandTable, c_arrFuncNames$799, dilr, animTypeNames, IrxFiles, valveWatch$1141, decalps,
    zon_writeon_dmaref, c_arrEnumNames$2086, c_arrCharKeyNames$2097). Infer an access-width pointer
    array (`const char *` when the targets are strings, else `void *`; flagged unproven) from the
    relocation layout in the manifest, then reopen and re-apply those 8 segments (worker w2).
33. (stage 5 skeleton) concurrent route mutations: claim/handoff retries starve while another driver
    holds the state lock; drivers should wait for the lock to clear before reading the revision (w2).
34. (stage 5 skeleton route) every apply record binds the WHOLE-tree manifest digest and all plan
    digests (order_skeleton_route._stale_inputs), so any manifest change stales all 47 records and forces
    a full re-apply + re-verification. Bind per-segment input digests (its plan, its manifest slice, the
    prepare's header digest) so a fix re-applies only the segments it touches. Decision 2026-11-02: fold
    item 32 (pointer-array initializers) into the first Phase C correction pass, which re-applies anyway.
