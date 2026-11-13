# Stage 4 source-owner planner brief (token-lean, draft-based)

You plan the stage-4 item(s) named in your prompt, as OWNER (role socom-source-owner-mapper).
AGENTS.md is in context; do not re-read it. Read docs/reconstruction/SOURCE_CORRELATION.md
("## Plan items" through "### Validation", and the `source sql` schema section) and the skill named
in your packet (socom-source-model-recovery, or socom-provider-boundary for a provider).

Use the tools; do not write your own parsers over the evidence or graph JSON:
- `source sql "SELECT ..."` (read-only SQL over the graph cache: artifacts, units, gnu_objects,
  segments, references, DWARF CUs/lines, __FILE__ refs, sinit order, local-symbol blocks) for every
  question about the slice; `reference relocations` / `debug inspect` for raw ELF detail.

Cycle per item (slug = item id with ':' -> '-'):
1. `progress work claim --item <id> --owner <OWNER> --lease-minutes 120 --expected-revision <rev>`;
   `progress work packet --item <id> --owner <OWNER>` (it shows the reservation and your scratch dir).
2. `source graph --output build/source-graph/graph.json` only if the graph is missing or stale;
   `source plan evidence --item <id> --check --output build/source-plans/<slug>-evidence.json`;
   `source plan draft --item <id> --output build/source-plans/<slug>.json`.
