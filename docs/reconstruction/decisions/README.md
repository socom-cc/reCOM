# User decisions

Decisions the user made where the binary does not settle a question. They are inputs, not
generated output: amendments and plans cite them by repository path, LF-normalized SHA-256 and
heading (stage-4 `name_basis: "user"` and per-entry `decision` objects, see
[SOURCE_CORRELATION.md](../SOURCE_CORRELATION.md)). A file is revised under the rule below;
`python tools/socom.py source placements check --file <file>` re-verifies a placement file.

| File | Decision |
| --- | --- |
| [stage4-function-placements.md](stage4-function-placements.md) | Source files for the 194 stage-4 unresolved functions (2026-11-05/06): one `## module/file` heading per destination, `.h` headings for inline and template code |
| [stage4-compiler-copies.md](stage4-compiler-copies.md) | The 10 compiler copies among them and the headers they come from |

Stored revisions live in [history/](history/). `stage4-function-placements.fe2f75ed....md` is
the revision that 19 accepted stage-4 plans cite. It predates the 2026-11-06 move of
`CMatrix::operator const float (&)[4][4]() const` from `## zmath/zmath.h` to
`## zmath/zmath_matrix.h`; no plan places that function.

## Revising a decision file

1. Before the edit, copy the file byte for byte to `history/<stem>.<sha256>.md`, where
   `<sha256>` is its current LF-normalized SHA-256 (the digest `source placements check`
   prints). Stored revisions are never edited or removed, because plans may cite them.
2. Edit the file in place.
3. Run `python tools/socom.py source placements check --file <file>`. Besides the lines and
   destinations, it lists the stored revisions and every plan citation of the file, with the
   revision each cites and whether it still holds.

A citation of a stored earlier revision holds when the current file's cited heading still
exists, names the same destination, and still lists every artifact the citing row or entry
places from it. `source plan validate` and the stage-4 gate review then report it as a note
("cites revision X; current Y; this heading's placements for the row unchanged"), and the plan
and later stages stay as they are. If the cited heading lost one of those artifacts, was
removed, or names another destination, the citation is a problem and the citing plan is
amended to cite the current file. A digest with no stored revision, or a stored file whose
content does not have its name's digest, is also a problem.
