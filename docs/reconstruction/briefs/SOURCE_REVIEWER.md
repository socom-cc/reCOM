# Stage 4 source-owner scrutinizer brief (token-lean, draft-based)

You independently challenge the stage-4 plan(s) named in your prompt, as ACCEPTER (role
socom-source-owner-scrutinizer; skill socom-source-owner-scrutiny). AGENTS.md is in context.
Read docs/reconstruction/SOURCE_CORRELATION.md ("## Plan items" through "### Validation", and the
`source sql` schema) and build/batch-helpers/SOURCE_PLANNER.md (the planners' rules).

Per plan:
1. The plan matches the sha256 its handoff cites; the item is awaiting_acceptance (re-check right
   before deciding); `source plan validate --plan <plan> --check` and `source plan draft --check
   <plan>` are ok. Rows carrying `draft_rule` (including P-mw-unit, P-gnu-section and the
   section-containment P-gnu-data) are proven by the tool: do not re-review them - EXCEPT
   `D-referenced` rows on GLOBAL data (known defect: one reader is not the definer): check each
   lies in its unit's place in data-section link order (.sdata/.sbss/.bss keep link order);
   a GLOBAL D-referenced row sitting between other units' data is a finding.
   `source plan open --plan <plan> --format json` lists what is still open; do not load whole plan
   or evidence JSON when a `source sql` query answers the question.
2. Review only: hand-decided artifacts (no `draft_rule`; `decide` writes these), each
   `override <artifact>: ...` note, hand rows taken from a `suggest` (S-* rules are not proofs:
   check the basis), `name_basis` provisional/invented/user owner rows and entry `decision`s
   (re-run `source placements check --file <decision file>`), owner-row paths, unresolved
   reasons, retire rows, header emits (H-template-family/H-class-header rows are drafted),
   provider `linked`/`archive`/`version` fields and the `reservation`. Use `source sql` and
   `reference relocations`, not your own parsers. Attack each positive claim: a contiguity placement
   rated high, a unit boundary without an anchor or a consistent relocation/symbol-order argument, a
   provider row without archive-member evidence, a header-emit reason that does not match the
   symbol, a retire row without evidence, or a reservation correction without evidence is a
   finding. Check the validator's review notes. Unnamed objects (user decision 2026-10-31) must be
   owned (provisional-file match medium, else invented name low), not left unresolved, when their
   extent is proven; a unit spanning segments must use the same path as in other plans. Every
   owned MSL template instance needs a header emit (header from sibling instances' DWARF), LOCAL
   copies like find/find_if (`<algorithm>`) included. An inline copy (binding 13/WEAK) referenced
   from functions of two or more units (incl. vtable/__sinit references) must be defined in a
   shared header (ODR): it emits to its class's header - a DWARF header unit, else the provisional
   header that declares the class (precedent: accepted 015 zai.h) - implicit and explicit members
   alike; a copy reached only through its class's vtable counts every unit that reads that vtable
   or constructs the class (parent ruling, as accepted 031/036/037); the unit that keeps the copy
   counts too (kept in A, used by B = 2 units). Implicit special members (implicit ctor/dtor/op=)
   always go to their class's header when one declares the class, whatever the unit count; so
   do instances of project templates (RTArray<...>, RTList<...>) to the header declaring the template.
   Known emit-check limit: it calls every dtor without its own DWARF subprogram implicit; a
   user-written body (deletes elements, sets members) referenced by one unit gets no emit and a
   note "user-written ...; used by 1 unit" - accept that note although emit-check lists the row. An inline copy referenced from
   one unit only may be defined in that .cpp (no emit, say so).
   When no header is evidenced at all (no DWARF header unit, no provisional header declares the
   class), the plan records no emit plus a note "used by N units; no header declares it" - do not
   ask for an invented header (precedent: CRemoteCtrl, CAiSCorpse). Say whether a competing split fits the evidence
   equally well; if so, the placement must be medium/low or unresolved.
3. Decide: `progress work accept --item <id> --accepter <ACCEPTER> --evidence "<data-derived
   summary>" --expected-revision <rev>` or `progress work reject --item <id> --reviewer <ACCEPTER>
   --reason "<every finding: artifact, what is wrong, evidence, fix>" --expected-revision <rev>`.
   Check exit code and JSON ok.

Read-only except scratch under build/source-plans/<ACCEPTER>/. No src/, Ghidra, memory or issue
ledger. Report <= 6 lines per item.
