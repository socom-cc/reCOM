# Stage 3 planner brief (token-lean)

You plan the stage 3 group(s) named in your prompt, as OWNER. AGENTS.md is already in your
context (CLAUDE.md imports it): do not re-read it. Read docs/reconstruction/RECONSTRUCTION.md
from "## Plan item" to the end of "### Dead entry reads" only.

Tools do the analysis; do not write your own decoders, CFG scanners or caller scanners:
- `python tools/socom.py recon facts --item <id> --output build/facts/<slug>.txt` - per function:
  demangled name, compile unit, DWARF and stage 2 prototype, data refs, argument registers read
  before write on ANY path, what sets v0/f0 at every exit (delay slots included), vtable/table
  slots, address-taken sites, and EVERY ELF call site with the caller's argument setup and the
  caller's first use of v0/f0 (andi 0xff, store width, test, overwritten, passed on).
  Also stack arguments read from the caller's area and registers passed through unchanged to
  other calls. Paths are not constant-folded: a read on a branch that can never run is still
  listed - check such reads in `recon asm` before declaring them.
  `--callers N` shows more call sites; `--function <addr>...` for single functions (callees,
  overrides, callers). Only 12 callers are listed by default: before any claim about how
  callers use a result (narrowing, sign, unused), raise `--callers` to cover every call site.
  A byte/halfword store of a result is the destination's width, not the return's; Metrowerks
  narrows byte/short returns inside the callee (andi/sll-sra before jr ra).
- `python tools/socom.py recon asm --function <addr>...` - annotated disassembly from the ELF.
- `python tools/socom.py recon refs --object <symbol|addr>...` - a table's relocated slots
  (vtable slot -> function; use it for overrides) and every code access to a global.
