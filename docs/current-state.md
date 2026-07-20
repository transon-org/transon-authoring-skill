# Current state — working handoff

> **Non-authoritative working memory.** A session-to-session handoff, not part of the
> contract. Where this and the contract docs (`SPEC.md`, `traceability.md`, `AGENTS.md`)
> disagree, **they win**. Update the narrative below at the end of a work session;
> regenerate the header with `python3 harness/scripts/update_memory.py --state`.

<!-- BEGIN generated: at-a-glance · python3 harness/scripts/update_memory.py --state -->
| | |
|---|---|
| Repo HEAD | `941ceb6` — docs: absorb RFC-003 into SPEC — repin 0.2.3, Language Reference grounding (FR-036/AC-039/AD-026) |
| Branch | `rfc-003-engine-repin-language-reference` |
| Engine pin | `transon==0.2.3` (see [pyproject.toml](../pyproject.toml)) |
<!-- END generated: at-a-glance -->

## Last action

_**RFC-003 in progress (branch `rfc-003-engine-repin-language-reference`, 2026-07-20).** Re-pin engine `0.1.7`→`0.2.3` + ground the shipped skill in the packaged Language Reference via `get_language_reference()` instead of the engine-repo `docs/SPECIFICATION.md`. **Committed:** T1 SPEC absorption (`941ceb6`) — FR-036/AC-039/AD-026, pin bump across AD-007/§11.7/§11.9/AGENTS, AD-018 authority swap, NFR-012/AC-032 drop the SPECIFICATION.md exemption, §11.8 pin+corpus baseline-reset policy, AD-023 refuse-capability claim made pin-neutral; RFC marked Accepted. **Uncommitted in working tree:** T2 repin mechanics — pyproject pin bumped, `.venv` on 0.2.3, snapshot regenerated (121→163 examples), all hard-coded `0.1.7` test/src literals updated, brittle example-count assertion de-frozen. `check_snapshot` + `check_evals --lint` + unit suites green; the `NO_CONTENT` deep-copy fix and new functions broke NO existing behavior. **One red:** `test_fr_029_v1_wave_covers_all_tag_families` — 0.2.3 adds a `split` tag family needing one new synthetic fixture (AD-021 intent pending user)._

_**RFC-003 implementation complete + committed (user accepted intents 2026-07-20).** Repin 0.2.3, FR-036 language subcommand + snapshot/drift (`resources/language-reference.json`, engine-free), authority swap (SKILL.md → `language` recipe; `check_parity` drops the SPECIFICATION.md exemption), and corpus regen. Corpus: 3 now-satisfiable refuses converted to constructed matched fixtures (`order-uppercase-currency`, `stripe-epoch-to-iso`, `github-branch-from-ref` — engine-verified); split-family synthetic `syn-split-string` minted (covers the new `split` tag family); 3 genuine-gap refuses added (`refuse-sha256-checksum`, `refuse-random-winner`, `refuse-recursive-flatten` — sha256/random/arbitrary-recursion confirmed absent at 0.2.3). Adversarial bucket = 5. **`evals/baseline.json` reset to empty (§11.8 pin+corpus reset)** — repopulates only from the next green live run. Full suite 664 passed; all gates green._

_**Still pending:** spec-reviewer pass → PR. **STOP before the ~$17 credentialed live real-host gate** — it is the A5-entry baseline dispatch (§11.8), user-run, and doubles as the RFC-003 baseline repopulation. SKILL.md rendered text changed (authority swap) so the eval baseline rerun is doubly required before A5 release._

_**Prior behavioral closure (2026-07-15, from former traceability essays).** First green §11.8 real-host gate (run 29381271246) — authoring 0.977 (43/44) ≥ 0.80, adversarial 1.000, correction 1.000; baseline accepted (`f672bcf`)._


## Status by milestone

Authoritative milestone DoDs live in [`SPEC.md` §14](SPEC.md). This is the living read.

- See SPEC §14 for A0–A5 definitions of done.

## Next steps (ordered)

1. RFC-003: collect the user's split-family + 3 refuse `intent_nl` texts (AD-021), then finish deterministic work — FR-036 language subcommand (in flight), convert 3 satisfiable refuses to matched + mint split fixture + 3 new genuine-gap refuses, T5 authority swap (SKILL.md → `language` recipe, drop `check_parity` SPECIFICATION.md exemption, add `language` to allowlist). Land green, spec-reviewer, PR. STOP before the ~$17 credentialed live gate (A5 entry).
2. A4 PRs #20/#21/#22 already merged into main; RFC-003 branched off the merged main.
3. A5: versioned release notes with pin, first PyPI publish (OQ-020), distribution-verification ladder, optional editor sink — after the RFC-003 baseline rerun (which doubles as the A5 entry, §11.8).

## Open blockers / waiting-on

- **RFC-003:** awaiting user AD-021 intent texts (split fixture + 3 refuse fixtures). FR-036 implementer running in background. Live gate is user-dispatched spend.

## Do-not-relitigate (pointers, not copies)

- Product contract → [`SPEC.md`](SPEC.md).
- Coverage matrix → [`traceability.md`](traceability.md).
- Golden rules → [`AGENTS.md`](../AGENTS.md).
