# Current state — working handoff

> **Non-authoritative working memory.** A session-to-session handoff, not part of the
> contract. Where this and the contract docs (`SPEC.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `traceability.md`, `AGENTS.md`)
> disagree, **they win**. Update the narrative below at the end of a work session;
> regenerate the header with `python3 harness/scripts/update_memory.py --state`.

<!-- BEGIN generated: at-a-glance · python3 harness/scripts/update_memory.py --state -->
| | |
|---|---|
| Repo HEAD | `d8a1659` — Merge pull request #25 from transon-org/docs-split-spec-architecture-roadmap |
| Branch | `spec-oq028-oq029-resolution` |
| Engine pin | `transon==0.2.3` (see [pyproject.toml](../pyproject.toml)) |
<!-- END generated: at-a-glance -->

## Last action

_**OQ-028 and OQ-029 resolved (branch `spec-oq028-oq029-resolution`) — no open OQs remain.**
**OQ-029:** one §11.6 grounding recipe in every channel; acquisition is documented, never encoded in the recipe. Decided on measurement, not assumption — a `uv run --with` prototype against a locally built wheel worked (0.11s warm, exit codes preserved, engine 0.2.3 resolved transitively, no console script needed) but was rejected on two counts: its command form differs from the native recipe, which is the forked recipe OQ-029 itself forbade, and its offline behavior depends on a prunable shared cache (cold cache + no network = exit 2), weakening NFR-003. No `SessionStart` hook, since packaging never runs `pip` (OQ-020). FR-037a now requires the plugin manifest `description` to state the `pip install transon-authoring` prerequisite, gated by AC-040.
**OQ-028:** Cursor gains a personal scope, so the adapters reach equal capability rather than a documented exclusion (NFR-007). New **FR-038 / AC-041** (A5, `[ ]`); §11.9 install table gains the Cursor personal destination. Evidence for the premise: Cursor's own Agent Skills docs (`cursor.com/docs/skills`, read 2026-07-21) list `~/.cursor/skills/` and `~/.agents/skills/` as user-level discovery locations — FR-038 adopts only `~/.cursor/skills/`. AC-041 is **structural only** and makes no host-discovery claim (OQ-008), so that premise stays unverified by any gate; A5 ladder step 3 exercises project scope only.
Deliberately SPEC-only, and the gap is **four artifacts**, not one: `adapters/cursor/adapter.json` (the exclusion), the shipped `adapters/cursor/README.md` ("project scope only — Cursor has no personal skill scope in v1"), `install/cursor.py` (docstring + scope-rejection path), and three tests that pin the superseded rule (`test_adapters.py`, `test_install.py::test_fr015_cursor_personal_scope_exit2`, the `test_check_parity.py` exclusion fixture). FR-038 names all of them so the implementer sweeps them together. `check_parity` stays green through the gap — verified in `scripts/check_parity.py`, it compares the two adapter manifests to each other, never to the contract._

_**Contract split into SPEC + ARCHITECTURE + ROADMAP (branch `docs-split-spec-architecture-roadmap`).** Matches the `transon-blockly` convention. `docs/SPEC.md` keeps §0–4, §7–9, §11–13, §17; `docs/ARCHITECTURE.md` takes §5, §6, §10 (all 26 `AD-*`); `docs/ROADMAP.md` takes §14–16, §18 (all `OQ-*`). **Section numbers are preserved and globally unique across the three docs**, so the ~100 files citing bare `§N` stay correct — only file+section pointers were rewritten. The move itself was verbatim (scripted split with a line-conservation assert). Follow-up commits then corrected the contract text the move made false: §0's now-completed "extract ARCHITECTURE.md" instruction, SPEC's preamble still calling itself the whole contract, §12 now naming the three-document contract, and ARCHITECTURE §10's package layout — which gained the two new docs, `id-ledger.json`, and the AD-026 `resources/language-reference.json` it had been missing since the repin. `CONTRACT_DOCS` widened in both harness gates — without it the ID lock goes red on 55 migrated AD/OQ IDs, which it correctly did before the fix. Gate messages genericized off `docs/SPEC.md`. Pointers updated in AGENTS.md, CLAUDE.md, README.md, harness/ (README, commands, agents, hygiene), and the `update_memory.py` generator. All six gates green._

_**Plugin + catalog distribution added to A5 (branch `spec-plugin-catalog-distribution`).** FR-037 splits the way FR-018 does: **(a) packaging — gating, A5** (`plugin.json` + self-hosted `marketplace.json`, §11.9 plugin layout) verified by `check_install` under new **AC-040**; **(b) external catalog submission — ongoing, non-gating**, begun only after the PyPI publish since a listed skill with an unpublished runtime is inert. AD-009 revised in place to name the plugin channel; the orphaned **OQ-007** ("plain skill then plugin") is now normative in AD-009/FR-037. New **OQ-029** (open) picks the plugin runtime-acquisition path — documented prereq vs `SessionStart` hook vs `uv run --with` — constrained to preserve NFR-003/OQ-020 and to not fork the §11.6 recipe. A5 gains ladder step 5; no A6. IDs registered: FR-037, AC-040, OQ-029. Marketplace hosts fetch the tree at `source`, so the plugin `SKILL.md` is a **committed generated artifact** held byte-identical to canonical by AC-040 — single source by enforced identity, not by absence; the repo is both plugin root and marketplace repo, and that tree sits outside the FR-015/016 install-manifest regime. Note `transon-authoring` is **not yet on PyPI** (404; engine `transon==0.2.3` is published) — that publish gates all outreach._

_**Editor sink removed from v1 scope (branch `spec-editor-sink-out-of-scope`).** UC-002 revised in place to "Cursor same path" — the ID is kept and the Cursor authoring path stays core; only the blockly-import handoff is dropped. G5 reduced to "Decoupled from the editor"; §3 gains "Not an editor JSON sink or blockly import handoff in v1"; `transon-blockly` dropped from the §4 Consumers table; A5 renamed "Release" with the optional UC-002 demo removed from its DoD and from the §18 readiness row; AGENTS.md rule 8 + README milestone line follow. No IDs issued or retired (ledger byte-unchanged); no FR/NFR/AC touched, so `traceability.md` is unaffected. Both harness gates green._

_**RFC-003 baseline gate GREEN + accepted (2026-07-20, run 29782513843; PR #23).** Full real-host gate over the 0.2.3 corpus (54 fixtures ×3): authoring 1.000, adversarial 1.000, correction 1.000, red=[], $18.63, 0 infra_error. `evals/baseline.json` repopulated with the 54 majority-passers (`test_fr_017_baseline_reflects_the_accepted_green_gate`). ec2-flatten-inventory now passes (failed the A3 gate); marginal 2/3 = ec2-flatten-inventory / refuse-recursive-flatten / seed-refuse-nonexistent-mode (future-flake watch). This satisfies the A5 entry condition (baseline reflects the shipped 0.2.3 SKILL.md)._

_**RFC-003 merged to main (PR #22, 2026-07-20).** Repin engine `0.1.7`→`0.2.3` + ground the shipped skill in the packaged Language Reference (`get_language_reference()`) instead of the engine-repo `docs/SPECIFICATION.md`. FR-036 (language subcommand + snapshot/drift, engine-free read via `resources/language-reference.json`), AC-039, AD-026; AD-018 authority swap; NFR-012/AC-032 drop the SPECIFICATION.md exemption; §11.8 pin+corpus baseline-reset. Corpus: snapshot 121→163 examples; 3 now-satisfiable refuses converted to constructed matched fixtures (`order-uppercase-currency`, `stripe-epoch-to-iso`, `github-branch-from-ref`); split-family synthetic `syn-split-string`; 3 genuine-gap refuses (`refuse-sha256-checksum`/`refuse-random-winner`/`refuse-recursive-flatten`). Adversarial bucket = 5. Full suite 664 passed; all gates green._

_**Prior behavioral closure (2026-07-15, from former traceability essays).** First green §11.8 real-host gate (run 29381271246) — authoring 0.977 (43/44) ≥ 0.80, adversarial 1.000, correction 1.000; baseline accepted (`f672bcf`)._


## Status by milestone

Authoritative milestone DoDs live in [`ROADMAP.md` §14](ROADMAP.md). This is the living read.

- See ROADMAP §14 for A0–A5 definitions of done.

## Next steps (ordered)

1. Merge the OQ-028/OQ-029 resolution (this branch). With no open OQs, `/run-milestone A5` is unblocked for the implementable slice: ladder 1 (dist smoke CI job), ladder 2 (distribution-faithful eval provisioning), FR-037a/AC-040 plugin packaging, FR-038/AC-041 Cursor personal scope.
2. A5 release: versioned release notes with the 0.2.3 pin + snapshot hash, first PyPI publish (OQ-020), the distribution-verification ladder (§14). The A5 entry condition (eval baseline reflecting the shipped SKILL.md) is met.

## Open blockers / waiting-on

- None. (Watch item: 3 fixtures passed the baseline gate 2/3 — future-flake candidates the ratchet will surface via `failure_modes`.)

## Do-not-relitigate (pointers, not copies)

- Product contract → [`SPEC.md`](SPEC.md) + [`ARCHITECTURE.md`](ARCHITECTURE.md) + [`ROADMAP.md`](ROADMAP.md).
- Coverage matrix → [`traceability.md`](traceability.md).
- Golden rules → [`AGENTS.md`](../AGENTS.md).
