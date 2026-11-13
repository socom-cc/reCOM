# Stage 3 plan reviewer brief (token-lean)

You independently review the plans named in your prompt, as ACCEPTER. AGENTS.md is already in
your context: do not re-read it. Read docs/reconstruction/RECONSTRUCTION.md from "## Plan item"
to the end of "### Dead entry reads", and build/batch-helpers/PLANNER.md (the planners' rules).

Use the tools; do not write your own decoders or scanners:
`recon facts --item <id> --output build/verifier-s3/<ACCEPTER>/<slug>.txt` (argument reads on any
path, exit v0/f0 sources, every call site with argument setup and v0/f0 use, slots, data refs,
DWARF/stage 2), `recon asm --function <addr>`, `recon refs --object <func addr|symbol>` (a function's table words, address sites, calls), `recon dwarf --name <symbol...>` or `--address <hex...>`, `recon live --item <id>` (all live names and
signatures in one call; `--function <addr...>` for callees outside the group), `recon types <names...>` (unique/missing/ambiguous in one call) and
`recon refs --object <symbol|addr>` (vtable slots; every code access to a global), `recon bytes --address <symbol|addr>` (initialized bytes, relocated words, strings), `recon void --function <addr>...` (rules-v6 void verdict with the blocking reader or caller chain: use it for every hand-written void row) and
`recon dwarf --die <offset>` (a DWARF entry with its children).
For a virtual, `recon void` also prints its vtable slot family verdict (rules v18, decision 2026-10-23): when it is void, a partial or non-void row for any member is a finding; a blocking override it names is evidence against a void row.
Ghidra MCP only for get_struct_layout.

Per plan (slug = id with "socom:" -> "socom-" and ":" -> "-"):
1. Plan matches its cited sha256 and the item is awaiting_acceptance (check again right before
   deciding); `recon validate --plan <plan>` passes; `recon program` into
   build/verifier-s3/<ACCEPTER>/ equals build/apply/<slug>-apply.json;
   `ghidra preflight-batch --program build/apply/<slug>-apply.json --output build/verifier-s3/<ACCEPTER>/<slug>-preflight.json`
   is ok with skips exactly the plan-unresolved functions.
   `recon draft --check build/recon-plans/<slug>.json` is ok: every row carrying `draft_rule`
   is exactly what the rules give (the tool proves those rows; do not re-review them), and no
   row claims a rule the tools did not apply.
2. Review only the rows WITHOUT `draft_rule` (the planner's open rows). Get their facts with
   `recon facts --function <addr> <addr> ...` (not --item). An open row that the rules could
   have decided is not a finding. Check EVERY open prototype against the facts: declared registers cover "args read before write";
   return type agrees with the exit lines and the callers' v0 use (positive width evidence
   only); bool vs uchar per the rule; receivers vs statics against the a0 column; restated
   stage 2 prototypes equal live. Check every global against its data refs and .symtab size.
   Check unresolved reasons: an unresolved function whose facts prove a full contract with
   spellable unique types is a finding.
   Partial rows (`prototype.partial`): validate checks the shape, the contradiction against
   `live_signature` and noreturn from the ELF; preflight-batch checks `live_signature` is still
   live (partial rows apply, they are not skips). Review each parameter's evidence and that the
   live signature is really disproven; a provable return (so a complete row) or a live type the
   facts do not disprove is a finding. Against Ghidra's default live signature a partial row
   needs no contradiction but every parameter typed (validate refuses `undefinedN`). A complete
   varargs row (`varargs: true`) needs its return decided by the usual rules (`recon void`).
   `dead_reads` rows: validate proves `masked` ones; for `unreachable` check why the named
   branch direction cannot happen.
   Recon repair plans (`socom:work:recon-repair-NNN`): no `recon draft --check`; check each
   row's `repair` reason against the facts and that `live_signature` is what `recon live` shows.
3. Decide: `progress work accept --item <id> --accepter <ACCEPTER> --evidence "<data-derived
   summary>" --expected-revision <rev>` or `progress work reject --item <id> --reviewer
   <ACCEPTER> --reason "<every finding: address, what is wrong, the evidence, the fix>"
   --expected-revision <rev>`. Read the revision right before; retry on conflict; check exit
   code AND JSON "ok".

Ghidra is read-only (no POST, decompile_function, disassemble_bytes, get_function_variables,
analysis, set_/rename_/create_/apply_/delete_/remove_/save_; no fingerprint). Scratch only under
build/verifier-s3/<ACCEPTER>/. No tracked files, memory or issue ledger.

Final report: at most 8 lines - per item: decision and the one-line gist of any finding; then
tool gaps if any.

Tracker lookups: `python tools/socom.py progress sql "SELECT ..."` (tables work_items, stages,
symbols, relocations, issues) instead of loading the JSON files yourself.

Header citations: PS2 SDK headers are not in the workspace. A row whose only evidence is a
recalled SDK declaration (eekernel.h, libvu0.h, sif*.h, ...) is a finding: every parameter
and the return must be proven by asm, callers, DWARF, mangled names or types/prototypes
already accepted live (issue b8acf0d9).

Scratch files: several agents run at once. Name every scratch file or folder after your
OWNER/ACCEPTER (e.g. build/verifier-s3/<owner>/), never a shared name like fill.py.

Integer sign evidence: reject `uint` (or `int`) typed only from `sltiu`/`sltu` or from a sign extension the callee applies to all 32-bit values; require positive evidence as in PLANNER.md. A DWARF-typed function-pointer member that stores a function is a valid declaration for it.

Function-pointer tables (table-family rule, decision 2026-10-24): for an open row whose width rests on a table
family, rerun `recon table-family --table <symbol|addr>`. Accept it only with `VERDICT <width>` equal to the
row's return and the function listed as an entry of that column. `VERDICT open`, a CONFLICT line for the row, or a
width that rests only on the dispatcher's or a caller's andi/sb/sh is a finding.

Rules v19 (decision 2026-10-24): `recon draft` and `recon void` default to rules 19, which also end chains at
integer-width table-family entries (f0), constructors returning this (f0) and slot families joined through a base
without a vtable; a null argument fits any pointer parameter in callback readings. `recon draft --check` keeps the
plan's own rules (`draft.rules_version`; plans drafted before v19 are checked under v18, and the JSON shows
`rules_version`); a v19 plan's hand-written rows must agree with the v19 decisions. For a hand-written void row in a
pre-v19 plan, `recon void` (v19) is the evidence; `--rules 18` reproduces the earlier verdict. `recon facts` no
longer links one switch's jump to another switch's cases, and shows a jump-table load left in v0 as
`case-address(...: no value)`.

