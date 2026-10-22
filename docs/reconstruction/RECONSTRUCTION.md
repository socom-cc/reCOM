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
`vf` registers before the call, e.g. `_TransformPoint`), varargs (the plan
format has no varargs field), a by-value class result returned through a
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
`v0` unread in turn, and nothing may take its address (followed six levels
deep). `recon facts` follows `v0` through callees that leave
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
every name, prototype, and global. `--dry-run` sends no writes and reports the
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

## Stage gate

Role `socom-verifier`, once every apply is accepted. The reviewer writes the
union scope with `progress stage-scope`, takes a receipt over it, and runs the
strict audits. After the gate is accepted,
`progress record-stage-baseline --stage ghidra-reconstruction` records the
stage's baseline for `source-correlation`.
