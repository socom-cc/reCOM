# Stage 2 checker brief

Standing instructions for an agent that checks one list of the release comparison. The
coordinator's prompt names you, your list and your scratch folder; everything else is here.
Read `RULES.md` and `COMPARISON.md` first, and `notes/zArchive.md` and `notes/zMPEG.md` as models.

## What you are checking

`python tools/release/compare.py` pairs every function of the release executable with a
prototype function and classes it. In the modules checked so far the deviating pairs it commits
to were right every time (two modules row by row, then 45 of 45 sampled). Its errors were of two
kinds: pairs it failed to make, shown as one "new" and one "removed" row, and byte-identical
small functions given to the wrong twin (two exact pairs between empty virtuals, told apart only
by position; the tool reads vtables since then). So a list holds:

- every **uncertain** row: unsure, new, removed, the weakly evidenced pairs (`slot-only`,
  `role-only`), the rows flagged `identical-copy` (equal bytes exist elsewhere and no vtable
  slot, table entry, caller or settled row decided which copy this is) and the rows flagged
  `caller-mismatch` (the two sides' callers do not correspond);
- a **sample** of the deviating rows, as a guard on the committed pairs;
- the count of exact rows, which you do not check.

You did not write the tool. Do not trust its uncertain rows, and treat a wrong sampled row as a
finding that matters more than any other.

## Limits

- You write one tracked file: your note (below). You change nothing under `src/`, `port/`,
  `tools/`, `tests/`, and none of the generated files (`function-map.tsv`, `COMPARISON.md`) or
  `settled-pairs.tsv`.
- No commit, no sub-agents, no tracker commands that change state.
- Ghidra is read-only for you and seldom needed. If you use it, every call names its program:
  `socom.elf` (prototype) or `SCUS_971.34` (release). No writes, renames, scripts or saves.
- No local paths, account names or disc locations in the note.
- Scratch goes only into the folder you were given under `build/release/`.

## Method

1. Print your list and its sheet:
   `python tools/release/compare.py --lists <module> --split <n>` and
   `python tools/release/compare.py --sheet <module> --list <letter>` (the prompt gives the
   exact arguments). The sheet shows, per row, both sides' call lists and callers by name, the
   strings and (file, line) tokens, the immediate deltas per base register and the differing
   instructions.
2. Settle each uncertain row. What has settled rows fastest so far, in this order: the call
   site inside an already paired caller; a scan of both images for callers of each side; the
   line-number arguments of the debug allocators; the slot between paired neighbours; strings.
   Disassemble both sides when those do not decide it (`tools/release/` decodes either
   executable; `port/tools/dev/` helpers work on the prototype).
   - A "new" row and a "removed" row that are one function: a pair, deviating.
   - A weak pair: confirm it or split it into a new and a removed row.
   - An `identical-copy` row: a vtable slot, a caller or a stored pointer decides which twin it
     is. Where nothing can, say so in one line ("twins undecidable"): the code is the same, and
     only the name is in doubt. Do several such rows as one batch.
   - A virtual function has no direct caller: use the vtable and slot the sheet shows for it.
   - A row you cannot settle stays unsure, with the reason.
3. Check each sampled deviating row: same function on both sides, yes or no. Do not describe
   what changed in it; that belongs to stage 4.
4. **Cross-check every committed pair of your owner files**, not only the sample. The sample of
   15 is too thin: in zNetwork a checker who compared the callers and the loaded function
   pointers of all 262 paired rows of its files found seven wrong pairs the sample had not
   shown (two crossed callbacks, four empty handlers one place off, a function paired with the
   wrong half of a split). Do the same over your list's address ranges: for each pair, the
   paired images of the prototype side's callers and address-loaders should be the release
   side's, and a pointer should go to the same argument or table offset. The tool's own pass
   flags only the cases where the two caller sets share nothing; you look at every difference.
   `build/release/check-zNetwork-a/xcheck.py` and `fptrs.py` are that checker's scripts (scratch,
   read them as an example, write your own in your folder). Most differences are callers that
   moved or were inlined: say so in a word and move on. Report every pair this shows to be
   wrong; those are the findings that matter most.
5. For a function that is really new: one line on what it does and a proposed name with its
   basis. A guess is fine when it is marked as a guess. For one that is really removed: one
   line on where its work went, if the callers show it.
6. Note a class layout change only when a row you settled shows it plainly. Do not go looking.

## The note

`docs/release/notes/<module>-<letter>.md` (or `<module>.md` for an unsplit module):

1. One paragraph: the list, the row counts per class, who checked (you) and who produced the
   pairing (`socom-release-compare-c1`), the commit you worked on.
2. **Checked rows**: one line per row: release address, prototype address and symbol, the
   tool's class and evidence kind, your verdict (confirmed / corrected to ...), the reason in a
   few words.
3. **Settled pairs**: every row whose class or counterpart you changed or settled, in the
   format of `settled-pairs.tsv` (release address, prototype address or `new` / `removed`,
   basis, your name, date). The coordinator adds them to that file.
4. **New and removed**: the really new functions (what they do, proposed name, basis) and the
   really removed ones.
5. **Still unsure**, with reasons.
6. **How the tool did**: right and wrong per class; for each wrong row, what misled it; the
   sample's result and the cross-check's result (pairs compared, differences looked at, pairs
   wrong) each on its own line.

## The report

Short: rows checked per class, the tool's score per class, the sample's result, rows settled
and left, anything you could not verify, and what cost you the most time.
