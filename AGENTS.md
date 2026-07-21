# AGENTS.md — Transon Authoring Skill (`transon-authoring`)

A standalone, distributable capability that lets **coding agents and CI** author correct,
engine-valid **Transon** JSON — grounded in the pinned engine metadata snapshot, backed by a
user-confirmed SampleSet, and blessed by the engine at `assurance: "matched"` before any template
is returned.

**The contract spans [`docs/SPEC.md`](docs/SPEC.md) (requirements, normative contracts,
governance, traceability), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (architecture, decision
records, package layout), and [`docs/ROADMAP.md`](docs/ROADMAP.md) (milestones, open questions,
risks, readiness).** Section numbers are global and unique across all three — read the cited section before changing
behavior. [`docs/traceability.md`](docs/traceability.md) tracks requirement → test coverage.
Milestones and their Definitions of Done live in ROADMAP §14; the per-requirement gate/test mapping
in SPEC §17.

## Golden rules

1. **SPEC-first (§12).** Behavior changes update the contract docs first, then code. If a required
   detail is missing or ambiguous, STOP and propose a spec change (use
   `harness/commands/propose-spec-change.md`) — never invent behavior inline.
2. **IDs are append-only (A0 lock).** FR/NFR/AC/UC/AD/OQ IDs are never renumbered; deprecate in
   place; new items take the next free number. Bound by `docs/id-ledger.json` +
   `harness/scripts/check_append_only_ids.py`.
3. **Authority precedence (AD-018 / NFR-001).** Transon semantics come only from: (1) the behavior
   of the **pinned running engine** (`transon==0.2.3`, local checkout at `../transon`); (2) the
   engine's packaged **Language Reference** via `get_language_reference()` / the `language`
   subcommand for the shipped skill surface (the engine repo `docs/SPECIFICATION.md` remains a
   maintainer-only design-time authority); (3) the pinned `get_editor_metadata()` snapshot; (4) the
   NL intent sidecar (hints only). **Never** model memory, web docs, or Context7 for Transon
   semantics. Context7 is allowed only for host-tooling APIs.
4. **Verify-before-return (AD-004 / G3).** Never report or return a template as success unless
   `verify` yields `ok: true` and `assurance: "matched"`. Failures use the §11.5 taxonomy.
5. **Samples before draft (AD-014 / AD-016).** No draft until `coverage_complete` **and**
   `confirmed` (independent flags). The library never sets `confirmed: true`.
6. **Deterministic gates (NFR-002).** Same SampleSet + template + pin ⇒ same `SampleCheck` /
   `Verdict`. Dry-run is sandboxed (AD-015/017): no real FS/network, in-memory write capture,
   includes from the SampleSet map only, base `Transformer`, marker `"$"`, 5s per-case timeout.
7. **Maker ≠ checker (§12).** Whoever implements a slice never reviews it — pre-merge review goes
   through the `spec-reviewer` role.
8. **Stay in scope (§3).** No MCP, no hosted/WASM engine, no new DSL or path syntax, no editor
   in-surface awareness, no editor sink, no custom transformer profiles in v1.
9. **Traceability in the same change (§12/§17).** FR/NFR/AC edits and implementation land with the
   matching `docs/traceability.md` update; tests cite their IDs
   (e.g. `def test_ac_018_deterministic_verdict():` or `# AC-018`).
10. **Name discipline.** `transon-authoring` here is the **product** (its `SKILL.md` + adapters
    under `adapters/` are deliverables, ARCHITECTURE §10). Harness procedures use distinct names
    (`run-milestone`, `implement-requirement`, `propose-spec-change`) — never name harness
    machinery after the product.
11. **No narrative comments or doc history (hygiene).** Comments explain non-obvious intent, never
    narrate what the code does or document the change being made. Contract docs carry current
    state only — no stacked revision parentheticals, no superseded-design diaries. Traceability
    cells list test references only. Session status goes to `docs/current-state.md`. When editing,
    delete existing comments/prose that violate this — do not preserve them out of conservatism.
    Full rule: [`harness/skills/hygiene.md`](harness/skills/hygiene.md).

## Stack

- Python ≥ 3.10, `src/` layout, hatchling build; package `transon_authoring`.
- Pinned engine dependency: `transon==0.2.3` (AD-007; PyPI — same version as `../transon`).
- Tests: pytest. Library is the contract; agents/CI invoke `python -m transon_authoring` (AD-006).
- License/packaging details are settled at release (NFR-008); record pin + snapshot hash then.

## Where things live

- Contract: `docs/SPEC.md` + `docs/ARCHITECTURE.md` + `docs/ROADMAP.md` · matrix:
  `docs/traceability.md` · ID ledger: `docs/id-ledger.json`.
- Working handoff (non-authoritative): `docs/current-state.md` — regenerate header with
  `python3 harness/scripts/update_memory.py --state`.
- Product code (ARCHITECTURE §10): `src/transon_authoring/`, `resources/`, `scripts/`, `evals/`,
  `adapters/`, `install/` — built across milestones A0–A5.
- AI-dev harness — **single-source, multi-tool**:
  - **Tool-neutral core** (canonical, edit here): `AGENTS.md`, `harness/` (agents, commands,
    scripts, githooks).
  - **Thin per-tool adapters** (point at the core, never copy it): `.claude/` and `.cursor/`.
  - Governance rules: [`harness/README.md`](harness/README.md) — read before changing the harness.
- Harness gates: `harness/scripts/check_traceability.py`,
  `harness/scripts/check_append_only_ids.py`. Product gates (`check_snapshot`, `check_parity`,
  `check_evals`, `check_install`, `sync_metadata`) are **A0–A4 deliverables** under `scripts/`
  and are separate from harness gates.
- Engine (separate repo): `../transon` — authoritative behavior + `docs/SPECIFICATION.md` +
  `get_editor_metadata()`. Editor (separate repo): `../transon-blockly`.

## Development loop (per requirement)

1. Read the requirement and its cited §11 contract text in `docs/SPEC.md`; confirm it belongs to
   the milestone in progress (ROADMAP §14 / SPEC §17).
2. Write the pytest test first, citing the ID in the test name or a comment.
3. Implement the minimal code in `src/transon_authoring/`.
4. Run pytest until green.
5. Update the matching `docs/traceability.md` row (status + test refs) in the same change.
6. Run the gates: `python3 harness/scripts/check_traceability.py` and
   `python3 harness/scripts/check_append_only_ids.py`. A red gate is a STOP: fix it, never weaken
   or bypass it.

**Working memory (end of session).** When a session changed code/docs, refresh the handoff so the
next session resumes cleanly: run `python3 harness/scripts/update_memory.py --state` to regenerate
the [`docs/current-state.md`](docs/current-state.md) header, then update its **Last action** /
**Next steps** narrative. Session status and closure notes go there — not into `SPEC.md` or
`traceability.md` cells. A stop hook nudges this for you.

Enable the binding hooks once per clone: `git config core.hooksPath harness/githooks`.
