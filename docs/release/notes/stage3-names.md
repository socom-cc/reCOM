# Stage 3: names in the release program (running note)

What the names tool (`tools/release/names.py`) has applied to the Ghidra program `SCUS_971.34`,
batch by batch, and what changed in the program that `docs/release/ghidra-applied.tsv` cannot
show. Each batch was applied by the coordinator from a reviewed plan, checked with the checker's
own reads before the save, saved by the coordinator through the bridge, and confirmed with
`--confirm-saved`. Tool by `socom-release-names-n1`, review and batch checks by
`socom-release-names-review-r1`.

## Before the names: types

The user copied the `project` category tree of `support/socom-types.gdt` into the release
program in Ghidra's Data Type Manager (2026-11-26). Checked through the bridge: 1,399 types under
`/project` in both programs, the same name, category, size and path in every row, no `.conflict`.
Layouts were compared by size, not member by member. The types stay linked to the archive.

## Batches

| Batch | Plan | Entries | Creates | Names | Labels | Plates | Outcome |
|---|---|---|---|---|---|---|---|
| pilot one, gamez/zArchive | 2f72ff6c... | 74 | 0 | 71 | 71 | 74 | saved, confirmed (216 rows) |
| pilot two, gamez/zIntersect | 251bc5d6... | 63 | 4 | 63 | 62 | 63 | saved, confirmed (192 rows) |
| whole map, first try | 2d683270... | 2 | 0 | 1 | 1 | 2 | stopped on its third entry; saved, confirmed (4 rows) |
| whole map, batch 1 | 700f6398... | 466 | 79 | 447 | 227 | 466 | stopped at 0x15a600; saved, confirmed (1,219 rows) |
| whole map, batch 2 | e53b253f... | 900 | 34 | 826 | 468 | 900 | full batch, no stop, no side effect; check clean; saved, confirmed (2,228 rows) |
| whole map, batch 3 | e53b253f... | 2,500 | 138 | 2,335 | 2,327 | 2,500 | full batch, no stop, no side effect; check clean; saved, confirmed (7,300 rows) |
| whole map, batch 4 | e53b253f... | 2,000 | 128 | 1,822 | 1,765 | 2,000 | full batch, no stop, no side effect; check clean; saved, confirmed (5,715 rows) |
| whole map, batch 5 | e53b253f... | 2,000 | 284 | 1,941 | 1,088 | 2,000 | full batch, no stop, no side effect; check clean; saved, confirmed (5,313 rows) |
| whole map, batch 6 | e53b253f... | 1,471 | 51 | 992 | 372 | 1,471 | end of the map, no stop, no side effect; check clean; saved, confirmed (2,886 rows) |

Batch 2 rewrote the plates of the two thunks of batch 1 (0x1405c0, 0x1405d0), which now name
their targets; those two rows were replaced, not added.

| C library by place, (provider: newlib) | 21523369... | 109 | 0 | 109 | 0 | 109 | no stop, no side effect; check clean; saved, confirmed (218 rows) |

The pass is complete (2026-11-26): a dry run of the whole-map plan after batch 6 sends nothing.
With the C library names the record holds 25,180 saved rows: 718 creates, 8,607 names, 6,381
labels and 9,474 plates. The release program has 9,493 functions (8,772 after the
auto-analysis): the 718 created by the tool and 3 created by Ghidra's analysis during batch 1.

## Check of the whole map

After batch 6 the checker read the whole end state with one script of its own (both programs,
read-only) and found it as planned: all 8,498 names are on their functions and equal the
prototype program's name at the map's counterpart; all 6,381 labels and 9,474 plates are the
planned ones; every created function has the map's extent without gaps; the map starts without a
Ghidra function, the differing extents and the Ghidra-only functions are exactly the plan's sets;
36 thunks (20 from the analysis, 2 of batch 1, the 14 predicted); `socom.elf` and the release
program's bookmarks as they were; every record row reads back. Not verifiable through the bridge:
labels other than the planned ones, and reference changes that leave bodies and signatures as
they were.

