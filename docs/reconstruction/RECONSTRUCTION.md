# Stage 3: Ghidra reconstruction

`ghidra-reconstruction` finishes what the DWARF import left: function
prototypes, names, and the globals those functions touch. Work is split into
callee-first groups. Each group has a file-only plan item and a live apply
item, the same plan/apply split as the debug import.

## Decomposition

`python tools/socom.py progress decompose-stage --stage ghidra-reconstruction
--expected-revision <n>` replaces the stage seed once `debug-metadata-import`
is accepted and its baseline is recorded (`progress record-stage-baseline`).
It builds the groups with `recon graph`, which reads only the immutable ELF:

- a function is a sized `FUNC` symbol (9,703 of them); Ghidra's extra
  functions and boundary defects are outside these groups;
- an edge is a `jal` to another function's start or a `j` tail call to one,
  decoded from the instruction, so calls through section symbols count;
- a call to a function's own start is self-recursion, not an edge; a target
  inside another body or outside every function is an anomaly (two, both
  into the unsized crt0 code at `0x1401d0`);
- recursive components stay in one group; a component's height is the longest
  chain of components it calls; groups take whole components of one height in
  address order, at most 32 functions each.

Indirect calls (vtables, function pointers) are not edges, so a group can
reach code that is not yet planned. Record such contracts in the plan's
notes; do not wait for them.

Every plan item depends on the apply items of the groups holding its direct
callees, so callee prototypes are live before callers are planned. Every apply
item depends on its plan. The seed keeps its ID, because later stages depend
on it, and becomes the stage gate: a reviewed item that waits for every apply.

Type gaps the debug import left (vtable pointers, RTTI records,
function-static locals, pointer-to-member data, multi-dimensional arrays; see
the open `b` issues) do not block function groups. Member offsets are already
correct, so adding a vtable pointer later does not move any field a prototype
uses. Those gaps get their own items when their tools exist.

## Plan item: `recon-plan-group`

Role `socom-recon-planner`. The packet lists the commands and allowed paths.

```powershell
python tools/socom.py recon evidence --item <plan-item> --output build/recon-plans/<slug>-evidence.json
python tools/socom.py recon validate --plan build/recon-plans/<slug>.json
python tools/socom.py recon program --plan build/recon-plans/<slug>.json --output build/apply/<slug>-apply.json
```

The evidence file is the starting point, not the answer. For each function
it gives the ELF names and demangling, the compile unit, the DWARF record and
what stage 2 did with it (prototype or skip reason), the argument registers
read before any write in the entry block, direct callees with their call
sites, callers, and every data address the function's `LO16`/`GPREL16`
relocations prove, with the object holding it.

The planner then reads live Ghidra (read-only) and writes the plan:

```json
{
  "kind": "socom-ghidra-recon-plan",
  "schema_version": 1,
  "work_item_id": "socom:recon-group:<id>",
  "group_sha256": "<from the evidence file>",
  "target": {"source_sha256": "00c9cee7f75b921fda1e848d04f64881b5a0b7841300591cac91371bb23d4f8a"},
  "functions": [
    {
      "address": "0x142250",
      "current_name": "<live name>",
      "rename": null,
      "prototype": {
        "return_type": "void",
        "parameters": [{"name": "block", "type": "void *"}],
        "evidence": ["a0 read at entry; DWARF parameter 'block'"]
      },
      "notes": []
    },
    {
      "address": "0x142bf0",
      "current_name": "<live name>",
      "prototype": null,
      "unresolved": ["receiver unproven: no vtable slot, no caller passes a0"]
    }
  ],
  "globals": [
    {
      "address": "0x5e1234",
      "current_name": "<live name>",
      "type": "CFoo *",
      "rename": null,
      "size": 4,
      "replaces_accepted": false,
      "evidence": ["written at 0x142c10 with the CFoo constructor's result"]
    }
  ]
}
```

### Drafted rows

`recon draft --item <plan-item> --output build/recon-plans/<slug>.json` starts
the plan. It decides the rows that a fixed rule settles, and marks every other
row `"draft": "open"` for the planner:

- `U-type`: unresolved. A mangled parameter class, or the class of a receiver
  proven by a const method or a constructor/destructor, is absent from the
  live program, names several live types, or contains `,` or `&`. A type that
  exists only as a provisional `NAME@hash` copy or in another case stays open.
- `U-vararg`: unresolved. The mangled signature ends in `...`.
- `U-byvalue`: unresolved. A mangled parameter is a class passed by value
  whose DWARF class or struct records (or live type) exceed one GPR slot (8
  bytes). Metrowerks passes such an aggregate as its address in a GPR
  (`Particle::Source::CheckExtents` 0x2392d0 reads its 16-byte CPnt4D as
  `lwc1 0..12(a1)`, the caller passing `addiu a1,s1,32`), while Ghidra's
  r5900 `__stdcall` (integer argument registers `maxsize="8"`) puts it on the
  stack, so no prototype gives it its storage. An aggregate of up to 8 bytes
  travels in the register itself only when its copy is trivial
  (`C2DBitmapPoly::SetCenterPos` takes PNT2D in a1: `ld a1` in every caller,
  `sd a1,56(sp)` at 0x2fe4d0; `list::const_iterator` arrives as `lw a1,N(sp)`
  at 0x197190). A class whose copy is not trivial travels as the address of
  a caller temporary whatever its size (review of repair 017): the 4-byte
  CAiMapLoc (user copy constructor) reaches
  `CSealCtrlAi::HandleFollowTickHideCheck` 0x2e1510 as `addiu a3,sp,568`, and
  `list::iterator` reaches 0x1d8470 as `addiu a1,sp,N`, read through
  `lw v1,0(a1)`. Copy-constructor symbols do not decide it (both iterators
  have one), so a decided prototype whose by-value DWARF class, struct or
  union parameter some direct caller sets to an address in its own frame
  (`addiu rN,sp|fp,imm`) becomes `U-byvalue` too; a function without direct
  callers keeps the size rule. This guards every rules version (coordinator
  decisions of 2026-10-29 and 2026-10-30).
- `U-storage`: unresolved. A decided prototype has a parameter Ghidra's r5900
  `__stdcall` would store elsewhere than Metrowerks passes it. The cspec has
  no `<rule>` groups, so a ninth float takes the next free `a0`-`t3` in
  Ghidra, while Metrowerks puts floats 9 and on in 8-byte stack slots from
  +0 after the other overflowing arguments (`collideCylinders` 0x254d90:
  floats 9-13 at incoming +0x0..+0x20, its `CPnt3D &` arguments in a0/a1;
  review r108). Ints past t3 go to the stack in both, so only a float that
  finds a GPR free in Ghidra differs, together with every argument after it.
- `P-stage2`: the stage 2 DWARF prototype is restated. This requires every
  type to name one live type, every argument register read on any path to be
  declared, no VU0 instructions, and, for `void`, every exit to leave v0 and
  f0 unset.
- `P-void`: a `void` prototype from the mangled signature. This requires
  every parameter type to resolve, the read registers to be declared, every
  `jr ra` to leave v0 and f0 unset, no VU0 instructions, and no word refs or
  address-taken sites (so no override or callback contract applies). A
  method's receiver must be proven by a const method, or by a register read
  beyond the parameters. Exits may also hold a callee's result when the
  "Return width" pass-through conditions hold (rules version 4).
- A stage 2 prototype returning `void` is restated even when v0 or f0 holds
  a value at an exit, when its DWARF record declares an explicit `void`
  (FT_void) or the leftover is provably unread (rules version 12). DWARF 1
  has no `bool`, so the records spell it `uchar`; a parameter the mangled
  signature declares `b` keeps `bool`.
