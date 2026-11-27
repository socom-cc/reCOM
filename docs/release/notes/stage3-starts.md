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