## C library functions named by their place

Decided by the user on 2026-11-26, after the pass: a C standard library function that stands in
the same place as in the prototype may take its name although the pair is not exact, and a worker
may name such a function too (`RULES.md`). The rule had left 111 newlib functions without a name.
The block has the same order in both executables: 108 of them lie in the longest run of pairs
whose order agrees, and one, `exit` (0x423c78), moved from the head of the block to its
alphabetical place and is named because its callers decide it. 66 were deviating pairs, 43
unsure ones. Their plates say "named although the pair is not exact" and why. Two more
(`strtok_r` 0x42af00, `_vfiprintf_r` 0x42b8b8) lie inside another Ghidra function and wait for
their own. The change to the tool and its application were made by the coordinator and compared
with the applied plan entry by entry (109 names and their plates, nothing else); other libraries
stay on exact pairs.

A plan of the whole map made after the apply is not usable yet, for two reasons seen in that
comparison and left for the next change to the tool: it no longer knows the analysis names it
replaced (ten plates would lose that part), and it counts a default thunk that shows its target's
name as a second holder of that name (0x279ff0 and 0x27a660 would be called collisions). The C
library names were therefore planned for their module alone.

## Stops, and what they showed

- **Whole map, first try.** `create_function` at 0x1401d0 (`_root`: a system call with no return)
  read back as 0x1401d0..0x1405b7 instead of eight bytes: the flow fell through into the next
  function, which was itself still to be created. The coordinator was refused the delete; the
  user removed the function by hand. Since then a create is sent only when its body can be
  predicted (`tools/release/createflow.py`): 4 creates are withheld (0x1401d0, 0x1631c0,
  0x163300, 0x1baa20).
- **Batch 1.** The rename of 0x15a600 to `AddDmacHandler2` was refused: Ghidra's syscall analysis
  had named the function `AddDmacHandler` and already put the label `AddDmacHandler2` at that
  address, and a function cannot take the name of a label at its own entry. Nothing was changed
  there. In the map 0x15a5f0 is `AddDmacHandler` and 0x15a600 is `AddDmacHandler2`.

## In the program but not in the record

Changes that Ghidra's analysis made after a create of batch 1, not asked for by the plan. The
checker compared the whole function list and every body with its baseline: these are the only
ones, and each leaves Ghidra's layout equal to the map's.

- After the create at 0x1532c8 (`_rix_000`): the jumps from `_doMC` (0x1530a8) to 0x153fb8 and
  0x154018 (at 0x153238, 0x15327c and 0x1532bc) became calls, functions were created at both
  targets (0x153fb8..0x154013 and 0x154018..0x154077, unnamed: the plan had them as lying inside
  `_doMC`), and `_doMC` was cut back from 0x154077 to 0x1532c3. Before, Ghidra had followed
  those jumps and `_doMC`'s body had a hole where 0x1532c8 lies; the tool's overlap check tests
  addresses, and a hole is not part of a body.
- After the create at 0x159da8: the jump at 0x159dec to 0x159ed8 became a call and the function
  0x159ed8..0x159fbb was created. It was a planned create (`sceIpuStopDMA`) and got its name and
  plate from the tool afterwards; only the create itself has no row.
- 0x1405c0 and 0x1405d0 are thunk functions (they begin with a jump), as predicted.

Which analyzer turns such a jump into a call cannot be seen through the bridge.

## What the tool learned from batch 1

Changed by the builder after batch 1 (plan schema 3); the coordinator compared the new whole-map
plan with the reviewed one entry by entry: the writes differ only in the cases below and in the
three functions batch 1 freed, which now get their names.

- Any change after a create that the plan did not predict (a function that appears or vanishes,
  a body, name or flag that changes) stops the run. Nothing is predicted: the bridge does not
  show which analyzer acts, so the tool removes the triggers instead.
