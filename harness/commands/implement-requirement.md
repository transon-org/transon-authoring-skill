# Implement a single requirement

Implement exactly one requirement — the FR/NFR/AC ID given as the argument, defined in
`docs/SPEC.md` — test-first, without scope creep.

## Procedure

1. Read the requirement and every §11 contract section it cites; read its row in SPEC §17 for the
   expected milestone and gate/test category. If the requirement belongs to a milestone whose
   prerequisites are not green (SPEC §18), STOP and say so.
2. Write the **pytest test first**, citing the ID in the test name or a comment
   (e.g. `def test_ac_021_cli_exit_codes():`). Derive engine-behavior expectations by running the
   pinned engine (`transon==0.1.7`) — never from memory (AD-018/NFR-001).
3. Implement the minimal code per the SPEC §10 layout.
4. Run pytest until green; do not weaken existing tests or gates.
5. Update the requirement's row in `docs/traceability.md` (status + test refs) in the same change.
6. Run `python3 harness/scripts/check_traceability.py` and
   `python3 harness/scripts/check_append_only_ids.py`; all green.
7. Commit with a `Refs: <ID>` trailer. Note that a `spec-reviewer` pass is required before merge.

## Hard rules

- One requirement per run.
- Ambiguity or missing behavior in the SPEC → STOP and escalate via
  `harness/commands/propose-spec-change.md`. Never invent behavior inline.
- Sandbox and profile invariants (AD-015/017) are non-negotiable in any code you touch.
