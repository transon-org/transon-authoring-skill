# Current state — working handoff

> **Non-authoritative working memory.** A session-to-session handoff, not part of the
> contract. Where this and the contract docs (`SPEC.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `traceability.md`, `AGENTS.md`)
> disagree, **they win**. Update the narrative below at the end of a work session;
> regenerate the header with `python3 harness/scripts/update_memory.py --state`.

<!-- BEGIN generated: at-a-glance · python3 harness/scripts/update_memory.py --state -->
| | |
|---|---|
| Repo HEAD | `b55a15d` — feat: release record, distribution-faithful eval provisioning, ladder-3 smoke |
| Branch | `a5-release` |
| Engine pin | `transon==0.2.3` (see [pyproject.toml](../pyproject.toml)) |
<!-- END generated: at-a-glance -->

## Last action

_**IN PROGRESS, UNCOMMITTED — single-`SKILL.md` restructure (spec written, code not swept).**
User decision 2026-07-22: stop carrying two copies of the body. The repo had the canonical
`SKILL.md` at the root plus a committed generated duplicate at `skills/transon-authoring/SKILL.md`
held byte-identical by AC-040. **The plugin-native path becomes THE canonical path** — one file,
single source by absence of a second copy rather than by an enforced-identity gate, so
edit-without-regenerating cannot happen. A root symlink was considered and rejected: a Windows
checkout without symlink support materialises a text file containing `../../SKILL.md`, which would
then be served as the skill body while `check_install` reads through the link locally and passes.
**Done (uncommitted):** SPEC FR-037(a), AC-040 (byte-identity clause deleted), §11.9 (new
"Canonical body location" — installers copy OUT of that directory and land files FLAT, so
`.install-manifest.json` `files` and `adapters/*/adapter.json` keep naming destination-relative
`SKILL.md` and uninstall still deletes the right paths), FR-019, ARCHITECTURE §10.
**Not started:** `git mv SKILL.md skills/transon-authoring/SKILL.md` (must be byte-identical — a
pure path change, no §11.8 baseline implication); delete `scripts/sync_plugin.py` +
`tests/test_sync_plugin.py`; sweep ~10 code call sites (`check_parity` root read + its
"exactly one SKILL.md" rule, `check_install` `PLUGIN_SKILL_REL`/staging tuple/identity block,
`install/_shared.py:108` source resolution, `scripts/_shared.py:91`, `host_harness`,
`eval_harness`, `local_eval`), 4 workflows, ~9 test files, and the FR-037 traceability row
(it cites the deleted `test_sync_plugin.py`). Then full suite + six gates.
Session ended here because the tool-safety classifier went down (Bash and subagent launches
refused; read-only tools fine)._

_**A5 implementable slice (branch `a5-release`, 4 commits through `2ac5ba6`, UNPUSHED).** Committed: the governed spec change
(`33f2724`) making the release record normative — repo-root `CHANGELOG.md` named in NFR-008 and
ARCHITECTURE §10, new **AC-042** verifying the version triplet against `pyproject.toml` +
`resources/metadata-snapshot.md`, and ROADMAP ladder 2 pinned to the **staged file subset** as the
installer's source root (not an unpacked sdist — that is ladder 1's claim). Then `5140202`:
**FR-038/AC-041** (Cursor personal scope — the exclusion was a product choice, so all four
superseded artifacts were swept together and `check_install` now exercises `cursor/personal`) and
**FR-037a/AC-040** (the §11.9 plugin tree, `scripts/sync_plugin.py`, byte-identity gate); project
version bumped `0.0.1` → `0.1.0`, which AC-040 forces `plugin.json` to match and `release.yml`
forces the tag to match.
Then `b55a15d`: **NFR-008/AC-042** (`CHANGELOG.md` + the release-record check; the row deliberately
stays `[ ]` — the mechanical half is green and cited, the release-checklist half has not happened),
**ladder 2** (`host_harness` provisions the workspace by running the shipped
`install/claude.py --target-root`; provisioning failure classifies `infra_error`; both eval
workflows bundle what the installer reads and assert it before provider spend; SPEC §11.8 reworded
to name the installer), and **ladder 3** (`cursor-activation-smoke.yml`, dispatch-only).
**`spec-reviewer` caught two falsehoods in the release record**, both since corrected and both
verified independently: `transon-authoring 0.0.1` **is already on TestPyPI** (uploaded 2026-07-22
from `main`, run 29915374804) — the record had claimed no upload existed; and ladder 1 was recorded
"green on the CI runs of this branch" when `a5-release` has never been pushed and has no runs. The
gate that governs this file cannot catch either: AC-042 checks only that the triplet agrees with
`pyproject.toml` and the snapshot provenance, so **every ladder/publication line is unverified
prose and must be checked by a human against `gh run list` before release**.
Ladder-3 caveats to settle before it is ever dispatched: it needs a `CURSOR_API_KEY` secret that
does not exist; OQ-027f(ii) is **not** satisfiable there (the key is the agent's own credential —
no proxy equivalent to the Anthropic path), so it is documented as accepted residual risk needing a
dedicated low-privilege key; the Cursor CLI installs via an unpinned `curl | bash` (Cursor ships no
versioned artifact); egress audits rather than blocks (Cursor publishes no endpoint list); and the
claim is limited to "the shipped recipe was used" — text output cannot distinguish activation from
the agent reading the installed file, since its cwd is the workspace._

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

1. **Finish the single-`SKILL.md` restructure** (see Last action): commit the SPEC edit, then do the
   `git mv` + call-site sweep, full suite + six gates, and a second `spec-reviewer` pass — the first
   one reviewed the two-copy design, so it does not cover this.
2. Push `a5-release` and open the PR (outward-facing; needs the user).
3. Small leftovers deliberately not done: `check_plugin` inspects only the first matching
   marketplace entry (a duplicate later entry with a bad `source` is unexamined); two hygiene
   stragglers in `host_harness.py` (the `run_fixture` comment narrates work the installer now does;
   `skill_md` is vestigial for the real host — supplied, ignored at the call site).
4. Maintainer-only A5 items, none of which an agent can perform — each fills a `_pending_` slot in
   the `CHANGELOG.md` 0.1.0 entry:
   a. **Entry-condition eval rerun.** The shipped body changed since the accepted baseline (the
      OQ-029 recovery line), so the full 54×3 real-host gate must be re-run before release
      (≈$18–19), with OQ-027f (i)–(iv) confirmed in force.
   b. **Ladder 2 probe first.** Dispatch one fixture via `--only` under the new installer
      provisioning and read the per-fixture majority before spending on the full gate.
   c. **Ladder 3.** Add the `CURSOR_API_KEY` secret, then dispatch `cursor-activation-smoke.yml`;
      tighten its egress from `audit` to `block` using the observed host set.
   d. **Ladder 4.** UC-004 walkthrough on a repo-free machine, TestPyPI then PyPI.
   e. **Publish.** Register the trusted publishers + environments, dispatch TestPyPI, push `v0.1.0`.
      FR-037b outreach begins only after this.
5. Flip the NFR-008 traceability row to `[x]` once 4a–4e are recorded.

## Open blockers / waiting-on

- The `SKILL.md` restructure is mid-flight: SPEC edited, code not swept. Finish it or revert the
  SPEC edit — do not push the branch in between.
- A5's DoD cannot close without the maintainer items in Next step 4.
- Confirm the `marketplace.json` owner identity (`transon-org`, inferred from the git remote) — the
  repo is named `transon-authoring-skill` while the plugin is `transon-authoring`.
- Watch item: 3 fixtures passed the baseline gate 2/3 — future-flake candidates the ratchet will
  surface via `failure_modes`.

## Do-not-relitigate (pointers, not copies)

- Product contract → [`SPEC.md`](SPEC.md) + [`ARCHITECTURE.md`](ARCHITECTURE.md) + [`ROADMAP.md`](ROADMAP.md).
- Coverage matrix → [`traceability.md`](traceability.md).
- Golden rules → [`AGENTS.md`](../AGENTS.md).