- A create that lies in a gap of an existing function's body is withheld: 0x317c00
  (`C2D::Enable`), in the 13 KB body Ghidra gives 0x315210.
- Creates that other creates fall or jump into are made before all others, so no create's
  analysis meets a jump to a planned start that does not exist yet.
- A planned name that is already a label at the function's entry is found when the plan is made
  and not sent. Every entry with a planned rename was read: 0x15a600 is the only case; it keeps
  `AddDmacHandler`, and its plate says why.
- Thunks the run creates are tracked like those of the starting snapshot (14 predicted).
- `--confirm-saved` also records a write that was sent but stopped the run before its read-back,
  and refuses while a function the report says to remove by hand still exists. A planned create
  that analysis already made gets a `create-by-analysis` row (not 0x159ed8 of batch 1).

Each batch is checked before its save with the checker's script (its own reads of both programs
against a baseline of the whole function list); the checker itself is called when the script
shows something unexplained, on a stop the tool does not explain, and for the whole map at the end.
What the script cannot see: labels other than the planned ones, and reference changes that leave
every body as it was.

## What the whole map will leave

- No Ghidra function of their own, 386 map functions (23,212 bytes): 373 starts without an
  instruction, 8 that lie inside another function (0x156978, 0x159780, 0x15b0b0, 0x1f4380,
  0x318580, 0x407c28, 0x42af00, 0x42b8b8), 5 withheld creates (0x1401d0, 0x1631c0, 0x163300,
  0x1baa20, 0x317c00).
- A function but no name, 810 (919 before the C library names): 602 new functions, 188 library
  pairs that are not exact, 15 unsure pairs, 4 flagged `name-changed`, `split` or `merged`,
  1 label clash.
- 28 boundary differences and 19 functions Ghidra has that the map does not.

## Every library named by its place

Decided by the user on 2026-11-27: the rule for the C standard library holds for every library,
to keep the release readable. Applied through a plan of the whole map (23288b71...), which
differed from the applied state in these entries only: 179 more library functions named, with
their plates and 3 mangled labels: Medius 112, SCE 29, RSA 18, lgAud 10, 989snd 6, libptt 3,
speech middleware 1. With the 109 of newlib, 288 library functions are named by their place: 7
of them deviating pairs out of place whose callers decide them, 46 unsure pairs in place. No stop,
no collision. The coordinator compared the whole function list with the baseline taken after the
signatures pass: exactly those 179 functions differ, in their name only; bookmarks and
`socom.elf` as they were. Saved and confirmed (361 rows).

Left on the old rule: 12 library pairs that are deviating, out of place and not decided by their
callers, and 12 unsure pairs out of place. A function but no name now: 631.

## Names for the functions the starts step made

After the function-starts step (`stage3-starts.md`) the release program had 382 more functions.
A plan of the whole map (ee819fc5...) differed from the applied state in those entries only:
282 names, 138 mangled labels and 382 plates; 74 of the new functions already carried the right
name from Ghidra's function-start patterns, and 9 pattern names on exact pairs were replaced by
the prototype's (`RFU005_ResumeIntrDispatch` to `RFU005`, four TLB stubs the patterns misname).
0x15a5d0 keeps `AddIntcHandler`: the prototype's `AddIntcHandler2` is a label there, like
`AddDmacHandler2` at 0x15a600. No stop, no collision. The coordinator compared the whole function
list with a baseline taken before the run: exactly the 282 renamed functions differ, in their name
only; bookmarks and `socom.elf` as they were. Saved and confirmed (802 rows).

9,199 of the map's 9,860 functions carry a name now. Without one: 626 new functions, 12 unsure
pairs, 12 library pairs that are deviating and out of place, 4 without a Ghidra function, 4
flagged pairs, 2 label clashes and 1 whose counterpart has no name.
