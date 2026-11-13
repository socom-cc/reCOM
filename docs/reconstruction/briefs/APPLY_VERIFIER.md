# Stage 3 apply verifier brief (token-lean)

You independently verify ONE live Ghidra apply. Your prompt gives ITEM (the -apply id), LABEL,
PREV and ACCEPTER. AGENTS.md is already in your context: do not re-read any docs.

1. Run (takes ~4 minutes; it takes its own full fingerprint, read-only):
   `python tools/socom.py ghidra check-recon-apply --item <ITEM> --label <LABEL> --prev <PREV> --fingerprint-output build/verifier-<ACCEPTER>/fp-now.json --output build/verifier-<ACCEPTER>/check.json`
   It checks: item statuses, plan sha256 cited by the accepted plan item, program regenerates
   from the plan, stored scope, live preflight, receipt reproduces the handoff receipt, your
   fingerprint equals <LABEL>-after, <LABEL>-before equals <PREV>-after, the stored diff
   recomputes, every diff row is explained (prototyped/restated/thunk/typed global/pointer
   type), live signatures equal the plan, apply calls equal the dry run within scope, and the
   strict tracker audit.
2. Read the JSON result. If "ok" is true and every check's detail is consistent (glance at the
   "explain" and "calls" details), accept:
   `python tools/socom.py progress advance-live-ghidra --item <ITEM> --accepter <ACCEPTER> --evidence "<line 1>" --evidence "<line 2>" ... --expected-revision <rev>`
   using the result's "evidence" lines verbatim; read the revision with
   `python tools/socom.py progress audit --strict` right before; retry on conflict.
3. If any check failed, do not accept and do not retry anything that writes: report the failed
   checks.

Never call Ghidra write endpoints or save. Write only under build/verifier-<ACCEPTER>/.

Final report: at most 4 lines - decision, receipt, failed checks if any.

When the bridge is not on 8089, every command that touches Ghidra needs SOCOM_GHIDRA_URL, including the final progress advance-live-ghidra (it runs a live preflight).
