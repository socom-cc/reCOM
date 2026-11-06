# User decisions

Decisions the user made where the binary does not settle a question. They are inputs, not
generated output: amendments and plans cite them by repository path, LF-normalized SHA-256 and
heading (stage-4 `name_basis: "user"` and per-entry `decision` objects, see
[SOURCE_CORRELATION.md](../SOURCE_CORRELATION.md)). Change one only together with the plans that
cite it; `python tools/socom.py source placements check --file <file>` re-verifies a placement file.

| File | Decision |
| --- | --- |
| [stage4-function-placements.md](stage4-function-placements.md) | Source files for the 194 stage-4 unresolved functions (2026-11-05/06): one `## module/file` heading per destination, `.h` headings for inline and template code |
| [stage4-compiler-copies.md](stage4-compiler-copies.md) | The 10 compiler copies among them and the headers they come from |
