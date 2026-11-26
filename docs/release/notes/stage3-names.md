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

The record holds 1,631 saved rows. The release program has 8,858 functions (8,772 after the
auto-analysis).

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

## Open before the next batch

- A function that appears or vanishes, or a body that changes, after a create is to stop the
  run, not only be reported.
- Creates that lie in the lowest-to-highest range of an existing function (one is left:
  0x317c00, inside the 13 KB body of 0x315210) and creates next to existing functions that jump
  into map starts that are not functions yet (0x156b30 and 0x156c40 to 0x156978, 0x159658 to
  0x159780, 0x1f4370 to 0x1f4380, 0x315210 to 0x318580) are to be withheld or batched apart.
- A planned name that already exists as a label at the function's entry is to be found when
  the plan is made (0x15a600 is the only case in the kernel region; the default-named functions
  elsewhere were not scanned).
- Thunks created by the run are to be tracked, for the label read-back at 0x288ad0.
- Not touched by any batch: 373 map starts without an instruction, 31 boundary differences,
  19 functions Ghidra has that the map does not, the 4 withheld creates.
