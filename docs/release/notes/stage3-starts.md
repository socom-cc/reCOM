# Stage 3: function starts in the release program (running note)

Giving a Ghidra function to the release-map functions that had none, with
`tools/release/starts.py`. Tool by `socom-release-starts-t1`, review and check script by
`socom-release-starts-review-r3`; applied, saved and confirmed by the coordinator. Decided by the
user on 2026-11-27: this comes before the globals. The names step is in `stage3-names.md`, the
signatures step in `stage3-signatures.md`.

## What was missing and what the plan does

After the names and signatures passes 386 map functions had no Ghidra function and 20 had a
body that differs from the map's extent. The plan (db2673fb..., 406 entries):

| Case | Entries | Plan |
|---|---|---|
| starts where Ghidra never disassembled | 371 | disassemble exactly the map's extent, flow following off, then create |
| functions inside another Ghidra function | 8 | create; Ghidra cuts the container back to its map extent, which also mends 8 of the 20 bodies |
| creates the names tool had withheld | 3 | create, with padding (0x1401d0) or dead words (0x1baa20) accepted; 0x317c00 after 0x318580 |
| bodies accepted as they are | 2 | 0x145210 (padding after a call), 0x15a418 (unreachable words after an `eret`) |
| withheld | 4 | 0x15d124 (its return's delay slot is the next function's entry), 0x3d4b98 (a switch Ghidra has not resolved), 0x1631c0 and 0x163300 (kernel snippets with code after an `eret`) |
| cannot be mended with creates | 10 | Ghidra split each into a thunk and a function at +0xc (0x193890, 0x196c40, 0x1a2760, 0x1a2ae0, 0x1f1de0, 0x227980, 0x22d3e0, 0x234900, 0x312950, 0x3bcd90); `create_function` takes no body |

The 371 are plain code that nothing references (one is referenced from data, one is partly
disassembled already). A body that differs from the map by padding or unreachable words only is
recorded as `extent-accepted`.

## What the endpoints do

Read from the plugin's and Ghidra's classes by the author and again by the reviewer:

- `disassemble_bytes` runs Ghidra's disassemble command over the range; the bridge's parameter
  named `restrict_to_execute_memory` is in fact "follow flow", and the tool sends it off. Only
  undefined bytes are disassembled; defined data is skipped.
- `create_function` with `disassemble_first` follows all flow and is never used.
- After a write Ghidra's analysis runs. The Shared Return analysis turns unconditional jumps to
  a function entry into calls and can create a function at the target of a jump that crosses a
  function; this is what changed `_doMC` in the names pass. It also runs after the disassembly
  of a start that ends in a jump (53 of the 371).

## The review

Verdict: safe to run the pilot, on these conditions: after any stop, any side effect, any data
defined elsewhere than predicted, any bookmark change, or a check that does not end clean, the
program is closed without saving; the tool's "remove the function by hand" advice is not used
(it would not give a cut container its body back); every run is saved, confirmed and replanned
before the next. The reviewer checked all 371 starts (extents equal the map's, every word
decodes, 329 have the same operations as their prototype counterpart) and reproduced all 382
predictions with its own model. Its defects, none blocking: a timeout while waiting for analysis
ended a run without its report (fixed by the coordinator before the pilot); the read-back of a
jump turned into a call is weak; the Shared Return effect after a disassembly is neither
predicted nor checked; two analyzers that run on new code are not modelled.

The tool's own snapshot does not see changes inside a body that keep its ends, orphan
instructions in a gap, references or flow overrides; the reviewer's check script compares the
code-unit state around every planned address, every function, both programs' bookmarks, the data
items and the jump sites against a baseline.

## Pilot

| Step | Entries | Outcome |
|---|---|---|
| 1 | 0x1435e0 | 3 instructions disassembled, function created with the map's 12 bytes; no stop, no analysis change; check clean; saved, confirmed |
| 2 | 0x1401d0 | function created with the predicted body 0x1401d0..0x1401df, the eight bytes of padding accepted (`extent-accepted`); it did not take its neighbour; check clean; saved, confirmed |
| 3, first entry | 0x15a5a0 | disassembled and created with the map's sixteen bytes; the run stopped because the function read back as `SetVCommonHandler`, not under a default name; accepted by the coordinator, saved, confirmed |

The stop in step 3: 0x15a5a0 is a kernel call stub (`li v1,0xe; syscall; jr ra; nop`), and
Ghidra's PS2 analysis names a function from the system call in it. The name it gave is the one the
prototype program has for the exact counterpart (0x15b1e0). The tool's snapshot of every function
and the reviewer's check both showed that name as the only difference; the function has no label
besides it. The coordinator accepted it on that evidence instead of closing without saving, which
the reviewer's condition would have asked for. 88 of the planned starts hold a `syscall`
instruction, so the tool has to predict this naming before the pilot goes on.
| 3, second entry | 0x162cf0 | disassembled over its map extent; the run stopped before the create because Ghidra had disassembled other code on its own; accepted by the coordinator, saved, confirmed |

The second stop in step 3: 0x162cf0 passes the address 0x163400 as a parameter (it installs debug
handlers; its prototype counterpart is `SetDebugHandler`). Ghidra's operand-reference analysis
took that address for code and disassembled 0x163400..0x1634fb, 63 instructions that end in an
`eret`, leaving one "Found Code" bookmark at 0x163400. The reviewer's check showed those 63 words
and that bookmark as the only differences; no function appeared or changed and no data was
defined. The coordinator accepted it: it is the handler that function installs, and it is what
Ghidra's analysis would have made had it reached 0x162cf0 by itself. Not in the record: those 63
instructions and the bookmark. The plan had listed the reference as one to undefined data.

