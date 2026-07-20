# Current state — working handoff

> **Non-authoritative working memory.** A session-to-session handoff, not part of the
> contract. Where this and the contract docs (`SPEC.md`, `traceability.md`, `AGENTS.md`)
> disagree, **they win**. Update the narrative below at the end of a work session;
> regenerate the header with `python3 harness/scripts/update_memory.py --state`.

<!-- BEGIN generated: at-a-glance · python3 harness/scripts/update_memory.py --state -->
| | |
|---|---|
| Repo HEAD | `45b6197` — Merge pull request #22 from transon-org/rfc-003-engine-repin-language-reference |
| Branch | `main` |
| Engine pin | `transon==0.2.3` (see [pyproject.toml](../pyproject.toml)) |
<!-- END generated: at-a-glance -->

## Last action

_**RFC-003 merged to main (PR #22, 2026-07-20; HEAD `45b6197`).** Repin engine `0.1.7`→`0.2.3` + ground the shipped skill in the packaged Language Reference (`get_language_reference()`) instead of the engine-repo `docs/SPECIFICATION.md`. FR-036 (language subcommand + snapshot/drift, engine-free read via `resources/language-reference.json`), AC-039, AD-026; AD-018 authority swap; NFR-012/AC-032 drop the SPECIFICATION.md exemption; §11.8 pin+corpus baseline-reset. Corpus: snapshot 121→163 examples; 3 now-satisfiable refuses converted to constructed matched fixtures (`order-uppercase-currency`, `stripe-epoch-to-iso`, `github-branch-from-ref`, engine-verified); split-family synthetic `syn-split-string`; 3 genuine-gap refuses (`refuse-sha256-checksum`/`refuse-random-winner`/`refuse-recursive-flatten`, capabilities confirmed absent). Adversarial bucket = 5. `evals/baseline.json` reset to empty (§11.8). Full suite 664 passed; all deterministic/in-PR gates green — the credentialed live real-host baseline gate remains pending (A5-entry dispatch, outside this PR; A5 is not unblocked until it runs). spec-reviewer verdict **merge** (stale-pin doc refs fixed); CodeRabbit review fixes applied._

_**Prior behavioral closure (2026-07-15, from former traceability essays).** First green §11.8 real-host gate (run 29381271246) — authoring 0.977 (43/44) ≥ 0.80, adversarial 1.000, correction 1.000; baseline accepted (`f672bcf`)._


## Status by milestone

Authoritative milestone DoDs live in [`SPEC.md` §14](SPEC.md). This is the living read.

- See SPEC §14 for A0–A5 definitions of done.

## Next steps (ordered)

1. Merge PR #22 (RFC-003) once CodeRabbit + CI settle.
2. Dispatch the credentialed live real-host eval gate (~$17) — it is the A5-entry baseline run (§11.8), repopulates the now-empty `evals/baseline.json`, and is required before A5 release because the authority swap changed SKILL.md rendered text.
3. A5: versioned release notes with pin, first PyPI publish (OQ-020), distribution-verification ladder, optional editor sink — after the baseline rerun above.

## Open blockers / waiting-on

- **RFC-003 live gate is user-dispatched spend** (~$17); nothing else blocks.

## Do-not-relitigate (pointers, not copies)

- Product contract → [`SPEC.md`](SPEC.md).
- Coverage matrix → [`traceability.md`](traceability.md).
- Golden rules → [`AGENTS.md`](../AGENTS.md).
