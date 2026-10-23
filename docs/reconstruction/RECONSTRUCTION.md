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

Rows keep their `draft_rule`. Planners do not edit them.
`recon draft --check <plan>` re-derives them and fails on any difference, or
on a row claiming a rule the tools did not apply. Reviewers run it and then
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
bool) only on positive evidence: `andi 0xff` at a call site or merge, a
DWARF-typed override or base, or the returned member's own type. Otherwise
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
as such. A scratch value also allows `void` (second decision of 2026-10-20): a
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
`recon void --function` prints the verdict and the blocking chain.

A function whose every exit returns a relocated pointer to a NUL-terminated
string (`recon bytes` shows the word's target and its text) returns
`char *`. The binary cannot show whether the pointee is `const`, so the plan
does not record it.

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
whose apply has not started.

```powershell
python tools/socom.py progress add-recon-repair --functions 0x3defd8 0x3e0550 --expected-revision <n> --dry-run
```

- The command refuses a function whose group plan and apply are not both
  accepted, or that an unfinished repair already lists. It adds
  `socom:work:recon-repair-NNN` (kind `recon-repair-plan`, file-only
  `build/recon-plans`, depending on the applies of the groups it corrects and
  of earlier accepted repairs of the same functions) and its `-apply` item
  (`recon-repair-apply`, the only one that owns `ghidra-writer`, waiting for
  the accepted plan). Both join the stage gate.
- The plan is a recon plan (`recon evidence --item`, `recon live --item`,
  `recon facts --item` accept the item) whose `group_sha256` is the repair's
  function-list digest and whose rows use the group row format, partial rows
  included, one per listed function. Each row adds `group` (the group it
  corrects) and `repair` (why the live state is wrong), sets a prototype, and
  records the live signature it replaces in `prototype.live_signature`. A row
  must change the live signature unless it only declares `dead_reads`.
  `globals` stays empty.
- `recon validate`, `recon program`, `ghidra preflight-batch` and
  `ghidra apply-recon` take the repair like a group; the apply refuses before
  any write unless every listed function still shows its `live_signature`.
  The receipt scope is the listed functions.
- `ghidra check-recon-apply --item socom:work:recon-repair-NNN-apply` adds the
  `limit` check: the fingerprint diff changes only listed functions (plus
  thunks and Ghidra-split targets showing a listed function's new signature),
  the scope and every apply call name only listed functions, no global is
  typed, and every listed function took its prototype.
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
  receivers. Live prototypes are not read; the evidence stays ELF-only so
  `validate` can regenerate its digest. A store of zero and a word copied through an
  FPR prove neither int nor float. Accesses whose base cannot be proven are
  counted per function as unattributed.
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
