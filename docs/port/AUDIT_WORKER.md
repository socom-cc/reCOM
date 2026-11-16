# Audit worker brief

You judge one list of the correctness audit ([AUDIT_PLAN.md](AUDIT_PLAN.md)). Read
[WORKER_BRIEF.md](WORKER_BRIEF.md) first; it applies in full. This file adds what is specific to
an audit list. Your prompt names the list, your scratch folder and the files you own.

## What you are given

- The list: `build/port/audit/<list>.md` (rows `| # | Address | Bytes | Symbol | File |`).
- One packet per function: `build/port/audit/packets/<list>/<row>-<address>.md`, with an
  `INDEX.md`. A packet holds the annotated ELF disassembly, the port's source body with file and
  line, the member offsets named, the ELF callers and the leads earlier notes recorded. Functions
  over 3,000 bytes have their disassembly split into `.partN.md` files. Read the packet; do not
  fetch the same facts again with the tools. Fetch only what a packet lacks (a callee's body, a
  type it does not name), and say in your note what was missing so the packet tool can be fixed.
- The scan: `build/port/audit/scan-<list>.md`, the mechanical comparison of each function with
  the port's compiled code, ranked. A reported difference is a place to look, not a verdict: it
  flags two thirds of correct functions too, and it cannot see guards the ELF lacks, the order
  of float operations, or call arguments. A function with no reported difference still gets the
  full comparison.

## What you do

1. Work in the scan's rank order, highest score first, so the likeliest defects are judged
   before a usage limit can stop you.
2. For each function compare the port's body with the ELF instruction by instruction, as
   AUDIT_PLAN.md "What correct means" says: operand order, widths and signedness, the order of
   float operations, constants' words, calls and their arguments (registers and stack), what is
   stored where and when, and guards the ELF does not have.
3. Verdict per function: `MATCH`; `DEFECT-FIXED` graded A (changes what the player sees, or
   crashes), B (wrong, masked on this disc) or C (cosmetic); `DEVIATION-KEPT` only with the
   reason recorded in the code; `UNJUDGED` with the reason. Fix defects in place, from the ELF.
   ELF quirks are kept and noted. Nothing is tuned and no guard is added.
4. After each function, append its row to your note and to `NOTES.md` in your scratch folder, so
   nothing is lost if you are cut off. Do not batch the writing to the end.

## Testing, in proportion

- No emulator run per function. A targeted trace only for a grade A or B fix that the demo
  mission can reach, several fixes per run.
- One smoke run at the end, by kind of change (WORKER_BRIEF.md "Testing"). The coordinator runs
  the full behaviour check on the merged commit.
- The default build must link on your final tree.

## The note

`docs/port/notes/audit-<list>.md`, part of your `mine.txt`. Keep the first column layout exactly,
because `auditlist.py` reads judged addresses from it:

```
| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
```

Above the table: counts by verdict and grade, the defect rate, the fixes in one line each with
the ELF address that justifies them, the kept deviations, leads for other lists, what the packets
lacked, and the runs. It must pass `python tools/socom.py audit independence --strict`.

## Final report

At most 12 lines: counts, the A and B fixes, kept deviations, runs, files changed (= `mine.txt`),
edit files for files you do not own, open questions, and how many rows are left if you stopped
early.
