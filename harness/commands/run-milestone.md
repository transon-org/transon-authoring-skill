# Run a SPEC milestone

Implement the milestone I name (`A0`–`A5`) from SPEC §14, end to end, in a single focused pass.

## Authority & guardrails

- The contract is `docs/SPEC.md`. Work only the **FR/NFR/AC IDs citing this milestone** in §17
  and the milestone's Definition of Done in §14; do not pull in scope from other milestones.
- Follow `AGENTS.md`: authority precedence (AD-018/NFR-001), verify-before-return (AD-004),
  samples before draft (AD-014), deterministic sandboxed gates (NFR-002, AD-015/017), append-only
  IDs, stay in scope (§3).
- **If a required detail is missing or ambiguous in the SPEC, STOP and propose a spec change
  first** (`harness/commands/propose-spec-change.md`; next free ID; never renumber; never invent
  behavior inline).
- Readiness: A0–A2 are declared ready in SPEC §18. A3 requires A2 green; A4 requires A3 (+ OQ-010
  for the Claude listing depth); A5 requires A4. If the named milestone's prerequisite is not
  green, STOP and say so.

## Procedure

1. Read the named milestone in SPEC §14, its DoD, and every requirement/AC it cites via §17.
2. Create a branch `aX-short-name` and a todo list — one item per FR/AC in the slice. Delegate
   design to `milestone-planner` when the slice has open design decisions.
3. For each requirement (delegate to `requirement-implementer`): write the pytest test **first**,
   citing the ID in the name/comment, then implement the minimal code per the SPEC §10 layout.
4. Run pytest until green.
5. Keep the harness gates green: `python3 harness/scripts/check_traceability.py` and
   `python3 harness/scripts/check_append_only_ids.py`. From A0 onward also keep the product gates
   the milestone has delivered green (`scripts/check_snapshot.py` at A0+, `scripts/check_evals.py`
   at A2+, …).
6. Update `docs/traceability.md` (status + test refs per ID) **in the same change**.
7. Satisfy the milestone's **Definition of Done** in SPEC §14 before finishing.
8. Request a `spec-reviewer` pass on the branch before merge (maker ≠ checker, §12).

## Notes

- **A0 pins the world:** `transon==0.1.7`, snapshot + provenance from the pinned engine
  (`../transon` locally, PyPI in CI), NL-intents sidecar skeleton, drift gate. Later milestones
  build on it.
- For design-heavy slices (A1 worker-subprocess timeout/IPC, A2 `check_samples`), lock the
  approach with `milestone-planner` before writing code.
- One branch / PR per milestone; reference the covered requirement IDs in the PR body and commit
  trailers (`Refs:` / `Slice:` — enforced by the commit-msg hook).
