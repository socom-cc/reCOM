# Follow-ups from the stage-4/5 placement wave (2026-11-06)

To settle after the wave (amendments 008-026, stage-5 rebase cfe12f6).

1. (done 2026-11-06, commit after 76443a9: decision revisions) Row 17: `CMatrix::operator const float (&)[4][4]() const`
   (0x223170) is under `## zmath/zmath.h` in docs/reconstruction/decisions/stage4-function-placements.md,
   but DWARF names `Z:\dev\gamez\zmath\zmath_matrix.h` as CMatrix's header (dwarf_cus 0x1e45f0,
   0x1eb350, 0x3c5bc0). Move the line under `## zmath/zmath_matrix.h`; its kept copy stays unresolved
   (no neighbour references it), so this needs only a decision-file change plus re-stamping the plans
   that cite the file (or a follow-up amendment when the copy gets an owner).
2. CEntityCtrl's RTTI name, RTTI and vtable (0x44ce00, 0x44ce10, 0x471b80) are still unresolved in
   source-segment-022; their reason ("~CEntityCtrl has no owner") is stale - ~CEntityCtrl is now in
   zEntity/ent_control.cpp. Resolve with the data-object placements (follow the owning unit).
3. Data objects: 352 stage-4 data rows remain unresolved; most should follow the new function owners.
4. Header citation line drift in emit-check (wrong citations on accepted rows since the stage-5
   prepare edited headers): one cross-plan fix, not per plan.
5. Wording errata recorded in acceptance evidence (no owner change): 016/024 cite zmath.h:128/:131
   (now :156/:159); 020's zbody_main.cpp row says PartInSpace has no unit candidate (it has a weak
   class-hint body.cpp that link order rules out); 025's handoff summary misdescribes ztex_dyn.cpp.
6. Three compiler copies stay unresolved (0x224740 remove_copy<CNode> - R1 puts it in node_vector.cpp;
   0x217560/0x2175f0 vector dtors) - a user row can't own copies not listed under its heading.
7. Tool: `progress rebase-function-order` doesn't refresh order item titles (e.g. order-segment-032 still says "5 units, 275 definitions"; it now has 6 units, 294; 033 217->219; 076 32->34). Cosmetic; fix in the rebase.
8. Tool/process: parallel accepts race on the tracker revision (order-segment-030 needed 8 retries). Consider a queued/locked accept helper for batch reviewers.
9. (settled 2026-11-06: user keeps ztex_dyn.cpp as is) ztex_dyn.cpp (user placement, accepted) holds only the ~CDynTexList inline copy 0x2174d0 (implicit dtor; only reference __sinit_zparticle.cpp), making it an object of its own between grid_cell.cpp and grid_clutter.cpp. An object with nothing but a compiler copy is unusual: likely the copy belongs to grid_cell.cpp or grid_clutter.cpp and ztex_dyn.cpp should not exist (the dtor's source home is ztex.h, already recorded). Ask the user.
10. (done 2026-11-06) Route tests fixed for the post-wave state; census refreshed. Gap: test 5 skips its real-prepare reservation comparison silently when the stored manifest_sha256 differs from the current one (true after every rebase) - make it say so or derive the comparison.
11. guard raw-image reports 382 findings: address comments (/* 0x140ef0 */ etc.) the port lane added to src/ bodies. Decide: allow-list port provenance comments in the guard, or move them to a port: prefix form the guard accepts.
12. (queued 2026-11-12, user decision: "Queue the change to fts_action.h") Move the CNodeAction header
    `src/gamez/zNode/node_action.h` -> `src/gamez/zFTS/fts_action.h`, next to its implementation
    `fts_action.cpp` (owner proven by the __FILE__ literal 'fts_action.cpp', socom:data:0x44e600;
    the header's own name was a correlation-stage placement, DWARF shows the class only through the
    orders.cpp / hud_actionbitmap.cpp units). Governed change, not a plain rename: the header carries
    stage-4 `emits` annotations for 0x1ff8d0 (source-segment-024) and 0x29a6b0 (source-segment-033),
    so it needs a stage-4 amendment for those two segments (decision row in
    docs/reconstruction/decisions/stage4-function-placements.md if the tool wants one, `source
    annotate` to regenerate the blocks), the include guard renamed, and 8 includers updated
    (hud_actionbitmap.cpp, fts_action.cpp, fts_mission.cpp, seal_ai.cpp, seal_command.cpp,
    seal_control.cpp, seal_env.cpp, zseal.h), then audit docblocks / source-trace and a port build.
    Do it when no port worker has those files open (first-queue pause before the user's play session).
