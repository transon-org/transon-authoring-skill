# Current state — working handoff

> **Non-authoritative working memory.** A session-to-session handoff, not part of the
> contract. Where this and the contract docs (`SPEC.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `traceability.md`, `AGENTS.md`)
> disagree, **they win**. Update the narrative below at the end of a work session;
> regenerate the header with `python3 harness/scripts/update_memory.py --state`.

<!-- BEGIN generated: at-a-glance · python3 harness/scripts/update_memory.py --state -->
| | |
|---|---|
| Repo HEAD | `3da2ea5` — docs: record the 0.1.1 publish |
| Branch | `main` |
| Engine pin | `transon==0.2.3` (see [pyproject.toml](../pyproject.toml)) |
<!-- END generated: at-a-glance -->

## Last action

_**`transon-authoring 0.1.0` IS PUBLISHED ON PyPI** (2026-07-25, tag `v0.1.0`, run 30180068652) —
OQ-020's first production release. `pip install transon-authoring` works from a clean venv and pulls
`transon==0.2.3` transitively; the full CLI surface exits 0. TestPyPI carries `0.1.0` too (run
30179949576), plus a GitHub Release at `v0.1.0`. **A5's Definition of Done is MET** — all five
ladder steps green/recorded, the `CHANGELOG.md` record cites the triplet and every outcome, the
first PyPI publish is done, and AC-040/041/042 are green. `NFR-008` is `[x]`; **no unchecked rows
remain in `traceability.md`**. `docs/release-runbook.md` is the how-to for future releases._

_**NFR-008 now requires a license, and AC-042 enforces it (2026-07-26).** Governed change, SPEC
first: NFR-008 requires a non-empty repo-root `LICENSE` and a non-empty **`[project] license`** in
`pyproject.toml`; AC-042 gained the mechanical half. This closes the hole that let `0.1.0` ship
unusable while its own gate stayed green.
**`spec-reviewer` caught a false green that would have made the whole change pointless:** the first
implementation matched a `license` key in **any** table, so a `pyproject.toml` with no `[project]`
license but a `[tool.something] license = "MIT"` exited 0 with "terms are declared" — blessing the
exact defect the gate exists to catch. Reproduced end to end. Same root cause gave two false reds
(column-0 anchoring rejected valid indented keys, and an earlier `[tool.x] license = ""` masked the
real declaration). Fixed by isolating the `[project]` table body before searching it; verified
against seven probe cases and confirmed red-first by reverting the scoping.
Two further findings were contract-precision and went into SPEC, not code: AC-042 now names
`[project]` scope and the two accepted spellings (the `{text=…}`/`{file=…}` tolerance had been
invented inline and frozen by a test), and NFR-008/AC-042 no longer disagree on the file needing to
be non-empty. Also cut two sentences of legal advocacy from NFR-008 (hygiene: constraints, not
argument) and normalised a "licence"/"license" split. Deliberately NOT enforced: that a
`{file = …}` target exists — AC-042 asserts terms are *declared*, not which terms, and says so._

_**`0.1.1` PUBLISHED (2026-07-27, tag `v0.1.1` at `273dc14`, run 30270216901) — the license gap is
closed on the index.** Verified against the *installed* artifact, not the build:
`pip install transon-authoring==0.1.1` resolves `transon==0.2.3` transitively, the §11.6 surface
exits 0, and the distribution carries `Metadata-Version: 2.4`, `License-Expression: MIT` and
`dist-info/licenses/LICENSE`. First release through the `pypi` deployment-approval gate, which
paused the run until approved — and that gate had already earned itself the day before by catching a
`v0.1.1` tagged one commit short. **PR [#29](https://github.com/transon-org/transon-authoring-skill/pull/29)
merged (`273dc14`)**: `main` was reset to `d98d440` so the 19 previously-direct-to-main commits got a
real diff, CodeRabbit's four findings were fixed, and the tag was moved onto the reviewed merge
commit. The `hatchling>=1.27` pin came out of that review and matters — 1.26.3 builds
`license = "MIT"` but emits the deprecated `License:` field and drops `License-File:`, so unpinned
the same source yields different license metadata per build host._

_**LICENSE GAP FOUND AND FIXED — `0.1.1` prepared (2026-07-26).** Auditing the repo for FR-037b
catalog readiness surfaced that **`0.1.0` shipped with no license at all**: no `LICENSE`, no
`license` field, no classifiers, `license: None` on PyPI. That makes it "all rights reserved" — not
legally usable by anyone who installed it. `AGENTS.md:61` had flagged that license details settle at
release and the obligation was simply missed; it did not break A5's DoD because NFR-008's normative
text (which I wrote) requires only version/pin/hash + ladder outcomes and never carried the license
in. **Now MIT**, declared three ways — repo-root `LICENSE`, `license`/`license-files` in
`pyproject.toml` (wheel verified carrying `License-Expression: MIT` and bundling the file), and PyPI
classifiers. Copyright line reads `Eugene Chernyshov`; swap to an entity if preferred.
Also fixed, all catalog-facing: `README.md` still said **"Status: Pre-A0"** for a shipped product and
was contract-facing rather than user-facing (rewritten around install + how-it-works); the repo had
**no description, homepage or topics** (set, 8 topics). `0.1.1` is committed with its CHANGELOG entry
and AC-042 green — **it needs a `v0.1.1` tag to publish**, which will pause for deployment approval.
FR-037b submissions deliberately deferred (its own framing is "driven by real adoption")._

_**Ladder 4 closed by interactive human attestation (2026-07-26).** In both real interactive Claude
Code and real interactive Cursor, from an un-nudged prompt in a workspace holding only the two
installer-provisioned skill files plus a SampleSet: the skill activated, verified to
`assurance: "matched"` on the first candidate, and **stopped at the FR-030 review loop** offering
approve/revise/stop rather than auto-emitting. On `approve` both returned the final envelope
**byte-identical to `python -m transon_authoring result`'s own stdout** — proof the approve exit
re-ran `result` instead of re-typing from memory, the failure that path historically had. Nothing
else exercises that gate: ladder 2 synthesises the approval, and headless runs emit directly.
Stated limit: outside any checkout, but on a machine that has the repo._

_**A5 release slice — MERGED to `main` 2026-07-25 (PR [#28](https://github.com/transon-org/transon-authoring-skill/pull/28), merge `d98d440`); all gates green on `main`.**
The agent-implementable half of A5 is complete; everything left is maintainer-only (Next steps).
The `marketplace.json` owner stays `transon-org` (org abstraction, no personal data published).
Delivered:_
- _**FR-037a/AC-040** — the §11.9 Claude Code plugin tree (`.claude-plugin/plugin.json` +
  `marketplace.json`), then restructured so **the plugin-native `skills/transon-authoring/SKILL.md`
  is THE canonical body** — one `SKILL.md` in the repo, single source by absence of a second copy
  (no generated duplicate, no identity gate); AC-005 reds on any other `SKILL.md`. The body moved
  byte-for-byte (blob `710e69a4`), a pure path change with no §11.8 implication._
- _**FR-038/AC-041** — Cursor personal scope; the project-only exclusion was a product choice, so
  all four superseded artifacts were swept and `check_install` exercises `cursor/personal`._
- _**NFR-008/AC-042** — repo-root `CHANGELOG.md` as the release record; `check_install` verifies its
  version triplet against `pyproject.toml` + `resources/metadata-snapshot.md`. Row is `[x]` since
  the release checklist completed._
- _**Ladder 1** dist smoke (pre-existing) and **ladder 2** installer-provisioned eval workspace —
  ladder 2 validated by a targeted `--only` probe (run 29961198852, majority `pass`, zero
  `infra_error`, $0.49). **Ladder 3** = `cursor-activation-smoke.yml`, dispatch-only, non-gating._
- _Project version `0.0.1` → `0.1.0` (AC-040 forces `plugin.json`; `release.yml` forces the tag)._

_**Decisions worth not relitigating:** the ≈$19 full eval rerun was dropped (`60be2fa`) — the A5
entry condition was already met by the green gate of 2026-07-20 (run 29782513843) and no §11.8 reset
trigger has fired; the `CHANGELOG` discloses that the baseline predates a few additive body edits.
**`transon-authoring 0.0.1` is already on TestPyPI** (run 29915374804) — AC-042 checks only the
triplet, so every ladder/publication line in the `CHANGELOG` is unverified prose to check against
`gh run list` before release. **Ladder 3 carries an unresolved credential-exposure risk** the
platform blocks closing (Cursor ships no pinnable artifact and no key-proxy): it runs an unverified
`curl|bash` binary with `CURSOR_API_KEY` present. Bounded by an `accept_unverified_cli_risk=yes`
dispatch gate, a mandatory throwaway key, and egress blocked to a derived allowlist — which cannot
eliminate the path, since Cursor's own API must stay reachable. **Three
`spec-reviewer` passes** (two-copy design; the restructure — whose lead finding was a guard landed
code-first, since fixed spec-first via AC-005; the CodeRabbit-fix commit) and **four CodeRabbit
rounds** are all settled._

_**OQ-028 and OQ-029 resolved (branch `spec-oq028-oq029-resolution`) — no open OQs remain.**
**OQ-029:** one §11.6 grounding recipe in every channel; acquisition is documented, never encoded in the recipe. Decided on measurement, not assumption — a `uv run --with` prototype against a locally built wheel worked (0.11s warm, exit codes preserved, engine 0.2.3 resolved transitively, no console script needed) but was rejected on two counts: its command form differs from the native recipe, which is the forked recipe OQ-029 itself forbade, and its offline behavior depends on a prunable shared cache (cold cache + no network = exit 2), weakening NFR-003. No `SessionStart` hook, since packaging never runs `pip` (OQ-020). FR-037a requires the plugin manifest `description` to contain the literal `pip install transon-authoring` (gated by AC-040), and the shipped `SKILL.md` now carries a channel-independent recovery line for `No module named transon_authoring` — without it a catalog user hit an unrecoverable error, since the manifest description is rendered at browse time and the agent never sees it. **This edits the shipped body the eval baseline was measured against.** No baseline reset is triggered (§11.8 resets are for pin/corpus/gate-model/harness changes), and the A5 pre-release rerun already covers it, but the current baseline now reflects slightly older text.
**OQ-028:** Cursor gains a personal scope, so the adapters reach equal capability rather than a documented exclusion (NFR-007). New **FR-038 / AC-041** (A5, `[ ]`); §11.9 install table gains the Cursor personal destination. Evidence for the premise: Cursor's own Agent Skills docs (`cursor.com/docs/skills`, read 2026-07-21) list `~/.cursor/skills/` and `~/.agents/skills/` as user-level discovery locations — FR-038 adopts only `~/.cursor/skills/`. AC-041 is **structural only** and makes no host-discovery claim (OQ-008), so that premise stays unverified by any gate; A5 ladder step 3 exercises project scope only.
`check_parity` stayed green through the SPEC-only gap — verified in `scripts/check_parity.py`, it compares the two adapter manifests to each other, never to the contract. (The four-artifact gap this entry described was closed by FR-038 on `a5-release`.)_

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

**A5 is complete.** The A5 section of this list is closed; what remains is post-release and
non-gating.

1. **Publish `0.1.1`** — prepared and committed (now also carries the NFR-008/AC-042 license
   requirement); needs the tag:
   `git tag v0.1.1 && git push origin v0.1.1`. The run now **pauses at `Review pending`** (the
   `pypi` environment gained required reviewers), so approve the deployment in the run's page. Then
   fill the Publication slot in the `CHANGELOG.md` `0.1.1` entry.
2. **FR-037b — external catalog submission** (non-gating) — **started** 2026-07-29.
   [Chat2AnyLLM/awesome-repo-configs#129](https://github.com/Chat2AnyLLM/awesome-repo-configs/pull/129)
   open (9-line additive entry in `plugin_repos.json`; their three required checks pass). Anthropic's
   official directory is a **web form** (`clau.de/plugin-directory-submission`) — maintainer action.
   **ComposioHQ deliberately skipped**: it asks contributors to vendor the plugin into the catalog
   repo, which would create a second `SKILL.md` outside this repo's gates — exactly what AC-005
   forbids. Prefer reference-based catalogs; they point at the self-hosted marketplace and leave the
   canonical body as the single copy.
3. Small leftovers deliberately not done: `check_plugin` inspects only the first matching
   marketplace entry (a duplicate later entry with a bad `source` is unexamined); two hygiene
   stragglers in `host_harness.py` (the `run_fixture` comment narrates work the installer now does;
   `skill_md` is vestigial for the real host — supplied, ignored at the call site).
4. ~~Protect the `pypi` environment~~ — **done** 2026-07-26: required reviewer `Evgenus`, plus a
   deployment branch policy restricting it to **`v*` tags**, so its Trusted Publishing identity is
   unreachable from a branch. `testpypi` left unprotected on purpose (rehearsal channel).
5. Watch items carried forward: three fixtures passed the accepted baseline 2/3
   (`ec2-flatten-inventory`, `refuse-recursive-flatten`, `seed-refuse-nonexistent-mode`) and are
   future-flake candidates the ratchet will surface via `failure_modes`; the eval baseline predates
   a few additive `SKILL.md` edits (disclosed in `CHANGELOG.md`, no §11.8 reset trigger fired).

## Open blockers / waiting-on

- **None blocking.** A5's DoD is met and `0.1.0` is published; remaining work is post-release and
  non-gating (Next steps).
- Note for the next release: the `pypi` environment now requires **deployment approval**, so a tag
  push pauses at `Review pending` until approved in the run's page. Self-review is deliberately
  allowed — a sole reviewer who also pushes tags would otherwise deadlock releases.

## Do-not-relitigate (pointers, not copies)

- Product contract → [`SPEC.md`](SPEC.md) + [`ARCHITECTURE.md`](ARCHITECTURE.md) + [`ROADMAP.md`](ROADMAP.md).
- Coverage matrix → [`traceability.md`](traceability.md).
- Golden rules → [`AGENTS.md`](../AGENTS.md).
