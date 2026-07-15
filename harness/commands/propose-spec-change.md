# Propose a spec change

Change `docs/SPEC.md` under the §12 governance and the A0 ID lock. Behavior changes update the
SPEC **first**, then code.

## Procedure

1. State the problem: what is ambiguous, missing, or wrong, and which existing IDs/sections it
   touches. If the change alters product behavior, no code lands until this change is merged.
2. Draft the edit:
   - **New requirement/decision** → next free number in its family (check `docs/id-ledger.json`
     for the current maximum). Never renumber, never reuse a retired number.
   - **Changed requirement** → **replace** the normative text in place, keeping the ID. Do **not**
     stack dated parentheticals (`*(rev YYYY-MM-DD …)*`, `*(added …)*`) or keep superseded wording
     alongside the new text. History lives in git; the SPEC carries the current state only.
   - **Removed behavior** → mark the ID deprecated in place as a **one-line stub** that keeps the
     ID and states it is deprecated (optionally naming the replacement). Never delete the entry;
     never retain the old normative body under the stub.
3. Keep the SPEC self-consistent in the same edit: §7–§9 text, §11 contracts, §13 gates, §14
   milestone DoDs, §17 traceability rows, §18 readiness — whichever the change touches.
4. Update `docs/traceability.md` for any new or changed FR/NFR/AC (new rows start unchecked;
   AC edits update the AC(s) column of the rows that cite them). Traceability **Tests** cells list
   test file/function references only — no session-closure or status essays.
5. Register new IDs: `python3 harness/scripts/check_append_only_ids.py --update` — the ledger diff
   is the reviewable record that an ID was issued.
6. Run both harness gates green; commit the SPEC + traceability + ledger together, before (or
   with) any implementation.
7. Session context for *why* the change was made goes in `docs/current-state.md` (**Last action**),
   not into the SPEC body.

## Hard rules

- Never renumber or delete an ID (append-only gate enforces this).
- Never change normative §11 contracts and code in a way that lands the code first.
- Resolving an OQ: mark it **Resolved (date): \<decision\>** in §15 in one or two lines, reflect
  the decision in the relevant AD/FR text in the same edit, and **delete** any superseded design
  narrative under that OQ. Do not keep "the runner was…" diaries in the SPEC.
- Never add changelog-style history to FR/NFR/AC/AD bodies, milestone DoDs, or traceability cells.
