# Stage 5 re-plan addendum (after the stage-4 amendment rebase, 2026-11-06)

Follow build/batch-helpers/ORDER_PLANNER.md, with these differences. These order plans were
accepted, then reopened by stage-5 reopenings for stage-4 amendments 008-026 (the user's function
placements, docs/reconstruction/decisions/stage4-function-placements.md) and rebased with
`progress rebase-function-order` onto stage-4 baseline 17256eb1. Their order target changed: new
units (the user's new files, e.g. zEntity/ent_entity.cpp, zAI/ai_search.cpp) and functions that left
the unresolved/holding state now have owners.
1. Before anything else, copy the current plan to build/order-plans/<slug>.prev.json (keep it).
2. `order plan validate --plan P` will say stale: re-draft the plan with the order drafting command
   the docs name for the segment (see FUNCTION_ORDER.md "Order plans"; `python tools/socom.py
   commands --json` lists them), then carry over every decision from the .prev plan whose rows are
   unchanged (same artifacts, same unit) - re-decide only new or changed rows, with evidence.
3. Settle open rows as the brief says; validate --check; hand off citing the plan sha256 and the
   .prev sha256. The order-link item (if yours) needs every segment plan first: do it last, after
   the others are handed off or accepted (`progress show` them).
Keep all scripts/outputs in build/order-plans/<OWNER>/ (your own folder; other planners work in
parallel). Report <= 2 lines per item.