- A destructor (`__dt`) is `P-dtor` as `void * (X * this, short
  __dtor_flags)`: every DWARF `__dt` record declares a `void *` return and
  the local Metrowerks CPlusLib.h declares the flags argument `short`; the
  body must read only a0/a1, leave a1 unread or sign-extend it from 16 bits,
  and return the entry a0 at every exit. A function whose DWARF record
  declares any non-void return (including a struct returned through a hidden
  pointer, which leaves v0 untouched) is never drafted `void` (rules
  version 14).
- A `__sinit_*` static initializer is `P-void` as `void (void)` whatever v0
  holds at its exits. It must have no mangled name, no argument reads, no
  direct call sites, only `jr ra` or tail-jump exits (rules version 9), and
  its `.p__sinit` table word as its only reference. The runtime fixes the contract: `__initialize_cpp_rts`
  calls each one through the `void (**)(void)` table and never reads v0, so a
  `__register_global_object` result left in v0 is residue (rules version 3).
- `P-slot-void`: a `void` prototype for a virtual function whose vtable slot
  family is void (rules version 18; see "Return width"). It takes only rows
  the older rules leave open. A stage 2 prototype returning `void` is
  restated; otherwise the mangled signature gives the parameters, and the
  vtable slot proves the receiver (a function stored in a vtable is a virtual
  member, so a0 is `this`). Every parameter type must resolve, the read
  registers must be declared, and there must be no VU0 instructions. A
  this-adjusting `@N@` stub stays open, because its receiver is the base part
  at +N. From rules version 20 a family declared void by DWARF (see "Return
  width") counts too, and from rules version 21 a family void through calls
  into void slot families.

Rows keep their `draft_rule`. Planners do not edit them.
`recon draft --check <plan>` re-derives them and fails on any difference, or
on a row claiming a rule the tools did not apply. It uses the rules version
the plan records in `draft.rules_version` (19, 20 or 21); a plan drafted before
rules version 19 is checked under version 18, the version every accepted plan
was last validated with, and `--rules N` overrides it. New drafts use rules
version 21. Reviewers run it and then
review only the open rows. A row written by hand that the rules
now decide must agree in substance: unresolved, or the same types. Before adoption, the rules (version 2) reproduced
the decision of all 95 accepted plans for every row they decided: 868 of
3031 functions, with no mismatch.

### Type spelling rules

- Write fundamental types as the Ghidra builtins the DWARF import uses:
  `uint`, `ushort`, `uchar`, `schar`, `longlong`, `ulonglong` (EE `long` is
  64-bit). The executor accepts only builtin names, so a C spelling such as
  `unsigned int` or `long long` would resolve to nothing and the prototype
  would be skipped; `recon validate` refuses them.
- A type name must resolve to exactly one program type, ignoring case.
  `ghidra preflight-batch --program build/apply/<slug>-apply.json` dry-runs
  the program against live Ghidra and lists every skip; run it before
  handoff.
- Do not use `void *` as a placeholder. Use it only where the original
  declaration is `void *` or the pointee is untyped. When the right type is a
  struct or function-pointer type the program does not have yet, leave the
  function unresolved and name the missing type, so a later type item can
  add it.
- The bridge parses prototypes with Ghidra's `FunctionSignatureParser`, which
  splits at every comma and looks types up by bare name. Template names with
  `,`, names with `&`, and names shared by several types therefore stay
  unresolved for now.

### Incomplete call contracts

A prototype must carry the whole call contract (AGENTS.md). Leave a function
unresolved, recording the parts that are proven, when the contract includes
something a prototype here cannot express: VU0 register inputs (callers load
`vf` registers before the call, e.g. `_TransformPoint`), varargs whose
`va_list` or ellipsis cannot be expressed (see "Partial prototypes" for the
varargs flag), a by-value class result returned through a
hidden pointer, or a function-boundary defect in the live program.

### Return width

A caller that tests or uses `v0` without narrowing it proves nothing about
the return width: Metrowerks returns `bool`/`uchar` zero-extended, so callers
of `_zmalloc<four>::release` (DWARF `uchar`) test `bne v0,zero` directly.
Type a 0/1 or byte result as `uchar` (or `bool` where a declaration says
bool) only on positive evidence: the function's own narrowing of the value
it returns (`andi 0xff`/`0xffff`, or `sll`/`sra` by 24 or 16, before `jr ra`), a
DWARF-typed override or base, the returned member's own type, or the
table-family rule below. A caller or dispatcher that narrows the result into
its own destination (`andi`, `sb`, `sh` after the call) proves only that
destination's width, never the callee's return (decision of 2026-10-24):
Metrowerks narrows a byte or halfword return inside the callee. Otherwise
leave the width unresolved; never infer `int` from the absence of narrowing.
Spell a one-byte boolean `bool` only where a declaration says bool (a header,
a mangled `b`, a DWARF-typed base or override); otherwise `uchar`, which is
how the DWARF import renders this compiler's bool.

`void` needs every exit to leave no value in `v0` and no override to return
one. One kind of leftover `v0` still allows `void`: the only definition
reaching the exit is a `lui v0` used solely as the base register of later
loads or stores (`lui v0,%hi(x); sw a0,%lo(x)(v0)`). This holds only when no
call site reads `v0` after the call.

A callee's result left in `v0` also allows `void` (decision of 2026-10-20).
`void f() { g(); }` and an unused `int f() { return g(); }` compile
identically, so this is a choice the caller decides. It applies when every
exit's `v0` and `f0` hold nothing or a callee's result (a `jal`/`jalr` or a
tail `j`), every direct call site leaves `v0` unread on every path, and nothing takes
the function's address or stores it in a table. A caller that returns the
value to its own callers passes the question on: its call sites must leave
`v0` unread in turn, and nothing may take its address (followed twelve levels
deep, rules version 17). `recon facts` follows `v0` through callees that leave
it untouched (also at tail-call exits, rules version 5), so a leftover that is really the function's own value shows
as such. A `syscall` writes `v0`: the EE kernel returns its result there,
so a kernel stub (`li v1,N; syscall; jr ra`) exits with
`v0<-syscall-result(v1=N: kernel value, width unknown)` and `recon void`
leaves it open unless something else proves `void` (until 2026-10-30 the
stubs showed `v0<-entry` and were wrongly proven void without a caller
check). A scratch value also allows `void` (second decision of 2026-10-20): a
copy, constant or arithmetic result left in `v0` or `f0` that another
instruction in the function also reads (it was stored, moved to the FPU,
passed on, or used as a base) is a temporary, under the same caller
conditions. A value computed only to be returned (a lone `li v0,0` before
`jr ra`) keeps the return unresolved. The caller conditions apply to `v0`
and to `f0`, for each register the function can leave a value in, and a
caller that tail-calls the function passes the question on like one that
returns its value (rules version 6). `recon facts` follows a value past
calls that may leave it untouched, so a caller that reads it after such a
call counts as a reader. A chain stops at a caller whose DWARF record
declares an explicit `void` return: code compiled against that declaration
never reads the value, even when the caller's address is taken (rules
version 8). A chain also stops where the caller's DWARF record declares a
return in the other register class: an integer or pointer return (read from
v0) ends an f0 chain, and a `float` return (read from f0) ends a v0 chain
(rules version 10). A function whose address is only formed in code and
passed straight to a direct call is a callback: when the callee's mangled
parameter at that argument register is a function pointer, its declared
result type is the callback's contract. A chain ends at such a callback
when the declared result is `void` or lives in the other register class,
and a callback declared `void` with no direct callers is `void` by that
declaration (rules version 11). Which argument register maps to which
parameter is settled by requiring every argument register to fit the
reading (function addresses only where the parameter is a function pointer). A
virtual function referenced only from vtables takes its slot's contract:
classes linked by DWARF inheritance form a family, functions at the same
vtable offset with the same method name are one virtual, and when the DWARF
records among them agree on one return class (and none disagrees) every
function in the slot has it (rules version 13). A `__dt` destructor that
keeps the Metrowerks contract returns `this` in v0, so an f0 chain ends there
(rules version 16).

