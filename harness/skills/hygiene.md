# Hygiene — narrative discipline for code and docs

Comments and docs explain **non-obvious intent, trade-offs, or constraints**. They do not narrate
what the code does, document the history of changes, or double as a session diary.

This is the tool-neutral body. Thin adapters under `.cursor/rules/` and `.claude/rules/` point here.

## Prohibited

- **Changelog / edit narration** in code or docs: `changed X to Y`, `NEW:`, `previously…`,
  `updated to handle…`, `switched from…`, `this now…`, `added …`, `*(rev YYYY-MM-DD …)*`,
  `*(added …)*`.
- **Code narration:** comments whose entire content is deducible from the next 1–3 lines
  (`# return the result`, `# loop over items`, `# import the module`).
- **Authorship / session markers:** `TODO(agent)`, `AI-generated`, `refactored in sprint 4`.
- **History prose in contract docs** (`docs/SPEC.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, and the FR/NFR/AC bodies inside them):
  superseded designs, decision diaries, stacked revision markers. History lives in git.
- **Status essays in `docs/traceability.md`:** the Tests column lists test file/function
  references only — no "behavioral closure", gate-run narratives, or session reports.

## Required / allowed

- Cite requirement IDs where project conventions demand it (`# FR-054`, `// AC-018`).
- Explain *why* when the reason is not obvious: invariants, intentional deviations,
  performance trade-offs, regulatory constraints.
- Explain *what* only for genuinely opaque constructs (complex algorithms, encoding tricks).
- Session status, closure notes, and "what we did this session" → `docs/current-state.md`
  (**Last action** / **Next steps**), never into SPEC or traceability cells.

## When editing existing code or docs

- **Delete** any comment or prose that violates the above — do not preserve a bad comment just
  because it already exists. Removing narrative noise is always a net improvement.
- **Never add** a comment or SPEC parenthetical to explain the change you are making. That
  belongs in the commit message / PR, and optionally in `docs/current-state.md`.
- SPEC revisions **replace** normative text (see `harness/commands/propose-spec-change.md`).
  Deprecated IDs stay as one-line stubs; resolved OQs keep a one/two-line decision only.