3. Do not load the plan or evidence JSON. `source plan open --plan <plan>` lists the open rows
   compactly (`--limit N` for more); every `decide` needs `--lease-owner <OWNER>` (you must hold
   the item's lease); record each decision with `source plan decide --plan <plan>
   --artifact X [--artifact Y ...] --owner <unit|0xGNU|lib:obj> --confidence c --basis "..."` or
   `--unresolved "<reason>"`. Overrule a drafted row only with `--override --evidence "..."`
   (reviewers check overrides). Rules v4 (default) attach a `suggest` {owner, rule, confidence,
   basis} to many open rows (S-class-flank, S-sole-referencer, S-weak-order). "WEAK copies close
   their object" (R2) has a counterexample (database.cpp copies 0x1729f0-0x172b40 precede its
   GLOBAL LoadWorld 0x172b60): never state it as fact, and a cut resting on it alone is low or
   unresolved (027 was rejected for this). COMMON variables (`common`) stay unresolved unless
   evidence other than "one object reads it" names a definer (rules v5).
   Rules v6 (default): D-referenced decides GLOBAL data only inside its unit's own data run;
   other GLOBAL data stays open with a low S-sole-referencer suggestion naming both flanks -
   decide it by data-section link order (.sdata/.sbss/.bss keep it: the owner must be linked
   between the flanking units), else unresolved. H-template-family now covers LOCAL MSL copies;
   `draft.open_row_header_emits` holds the emit an open row gets once you own it - add it with
   `decide --header-emit` (draft --check proves it). Check each suggestion's basis against `plan open`'s
   flanking anchors / WEAK copies / sole referencer, then `decide --accept-suggestion --artifact X
   [...]` (recorded as hand rows, reviewed), or decide differently. Also via `decide`:
   `--contradiction <kind> --provisional-file <path> --line N --elf-evidence "..."` and
   `--header-emit <src/...h|<name>> --reason template|inline|weak [--library MSL]
   --emit-evidence "..."` - no hand JSON for these. The only hand edits (json.load/json.dump) are a new owner row
   (add it once, then decide into it), owner-row paths and the `reservation` row (most segments
   must confirm or correct it). Do not pipe tool JSON in PowerShell (it adds a BOM): use
   `--format json` or `--output`.
   Provider fields: a drafted MW-unit row carries `linked: "unknown"`; set `linked` from stationery
   evidence and add `archive`/`version` only when the ELF evidences them (e.g. lgAud: liblgaud.a,
   1.06). Data-only members are GNU objects; check room between objects with `source sql` on
   `object_sections` (`room_for_member`).
   Rules (user decisions 2026-10-30/31): keep src/<Apps|gamez>/<module>/ placement and existing
   basenames; original Z:\dev path on the owner row when evidenced; existing provisional files cited
   exactly; unevidenced/empty provisional files stay unowned (retire only with evidence); providers:
   one row per archive member, no source bodies, no workspace paths (toolchain objects:
   `archive_member.linked: "object"`); MSL template instances in `header_emits` with
   `{"header": "<string>", "library": "MSL"}`; annotations only for named artifacts. Confidence:
   high only for direct anchors; contiguity is medium or low. Prefer `unresolved` with a reason over
   a guess.
   Placement argument for inline (binding-13) single copies: containment strictly between two
   anchors of the same unit (no other object/unit between) - not "first caller", which is not
   reliable on its own. Copies at a unit edge stay open/unresolved unless other evidence decides.
   Header emits for inline functions with no DWARF: implicit special members (implicit ctors/dtors,
   copy ctors) go to their class's header; explicit inline members without a header unit in the
   debug info get no emit - UNLESS functions of two or more units reference the copy (incl. vtable
   and __sinit references; a copy reached only through its class's vtable counts every unit that
   reads that vtable or constructs the class; the unit keeping the copy counts too): then it is
   defined in a shared header (ODR). Implicit special members always go to their class's header
   when a header declares the class, and project template instances (RTArray<...>) to the header
   declaring the template and emits to its class's
   header (DWARF header unit, else the provisional header declaring the class, cite file:line);
   add that directory to the reservation. Five plans were rejected for missing these. If no
   header is evidenced at all (no DWARF header unit, no provisional declaration), record no emit
   and a note "used by N units; no header declares it" - never invent a header. MSL template
   instances ALWAYS need an emit: take the header from the
   DWARF header units of other instances of the same class template (`<vector>` for
   __vector_imp/__vector_pod/__vector_deleter, `<list>`, `<msl_utility>` for compressed_pair_imp and
   compile_assert); argue it when no instance has one (three plans were rejected for this). Contradictions with existing provisional source (a function the ELF puts
   in another unit, a signature/constness mismatch) go into the plan's structured `contradictions`
   rows (artifact, provisional file:line, ELF evidence), not into `notes`.
   Unnamed objects (user decision 2026-10-31): authored code in an object the ELF names no unit for
   (no DWARF CU, __FILE__ or sinit) but whose extent you can prove is OWNED, not unresolved: if
   exactly one existing provisional file in the module dir already defines its functions, use
   that file (confidence medium); otherwise invent a descriptive file name from its main class
   (e.g. zsys_spr.cpp, confidence low); set the owner row's `name_basis` to "provisional" or
   "invented" (validate checks the artifacts lie in unit-less clusters); if one vs two objects is
   unproven, use one row and say so in a note.
   User placements: a file the user named in a decision file (`## <module>/<file>` headings) gets
   `name_basis` "user", confidence medium at most, and `decision` {file, sha256, heading} (sha256 =
   LF-normalized digest, printed by `source placements check --file <file>`; heading as written).
   Every artifact of the row must be listed under that heading. A placement into a unit the graph
   knows, or into a header (inline copy, with its header-emit row), cites the same object on that
   artifact's entry instead (with confidence and basis). Cluster/candidate rules still apply.
   Cross-segment units: a unit spanning segments must use the same owner-row path in every plan;
   check other plans under build/source-plans/ for the same unit before choosing a path.
   For binding-13 inline copies, cite the LOCAL symbol block holding the kept copy's literals and
   list every library member that also defines the copy. For provider plans, settle project object
   vs archive member with the toolchain's stationery file lists (`*.mcp.xml` FILELIST/overlay) and
   DWARF producer, read-only, cited by file and line (never an install path).
   Hand edits only through json.load/json.dump (never hand-built strings). Windows paths in
   Python source must be raw strings (r"Z:\dev\...") - in a normal literal `\a`/`\f` become
   control characters (happened twice); use a quoted heredoc (<<'EOF') or the Write tool for
   scripts. A control character in a plan string is a rejection.
   Replans after a graph refresh: start from a fresh draft and reuse the earlier plan's notes and
   evidence (the old plan file is kept beside it as `<slug>.prev.json` when the parent says so).
4. `source plan validate --plan build/source-plans/<slug>.json --check --fill-annotations`, then
   `--check` again, then `source plan draft --check build/source-plans/<slug>.json`; all ok.
5. `progress work handoff --item <id> --owner <OWNER> --summary "<owners N, unresolved U, retire R,
   open rows decided K>" --evidence "plan build/source-plans/<slug>.json sha256:<hex>; validate --check
   ok; draft --check ok" --expected-revision <rev>`.

Write only build/source-plans/<slug>.json, <slug>-evidence.json and scratch under
build/source-plans/<OWNER>/. No src/, Ghidra, memory or issue ledger. Report <= 6 lines per item:
counts (drafted vs hand-decided), plan sha256, what a scrutinizer should check first, tool gaps.
