# Stage 3: references to globals in the release program

The references from code to globals that Ghidra's analysis could not make in the release program
`SCUS_971.34`, added with `tools/release/references.py`. Tool by `socom-release-refs-f1`, review
and check script by `socom-release-refs-review-r6`; applied, saved and confirmed by the
coordinator on 2026-11-28. The user asked for the step after the value of gp was set
(`stage3-globals.md`).

## Why they were missing

- The block for the uninitialised data (0x48d200 to 0x5d6cff) did not exist when the analysis
  ran: the analyzer drops a reference to an address no block holds.
- gp had no value for most functions, so an access through gp had no target.

The decompiler resolves both today (the block exists, gp is set), but the reference lists of the
globals were incomplete: "who reads or writes this" showed a fraction of the truth.

## What is added, and how

One call per reference (`add_memory_reference`), derived from the instructions of the executable
with the data-flow of `tools/release/dataflow.py`:

- a load or store through gp or through a `lui` pair: READ or WRITE on the address operand;
- an address computation (`addiu`): DATA on the destination register.

Source type ANALYSIS: these are the references the analyzer makes itself when it can. The record
keeps every one (`docs/release/ghidra-applied.tsv`, kind `reference`), so they can be told from
Ghidra's own.

Read from the plugin's and Ghidra's classes by the author and again by the reviewer: the call
adds one reference, never duplicates one, creates no symbol, data or code unit at the target and
starts no analysis. Each write is its own transaction.

## The review

Verdict: safe to run the pilot; two defects to fix before any batch, both fixed and the new plan
compared with the reviewed one (1,157 entries moved to withheld, nothing else changed).

- A reference into the middle of a data item gives its target a name built from the item
  (`item+0x..`, `item.field`, `item[i]`). The tool accepted only plain automatic names and would
  have stopped after a correct write.
- The first plan went beyond the analyzer. The derivation reproduced the prototype's references
  exactly, but only because those targets were in uninitialised memory, where Ghidra marks the
  address computation itself. For initialised data it marks the access or the store instead, or
  nothing. The address computations into the initialised block were exactly what the release
  analysis had chosen not to mark.

The reviewer decoded all planned references independently (no mismatch) and read 216 by hand
against the listing (all real addresses of globals).

## Applied

| Kind | Uninitialised data | Initialised data |
|---|---|---|
| load through gp | 3,597 | 758 |
| store through gp | 2,320 | 393 |
| address through gp | 283 | 351 |
| load through an address pair | 3,003 | - |
| store through an address pair | 1,282 | - |
| address pair | 6,443 | - |
| **total** | **16,928** | **1,502** |

18,430 references to 4,528 addresses (3,996 in the uninitialised data): 7,358 READ, 3,995 WRITE,
7,077 DATA.

| Run | References | Outcome |
|---|---|---|
| pilot, `gamez/zBone`, first two | 2 | a gp load and an address pair; the user read both in the References editor: type, operand, source Analysis and primary as planned; check clean; saved, confirmed |
| pilot, the rest of the module | 20 | a load at an offset inside a labelled object, a gp store, a pair store, then the rest; saved, confirmed |
| pilot, three from the whole plan | 3 | a gp address and a gp store into initialised data, a load inside a typed structure (0x52718d now reads `zSys.isCdBoot`); check clean; saved, confirmed |
| batch 1 | 250 | no stop; check clean; saved, confirmed |
| batch 2 | 1,000 | no stop; check clean; saved, confirmed |
| batches 3 to 9 | 17,155 | no stop; saved and confirmed after each |

No run stopped and analysis answered no write. Every answer reported the new reference as
primary. The reviewer's check compared the whole program with a baseline after each batch
(functions, signature lines, data items, labels, types, bookmarks, the references of every
planned instruction and target, and the decompiler text of twenty functions spread over the
plan). Its items, all of two kinds the coordinator classified and accepted:

- the decompiler's line `WARNING: Globals starting with '_' overlap smaller symbols at the same
  address`, in functions that read four bytes at an address without sized data. The prototype's
  twin functions carry the same line;
- a dropped cast where `(type *)0x...` became `&DAT_...`.

The function map changed during the pilot (`library-pairs.md`); the tool refuses a plan made from
another map, so both plans were made again and compared with the reviewed ones: the same entries.
A fresh plan has nothing left to apply.

## Visible effect

- A global's reference list now holds its readers and writers.
- A target with no label and no data reads `DAT_<address>` in the decompiler where it read
  `uRam<address>`; a target inside a typed object reads as its member.
- A named object without a type still shows only its first address by name: `boneArchive`
  (0x4b4320) is read at +4 and +8 as `_DAT_004b4324` and `_DAT_004b4328`. The prototype program
  shows the same, because it never typed the object either.

## Withheld

| Reason | Count |
|---|---|
| access through a register plus an offset (the analyzer marks fewer than half; a third fall outside the object they start from) | 1,535 |
| address pair into the initialised block | 1,096 |
| instruction that already carries another reference | 109 |
| gp address into the initialised block: a base, stored, or a second reference in the function | 61 |
| left half of an unaligned load | 36 |
| `lui`/`ori` constant | 16 |
| the value of gp itself | 9 |
| into code that is no function entry | 3 |
| outside every block | 2 |

## Open

- **Types for named globals the prototype program left untyped.** 1,531 named globals had no type
  to carry because the prototype program has no data item there, 631 of them larger than 8 bytes.
  The debug data and the source know many of these types (`boneArchive` is a `CScriptArchive`).
  With a type their members would read by name. Not started; the user's decision. Objects whose
  layout changed in the release need their type corrected in stage 4 first.
- The register-offset accesses: member accesses of typed objects resolve in the decompiler once
  the object has its type, so they follow from the point above rather than from more references.
