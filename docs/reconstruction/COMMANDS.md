# soCOM Command Index

Generated from `python tools/socom.py commands --json`.

| Command | Category | Workspace writes | Ghidra requirement | Live Ghidra writes | Purpose |
| --- | --- | ---: | --- | ---: | --- |
| `python tools/socom.py commands` | docs | no | none | no | List the authoritative machine-readable command registry. |
| `python tools/socom.py help` | docs | no | none | no | Show registry metadata for one command path. |
| `python tools/socom.py doctor` | validation | no | optional | no | Run categorized workspace health checks. |
| `python tools/socom.py env` | validation | no | none | no | Report the local host and pinned toolchain environment. |
| `python tools/socom.py policy show` | docs | no | none | no | Show machine-readable reconstruction policy and stage order. |
| `python tools/socom.py toolchain bootstrap` | toolchain | yes | none | no | Acquire and verify the pinned Metrowerks toolchain. |
| `python tools/socom.py toolchain verify` | toolchain | no | none | no | Verify pinned compiler identity and optional compile readiness. |
| `python tools/socom.py reference census` | reference | yes | none | no | Parse the immutable ELF into a deterministic evidence census. |
| `python tools/socom.py reference verify` | reference | no | none | no | Deep-compare the complete stored census with a fresh ELF parse. |
| `python tools/socom.py reference show` | reference | no | none | no | Query stored reference sections or symbols. |
| `python tools/socom.py reference relocations` | reference | no | none | no | Query MIPS relocations with symbol and HI16/LO16 context. |
| `python tools/socom.py debug inspect` | debug | no | none | no | Inspect DWARF 1 and line-program facts. |
| `python tools/socom.py debug graph` | debug | no | none | no | Build the scoped DWARF import graph without mutating Ghidra. |
| `python tools/socom.py debug conflicts list` | debug | no | none | no | List scoped blocking DWARF definition conflicts. |
| `python tools/socom.py debug import-plan` | debug | no | none | no | Build a deterministic scoped Ghidra import plan. |
| `python tools/socom.py debug apply-program` | debug | no | none | no | Translate an accepted type plan into deterministic Ghidra type operations. |
| `python tools/socom.py debug batch-program` | debug | no | none | no | Translate an accepted DWARF batch plan into deterministic Ghidra function and global operations. |
| `python tools/socom.py ghidra preflight` | ghidra | no | required | no | Verify project soCOM and the explicit socom.elf program. |
| `python tools/socom.py ghidra preflight-batch` | ghidra | no | required | no | Dry-run a batch program against live Ghidra: every read and pre-write check, no writes. |
| `python tools/socom.py ghidra fingerprint` | ghidra | yes | required | no | Fingerprint every function signature, data item, type, block and reference; optionally diff two. |
| `python tools/socom.py ghidra apply-batch` | ghidra | yes | required | yes | Apply a translated batch program (names, prototypes, globals) under the item's writer lease and verify it. |
| `python tools/socom.py ghidra apply-recon` | ghidra | yes | required | yes | Apply a reviewed reconstruction group or recon repair program under the item's writer lease and verify it. |
| `python tools/socom.py ghidra restore-accepted` | ghidra | yes | required | yes | Replay accepted Ghidra applies on a fresh baseline import and prove their receipts reproduce. |
| `python tools/socom.py ghidra repair-labels` | ghidra | yes | required | yes | Delete the readable labels a recorded label repair names, under the repair item's writer lease. |
| `python tools/socom.py ghidra check-names-repair` | ghidra | yes | required | no | Run the names repair verifier's checklist read-only and print evidence lines. |
| `python tools/socom.py ghidra repair-names` | ghidra | yes | required | yes | Give mangled functions their readable names (names repair), with --dry-run, under the writer lease. |
| `python tools/socom.py ghidra repair-signatures` | ghidra | yes | required | yes | Restore function signatures a recorded repair names, under the repair item's writer lease. |
| `python tools/socom.py ghidra map-zero-fill` | ghidra | yes | required | yes | Map the ELF load image's zero fill in Ghidra under the item's writer lease. |
| `python tools/socom.py ghidra apply-types` | ghidra | yes | required | yes | Apply a translated type program under the item's writer lease and verify it. |
| `python tools/socom.py ghidra data-overlap` | ghidra | no | required | no | Report overlapping Ghidra data roots. |
| `python tools/socom.py ghidra receipt` | ghidra | yes | required | no | Create a portable deterministic semantic receipt. |
| `python tools/socom.py audit agent-surface` | audit | no | none | no | Audit command, skill, role, and harness alignment. |
| `python tools/socom.py audit capability-coverage` | audit | no | none | no | Audit active, deferred, and target-inapplicable capabilities. |
| `python tools/socom.py audit current-metadata` | audit | no | none | no | Verify generated current progress metadata. |
| `python tools/socom.py audit docblocks` | audit | no | none | no | Validate source annotation grammar and evidence identities. |
| `python tools/socom.py audit docs` | audit | no | none | no | Audit local documentation links and registered command invocations. |
| `python tools/socom.py audit final-elf-catalog` | audit | no | none | no | Report typed file and loaded-memory ELF coverage. |
| `python tools/socom.py audit independence` | audit | no | none | no | Reject foreign-project, machine-specific, or external-workspace dependencies. |
| `python tools/socom.py audit issues` | audit | no | none | no | Validate the workspace issue ledger. |
| `python tools/socom.py audit live-validation-surface` | audit | no | none | no | Reject retired shadow state and changed immutable inputs. |
| `python tools/socom.py audit pipeline-reachability` | audit | no | none | no | Prove each stage has a reachable evidence producer. |
| `python tools/socom.py audit provenance` | audit | no | none | no | Audit immutable ELF and compiler provenance. |
| `python tools/socom.py audit retired-surface` | audit | no | none | no | Reject obsolete analysis-backend files and terms. |
| `python tools/socom.py audit source-trace` | audit | no | none | no | Validate source-to-artifact topology and accepted coverage. |
| `python tools/socom.py audit source-fragments` | audit | no | none | no | Inventory prohibited production source fragments. |
| `python tools/socom.py audit workflow-contracts` | audit | no | none | no | Audit reservation, acceptance, and mutation contracts. |
| `python tools/socom.py audit workspace` | audit | no | none | no | Detect generated artifacts outside approved roots. |
| `python tools/socom.py guard modern-cpp` | guard | no | none | no | Reject constructs unavailable to the pinned 2000-era Metrowerks compiler. |
| `python tools/socom.py guard original-symbol` | guard | no | none | no | Reject Ghidra autogenerated identities as authored source dependencies. |
| `python tools/socom.py guard provider` | guard | no | none | no | Reject explicit reconstruction shims, stubs, fakes, and dummy providers. |
| `python tools/socom.py guard raw-assembly` | guard | no | none | no | Reject unreviewed inline/raw assembly in provisional source. |
| `python tools/socom.py guard raw-image` | guard | no | none | no | Reject hard-coded addresses in the original PS2 image range. |
| `python tools/socom.py guard raw-offset` | guard | no | none | no | Reject numeric byte/void pointer offsets used as recovered fields. |
| `python tools/socom.py guard reinterpret-cast` | guard | no | none | no | Reject C++ reinterpret_cast as a substitute for recovered types. |
| `python tools/socom.py guard source-fragments` | guard | no | none | no | Reject production .inl files and quoted inclusion of source files. |
| `python tools/socom.py guard source-shape` | guard | no | none | no | Reject common source-shape scaffolds which hide unrecovered semantics. |
| `python tools/socom.py guard source-placement` | guard | no | none | no | Reject machine-specific paths in active source. |
| `python tools/socom.py issue audit` | issue | no | none | no | Validate the workspace issue ledger. |
| `python tools/socom.py issue list` | issue | no | none | no | List open or all workspace issues. |
| `python tools/socom.py issue show` | issue | no | none | no | Show one workspace issue. |
| `python tools/socom.py issue report` | issue | yes | none | no | Record a tooling/process problem. |
| `python tools/socom.py issue request` | issue | yes | none | no | Record a tooling/process improvement request. |
| `python tools/socom.py issue resolve` | issue | yes | none | no | Resolve a workspace issue. |
| `python tools/socom.py issue reopen` | issue | yes | none | no | Reopen a workspace issue. |
| `python tools/socom.py docs readme-progress` | docs | yes | none | no | Check or update the generated README progress snapshot. |
| `python tools/socom.py docs command-index` | docs | yes | none | no | Check or update the generated complete command index. |
| `python tools/socom.py docs capability-coverage` | docs | yes | none | no | Check or update the generated tool coverage inventory. |
| `python tools/socom.py recon graph` | recon | no | none | no | Build the deterministic callee-first function groups from the ELF. |
| `python tools/socom.py recon evidence` | recon | yes | none | no | Write a reconstruction group's file-only planning evidence. |
| `python tools/socom.py recon validate` | recon | no | none | no | Check a reconstruction plan against its group and the ELF. |
| `python tools/socom.py recon program` | recon | yes | none | no | Translate a valid reconstruction plan into an apply program. |
| `python tools/socom.py ghidra check-recon-apply` | ghidra | yes | required | no | Run the stage 3 apply verifier's checklist read-only and print evidence lines. |
| `python tools/socom.py recon facts` | recon | no | none | no | Print compact ELF-derived call-contract facts for functions or a group. |
| `python tools/socom.py recon asm` | recon | no | none | no | Print annotated ELF disassembly of functions. |
| `python tools/socom.py recon draft` | recon | no | required | no | Draft a plan's rule-decided rows from facts and live types, or --check a plan's drafted rows. |
| `python tools/socom.py recon void` | recon | no | none | no | Print the void verdict of functions: exit values, the first blocking caller chain, and the vtable slot family verdict. |
| `python tools/socom.py recon bytes` | recon | no | none | no | Print initialized bytes at an address or symbol, with relocated words and strings. |
| `python tools/socom.py recon dwarf` | recon | no | none | no | Print DWARF 1 entries by offset with their children. |
| `python tools/socom.py recon refs` | recon | no | none | no | Print a data object's relocated slots and every code access to it. |
| `python tools/socom.py recon live` | recon | no | required | no | Print live Ghidra names and signatures of functions or a group. |
| `python tools/socom.py recon types` | recon | no | required | no | Print every live Ghidra type matching each name, ignoring case. |
| `python tools/socom.py recon contradictions` | recon | no | optional | no | List group functions whose live signature contradicts the ELF facts, with each owning group's apply state. |
| `python tools/socom.py recon layout` | recon | yes | none | no | Write ELF-derived layout evidence of a class (and its bases and derived classes): every proven access per offset. |
| `python tools/socom.py recon type-plan validate` | recon | no | none | no | Check a code-derived type plan against regenerated layout evidence. |
| `python tools/socom.py recon type-plan show` | recon | no | none | no | Render a code-derived type plan as a review table with its validation. |
| `python tools/socom.py recon type-plan live` | recon | no | required | no | Check a valid code-derived type plan against the live program, read-only: no target or forward-declared name exists, and every referenced live type and instantiation source resolves exactly once with the recorded layout. |
| `python tools/socom.py recon type-plan program` | recon | yes | none | no | Translate a valid code-derived type plan into a type apply program. |
| `python tools/socom.py recon type-plan affected` | recon | no | none | no | List the reconstruction groups whose functions name a planned class, and which rows were left unresolved for it. |
| `python tools/socom.py ghidra apply-type-plan` | ghidra | yes | required | yes | Apply a reviewed code-derived type program under the item's writer lease and verify it (--dry-run: read-only checks). |
| `python tools/socom.py progress add-type-plan` | progress | yes | none | no | Add a file-only code-derived type plan item and its live apply item to the stage 3 gate. |
| `python tools/socom.py progress add-recon-repair` | progress | yes | none | no | Add a numbered stage 3 recon repair (file-only plan item and live apply item) for functions of applied, accepted groups whose live prototype is wrong. |
| `python tools/socom.py recon partial-candidates` | recon | no | optional | no | List unresolved rows of accepted plans whose live signature is Ghidra's default and whose parameters the facts prove, for a partial-prototype repair or re-plan. |
| `python tools/socom.py progress init` | progress | yes | none | no | Initialize unified reconstruction state. |
| `python tools/socom.py progress next` | progress | no | none | no | Select ready work from the canonical stage graph. |
| `python tools/socom.py progress show` | progress | no | none | no | Show the tracker or one exact entity. |
| `python tools/socom.py progress status` | progress | no | none | no | Show derived stage, lease, and next-work status. |
| `python tools/socom.py progress find` | progress | no | none | no | Search unified reconstruction entities. |
| `python tools/socom.py progress sql` | progress | no | none | no | Query the derived read-only SQLite cache of tracker, census and issues. |
| `python tools/socom.py progress audit` | progress | no | none | no | Audit tracker structure and strict derived invariants. |
| `python tools/socom.py progress snapshot` | progress | yes | none | no | Check or update the README progress snapshot. |
| `python tools/socom.py progress report` | progress | no | none | no | Render an on-demand progress report. |
| `python tools/socom.py progress migrate` | progress | yes | none | no | Migrate canonical tracker state to the current schema. |
| `python tools/socom.py progress add-repair` | progress | yes | none | no | Add a recorded Ghidra repair item once the applies it corrects are accepted. |
| `python tools/socom.py progress handoff-live-ghidra` | progress | yes | required | yes | Save and hand off a leased Ghidra item with a stable semantic receipt. |
| `python tools/socom.py progress advance-live-ghidra` | progress | yes | required | no | Accept a Ghidra handoff only when its live semantic receipt is unchanged. |
| `python tools/socom.py progress rebaseline-live-ghidra` | progress | yes | required | no | Record a fresh-import baseline receipt after a Ghidra version re-pin. |
| `python tools/socom.py progress decompose-stage` | progress | yes | none | no | Replace a stage seed with its registered producer's work items. |
| `python tools/socom.py progress stage-scope` | progress | no | none | no | Write the union of an accepted stage's writer receipt scopes. |
| `python tools/socom.py progress record-stage-baseline` | progress | yes | required | no | Record an accepted stage's live receipt over the union of its writer scopes. |
| `python tools/socom.py progress work claim` | progress | yes | none | no | Claim ready work with a bounded lease. |
| `python tools/socom.py progress work heartbeat` | progress | yes | none | no | Renew an owned work lease. |
| `python tools/socom.py progress work handoff` | progress | yes | none | no | Submit work and evidence for independent acceptance. |
| `python tools/socom.py progress work accept` | progress | yes | none | no | Independently accept handed-off work. |
| `python tools/socom.py progress work reject` | progress | yes | none | no | Independently return handed-off work for rework with findings. |
| `python tools/socom.py progress work reopen` | progress | yes | none | no | Return an accepted reconstruction plan whose apply has not started for re-planning, with the reason. |
| `python tools/socom.py progress work release` | progress | yes | none | no | Release an owned work lease. |
| `python tools/socom.py progress work leases` | progress | no | none | no | Show all active leases and exclusive resources. |
| `python tools/socom.py progress work packet` | progress | no | none | no | Render the exact contract for an actively leased item. |
| `python tools/socom.py progress work show` | progress | no | none | no | Show one or all structured work items. |
| `python tools/socom.py source owners` | source | no | none | no | Inventory provisional source owners. |
| `python tools/socom.py source artifacts` | source | no | none | no | Inventory source artifact annotations. |
| `python tools/socom.py source audit` | source | no | none | no | Audit soCOM workspace independence. |
| `python tools/socom.py verify asm` | verification | no | required | no | Read function and assembly evidence from Ghidra. |
| `python tools/socom.py verify functional` | verification | no | none | no | List or run one deterministic behavioral smoke target. |
| `python tools/socom.py verify functional-batch` | verification | no | none | no | Run a reviewed batch of behavioral smoke targets. |
| `python tools/socom.py verify linked-byte` | verification | no | none | no | Fail-closed linked-byte-match stage verification. |
| `python tools/socom.py verify final-elf` | verification | no | none | no | Fail-closed final-validation stage verification. |