What this shows about the map: the release's handler starts at 0x163400, while the map has one
row 0x163300..0x16351b paired with the prototype's `_kDebugException` (0x164040), and that row
holds an `eret` at 0x1633f0, the handler from 0x163400 to its `eret` at 0x1634f8, and more words
after it. The row covers more than one routine; it is one of the two starts withheld for code
after an `eret`. Left for the comparison to settle.
| 3, three more | 0x162cf0, 0x16fef0, 0x1d2780 | 0x162cf0 created; 0x16fef0 disassembled where it was not yet code and created with its map extent; 0x1d2780 disassembled and created as the predicted thunk of 0x20ae80. The run stopped at the thunk on the tool's own expectation, not on the program: it expected the thunk's signature line under the target's name, and a thunk shows it under its own (`undefined thunk_FUN_0020ae80(void)`). The reviewer's check was clean, with nothing unexplained; the expectation is corrected in the tool. Saved, confirmed |
| 3, the last three | 0x390018, 0x34b850, 0x405e50 | disassembled and created, no stop; analysis defined one pointer, at 0x44c678, an address the plan lists as possible; check clean; saved, confirmed |
| 4 | 0x318580, 0x317c00 | both created, no stop; the create at 0x318580 cut `C2DBitmapPoly::GetTrans` (0x315210) from 13 KB back to the map's eight bytes, as predicted, and 0x317c00 took its place in what had been a gap of that body; check clean; saved, confirmed |
| 5 | 0x42af00 | `strtok_r` created inside what Ghidra had as `strtok`; `strtok` (0x42aee0) cut back to 0x42aee0..0x42aeff and the jump at 0x42aef8 turned into a call, both as predicted; check clean; saved, confirmed |

The pilot is complete: 12 functions created, one of every kind of case. Three runs stopped, each
on something the tool did not yet predict (a name from Ghidra's pattern file, code found through
an operand reference, the text of a thunk's signature line); each was understood, accepted on the
evidence of the reviewer's check, and is predicted now. The last five entries, with both container
cuts, ran without a stop.

## Batches

| Batch | Entries done | Outcome |
|---|---|---|
| 1 (of 40) | 25 created, 0x1522d0 disassembled | stopped after the disassembly of 0x1522d0: analysis defined 11 data items the plan had not listed; accepted by the coordinator, saved, confirmed |

The stop in batch 1: the plan expects data only at an address the new code names directly
(0x443ab0 here). Ghidra's analysis also defines data at the offsets the code reads and writes from
such a base: 0x443ab4 (a pointer) and 0x443ab8..0x443acc (seven four-byte items), and three
hardware registers at 0x10004004..0x1000400c. The reviewer's check showed those 11 items as the
only differences. Data of this kind is what Ghidra's analysis made all over the program (it holds
over 32,000 such items); none of it lies in code. Accepted; the tool is to accept data that
analysis defines outside executable memory and list it, and to keep stopping on data inside code.
| 2 (of 60) | 60 created | no stop; 43 named by Ghidra's patterns and 2 containers cut, all predicted; the check's 86 items are those names; saved, confirmed |
| 3 (of 150) | 150 created | no stop; 40 named by the patterns, 2 containers cut, 2 bodies accepted with dead words; one byte of data defined by analysis away from code (0x45ff30); saved, confirmed |
| 4 (the rest) | 59 created, 0x3c9c98 disassembled | stopped after the disassembly of 0x3c9c98: analysis replaced seven untyped items at 0x44c208..0x44c20f by one eight-byte item; accepted by the coordinator, saved, confirmed |

The stop in batch 4: 0x3c9c98 reads eight bytes at 0x44c208 as one value. Earlier analysis had
left those bytes as an `undefined2` and six `undefined1` items; Ghidra took them into one
`undefined8`. Both the removed items and the new one are Ghidra's own untyped placeholders, in a
data area; the reviewer's check showed these eight changes and nothing else. The tool now accepts
and lists an untyped item that analysis takes into a wider one away from code, and still stops
when a typed item is removed.
| 5 (the rest) | 76 created | no stop; 2 containers cut, 2 bodies accepted with dead words; five data items defined by analysis, three of them at predicted addresses, two away from code; saved, confirmed |

## Result

The step is complete (2026-11-27): a fresh plan has no entry left to apply, and its dry run sends
nothing. The release program has 9,875 functions (9,493 before the step). The record gained
371 `disassemble` and 382 `create` rows (the functions made by this step, 12 of them in the
pilot), 8 `cut-by-analysis`, 7 `extent-accepted`, 83 `name-by-analysis` and 1 `label-by-analysis`;
it holds 30,736 rows, all saved.

Of the 9,860 functions of the map, 9,843 now have a Ghidra function with the map's extent or an
accepted one. What is left, each with its reason in the plan:

- 3 bodies accepted as they are: 0x1401d0 and 0x145210 (padding), 0x15a418 (unreachable words
  after an `eret`).
- 4 withheld: 0x15d124 (its return's delay slot is the entry of 0x15d128), 0x3d4b98 (a switch
  Ghidra has not resolved), 0x1631c0 and 0x163300 (code after an `eret`; the handler at 0x163400
  inside the second row is code without a function).
- 10 that creates cannot mend: Ghidra split each into a thunk and a function at +0xc.

Nine runs stopped in all, five kinds of cause: a name from Ghidra's function-start patterns, code
found through an operand reference, the tool's expectation of a thunk's signature line, data
defined at offsets from a base, untyped data taken into a wider item. Each was accepted by the
coordinator on the evidence of the reviewer's check, item by item, and the tool predicts or
accepts each kind now; none needed the program closed without saving. In the program without a
record row: the 63 instructions at 0x163400 with their bookmark, and the data items analysis
defined (listed in the apply reports).