A vtable slot family is void as a whole when one override proves it
(decision of 2026-10-23, "Yes, with a conflict check"; rules version 18). C++
gives every override the base's return type. The family is every function
in one virtual function's vtable slots. Each `__vt__` table is split into
blocks: an RTTI header word, the complete-object offset, then the slots. A
block starts at the table's start and at each relocated word that names an
`__RTTI__` record. Slot i of a class's block at subobject offset N is slot i
of the primary block of every base that the class's RTTI base list places at
N. A `@N@` stub joins the overrider it jumps to, and a function stored in
several slots joins all of them. One member must prove void with its own
body: every exit is `jr ra` with v0 and f0 unset, its argument reads fit its
mangled signature (so it is no struct returned through a hidden a0), and no
DWARF record declares a return. If no member writes a value that a caller
reads, `recon void` gives VERDICT void for every member. A member blocks the
rule in four cases. Its DWARF record declares a non-void return. An exit
holds its own value: not a callee's result (an indirect tail call counts as
one) and not a scratch value. It leaves a value and its address is formed in
code or stored outside vtables. Or a direct caller reads what it leaves,
followed through callers that return it as above; a caller in the same
family hands the value to the slot, which ends that chain. This walk uses
the version 17 contracts, not other families' verdicts. Members whose
method names differ are not provably one virtual, so they decide nothing. A
void family also ends other functions' chains, like a declared slot
contract. `recon void --function` prints the verdict and the blocking chain.
For a function stored in vtables it also prints the family, the override
that proves void, and each blocking override with its reader. `--rules 17`
(also on `recon draft`) gives the earlier verdicts. Rules version 19 (below)
also joins families through a base that has no vtable of its own.

Table-family rule (decision of 2026-10-24, "Yes, with conflict check"). The
entries of one function-pointer table column share the column's declared
function-pointer type, so one entry's own narrowing proves the return width
of every entry. A column qualifies when an indirect call loads its target from
the table through a variable index (an array dispatch, not one constant slot of
a struct of function pointers). Example: UICommandTable's 147 handlers at +0x8
of 12-byte rows, called by `jalr` in zAnimUIMenuTick, some through thunks such
as 0x1d6af0. The row stride is the index's scale when the tool can trace it,
otherwise the smallest stride that keeps code addresses apart from other
words. A thunk entry stands for its target. A witness is an entry whose own
body narrows the value at an exit (`andi v0,v0,0xff` before `jr ra`:
UINetCnfUninit at 0x1d20b4) or whose DWARF record declares the width.
Narrowing a returned local, or a callee's narrowing, is consistent with the
width but is not a witness. The rule fails when the witnesses disagree or any
entry contradicts the width in one of four ways:

- It returns an unnarrowed or wider non-constant value: a word load, an
  argument, arithmetic, an unknown or DWARF-`int` callee result, or v0 left
  unset.
- It returns a value with the other sign extension (`lb` or `sll`/`sra` in a
  `uchar` column, `lbu` in a `schar` column).
- It returns a constant outside the width.
- It reads argument registers beyond the shared mangled parameters, or its
  mangled parameters differ from the column's.

Constants inside the width and 0/1 compare results (`slt`, `sltu`, `xori 1`)
fit any width. DWARF `uchar` functions return them unnarrowed (14 exits), so
they are never witnesses. The dispatcher's own narrowing of the result
(zAnimUIMenuTick's `andi v0,v0,0xff` at 0x1d027c) is listed but proves
nothing. `recon table-family --table <symbol|address> [--column N]
[--stride N] [--json]` lists each entry with its exit-value class (own
narrowing with width and sign, constant-only, 0/1 compare, typed callee or
member value, unnarrowed) and its argument reads. It prints `VERDICT
<width>` with the witnesses, or `VERDICT open` with the conflicting entries.
This is an evidence rule for planner rows, not a `recon draft` rule; only
its use as a contract that ends f0 chains (rules version 19, below) reaches
drafted rows.

Rules version 19 (decision of 2026-10-24, "Yes, all three") lets three more
contracts end a leftover v0/f0 chain, so the function that leaves the value
can be void. Each only removes a blocker: the conflict checks above still
apply and no type is asserted.

- A function-pointer table entry whose column has an integer `recon
  table-family` verdict is called only through the column's type, which
  returns in v0, so an f0 chain ends there, as at a callback declared to
  return an integer (rules version 11). Every reference to the entry must be
  a word of such a column: no address formed in code, no other table or
  vtable. UICommandTable's entries (UISysPostInit, UISetMenuState,
  OnRemoveEquipment, ...) end the f0 chains of the callees they return.
- A `__ct` constructor that returns its entry a0 in v0 at every exit
  (through plain copies) and whose address is never formed in code or
  stored keeps the `void *` contract of every DWARF `__ct` record, so an f0
  chain ends there, as at a destructor (rules version 16).
  CSaveModule::CSaveModule ends CSaveManager::RegisterModule's chain to
  `__sinit_fts_mission.cpp` (issue bab16750), so RegisterModule is void.
- A base class without a vtable of its own still links the blocks that
  place it. Its slots are a prefix of each such block, and a slot that holds
  one of the base's own (inherited, not overridden) methods proves that the
  prefix reaches it, so the slots up to there are one family across those
  blocks. zdb::CTextureRelocMgr::PreGetSprPacket in
  `__vt__Q23zdb15CBatchRelocator+0x10` joins
  CDblBufTextureRelocator::PreGetSprPacket in its own vtable's slot +0x10,
  and the base's empty body proves the family void.

Version 19 also closes a gap in the version 11 callback reading: a null
argument (`move a3,zero`) fits any pointer parameter, so a reading that a
null `void *` used to reject is tried again. CZWeapon::PreTick, passed in a2
to `CSched_Manager::AddTask(const char *, bool (*)(float, void *), float,
void *)`, takes the declared `bool` result, which ends
CZProjectileList::PreTick's f0 chain. A slot family's own walk uses these
contracts but still no other family's verdict. `recon void` marks a family
that version 19 joined. `--rules 18` (also on `recon draft`) gives the
earlier verdicts.

Rules version 20 (decision of 2026-10-29, C2D::Draw 0x300c70) lets DWARF
declare a slot family void. C++ gives every override the return type of the
virtual it overrides, so when the DWARF record of an override (not an `@N@`
stub) declares an explicit `void` return (FT_void), the family is void
provided no member's record declares another return, the members share one
method name, and every blocker is only a hand-off the walk cannot follow: a
caller that returns the value and whose address is taken or stored in a
table, or a chain deeper than twelve. A member whose exit holds its own
value, or a caller that reads the value, still blocks. C2D::Draw's v0
reaches the address-taken VisualGratification and CCycleButton::Draw
through C2DString::Draw, but 9 of the 18 Draw overrides in slot +0xc are
DWARF-void, so it is void. `recon void` prints `slot family declared void`
and `VERDICT void: its vtable slot family is declared void (rules version
20)` only where version 19 leaves the function open; a function version 19
already proves keeps its verdict line. Over all 9703 functions, versions
17-19 give the same verdicts as before and version 20 changes one verdict
(0x300c70). `--rules 19` gives the earlier verdicts.

