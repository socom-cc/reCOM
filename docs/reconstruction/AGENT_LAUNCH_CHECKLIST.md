# Agent launch checklist

Use this checklist before assigning or beginning a reconstruction packet.

## Parent/controller

1. Run `python tools/socom.py doctor --infrastructure-only --ghidra`.
2. Run `python tools/socom.py progress audit --strict`.
3. Inspect `progress next`, dependencies, blockers, and evidence.
4. Select one narrow role and its matching skill from `AGENTS.md`.
5. Claim the work, then render `progress work packet --item <id> --owner
   <owner>`. An apply packet must be the sole claimant of `ghidra-writer`.
6. Give the worker the rendered role, skill, paths, addresses/DIE ranges,
   program/scope, evidence, deliverables, and prohibitions unchanged.

## Worker

- For an apply packet, re-run Ghidra preflight and pass `program=socom.elf` on
  every program call. A plan packet must not call or mutate Ghidra.
- Read before writing and remain inside the claimed resources.
- Preserve contradictions rather than choosing attractive source or
  decompilation.
- Heartbeat long work and run the narrow verifier/guards.
- For a Ghidra writer item, finish only through
  `progress handoff-live-ghidra`; generic handoff is rejected.

## Accepter

- Be independent of the handoff owner.
- Reproduce evidence and inspect semantic propagation.
- Use `progress advance-live-ghidra`; it rechecks the stored receipt scope and
  never saves.
- Accept only the claimed scope. Return incomplete or contradictory work
  without weakening criteria.

Roles do not launch nested agents. The controller retains scheduling, resource,
issue-routing, integration, and acceptance authority.
