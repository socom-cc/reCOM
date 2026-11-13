# Stage 4 amendment planner brief (user placements, amendments 008-026)

Follow build/batch-helpers/SOURCE_PLANNER.md for tools and rules, with these differences.

These items are accepted plans reopened by a governed amendment (SOURCE_CORRELATION.md "Amending an
accepted plan"). Do NOT redraft from scratch: revise the existing plan file
build/source-plans/<slug>.json. First copy it to build/source-plans/<slug>.prev.json (keep it).

What changes: only the artifacts the user placed. The decision file is
docs/reconstruction/decisions/stage4-function-placements.md (LF sha256
fe2f75edb96e8fe022e2d298cb3ce68bb7ddc6caa2b9a4d41a0216da1e5680c4; re-print it with
`python tools/socom.py source placements check --file docs/reconstruction/decisions/stage4-function-placements.md --json`,
which lists every placed artifact with its plan item and heading). For each placed artifact of
your item: move it from the plan's `unresolved` list into an owner row for its destination:
- a new file (placements check: `new: true`, or a unit the graph does not know): an owner row with
  `name_basis: "user"`, confidence medium (low if the evidence is thin), workspace_path = the
  heading's real src/ path, and `decision` {file, sha256, heading} - heading exactly as written;
- an existing unit the graph knows: add the artifact to that unit's owner row with a per-entry
  `decision` object, confidence medium at most, basis citing the decision line and the contiguity
  the placements check verified;
- a `.h` heading (inline/template code): keep the artifact owned by the unit whose object holds the
  kept copy (by contiguity), add the header-emit row for the header named in the heading, and cite
  the decision on the artifact's entry. compiler copies listed in
  docs/reconstruction/decisions/stage4-compiler-copies.md stay as they are unless they are among
  your unresolved rows, then handle them the same way (header or MSL `<list>/<vector>/<algorithm>`).
Keep every other row, note, contradiction and the reservation unless the new files need the
reservation extended (new directories/files must be inside it). The user's `Note:` lines are their
reasoning: quote them in the row basis where relevant. Data objects are NOT part of these
amendments: leave unresolved data rows unresolved.
Cross-plan units: zanim_cmd_tick.cpp (016, 017), seal_body.cpp (031, 032) and zmath.h (016, 024,
026) span plans - use the same owner-row path everywhere; read the other plans before writing.
Then validate (`source plan validate --plan ... --check --fill-annotations`, `--check` again,
`source plan draft --check ...`) and hand off with `progress work handoff`, summary
"amendment <NNN>: placed P (new files F), unresolved U->U'", evidence citing the plan sha256, the
.prev sha256, validate ok and the decision file sha256. Re-read the tracker revision before every
mutation; on a revision/lock conflict wait for .agent/RECONSTRUCTION_PROGRESS.json.lock to clear
and retry (up to 5 times). Report <= 5 lines per item.