Rules version 21 (decision of 2026-10-30, "call through a void slot
family") is the default. A function exit whose v0/f0 holds only the result
of a call or tail call through a vtable slot whose whole slot family `recon
void` decides void leaves no value. Such an exit counts as unset: a function
whose every exit leaves v0/f0 unset or holding only such results is void
without a caller check (`VERDICT void: every exit leaves v0 and f0 unset or
holding only the result of a call or tail call through a vtable slot whose
whole slot family is void, so it leaves no value (rules version 21)`), an
override like that witnesses its own family and blocks nothing, and a tail
jump through such a slot is no indirect-jump problem for the pass-through
rules. The slot must be proven from the ELF and DWARF (`recon_vcall`): the
jump register is a `lw` from a vtable pointer that is a `lw` from an object
pointer, each the only definition; the object's class is the proven
receiver `this`, a mangled class-pointer parameter, or reached from one
through DWARF-typed members (a by-value class member or base at an `addiu`
offset, a pointer member or an array of class pointers at a `lw` offset);
the class's own constructor or destructor stores one block of
`__vt__<class>` at the vptr offset; and the slot word is inside that block.
A member typed otherwise (an integer, `void *`, MSL's `unsigned long *`
vector storage) proves nothing, so the call stays unproven. Families that
witness each other through such calls settle to the least fixpoint, so no
verdict depends on query order. A function version 20 proves void keeps its
verdict line word for word; otherwise `recon void` lists each indirect call
or jump whose result reaches an exit with the slot it is proven to go
through (`slot call jr t9@...: this:C2DButton +0x170 _bmp:CPlainBmp vptr
+0xc -> __vt__9CPlainBmp+0x20; slot family ... (method SetTrans): void`),
and any void it reaches says it rests on rules version 21. Examples:
C2DButton::SetBackgroundAlpha (0x393a00, `jr t9` into SetTrans through the
embedded `_bmp`) and CEntity::OnDeath (0x1ee390, `jr t9` into
CEntityCtrl::OnDeath through `m_control`) are void.
CUIVariable::UpdateDependents (0x39e8d0) stays open: it iterates
`m_attached_items`, whose DWARF storage (`__vector_pod::data_`) is
`unsigned long *`, so the UIVarMixin element class is not proven. Over all
9703 functions version 21 turns 26 open verdicts void (2580 -> 2606 void),
changes only the blocker named by 6 open verdicts, and leaves every other
verdict line unchanged. `--rules 20` (also on `recon draft`) gives the
earlier verdicts; `recon draft --check` keeps each plan's own
`draft.rules_version`.

`recon facts` gives each proven switch jump (`lw v0,0(v0); jr v0` through a
jump table of the function) only the cases of its own table. Earlier every
switch reached every table's cases, so a register that the code between two
switches sets on every path looked live on entry (CSealCtrlAi::SetAiMode's
`lui a3` in the delay slot before its second switch: issue 790e12b3), and
jump-table loads looked like exit values (CTParam::Tick). The load a switch
jumps through is a case address, never a value: where a case leaves it in v0
at an exit, the facts show `case-address(...: no value)` and `recon
table-family` counts that exit as leaving v0 unset.

A function whose every exit returns a relocated pointer to a NUL-terminated
string (`recon bytes` shows the word's target and its text) returns
`char *`. The binary cannot show whether the pointee is `const`, so the plan
does not record it.

A caller that stores a function's unchanged result into a DWARF-typed pointer
member proves that pointer return (decision of 2026-10-30). The member's
DWARF type is the proof: v0 goes straight from the call into the member
(`jal f; ...; sw v0,k(s0)` with only plain copies between), and the DWARF
record of the class at that offset types the member as a pointer, so `f`
returns that pointer type. Precedents: 0x14fd38 `sceDmaGetChan`
(`sceDmaChan *`) and `CSTable::FindString`. Anything else proves nothing: a
conversion, arithmetic or a comparison on v0 before the store, a store into
a member whose DWARF type is an integer or `void *`, a store into a slot with
no DWARF record (a stack temporary, a global without a typed record, an
offset that no member covers), or a width alone. Cite the caller's store
site, the member, and its DWARF type in the row's evidence.

### Partial prototypes

Some live signatures come from Ghidra's library type archives (glibc parameter
order, the 160-byte `/stdio.h/FILE`) and contradict the code, while the return
cannot be proven (`__assert` never returns; `vfprintf`'s width is unobserved).
An unresolved row would keep the wrong signature, and callers would decompile
with wrong arguments. Such a row sets its proven parameters and leaves the
return `undefined` (decision of 2026-10-22):

```json
"prototype": {
  "partial": true, "return_type": "undefined", "calling_convention": "__stdcall",
  "varargs": false, "noreturn": true,
  "parameters": [
    {"name": "file", "type": "char *", "evidence": ["move a3,a0 at 0x3def4c: the second %s"]},
    {"name": "line", "type": "int", "evidence": ["move t0,a1 at 0x3def44: the %d"]},
    {"name": "failedexpr", "type": "char *", "evidence": ["a2 passes through as the first %s"]}
  ],
  "live_signature": "void __stdcall __assert(char * __assertion, char * __file, int __line)",
  "contradiction": ["glibc order: the code makes a1 the line and a2 the expression"],
  "noreturn_evidence": ["no jr; the only exit tail-jumps to abort (j at 0x3def64)"]
},
"unresolved": ["return: the function never returns, so no value is observable"]
```

- `recon validate` allows it where `live_signature` (verbatim from
  `recon live`) contradicts the parameters: another count, varargs, or a type
  at some position. A live `undefined*` type claims nothing. Every parameter
  needs evidence, `unresolved` says why the return stays open, and a thunk
  cannot be partial. The apply refuses before any write when the live
  signature has changed.
- It is also allowed where the live signature is Ghidra's default and claims
  nothing: `undefined f(void)`, or `undefined __stdcall f(void)` (the
  placeholder the signature repairs restore) (decision of 2026-10-22, "Yes,
  extend it"). Then `contradiction` is optional and every parameter needs a
  proven type: an `undefinedN` parameter leaves the row unresolved
  (`_printf_r` and `_sprintf_r` wait for `_reent`; `__svfscanf`, with three
  proven parameters, is partial).
- A recon repair row may also replace a live signature whose only defect is
  an unproven return (`withdraws_return`, see "Repair item: recon repairs");
  a group row may not.
- The bridge sends `undefined socom_prototype(...)`. Ghidra's
  FunctionSignatureParser resolves `undefined` to DataType.DEFAULT, and the
  decompiler keeps such a return unlocked. A register whose type nothing proves
  may be `undefined4` or `undefined8`; no complete row uses these types.
- `varargs: true` needs `varargs_evidence` and a fixed parameter. It appends
  `, ...`, which the parser turns into Ghidra's varargs flag, and registers
  after the fixed parameters may then be read. A `va_list` is an ordinary
  parameter: type it from a live type the evidence supports, or `undefined4`.
- A complete row may also set `varargs: true` (with `varargs_evidence`) when
  every fixed parameter is proven and the existing rules decide the return: a
  `recon void` verdict of void (`fprintf`: none of its 271 callers reads v0)
  or a proven width (decision of 2026-10-22). `recon draft --check` accepts
  it where the draft is U-vararg; U-vararg stays the draft rule for the rest.
- `noreturn: true` needs `noreturn_evidence` and the proof `recon validate`
  takes from the ELF: no `jr` in the body, branches stay inside it, and every
  `j` (or a final `jal`) enters a function proven the same way. It is recorded
  but not applied. The bridge's `set_function_no_return` changes a function
  modifier, and that wakes Ghidra's Call-Fixup Installer (a default-enabled
  function-modifier analyzer), which clears and repairs the flow after every
  call site; routine work never clears flow. `set_function_prototype` leaves
  the flag as it was, and the read-back expects it so.
- `recon draft --check` accepts a partial row where the draft is unresolved
  (U-type, U-vararg) or open (the rules decided nothing), never where the
  draft decides a prototype.

`recon contradictions [--groups applied|all] --output build/facts/contradictions.txt`
lists group functions whose live signature contradicts the facts: argument
reads it does not declare, a mangled signature of another count or shape, an
applied prototype that drifted, or a reviewed row that records it as wrong (a
contradiction, a disagreement, a wrong width or a different type; a remark
that a signature is unproven or comes from a library archive is not one).
Each comes with its group, whether that group is applied, and its recon
repairs; the newest applied repair supersedes the group's row. Both default
forms above claim nothing. Reads that "Dead entry reads" below proves masked,
or that an accepted plan or repair declares dead, are not listed. A thunk
shows its target's signature, so it is not checked against its own facts;
thunks that would conflict are listed at the end. `--fingerprint <file>`
reads a stored fingerprint instead of Ghidra.

`recon partial-candidates [--groups applied|all] --output build/facts/partial-candidates.txt`
(read-only, `--fingerprint` as above) lists unresolved rows of accepted plans
whose live signature claims nothing and whose parameters the facts prove: the
stage 2 DWARF parameters, or the mangled signature's with a receiver proven as
the draft rules prove it, every type exactly one live type, every argument
read declared (masked reads dropped); no thunk, VU0, constructor or
destructor. Each row names its route: a recon repair for an applied group, a
re-plan (`progress work reopen`) before the apply. A partial row still needs
per-parameter evidence and review.

### Dead entry reads

The entry-block scan treats a partial load completed by its partner (`lwl` +
`lwr`, `ldl` + `ldr` at the canonical offsets) as a write. A read that the
code later masks off entirely (for example the 64-bit insert idiom in
`__muldi3`) can be declared on the prototype:

```json
"dead_entry_reads": [
  {"register": "t1", "site": "0x16bb14", "evidence": ["and t1,t1,a1 keeps the high half; and t1,t1,a3 at 0x16bb28 clears it"]}
]
```

`recon validate` accepts a row only when the entry block reads that register
and the site is inside the function; the reviewer checks the evidence. The
row is copied into the program's notes.

A dead read outside the entry block (one `recon facts` lists under "args read
before write (any path)") is declared per site with `dead_reads`, and
`recon validate` checks each row's proof from the ELF:

```json
"dead_reads": [
  {"register": "a2", "site": "0x16bb7c", "kind": "masked", "evidence": ["and a2,a2,v1 keeps the high word; and a2,a2,a0 at 0x16bba4 clears it"]},
  {"register": "a2", "site": "0x16779c", "kind": "unreachable", "branch": "0x167724", "direction": "taken",
   "evidence": ["bc1fl is taken only if 1e30+x <= 1.0, impossible for |x| < 2^-28: fdlibm's uninitialised k"]}
]
```

- `masked`: from the site, every path must clear the bits still holding the
  incoming value before an instruction observes them. Constant `and`/`andi`
  masks narrow them (masks are evaluated from `lui`/`li`/shift definitions),
  `or`/`xor` into the same register and shifts move them, a narrow store or a
  shift into another register may ignore them, and a write without a read ends
  them; they may not be live across a call, a tail jump or the end of the body
  (a `jr ra` ends them). The contradiction scan applies the same proof to
  every undeclared read, so the word-insert idiom of `__divdi3`, `__moddi3`,
  `__umoddi3` and `_ulp` needs no row.
- `unreachable`: removing the `taken` or `not-taken` edge of the conditional
  `branch` must leave no path from the entry to the read; why that direction
  cannot happen is evidence for the reviewer.
- The site must be one `recon facts` lists for the register; each row is
  copied into the program's notes. Shift-immediate instructions read only rt:
  their rs field is reserved, and once made inline data (`_copyRefImage`'s
  clamp mask) look like a read of a3.

`recon validate` refuses a plan unless:

- it names its item and the decomposed group's digest, and targets this ELF;
- every group function appears exactly once, with the live `current_name`
  and either a prototype with evidence or the reasons it stays unresolved;
- every type is spellable through the bridge (no `,` or `&`, builtins by
  their Ghidra names);
- parameter names are identifiers and do not repeat;
- the prototype declares every argument register the entry block reads
  (under `__stdcall`, floats take `f12`-`f19` and everything else the next of
  `a0`-`t3`);
- no parameter is a class, struct or union passed by value whose DWARF
  records exceed one GPR slot (8 bytes; see `U-byvalue`): Ghidra would put
  it on the stack where Metrowerks passes its address; nor one a direct
  caller passes as the address of a stack temporary; nor a parameter Ghidra
  would store elsewhere than Metrowerks passes it (more than 8 floats with a
  GPR still free; see `U-storage`). `recon partial-candidates` leaves such
  rows out, and `recon by-value-rows` (read-only, JSON) lists rows of
  accepted or applied group and repair plans that already declare one, each
  parameter with its `kind` (`over-gpr`, `by-address` or `storage`; `live`
  marks the row the accepted applies left in Ghidra);
- a partial prototype carries the proof "Partial prototypes" lists;
- each global changes something, has evidence, is not a type that
  `apply_data_type` would resolve to a different type, and is referenced by
  one of the group's functions.

A global that an earlier accepted apply typed keeps that type unless the plan
sets `replaces_accepted` and its evidence explains the correction.

Hand off with `progress work handoff`, citing the plan's SHA-256. An
independent reviewer reruns `recon validate`, spot-checks the evidence, and
accepts or rejects with findings.

## Apply item: `recon-apply-group`

Role `socom-ghidra-reconstructor`, under the exclusive writer lease.
`recon program` translates the accepted plan into the batch-apply program
format; `ghidra apply-recon` checks that the plan item is accepted and cites
the plan's digest, that the program regenerates from the plan, and that live
preflight passes, then applies through the batch executor, which reads back
every name, prototype, and global (a partial row's live signature must still
be the one its plan replaces). `--dry-run` sends no writes and reports the
calls an apply would make. The receipt scope is every group function and every
planned global. Hand off with `progress handoff-live-ghidra`; acceptance is
`progress advance-live-ghidra` by someone else.

## Repair item: readable function names

`socom:work:ghidra-repair-readable-function-names` gives every function that
still carries a Metrowerks mangled name the readable qualified name stage 2
gives DWARF functions (`SetPosition__Q23zdb5CNodeFfff` becomes
`zdb::CNode::SetPosition`), and keeps the mangled name as a label. The program
is computed from the ELF alone (`ghidra repair-names`, with `--dry-run`):

- overloads share their readable name (decision of 2026-10-19); each keeps its
  distinct mangled label, and signatures tell them apart;
- a mangled name on several addresses (file-local copies) and thunks are left
  alone;
- nothing but names changes. `ghidra check-names-repair` is the verifier's
  read-only checklist: only Function and Signature names may differ from the
  previous fingerprint.

Plans written before the repair still name the mangled form in
`current_name`. The executor accepts the live name only when it equals that
name's exact readable form.

The stage gate depends on stage 3 repairs as well as every apply.

## Repair item: recon repairs

A wrong prototype in a group that is already applied (a library-archive
signature an unresolved row left live, or a row the facts now settle) is
corrected by a numbered recon repair; `progress work reopen` covers only plans
whose apply has not started. A repair may also (or only) list globals: sized
.symtab objects without a DWARF record, such as the static members of a class
that has no DWARF class record (`zdb::CVisual`, decision of 2026-10-24).

```powershell
python tools/socom.py progress add-recon-repair --functions 0x3defd8 0x3e0550 --expected-revision <n> --dry-run
python tools/socom.py progress add-recon-repair --globals 0x4765f4 0x4765f8 --expected-revision <n> --dry-run
python tools/socom.py recon global-facts --item socom:work:recon-repair-NNN --output build/facts/<slug>-globals.txt
```

- The command refuses a function whose group plan and apply are not both
  accepted, or that an unfinished repair already lists. It refuses a global
  that is not the start of a sized .symtab `OBJECT`, lies inside a function,
  has file-local copies (no canonical copy), has a DWARF record (stage 2 typed
  and named it from DWARF; a repair may not contradict DWARF), is in an
  unfinished repair, or is in the receipt scope of an apply awaiting
  acceptance. It adds `socom:work:recon-repair-NNN` (kind `recon-repair-plan`,
  file-only `build/recon-plans`, depending on the applies of the groups it
  corrects, of earlier accepted repairs of the same functions or globals, and
  of the accepted group or repair applies whose receipt scope lists a global)
  and its `-apply` item (`recon-repair-apply`, the only one that owns
  `ghidra-writer`, waiting for the accepted plan). Both join the stage gate.
  A repair's `batch.globals` (absent when it lists none) joins its digest.
- The plan is a recon plan (`recon evidence --item`, `recon live --item`,
  `recon facts --item` accept the item) whose `group_sha256` is the repair's
  function-list digest and whose rows use the group row format, partial rows
  included, one per listed function. Each row adds `group` (the group it
  corrects) and `repair` (why the live state is wrong), sets a prototype, and
  records the live signature it replaces in `prototype.live_signature`. A row
  must change the live signature unless it only declares `dead_reads`.
  `globals` has one row per listed global (empty when it lists none):

  ```json
  {
    "address": "0x4765f4",
    "symbol": "m_dmaChain__Q23zdb7CVisual",
    "label": {"namespace": "zdb::CVisual", "name": "m_dmaChain"},
    "live_type": "",
    "type": "_word128 *",
    "repair": ["mangled name only, untyped although every access is a pointer"],
    "evidence": [".symtab OBJECT, 4 bytes; ..."]
  }
  ```

  `symbol` is the .symtab object name (the live name the apply replaces, kept
  as a label); `label` is null or exactly its demangled qualified name;
  `live_type` is the type `audit_global` shows now (`""` when no data is
  defined); `type` is a type proven from the .symtab size and the code's
  accesses (never `undefined*`, an analysis type such as `dword`, or a
  spelling whose builtin, pointer or array size differs from the .symtab
  size), or `keep` with `keep_reason` (why it stays: what is unproven). A row
  must change the label, the type or both. `recon global-facts --address
  <addr...>` (or `--qualifier zdb::CVisual`, or `--item`) lists, per global,
  its .symtab names, size, binding and section, DWARF records, readable label,
  initial bytes (or zero fill), relocated words pointing at or inside it, and
  every code access: width, signedness, load or store, the stored value (a
  constant, a typed parameter of the function, a call result, a load) and
  where a loaded value or the address goes (compares, masks, arithmetic,
  dereferences, the mangled parameter type of each callee it is passed to,
  stores elsewhere, a value left in v0/f0 at a return and what callers do
  with it).
- A repair row may withdraw an unproven live return. It is a partial row
  with `"withdraws_return": true` whose `contradiction` says why the live
  return is unproven and whose `unresolved` says why the return stays open.
  Three kinds of live return qualify:
  - a sub-word or bool type that rested only on a caller's or dispatcher's
    narrowing, which proves only its destination (decision of 2026-10-24);
  - a type of any width, `int` and pointers included, whose only support was
    a recalled SDK or C-library header declaration (decision of 2026-10-29,
    issue b8acf0d9, "Re-prove from asm"): a planner re-proves the return from
    the asm and the callers, and withdraws what nothing proves;
  - a `void` that `recon void` does not confirm (decision of 2026-10-29,
    "Extend tool, withdraw"). `contradiction` cites the open verdict line of
    `recon void` (newest rules) verbatim and never a `VERDICT void` for the
    function itself; a callee's verdict it describes is evidence when the
    line before it, or its `## label` block, names the callee's entry
    address (labels are `name@0x...`). A void is
    not withdrawn when the function's own DWARF record declares FT_void,
    when `recon void` proves it (`VERDICT void`, or every exit leaves v0
    and f0 unset), or when the drafter's `__sinit_` rule proves it.

  The live return must not be `undefined*`, and a return the function's own
  DWARF record declares is not withdrawn (stage 2 typed it from DWARF). The
  parameters must equal the live ones exactly: names, types, order,
  receiver, varargs and `__stdcall`. Only this defect is allowed: a
  contradicted live signature is an ordinary partial row, and a group plan
  refuses `withdraws_return`. The program marks the row `withdraws_return`
  (its note says when the withdrawn return is a void), and the
  `check-recon-apply` read-back expects `undefined <convention>
  <name>(<live parameters>)`, checks that the program's parameters are the
  live signature's, and counts the withdrawn voids.

  ```json
  "prototype": {
    "partial": true, "withdraws_return": true, "return_type": "undefined",
    "calling_convention": "__stdcall", "varargs": false,
    "parameters": [{"name": "code", "type": "ushort", "evidence": ["andi v0,a0,0xffff at 0x151460"]}],
    "live_signature": "ushort __stdcall euc2jis(ushort code)",
    "contradiction": ["return: the live ushort is a width the code does not prove"]
  },
  "unresolved": ["return width unproven: no exit narrows v0 before jr ra; only the caller's andi narrows"]
  ```

  `recon withdrawal-candidates [--kind void|header|all] [--rules N]
  --output build/repair-pass/withdrawal-candidates.json` (read-only, JSON;
  tracker, accepted plans and the ELF only) lists the rows these withdrawals
  may take over accepted applies: the row each function shows is the newest
  recon repair whose plan and apply are accepted (a keep row leaves the
  earlier row), else its group's row. `void` lists applied void rows whose
  `recon void` verdict is open, with that verdict line; it excludes the
  function's own DWARF FT_void record, the drafter's `__sinit_` rule, and a
  row citing a DWARF `subroutine_type` that declares FT_void (a callback
  member type, cited as `subroutine_type 0x...`, `subroutine type 0x...` or
  either with `DIE`; the DIE is checked). `recon validate` does not yet see
  such a citation in the row a withdrawal supersedes: check
  `withdrawal-candidates` before withdrawing a void. `header` lists applied rows whose return
  is a type (not void, `undefined*` or partial) and whose row cites a
  recalled SDK or C-library header (type-archive paths such as
  `/stdio.h/FILE` are not citations), with the headers, the citing lines and
  the rest of the evidence; a return the function's DWARF record declares is
  left out. Each row names its plan item, its group and any unfinished repair
  of the function (`progress add-recon-repair` refuses those). Live
  signatures are not read: `recon live --item` gives the repair row's
  `live_signature`.
- A repair row may also keep a listed function as it is (coordinator
  decision of 2026-10-29: no command drops a function from a registered
  repair, and some listed functions no row can express, such as 0x2392d0's
  by-value CPnt4D):

  ```json
  {
    "address": "0x2392d0",
    "current_name": "Particle::Source::CheckExtents",
    "group": "socom:recon-group:<id>",
    "keep": true,
    "keep_reason": ["CPnt4D (16 bytes) by value: no prototype gives it its storage"]
  }
  ```

  It cites its group and carries no prototype, rename or `unresolved`. The
  program marks it `keep` and emits no call for it; the `check-recon-apply`
  read-back expects its live signature unchanged, and the `limit` check
  counts it as listed (it must not change, and no apply call may name it).
  Later readers keep the earlier row in force. `recon program` reports
  `keep_count` apart from `unresolved_count`; the program file's own summary
  still counts keep rows as unresolved, so accepted programs regenerate.
- GhidraMCP labels only in the global namespace (`rename_label` and
  `create_label` take no namespace), so the readable label is the qualified
  spelling itself, `zdb::CVisual::m_dmaChain`, exactly as stage 2 labelled
  `zdb::CVisual::m_camera`; the program renames the mangled primary symbol to
  it and re-creates the mangled name as a label.
- `recon validate`, `recon program`, `ghidra preflight-batch` and
  `ghidra apply-recon` take the repair like a group; the apply refuses before
  any write unless every listed function still shows its `live_signature` and
  every listed global still shows its `symbol` and `live_type`. A typed
  global replacing a type an earlier apply chose says so
  (`replaces_accepted`); a keep row's type is left alone. The receipt scope
  is the listed functions and globals. A later group apply accepts a global
  whose live name is the readable form of the mangled name its plan records
  (a repair labelled it) and keeps that label.
- `ghidra check-recon-apply --item socom:work:recon-repair-NNN-apply` adds the
  `limit` check: the fingerprint diff changes only listed functions (plus
  thunks and Ghidra-split targets showing a listed function's new signature),
  the scope and every apply call name only listed functions and globals, the
  program's globals are exactly the listed ones, every listed function but a
  keep row's took its prototype, and every listed global its planned label
  and type. The
  read-back checks each listed global's name, type (a keep row's recorded
  `live_type`) and length in the fresh receipt, and that each relabelled
  global's mangled symbol was re-created (its `create_label` call; the bridge
  has no read-only listing of labels).
- Later readers (thunk checks in `recon validate`, `recon contradictions`)
  take the newest accepted repair's row over the group's row.

## Code-derived type plans

A class with member functions, a vtable or RTTI but no DWARF `class_type`
record (`zdb::CVisual` and its derived classes) leaves its functions
unresolved ("receiver type X is absent"). Its layout is recovered from
instruction evidence only, as a reviewed type plan and a governed apply:

```powershell
python tools/socom.py progress add-type-plan --class zdb::CVisual --with-derived --expected-revision <n>
python tools/socom.py recon layout --class zdb::CVisual --with-derived --output build/type-plans/zdb-cvisual-layout.txt
python tools/socom.py recon type-plan validate --plan build/type-plans/zdb-cvisual.json
python tools/socom.py recon type-plan show --plan build/type-plans/zdb-cvisual.json --output build/type-plans/zdb-cvisual-review.md
python tools/socom.py recon type-plan live --plan build/type-plans/zdb-cvisual.json
python tools/socom.py recon type-plan program --plan build/type-plans/zdb-cvisual.json --output build/apply/<item>.json
python tools/socom.py ghidra apply-type-plan --program build/apply/<item>.json --item <apply-item> --owner <owner> --scope-output build/receipts/<item>-scope.json --report-output build/apply/<item>-report.json --dry-run
python tools/socom.py recon type-plan affected --plan build/type-plans/zdb-cvisual.json
```

- `progress add-type-plan` adds a file-only `recon-type-plan` item
  (`build/type-plans`, no dependencies) and its `-apply` item
  (`recon-type-apply`, the only one that owns `ghidra-writer`, waiting for the
  accepted plan). Both join the stage gate, as stage 3 repairs do.
- `recon layout` lists, per class, its RTTI records and base list
  (Metrowerks `type_info_base_list`: base and offset), vtable slots,
  members with the proof that a0 is `this` (constructor, destructor, const,
  vtable slot, an argument register read beyond a static function's
  parameters, a member operator other than new/delete, or a DWARF `this`
  formal parameter; others are listed unresolved), allocation sizes
  (`operator new(N)` reaching a constructor; the most derived of the
  constructor's class and any family vtable stored into the object), derived
  constructors' this-adjustment, and every access proven relative to the
  class: this, typed parameters, allocation results, followed through copies,
  spills, loads, indexes and calls. Each offset shows widths, kinds,
  signedness, pointer use, typed callees, constants, vtable stores and
  bitfield masks, with every site; conflicts and accesses beyond the
  allocation size are flagged. Every call row records what the callee takes
  in that register: `parameter_type` (mangled parameter or receiver),
  `no_parameter` (the settled parameter list does not use it), or
  `parameter_unknown` with the reason (indirect call, no mangled parameter
  list, registers not settled past a by-value class or varargs, or an
  unproven receiver whose member and static readings differ). DWARF 1
  parameter lists cannot settle registers (they omit unnamed parameters) and
  all but nine DWARF subprograms have mangled names, so DWARF only proves
  receivers. A by-value parameter whose mangled class is a DWARF
  enumeration (no composite of that name) is a scalar in one GPR and
  settles the registers after it. Live prototypes are not read; the evidence stays ELF-only so
  `validate` can regenerate its digest. A store of zero and a word copied through an
  FPR prove neither int nor float. Accesses whose base cannot be proven are
  counted per function as unattributed.
- Every function is analyzed, callees first, so pointers held outside the
  class family are attributed too (`held@<load>` and `return@<call>` roots;
  the function row gives each proof, and `type-plan show` prints it for
  cited sites): a 4-byte load of a DWARF member or global typed as a
  pointer to a family class, from a pointer typed as its holder (this, a
  mangled parameter or another holder; every DWARF record of the holder
  must agree); an element of pointer storage whose DWARF type lost the
  element type (`std::vector<T *>` stores `unsigned int *data_`), typed when
  code passes that storage plus an index as a mangled `T **` or `T *&`
  parameter (`holders.element_storage`, keyed by the innermost
  non-template DWARF record such as `CVisualVector+0x8`; disagreeing proofs
  refuse the storage); a call result when every exit of the callee returns
  NULL or a pointer of one proven class (`holders.typed_returns`); and a
  function-local static read back after a store, when only that function's
  direct loads and stores reference it. A call whose callee returns its
  entry a0 plus k on every exit yields the caller's a0 plus k. A pointer met
  at different offsets on joining paths (a loop pointer) is that pointer plus
  an index. Loads from family objects keep their own attribution. Holders
  without DWARF layouts (a declaration-only record such as
  `tag_DelayedNode`), casts after a runtime type test, virtual-call results
  and `__dynamic_cast` results are not typed.
- A plain struct has no member function, vtable, RTTI or DWARF record; only
  mangled parameter types name it (`tag_ObjectHeader`, the `a2` of
  `zdb::CVisual::VuObjectSetup` and both `VuBatchProgram`s). Lay it out with
  `recon layout --class tag_ObjectHeader --struct` (and plan it with
  `progress add-type-plan --class tag_ObjectHeader --struct`; the batch
  records `"struct": true`, the plan's `layout` spec too). `--struct` refuses
  a name with members, a vtable, RTTI or a DWARF record, and one no mangled
  `S *` / `S &` parameter names. Its roots are those parameters in every
  function, followed as for classes. A function that passes, as such a
  parameter, an address it can name at every use (its own frame `sp+N`, a
  symbol-table object, a call result or an entry argument, plus N) builds or
  reads the struct there: its own accesses to `base+N+k` before and after the
  call are attributed at `+k` (`built@<pass sites>` roots), inside a region
  that ends at the next address of that base the function passes or stores
  (another object), the frame top or a saved-register slot, the object's end,
  or the `operator new` size. `caller_built.regions` lists every region with
  its bound; a region whose address is also passed as a different type (the
  slot is reused), that nothing bounds, or that a loaded or indexed pointer
  addresses is refused, and its accesses, and any access that passes a
  region's end, is indexed from its start or lies where a lower object of
  known size may extend, are listed in `caller_built.flagged` instead of
  attributed. `size_bounds` gives the largest attributed extent, the region
  bounds (room before the next object: an upper bound, not a size proof),
  `operator new` sizes whose result is passed as the struct (these are its
  `size_evidence`), same-offset copies and indexed sites. The plan names the
  struct `mangled-symbol` with the symbols of its `name_evidence`. Class
  layouts never use caller-built regions, so their evidence and digests do
  not change.
- Command records (`tools/_socom/type_records.py`): zAnim callbacks take a
  `_zanim_cmd_hdr *` that is really their command's record (DWARF for
  `zcam_main.cpp` casts it: `cmd_ptr = (_camera_params_cmd *)hdr`). Lay out
  one family with `recon layout --records <command or set::*...> [--class
  VALVE_CMD_DATA] --output build/type-plans/zanim-<family>-layout.json` and
  plan it with `progress add-type-plan --records <commands...> --family
  <family> [--class <class>]` (item `type-plan-zanim-<family>`; the batch and
  the plan's `layout` record the expanded, sorted `records`, `family`,
  `registrar` and the optional class). The registrar is configured
  (`REGISTRARS["zanim"]`: `CZAnimMain::AddCmd`, name in a1, parser/begin/
  tick/end in a2/a3/t0/t1); which callback register holds the record, and
  that a parser returns it, comes from AddCmd's mangled function-pointer
  parameter types. A registration is a direct call whose a1 is a string and
  whose role registers are function addresses or NULL; the callback receives
  (or the parser returns) that command's record, with the registration site
  as its proof. A direct callee receives it when the record is passed
  unchanged in a register its mangled parameter (or a registration) types as
  the header (`CTDoor::Begin` jumps to `CTMove::Begin`: DOOR records reach
  it); a function returning a record returns, at every exit, NULL, an
  allocator result (`_calloc` a0*a1, `_malloc` a0: the record's allocation),
  a `_realloc` result (a variable tail; its argument was the record) or
  another function's result or tail jump (which then returns it too). A
  pointer reached for several commands is attributed to each (`record A|B`).
  Each record row (`record <command>`) gives the header (`_zanim_cmd_hdr`
  from DWARF) at +0, registrations, record pointers with proofs,
  allocations, `data_size` (2-byte header stores at +2 keeping bits 0-1 and
  writing constant bits 2-15), DWARF casts (callback parameters and locals
  typed as a pointer to a composite with the header at +0) and the offsets.
  Calls on embedded objects (`VALVE_CMD_DATA::Compare(rec+8)`) are sub-object
  passes, so the class is laid out beside the records.
- A records plan maps every record to exactly one type (`records`: sorted
  command names). Records sharing one layout share one type (`TASK_MOVE` for
  MOVE and DOOR). A record whose callbacks DWARF casts to an existing record
  type is mapped to a `dwarf` type: `{"name": "_camera_control_cmd", "kind":
  "dwarf", "category": "/project", "name_provenance": "dwarf",
  "name_evidence": ["0xf3cbf"], "records": [...]}` with no layout of its own;
  the validator derives its members from DWARF and checks the records'
  accesses against them, the program never creates it
  (`referenced_types`), and `type-plan live` proves it resolves to exactly
  its path with the DWARF members. Other records get a new `struct` with the
  header at +0 (a `/project/_zanim_cmd_hdr` base or field, or a live DWARF
  base that contains it such as `/project/TASK_HDR` with its `size`); its
  size must equal every record's allocation and `data_size` (or cite
  `size_evidence` for a variable tail), and invented record type names are
  `_<module>_<name>_cmd` or `TASK_<NAME>`. A GPR store of a constant is
  width evidence only (Metrowerks stores float immediates with `lui`/`sw`).
- The plan (format in `tools/_socom/type_plan.py`) gives each type its
  qualified name, category (`/project/<namespaces>`), size, alignment, bases
  at their RTTI offsets (component named by the bare base type name), the
  vptr `__vt` (pointing to `<Class>_vtbl`, opaque unless every slot type is
  proven), fields with evidence sites, padding, accesses beyond the size with
  reasons, and unresolved notes. Invented names are `C`/`tag_`/`m_` names
  marked `invented-provisional`, after a naming survey of neighbouring
  DWARF classes. Every type spelling is a Ghidra builtin, a plan type or a
  `/project/...` live path.
- Names a type plan does not invent are proven: `elf-symbol` (a layout
  class), or `name_evidence` for `mangled-symbol` (mangled `.symtab` names in
  which the type is a member qualifier, a parameter type or a template
  argument), `rtti` (the `__RTTI__` object) or `dwarf` (a record of that leaf
  name). Nested helper types (`zdb::CMesh::CMeshLOD`, category
  `/project/zdb/CMesh`) are planned like any other type when evidence
  reaches them by value.
- A `forward` type declares a proven name without layout evidence
  (`zdb::tag_DETAIL_PARAMS`, named only by `VuDetailMap`/`VuBatchProgram`
  parameters): no size, bases or fields, a `reason`, and at least one plan
  member pointing to it; it is never used by value or as a base. The program
  creates forward declarations first, as empty structures (the route the
  DWARF import used for declaration-only types and the opaque vtables use).
- A template instantiation that no live type provides
  (`std::vector<zdb::CMesh::CMeshLOD, ...>`, its `__vector_imp` and
  `__vector_deleter`) gives `instantiation`: the live `source` of the same
  template and namespace, the `arguments` (`from` -> `to`) whose substitution
  turns the source's name into the plan's, and the source's
  `get_struct_layout` rows (`source_size`, `source_layout`). Each row becomes
  a base (a stage-2 `super_<identifier>` component; the plan names it by the
  base type without template arguments) or a `template-copy` field with the
  source member's name, offset and size, typed as the source member with the
  arguments substituted (`CLOD_band *` becomes `zdb::CMesh::CMeshLOD *`;
  members that do not mention an argument are copied unchanged). A DWARF
  record of the template must have the same members and bases. Copied
  members need no cited evidence, but every access inside the instantiation
  must agree with them; a vector is never flattened into words.
- A call that passes `this+N` as `T *` or `T &` proves a `T` sub-object at
  `+N`. Validation matches every such call against the plan's sub-objects:
  plan types, and the DWARF bases and by-value members of live types, empty
  bases included. A call on an empty base at a member's end
  (`Metrowerks::compile_assert<1>` after `CVisual::m_dynTexList`'s second
  vector, `0x30df0c`) belongs to that member, not to the next field; a call
  that no sub-object explains is a problem, unless it lies inside a by-value
  live type without a DWARF record. DWARF 1 names drop template arguments, so
  records of one name can disagree (a pointer `vector`'s `__vector_imp` ends
  in `compile_assert<1>` at +0xc, a class `vector`'s does not); such a
  sub-object counts only when the records the DWARF import named with the
  live type's path (an instantiation's `source`) have it, read on first need
  from the type identities (about 20 s). An address pass whose parameter type
  is `parameter_unknown` is a problem unless the `notes` or `unresolved`
  text of a member whose extent holds the address (end included) cites the
  site (`0x30f454`, or a range containing it).
- `recon type-plan validate` regenerates the evidence and refuses a plan
  whose layout digest differs, a field without a matching access, a size
  that differs from allocations, overlaps or uncovered bytes, accessed
  padding, contradicted widths, kinds or signedness, placeholders
  (`void *`, `undefinedN`, byte arrays) where the evidence is stronger (a
  typed pointer passed or a typed pointer parameter stored), unproven names,
  or a base the RTTI does not list. Evidence for a base's fields may come
  from any class that embeds it. `show` prints a Markdown review: forward
  declarations, every invented-provisional name, and per type a table of
  offset, size, type, name, provenance, evidence count, sample sites
  (instruction and function) and notes (field notes and unresolved text),
  then outside accesses, unresolved notes and the validation result.
- `recon type-plan live` runs the apply's read-only live checks before
  handoff: no target exists, no live type shares a target's name (ignoring
  case), no forward-declared name has a live or `<name>@<hash>` variant, and
  every referenced live type and instantiation source resolves to exactly
  one path, each source's live layout equal to its recorded `source_layout`.
- `recon type-plan program` writes the type apply program (forward
  declarations first, temporary names, read-back of every layout, then
  category moves and renames); `ghidra apply-type-plan` applies it with the
  type executor under the writer lease after checking the accepted plan's
  digest and repeating the live checks (`--dry-run` stops there). Hand off
  with `progress handoff-live-ghidra`.
- After the apply, `recon type-plan affected` lists the groups whose rows
  were left unresolved for the plan's proven names (classes, structs and
  forward declarations; `replan` before their apply, `after-apply` once
  applied) and the groups not yet planned.

## Stage gate

Role `socom-verifier`, once every apply is accepted. The reviewer writes the
union scope with `progress stage-scope`, takes a receipt over it, and runs the
strict audits. After the gate is accepted,
`progress record-stage-baseline --stage ghidra-reconstruction` records the
stage's baseline for `source-correlation`.
