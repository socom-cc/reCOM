# Readable-names repair verifier brief (token-lean)

You independently verify `socom:work:ghidra-repair-readable-function-names` (label n001) as
ACCEPTER. AGENTS.md is already in your context: do not re-read it. Never mutate Ghidra; never
save. Do not decompile or browse functions: the check below covers the whole program.

1. Run (several minutes; it takes a fresh fingerprint):

   python tools/socom.py ghidra check-names-repair --label n001 --prev <PREV>
     --fingerprint-output build/verifier-<ACCEPTER>/fp-now.json
     --output build/verifier-<ACCEPTER>/check.json

2. If `ok` is false, do not accept. Reply with the failed checks' detail lines only.

3. If `ok` is true, spot-check three renamed rows in the stored diff
   (build/fingerprints/n001-diff.json) by reading only those rows: before name mangled, after
   name its readable form, nothing else different. Then accept:

   python tools/socom.py progress advance-live-ghidra --item socom:work:ghidra-repair-readable-function-names
     --accepter <ACCEPTER> --expected-revision <current revision from `progress audit --strict`>
     --evidence "<each evidence line from check.json>" (one --evidence per line)

   On a revision conflict, re-read the revision and retry.

Report in at most 8 lines: ACCEPTED/REJECTED, revision, receipt, failed checks if any.
