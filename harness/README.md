# harness/ — the tool-neutral harness core

`harness/` holds the **entire tool-agnostic implementation harness** in one place. `.claude/` and
`.cursor/` are thin adapters at the repo root (each tool mandates its own root dir); `.github/` is
the CI (GitHub mandates the root).

- `agents/` — subagent role bodies (`milestone-planner` · `requirement-implementer` ·
  `spec-reviewer`)
- `commands/` — command procedures (`run-milestone` · `implement-requirement` ·
  `propose-spec-change`)
- `skills/` — tool-neutral skill / always-on rule bodies (`hygiene`)
- `scripts/` — deterministic harness gates (`check_traceability` · `check_append_only_ids`)
  and harness utilities (`update_memory`)
- `githooks/` — binding git hooks (`pre-commit` · `commit-msg`); enable with
  `git config core.hooksPath harness/githooks`

**Harness vs product.** The product itself is a skill (`SKILL.md` + `adapters/` + the
`transon_authoring` library — ARCHITECTURE §10), and it ships its own gates under `scripts/`
(`check_snapshot`, `check_parity`, `check_evals`, `check_install`). Those are **deliverables**,
governed by the SPEC. Everything in `harness/` is meta — it exists so agents implement the SPEC
without drifting from it, and it must never be confused with, or named after, the product skill.

## Harness governance (the rules for changing the harness)

These harden the harness, not the product — harness changes need *no SPEC change*; product
behavior still goes SPEC-first (SPEC §12). Ported from the `transon-blockly` harness:

1. **Single source.** A command / agent-role *body* lives once, here in `harness/`. `.claude/` and
   `.cursor/` carry only tool-specific frontmatter + "read the `harness/` body and follow it" —
   they reference the core, **never each other**. Don't copy a body into a tool; copying
   re-creates the drift the harness exists to prevent.
2. **Both tools, equally.** Any new command / agent / hook lands in `harness/` **and both**
   `.claude/` and `.cursor/` adapters — or carries an explicit, documented exclusion (record it
   here). Claude Code and Cursor are first-class peers.
3. **Gated, not hoped.** `check_traceability.py` and `check_append_only_ids.py` bind in the
   pre-commit hook and CI. A red gate is a STOP: fix it, never weaken or bypass it.
4. **Docs split by role.** `AGENTS.md` + `harness/` + the adapters *operate*; `docs/SPEC.md` +
   `docs/traceability.md` + `docs/id-ledger.json` *contract*; `docs/current-state.md` is
   **non-authoritative working memory** (session handoff — regenerate its header with
   `python3 harness/scripts/update_memory.py --state`). Adapters reference the operating
   contract, never restate it.
