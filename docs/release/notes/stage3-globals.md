# Stage 3: globals in the release program (running note)

The prototype's global names, and the few types it has for data, carried onto the paired data of
the release program `SCUS_971.34` with `tools/release/globals.py`. The pairing is
`docs/release/data-map.tsv` (made by `tools/release/datapair.py`, by `socom-release-data-d1`;
checked by `socom-release-data-check-k1`, see `data-pairing.md`). Tool by
`socom-release-globals-g1`, review and check script by `socom-release-globals-review-r5`;
applied, saved and confirmed by the coordinator. The user ordered this step after the function
starts (`stage3-starts.md`).

## What is carried, and how

Per paired data object, in this order, with calls that clear nothing:

- a type, only where the release bytes are still undefined (`apply_data_type` with
  `clear_existing` false; the bridge client refuses the call in any other form);
- the prototype program's name as a label (`create_label`), and the ELF symbol as a second label
  where the two differ;
- a one-line plate: `Release data map: <class> pair with prototype <address> <symbol> (evidence
  ..; flags ..)`. It shows `single-aligned` and the flags of a deviating pair.

Read from the plugin's and Ghidra's classes by the author and again by the reviewer: `set_global`
with a type and `apply_data_type` in its default form clear the range before they create data,
and a clear removes instructions, defined data and their outgoing references, so neither is ever
sent; a label changes no code unit and starts no analysis; a label on an address whose only name
is an automatic one (`DAT_`, `PTR_`, `s_`) becomes the primary name, and on an address with a
stored name it is added beside it; a pointer type creates its reference when it is laid down.

## What the plan held

| | Count |
|---|---|
| labels | 1,855 (188 on deviating pairs, 127 on pairs that rest on one aligned witness) |
| second labels | 178 |
| plates | 1,855 |
| types | 23 (float, uchar, int, `char *`, bool, one `EQUIP_ITEM[11]`) |

Few types: the prototype's globals mostly have none. About 4,000 are typed there, 3,900 of them
strings, and 3,657 strings are typed the same way in the release already. The prototype
program's name for a data object is usually its ELF symbol; a readable name exists for about 340
(`X::__vt`, `X::__RTTI` and the like).

Not named, each with its reason in the plan: 4,795 literals (`@N` symbols have no name to carry),
439 anonymous objects, 210 pairs the pairing check withholds, 5 addresses inside a data item, 4
conflicting rows, 3 addresses that are instructions, and 2,241 pairs outside the program's
memory (below). Unsure, new and removed rows get nothing.

## The review

Verdict: safe to run the pilot; no blocking defect. The reviewer read the three write endpoints
itself, checked how each of the 23 planned types resolves by name (none adds a type to the
table), and compared a sample of 191 planned entries with the prototype's names, the data map and
the live program: all as planned. Its remarks: one stop message is worded wrongly; after any stop
the report has to be confirmed or discarded before anything else, because a write that took
effect without reading back leaves no unsaved row; the tool's snapshot does not watch the type
table or code made by the data-reference analysis, which the reviewer's check script covers; 18
of the single-aligned names sit on all-zero bytes, so their content cannot confirm the pair (they
are named, and their plate carries the flag).

## Applied

| Run | Entries | Outcome |
|---|---|---|
| pilot, `gamez/zCamera`, one entry | 1 | `fogCheck` (0x48c850): type `uchar`, label, plate; check clean; saved, confirmed |
| pilot, one vtable | 1 | 0x4893c0: `zdb::CCamera::__vt` primary, the mangled symbol second, the pointer item unchanged; check clean; saved, confirmed |
| pilot, the rest of the module | 7 | check clean; saved, confirmed |
| pilot, two from the whole map | 2 | a `char *` with its one predicted reference, an `EQUIP_ITEM[11]`; check clean; saved, confirmed |
| batch 1 | 200 | no stop; check clean; saved, confirmed |
| batch 2 | 800 | no stop; the check listed 184 items, all of one kind (below); saved, confirmed |
| batch 3 | 844 | no stop; 17 types, 2 predicted references; check clean with every report; saved, confirmed |

No run stopped and analysis answered no write. The 184 items of batch 2: a pointer's automatic
name is built from its target, so `PTR_PTR_00489660` reads `PTR___RTTI__16C2DMessageString_00489660`
once the target is labelled. The coordinator classified every item: type, length and reference
count unchanged, the new text a label of the plan, nothing else. No stored symbol changed; with
the last batch applied the check counts them as explained.

A fresh plan has nothing left to apply (1,855 plates, 2,033 labels and 3,680 types unchanged).
The record gained 1,855 `data-label`, 178 `data-label-mangled`, 1,855 `data-comment` and 23
`data-type` rows.

## The uninitialised data

The user added the missing block in the Memory Map window on 2026-11-27: `.bss`, 0x48d200 to
0x5d6cff, read and write, not executable, uninitialised. The coordinator compared the whole
program with the reviewer's baseline afterwards: the block is the only difference, and no
analysis ran.