Rules v21 (decision 2026-10-30, now the default): an exit holding only the result of a call or tail call through a
vtable slot whose whole slot family is void leaves no value. Accept a void row on it only when `recon void` itself
prints the VERDICT void for the function (or its slot family) and its `slot call ...` lines show each such call
proven (object class, vptr +N -> `__vt__...+0x..`, family `void`). A `no vtable slot proven` line, or a slot argued
by hand that the tool cannot prove (e.g. through MSL vector storage typed `unsigned long *`), is a finding against a
void row that rests on it. `recon draft --check` keeps each plan's own `draft.rules_version`; `--rules 20` gives the
earlier verdicts. Withdrawal rows (`withdraws_return`) of a live void must cite the v21 open verdict verbatim; a void
v21 proves is not withdrawn.

Pointer returns proven by callers (decision 2026-10-30; precedents 0x14fd38 sceDmaGetChan, CSTable::FindString):
accept a pointer return when a caller stores the function's UNCHANGED v0 (only plain moves between the call and the
store) into a member whose DWARF type is that pointer; check the store site, the member offset in `recon dwarf`, and
that the row's return equals the member's DWARF type. A conversion, arithmetic or compare first, a store into an
integer or `void *` member, or into a slot with no DWARF record (stack temp, untyped global, an offset no member
covers) proves nothing: such a row is a finding.
