# Current state — working handoff

> **Non-authoritative working memory.** A session-to-session handoff, not part of the
> contract. Where this and the contract docs (`SPEC.md`, `traceability.md`, `AGENTS.md`)
> disagree, **they win**. Update the narrative below at the end of a work session;
> regenerate the header with `python3 harness/scripts/update_memory.py --state`.

<!-- BEGIN generated: at-a-glance · python3 harness/scripts/update_memory.py --state -->
| | |
|---|---|
| Repo HEAD | `b5469fa` — ci: run check_parity + check_install in the tests matrix; NFR-008 manifest citation |
| Branch | `a4-distribution` |
| Engine pin | `transon==0.1.7` (see [pyproject.toml](../pyproject.toml)) |
<!-- END generated: at-a-glance -->

## Last action

_**A4 distribution slice (branch `a4-distribution`, 2026-07-19).** OQ-010 resolved (no headless skill listing in Claude Code — verified against the current CLI; gate asserts install integrity + discoverability preconditions) and OQ-020 resolved (public PyPI `transon-authoring`). Landed: `adapters/` (single-source, no body copies), `install/claude.py`/`install/cursor.py` (idempotent, manifest-scoped uninstall, NFR-008 triplet in `.install-manifest.json`), `scripts/check_parity.py` (parity + NFR-012 self-sufficiency lint), `scripts/check_install.py` (temp-dir rehearsal + OQ-010 frontmatter lint + Cursor smoke), CI wiring on both matrix OSes. Full suite 647 passed; all gates green. **Note:** the NFR-012 lint forced two small rendered-text edits to `SKILL.md` — re-run the real-host eval baseline before the A5 release._

_**Prior behavioral closure (2026-07-15, from former traceability essays).** First green §11.8 real-host gate (run 29381271246) — authoring 0.977 (43/44) ≥ 0.80, adversarial 1.000, correction 1.000; baseline accepted (`f672bcf`)._


## Status by milestone

Authoritative milestone DoDs live in [`SPEC.md` §14](SPEC.md). This is the living read.

- See SPEC §14 for A0–A5 definitions of done.

## Next steps (ordered)

1. Merge PR #19 (`a4-distribution`; spec-reviewer verdict: merge — review nits 5–8 left open by decision).
2. A5: versioned release notes with pin, first PyPI publish (OQ-020), optional editor sink demo — after re-running the real-host eval baseline (SKILL.md rendered text changed in A4).

## Open blockers / waiting-on

- None.

## Do-not-relitigate (pointers, not copies)

- Product contract → [`SPEC.md`](SPEC.md).
- Coverage matrix → [`traceability.md`](traceability.md).
- Golden rules → [`AGENTS.md`](../AGENTS.md).