A new plan with the block present held 1,839 more labels, 151 second labels, 1,839 plates and 228
types. Here the prototype has real types: string tables (`CSTable`, 29), scalars, pointers to
textures, nodes and the HUD, and class instances such as `CZNetwork`, `CTexManager`, `CAiMaps`,
`CEntityList`, `_zsys_public`, `CPnt4D[20]`, `RecoTuple[300]`.

The reviewer checked what is new about it before any write: creating data in an uninitialised
block behaves as elsewhere and makes no reference, because there is no stored value; all 61 type
names resolve to the prototype's path and size, add nothing to the type table, and none is one of
the empty placeholder types; no typed object runs past the next paired object (sizes come from
neighbour arithmetic, since an uninitialised object has no content); the objects whose layout
the pairing check found changed are not among the typed ones. Of the 747 names that rest on one
aligned witness it read 100 against the instructions that use them in both programs: none wrong
(68 anchored by an independently witnessed neighbour, 31 by position and access width, 1 not
checkable). Verdict: safe to apply, with one type withheld: `m_hud_textcolor__4CHUD` (0x577f90),
contradicted and offset-changed, which keeps its name (a row in `settled-data.tsv`).

| Run | Entries | Types | Outcome |
|---|---|---|---|
| pilot | 6 | 6 | an `int`, a locale id, a `CNode *`, a stream object, `RecoTuple[300]`, `CZNetwork`; check clean; saved, confirmed |
| batch 1 | 300 | 37 | no stop; check clean; saved, confirmed |
| batch 2 | 600 | 74 | no stop; check clean; saved, confirmed |
| batch 3 | 933 | 110 | no stop; check clean; saved, confirmed |

With both passes the release program has 3,694 named data objects, 329 second labels, 3,694
plates and 250 types from this step; a fresh plan has nothing left to apply. Still without a
name: 5,185 literals, 449 anonymous objects, 210 pairs the pairing check withholds, and 14 single
cases (an existing label, addresses inside an item or an instruction, conflicting rows, `_end`
just past the block).
## Open

- The memory block for the uninitialised data: done, see above. The references into it were
  added by the references step (`stage3-references.md`).

- **67 objects where analysis already defined untyped data** (81 items: 77 untyped scalars, 4
  pointers). Their real type would need a clear. It would drop 4 outgoing references, all of
  which the new `char *` types make again; the 559 references to these objects stay. Not built;
  the user's decision.
- The pairs nobody can confirm: names taken from a single aligned witness carry the flag in
  their plate.

## A wrong name found and corrected

While revising the name proposals with the new globals as context, `socom-release-newnames-p1`
saw that the RTTI record at 0x479f68, labelled `__RTTI__23CStickAccelerationTuner`, holds the
class name "CStickInertiaTuner": the release replaced that tuner class. The pair rested on order
alone, with one witness, and was not on the pairing check's withhold list, although the vtable
pointing at the record was (the `InitSystemTuners` group).

Every RTTI record holds its class name and every vtable points at its record, so the coordinator
checked all 678 such labels of this step against the release image: 677 agree, this one does not,
8 cannot be read that way. Corrected: the pair is settled as removed in `settled-data.tsv`; the
label in the release program was renamed to `__RTTI__18CStickInertiaTuner`, the name its own
string gives, and its plate says so (one `rename_label` and one `set_comment` through the bridge,
read back and saved; the record's two rows for the address follow). A fresh plan of the step
still has nothing to apply.

The same self-check is a way to name what is new in the release from its own strings: RTTI
records and vtables of classes that have no prototype counterpart. Not done here.

## The value of gp

The revision of the name proposals showed that many globals reached through the `gp` register
still appeared in the decompiler as raw variables (`iGpffff9114`) although their addresses carry
labels. `socom-release-gp-q1` found the cause, read-only: the decompiler resolves `gp + offset`
from the value of gp that the program's context holds at a function's entry, not from references.
In the prototype the MIPS constant analyzer set that value for every function because the
executable has a `_gp` symbol. The stripped release has none; the analyzer worked the value out
(0x494670, from `move gp,a0` in the entry function) only partway through its run, so functions it
had already passed never got it, and no function made later by the release tools has it. Of the
1,496 release functions that use gp, 933 decompiled with raw gp variables (4,685 accesses).

Fix, done by the user in the Ghidra window on 2026-11-28: Set Register Values, `gp` = 0x494670,
over the code block 0x00100000 to 0x0048d1ff. It writes only the context: no references, no
data, no names, no function bodies, no analysis. The bridge has no endpoint for register values,
and re-running the analyzer would have re-flowed every function.

Checked by the coordinator against a baseline taken before: all 1,496 functions decompiled again,
and none shows a raw gp variable (933 before); the function count (9,875), every name and
signature line and both programs' bookmarks are unchanged. The references themselves were a step
of its own, done on 2026-11-28: see `stage3-references.md` (18,430 references added).