- `python tools/socom.py recon dwarf --die <offset>...` - a DWARF entry (e.g. a subroutine
  type's return and parameters) with its children, compactly.
- `python tools/socom.py recon refs --object <func addr|symbol>` - table words, address formation
  and call sites of a function (callbacks, vtable entries) in one call.
- `python tools/socom.py recon dwarf --name <symbol...>` (or `--address <hex...>`) - DWARF records by exact name or address
  (a global's element type, a function's declaration) without knowing the DIE offset.
- `python tools/socom.py recon live --item <id>` (or `--function <addr...>` for callees
  outside the group) - every group function's live name and
  signature in one call (use it for current_name; do not call get_function_by_address per
  function).
- `python tools/socom.py recon types <name> <name> ...` - for each type name: unique, missing
  or AMBIGUOUS, with paths and sizes, in one call (do not call search_data_types per name).
- Ghidra MCP (read-only, program=socom.elf): only get_struct_layout for member offsets.

Recon repairs (`socom:work:recon-repair-NNN`): no draft; start from `recon evidence --item` and
`recon live --item`; every row adds `group`, `repair` (why the live state is wrong) and
`prototype.live_signature`, and must change the live signature (RECONSTRUCTION.md "Repair item:
recon repairs").

Per group (slug = id with "socom:" -> "socom-" and ":" -> "-"):
1. Revision: `python tools/socom.py progress audit --strict`; claim:
   `progress work claim --item <id> --owner <OWNER> --lease-minutes 120 --expected-revision <rev>`.
   Check exit code AND JSON "ok"; on conflict re-read and retry.
2. `recon draft --item <id> --output build/recon-plans/<slug>.json` writes the plan with every
   row a fixed rule decides (`draft_rule`: unresolved on missing/ambiguous/unspellable types or
   varargs; restated stage 2 prototypes; provable void methods). Do NOT change drafted rows;
   reviewers re-derive them with `recon draft --check`. Rows with `"draft": "open"` are yours (their `open_reason` says which rule condition failed):
   `recon evidence --item <id> --output build/recon-plans/<slug>-evidence.json`, then
   `recon facts --function <open addrs...> --output build/facts/<slug>.txt` (open rows only;
   read the file once). Replace each open row with a full row (drop the "draft" and "open_reason" keys).
3. Decide each prototype (assembly > relocations > DWARF/stage 2 > mangled name). Rules
   reviewers enforce:
   - Ghidra builtin names (uint, ushort, uchar, schar, longlong, ulonglong; EE long is 64-bit;
     Ghidra uint16 is 16 bytes). Class types only if exactly one /project type has the name.
   - Declare every argument register in "args read before write".
   - Return width only on positive evidence (the function's own andi 0xff / sll-sra before
     jr ra, DWARF-typed base/override, the returned member's own type, a table-family
     verdict, a value needing the width). A caller's or dispatcher's andi/sb/sh is its own
     destination width and proves nothing (decision 2026-10-24); a caller that only tests v0
     proves nothing; constant-only returns (0/1, -1/1) stay unresolved on width. `void` only if
     no exit sets v0 (see "exit" lines) and no override returns a value, except a `lui v0` used
     only as a load/store base with v0 unread at every call site, or a callee's result passed
     through when every direct caller leaves v0 unread and nothing takes the address
     (RECONSTRUCTION.md "Return width", decision 2026-10-20; `recon draft` decides most; `recon void --function <addr>...` prints the v6 verdict and the blocking reader or chain for any row). A returned relocated pointer to a string (`recon bytes --address <sym|addr>`
     shows .rodata/.data bytes, relocated words and strings) is `char *`.
     A pointer return is proven when a caller stores the function's UNCHANGED result into a
     DWARF-typed pointer member (decision 2026-10-30; precedents 0x14fd38 sceDmaGetChan ->
     `sceDmaChan *`, CSTable::FindString): v0 goes straight from the call into the member
     (`jal f; ... sw v0,k(s0)`, only plain moves between) and the class's DWARF record types the
     member at +k as a pointer; that member type is the return. Cite the store site, the member
     and its DWARF type. A conversion, arithmetic or compare on v0 first, a store into an
     integer or `void *` member, or a store into a slot with no DWARF record (stack temp,
     untyped global, offset no member covers) proves nothing.
     `__sinit_*` static initializers are void(void) whatever v0 holds (runtime table contract;
     `recon draft` decides them).
     A virtual is void when `recon void` says its vtable slot family is void (an override's own body proves void and no override writes a value a caller reads; rules v18, decision 2026-10-23; `recon draft` drafts P-slot-void, @N@ stubs stay yours with a void return); a blocking override it names keeps the return open.
   - `bool` where a declaration says bool (mangled b, `_b` callback type, header, DWARF
     base/override), else uchar. Globals: a proven 1-byte flag (only tested against 0,
     stored 0/1, an sltu result or a bool parameter, no arithmetic) is `bool` (user decision
     2026-10-24; the bridge resolves `bool` to Ghidra's builtin since 1e9dfac; repair 005
     precedent); other byte globals stay uchar. A function returning such a bool global's
     value unchanged (other exits 0/1) is proven `bool`.
   - A parameter passed unchanged into a callee's typed parameter is NOT width/sign evidence
     for this function (a consumer's type proves nothing about the producer; group 129,
     group 309 review). Cite callers' typed arguments, entry narrowing/extension, or signed
     compares instead; otherwise the parameter is unproven.
   - Static member: prove a0 at every call site (facts "a0=" column) is not a receiver.
   - Thunks: only an 8-byte body `j target` (or `b target`) with a `nop` delay slot is a
     Ghidra thunk; it shares its target's signature, so its row may only restate the target's
     planned prototype (`recon validate` enforces it). A this-adjusting stub
     (`j target; addiu a0,a0,-N`, names like `@128@Method`) is NOT a thunk: its receiver is
     the inner base part at +N (precedent CZSealBody::@272@GetRootPart, `CBody * this`).
   - Constructors (`__ct__`) return `void *`, never `X *`: all 70 DWARF __ct records in the
     program declare `void *`. Type a no-DWARF constructor `void *` when every exit returns
     the entry a0.
   - A header declaration counts only when its source is in the workspace or the program
     (DWARF, mangled names, a local runtime source, types/prototypes already accepted live).
     There are no PS2 SDK headers here: a declaration recalled from memory is not evidence,
     so an SDK row needs asm/caller/precedent proof of every parameter and the return.
   - Unresolved, with the precise reason: missing struct/function-pointer types (no void *
     placeholders), ',' or '&' or ambiguous type names, by-value class returns, varargs,
     VU-register inputs, boundary defects.
   - Partial row (decision 2026-10-22; RECONSTRUCTION.md "Partial prototypes"): only when the
     live signature (`recon live`, copied verbatim into `live_signature`) contradicts the proven
     parameters (count, order, a type the facts disprove) and the return is unprovable. Set
     `partial: true`, return `undefined`, `calling_convention`, `varargs`, per-parameter
     `evidence`, `contradiction`; keep `unresolved` = why the return stays open. `noreturn`
     (+ `noreturn_evidence`) only when no path returns; it is recorded, never applied. A va_list
     is a plain parameter (`undefined4` if no type is proven). Never on thunks or drafted P- rows.
     Also allowed when the live signature is Ghidra's default (`undefined NAME(void)`, with or
     without `__stdcall`): then `contradiction` is optional and EVERY parameter needs a real type
     (an `undefinedN` parameter keeps the row unresolved, e.g. `_printf_r` without `_reent`).
   - Varargs with a decided return (a `recon void` verdict of void, or a proven width): a complete
     row with `varargs: true` + `varargs_evidence` (e.g. fprintf), not a partial row.
   - `dead_entry_reads` only with the masking instructions as evidence; a dead read outside the
     entry block goes in `dead_reads` (per site, `kind` masked or unreachable + `branch`/`direction`;
     RECONSTRUCTION.md "Dead entry reads"). No renames without
     strong evidence. Globals only when every access proves the type (facts data refs).
4. Complete build/recon-plans/<slug>.json (keep its "draft" block); run `recon validate --plan ...`,
   `recon program --plan ... --output build/apply/<slug>-apply.json`, and
   `ghidra preflight-batch --program build/apply/<slug>-apply.json --output build/preflight-recon/<slug>.json`
   until all pass and every skip is a function you marked unresolved.
5. Hand off: `progress work handoff --item <id> --owner <OWNER> --summary "<N prototypes, U
   unresolved, G globals>"' (totals only, computed from the plan file; no breakdowns - a wrong
   sub-count cannot be amended) --evidence "plan build/recon-plans/<slug>.json
   sha256:<sha>; recon validate ok; preflight-batch ok (<calls>)" --expected-revision <rev>`.
   Evidence is immutable: data-derived, checked facts only. Do not cite counts no tool
   reproduces (e.g. virtual call sites per vtable slot); cite the facts the tools print.

Never mutate Ghidra (no POST, decompile_function, disassemble_bytes, get_function_variables,
analysis, set_/rename_/create_/apply_/delete_/remove_/save_; no fingerprint). Write only your
groups' files under build/recon-plans/, build/apply/, build/preflight-recon/, build/facts/.
No tracked files, memory or issue ledger. Do not spawn agents.

Final report: at most 8 lines - per group: id, prototypes/unresolved/globals, plan sha256;
then only contradictions or tool gaps (e.g. a fact `recon facts` got wrong or lacks).

Tracker lookups: `python tools/socom.py progress sql "SELECT ..."` (tables work_items, stages,
symbols, relocations, issues) instead of loading the JSON files yourself.

Scratch files: several agents run at once. Name every scratch file or folder after your
OWNER/ACCEPTER (e.g. build/verifier-s3/<owner>/), never a shared name like fill.py.

Integer sign evidence (review of group 226, 2026-10-23): `sltiu`/`sltu` alone does not prove an unsigned declared type (Metrowerks emits it for DWARF `int`, e.g. CWeaponSel::SetItemPos bounds checks). Use positive sign evidence only: entry narrowing (andi 0xff/0xffff, sign/zero extension the callee itself applies to the argument), signed compares/divides on the value, DWARF or mangled types, or callers' argument extension. A callee's `dsll32/dsra32` that it also applies to plain 32-bit loads is not sign evidence.
A function stored into a DWARF-typed function-pointer member (e.g. ThreadParam.entry `void (*)(void *)`) takes that member's type as its declaration, like a callback passed to a typed call.

zAnim command callbacks (scan build/facts/zanim-commands.md, screen build/facts/repair-004-screen.md): functions registered via CZAnimMain::AddCmd (a2 parser, a3 begin, t0 tick, t1 end; DWARF zanim_cmd DIE 0x9dd1e) take that member's type as their declaration: parser `_zanim_cmd_hdr * (_zrdr *)`, begin/end `void (_zanim_cmd_hdr *)`, tick `bool (_zanim_cmd_hdr *, float *)` (AddCmd mangled `_b`); Class:: callbacks are static (dispatch passes the record/zrdr in a0). Confirm each body reads nothing beyond that contract. Thunks (e.g. CTDoor -> CTMove) restate their target's row.

Function-pointer tables (table-family rule, decision 2026-10-24; RECONSTRUCTION.md "Return width"): a function
stored in a data table column that an indexed jalr dispatches (e.g. UICommandTable +0x8, zAnimUIMenuTick) shares
the column's return width. Run `recon table-family --table <symbol|addr>`: on `VERDICT uchar` (or another width)
every entry takes that return, even a constant-only one; cite the verdict line and its witness (e.g. "recon
table-family UICommandTable: VERDICT uchar; witness UINetCnfUninit andi v0,v0,0xff@0x1d20b4"). On `VERDICT open`
the width stays unproven unless the row has its own evidence; the CONFLICT entries say why. Parameters still come
from the usual rules.

Rules v19 (decision 2026-10-24, "Yes, all three"; RECONSTRUCTION.md "Return width"): `recon void`/`recon draft` now end
leftover v0/f0 chains at (1) function-pointer table entries whose `recon table-family` verdict is an integer width (f0
is never read through them, e.g. UICommandTable's UISysPostInit), (2) `__ct` constructors that return this and have no
table/address refs (CSaveModule::CSaveModule), and (3) slot families joined through a base without its own vtable
(CTextureRelocMgr::PreGetSprPacket + CDblBufTextureRelocator::PreGetSprPacket). A null argument now fits any pointer
parameter when reading a callback's declared type (CZWeapon::PreTick via AddTask). These only remove blockers; trust
the VERDICT line. `recon facts` gives each switch `jr` only its own jump table's cases, so reads and exits that came
from another switch's cases are gone; a jump-table load left in v0 shows as `case-address(...: no value)`, not a value.

Rules v21 (decision 2026-10-30, "call through a void slot family"; default for `recon void`/`recon draft`;
RECONSTRUCTION.md "Return width"): an exit whose v0/f0 holds only the result of a call or tail call through a vtable
slot whose whole slot family `recon void` decides void leaves no value. So a function whose exits leave only such
results is void with no caller check (`VERDICT void: every exit leaves v0 and f0 unset or holding only the result of
a call or tail call through a vtable slot whose whole slot family is void ... (rules version 21)`), such an override
witnesses its own family (C2DButton::SetBackgroundAlpha 0x393a00 -> SetTrans; CEntity::OnDeath 0x1ee390 ->
CEntityCtrl::OnDeath), and a void-slot tail jump no longer blocks pass-through. The tool must prove the slot: each
`slot call ...` line shows the object's class proof (this, a mangled class-pointer parameter, DWARF-typed members),
the vptr its constructor stores and the slot word; `no vtable slot proven` means the call proves nothing (e.g.
CUIVariable::UpdateDependents 0x39e8d0: m_attached_items is DWARF `unsigned long *` storage, so it stays open). Do not
argue a slot by hand where the tool cannot prove it. Verdicts v20 already proves keep their exact line; a void only
v21 reaches ends with `(rules version 21: ...)` or names rules version 21.
