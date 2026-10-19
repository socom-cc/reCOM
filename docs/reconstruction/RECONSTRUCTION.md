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

## Stage gate

Role `socom-verifier`, once every apply is accepted. The reviewer writes the
union scope with `progress stage-scope`, takes a receipt over it, and runs the
strict audits. After the gate is accepted,
`progress record-stage-baseline --stage ghidra-reconstruction` records the
stage's baseline for `source-correlation`.
