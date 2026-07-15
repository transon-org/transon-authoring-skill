# Current state — working handoff

> **Non-authoritative working memory.** A session-to-session handoff, not part of the
> contract. Where this and the contract docs (`SPEC.md`, `traceability.md`, `AGENTS.md`)
> disagree, **they win**. Update the narrative below at the end of a work session;
> regenerate the header with `python harness/scripts/update_memory.py --state`.

<!-- BEGIN generated: at-a-glance · python harness/scripts/update_memory.py --state -->
| | |
|---|---|
| Repo HEAD | `12b3e38` — docs: slice F — historical banners on docs/proposals/ |
| Branch | `hygiene-culture-and-denoise` |
| Engine pin | `transon==0.1.7` (see [pyproject.toml](../pyproject.toml)) |
<!-- END generated: at-a-glance -->

## Last action

_**Hygiene culture + de-noise (in progress on `hygiene-culture-and-denoise`).** Phase 1 landed: working-memory sink, revision protocol (replace text / no stacked revs), hygiene rule, spec-reviewer + CodeRabbit awareness, handoff stop hooks. Phase 2 slices A–D cleaned SPEC history (§15 OQs, §14 DoDs, §7–§9 FR/NFR/AC, §6/§11 residual). Slice E: slimmed `docs/traceability.md` Tests cells to test references only._

_**Prior behavioral closure (2026-07-15, from former traceability essays).** First green §11.8 real-host gate (run 29381271246) — authoring 0.977 (43/44) ≥ 0.80, adversarial 1.000, correction 1.000; baseline accepted (`f672bcf`)._


## Status by milestone

Authoritative milestone DoDs live in [`SPEC.md` §14](SPEC.md). This is the living read.

- See SPEC §14 for A0–A5 definitions of done.

## Next steps (ordered)

1. Open a PR for `hygiene-culture-and-denoise` when ready for review (local + CodeRabbit).
2. Resume product work (A4 distribution slice) under the new hygiene culture.

## Open blockers / waiting-on

- None.

## Do-not-relitigate (pointers, not copies)

- Product contract → [`SPEC.md`](SPEC.md).
- Coverage matrix → [`traceability.md`](traceability.md).
- Golden rules → [`AGENTS.md`](../AGENTS.md).
