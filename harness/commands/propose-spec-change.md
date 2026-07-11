# Propose a spec change

Change `docs/SPEC.md` under the §12 governance and the A0 ID lock. Behavior changes update the
SPEC **first**, then code.

## Procedure

1. State the problem: what is ambiguous, missing, or wrong, and which existing IDs/sections it
   touches. If the change alters product behavior, no code lands until this change is merged.
2. Draft the edit:
   - **New requirement/decision** → next free number in its family (check `docs/id-ledger.json`
     for the current maximum). Never renumber, never reuse a retired number.
   - **Changed requirement** → edit in place, keeping the ID; note the revision inline if the
     change is substantive (the SPEC does this with "rev YYYY-MM-DD" markers).
   - **Removed behavior** → mark the ID deprecated in place (see FR-013 for the pattern); never
     delete the entry.
3. Keep the SPEC self-consistent in the same edit: §7–§9 text, §11 contracts, §13 gates, §14
   milestone DoDs, §17 traceability rows, §18 readiness — whichever the change touches.
4. Update `docs/traceability.md` for any new or changed FR/NFR/AC (new rows start unchecked;
   AC edits update the AC(s) column of the rows that cite them).
5. Register new IDs: `python3 harness/scripts/check_append_only_ids.py --update` — the ledger diff
   is the reviewable record that an ID was issued.
6. Run both harness gates green; commit the SPEC + traceability + ledger together, before (or
   with) any implementation.

## Hard rules

- Never renumber or delete an ID (append-only gate enforces this).
- Never change normative §11 contracts and code in a way that lands the code first.
- Resolving an OQ: mark it **Resolved (date)** in §15 with the decision, and reflect the decision
  in the relevant AD/FR text — same edit.
