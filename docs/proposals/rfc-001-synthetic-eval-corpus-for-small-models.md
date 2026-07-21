# RFC-001: Synthetic eval corpus from `docs.examples` (small-model gate)

- **Status:** **Accepted & absorbed into SPEC (2026-07-12).** Normative wording lives in
  `docs/SPEC.md`: **AD-021** (synthetic corpus + small-model gate), **FR-029** (generator +
  seed provenance + regen lint), **AC-030** (regen gate), **OQ-024** (resolved decisions for
  OQ-R1–R6 and the baseline-reset rule), plus §11.8 gate-model policy and synthetic-fixtures
  rules. This file is historical rationale only; on conflict the SPEC wins.
- **Type:** Eval-corpus / measurement-policy proposal for `transon-authoring` (skill improvement
  loop only). Does **not** change Transon template semantics, `verify`, or SampleSet schema.
- **Pin assumed:** `transon==0.1.7`, `metadata_version` `"3.0"`, flat `docs.examples` length
  **121** (same engine export the Blockly host surfaces as examples).
- **Related (already normative):** FR-010, FR-017, FR-018, AD-010, AD-011, AD-018, AD-020,
  NFR-010, NFR-011, §11.8.

## One-line summary

Grow the skill-improvement eval corpus by minting SampleSets from the pinned `docs.examples`
templates (synthetic inputs → pinned `Transformer` outputs), hide those templates from the skill
under test, and make a **small model** the primary NFR-010 gate model so the skill is driven to
work without a large frontier model.

## Why

The planned improvement loop (FR-017 / AD-010 / §11.8) scores committed fixtures and ratchets
targets. Today the seed set is tiny and hand-built; real-use capture (FR-018) is slow and
privacy-gated. Separately, the committed `evals/runner.json` pins a large model
(`claude-sonnet-5`). That measures “works with a strong model,” not “good enough for small
models.”

We already have an engine-authoritative template corpus: the pinned snapshot’s `docs.examples`
(121 cases). Those templates are known-good. We can treat each as a **fixture factory**:

1. Assume input shapes from the example’s own `data` and from metadata-informed variation
   (cardinality / combinatorics — stratified, not exhaustive).
2. Generate synthetic inputs.
3. Obtain outputs only by running the **pinned** `Transformer` (AD-018) — never by model memory.
4. Build a confirmed SampleSet + `intent_nl`.
5. Keep the seed template in-repo as **regen provenance only**; never put it in the eval prompt
   or tools path for the skill under test.
6. Score as today: skill submits a template → `verify` → `assurance: "matched"` (behavioral
   match, **not** bit-identical recovery of the seed).

This is compatible with the existing gate shape; it is a **corpus-growth and runner-policy**
method the SPEC does not yet describe.

## Decisions locked for this draft

> **Historical (superseded 2026-07-12):** the deferrals below (notably D1) were fulfilled the
> same day — the SPEC edit landed as AD-021/FR-029/AC-030/OQ-024. They are kept verbatim as the
> decision record at drafting time.

Recorded from author answers (2026-07-12); change only by editing this RFC.

| # | Topic | Decision |
|---|--------|----------|
| D1 | SPEC timing | **Draft RFC only.** Normative SPEC edit deferred until the author’s current task finishes. |
| D2 | `intent_nl` | **LLM-drafted, human-reviewed (C).** Drafting **may** (should) ground on example `doc` and/or NL sidecar text (**B as context for C**). Sidecar remains hints-only for runtime authoring (AD-018); here it is prompt material for fixture authors. |
| D3 | Small models | **Primary NFR-010 gate model (C)** — replace the current runner pin when this lands in SPEC/policy, not a side advisory track. |
| D4 | Seed template | **Keep in repo as provenance / regen input (B).** Never shown to the skill under test. |
| D5 | Generator scope (v1) | **Pinned `docs.examples` only (A)** — the flat 121-case corpus in the authoring metadata snapshot (same list Blockly uses from the engine export). No hand-only seeds, no cross-rule combinatoric templates beyond that list, in v1 of this proposal. |

## Non-goals (v1 of this proposal)

- Changing `verify` / match / SampleSet schemas.
- Scoring template isomorphism or “recovered the hidden seed.”
- Using editor codec corpora or Blockly-only fixtures (FR-010: no editor-only corpus entries).
- Auto-committing LLM `intent_nl` without human review.
- Exhaustive enumeration of all input shapes for every rule.
- Training / fine-tuning a model (eval + skill-text improvement only).

## Proposed pipeline

```text
docs.examples[i].template
        │
        ▼
 synthetic inputs (stratified variation)
        │
        ▼
 pinned Transformer.transform  ──►  outputs / writes
        │
        ▼
 SampleSet (cases + coverage + confirmed for CI)
        │
        ▼
 intent_nl  ← LLM draft grounded on example doc / NL sidecar → human review
        │
        ▼
 EvalFixture (expect: matched)
   + seed-template provenance file (regen only; not in prompt)
        │
        ▼
 check_evals with small-model runner pin
        │
        ▼
 tweak SKILL.md / grounding until gate green → baseline / target ratchet
```

### Fixture layout (illustrative; not schema-frozen)

Committed eval case (skill-visible):

- `evals/cases/<id>.json` — `EvalFixture` per §11.8: `intent_nl`, `samples`, `expect`.
- No seed `template` field in the fixture object shown to the harness user message.

Regen provenance (skill-invisible):

- e.g. `evals/seeds/<id>.json` — `{ "source_example": "<docs.examples name>", "template": …,
  "generator": { "version": …, "notes": … } }` used only by a maintainer script to regenerate
  SampleSet I/O when the pin or generator changes.

Exact paths/schema are deferred to the SPEC change; the invariant is D4.

### Scoring (unchanged semantics)

Per §11.8 / OQ-016: `matched-success` iff

`python -m transon_authoring verify --template <submitted> --samples <fixture SampleSet>`

yields `ok` and `assurance: "matched"`. The seed template is irrelevant to the score.

### Runner policy (D3)

When promoted to SPEC: change `evals/runner.json` `model_id` (and provider if needed) to the
chosen **small** model via an explicit eval-policy commit (AD-020). That becomes the NFR-010
identity. Re-seeding `evals/baseline.json` / adjusting `evals/targets.json` will likely be
required in the same change — large-model baselines are not assumed transferable.

Which concrete small model ID is **open** (see OQ-R1 below).

## Relationship to the three loops

| Loop | Role of this RFC |
|------|------------------|
| Sample elicitation (live authoring) | Unaffected. Synthetic SampleSets are for **evals/CI fixtures**, not a substitute for user confirm in interactive use. |
| Template repair (`repair_attempts`) | Unaffected. Still in-session. |
| Skill improvement (FR-017) | **This RFC.** Corpus minting + small-model primary gate to drive `SKILL.md` quality. |

## What must land in a future SPEC edit (checklist, not done here)

> **Historical (done 2026-07-12):** this checklist landed as AD-021 (item 1, 5), the §11.8
> gate-model policy (item 2), FR-029/AC-030 (item 3), and the §14 A3 note (item 4).

When the author resumes SPEC work, expect roughly:

1. New AD (or AD-020 amendment): synthetic fixtures from `docs.examples` are an allowed corpus
   source; outputs must come from the pinned engine; seed templates are provenance-only.
2. Runner policy: small model is the NFR-010 pin (name the model; record as eval-policy).
3. Optional FR for a `scripts/` generator + provenance layout + regen gate on pin bump.
4. Traceability / milestone note: corpus expansion is improvement-loop work (post-A2 harness;
   usable while iterating A3+ skill body).
5. Explicit statement that `intent_nl` for synthetic fixtures is human-accepted even when LLM
   drafted.

Do **not** invent IDs in this draft file.

## Open questions (for the later SPEC pass)

- **OQ-R1** — Which small `provider` / `model_id` becomes the primary gate pin?
- **OQ-R2** — Stratification budget: how many synthetic input variants per example (min/max),
  and which dimensions (scalars, missing keys, empty collections, `NO_CONTENT`-relevant
  shapes, writes-capable examples)?
- **OQ-R3** — Must every one of the 121 examples produce ≥1 fixture in v1, or is a tagged
  subset enough for the first small-model baseline?
- **OQ-R4** — For examples whose engine `result` already covers one I/O pair: always add
  extra synthetic cases, or allow a fixture that only reuses corpus `data`/`result` plus
  synthetic extras?
- **OQ-R5** — Refuse-bucket strategy under a small-model primary gate (invented operator
  names, etc.): keep hand adversarial seeds only, or also synthesize refuse intents?
- **OQ-R6** — Provenance path/schema and whether `check_evals --lint` must prove every
  synthetic SampleSet still regenerates bit-identically from its seed under the current pin.

## Risks

- **Under-specified intents:** weak `intent_nl` makes “matched” luck or overfit to SampleSet
  leakage; human review (D2) is mandatory.
- **SampleSet leakage:** too few / too narrow cases let many wrong templates pass; stratification
  (OQ-R2) matters more than raw count.
- **Gate cliff:** switching the primary model to a small one may drop authoring rate below 80%
  until `SKILL.md` improves — expected; plan a baseline reset rather than silently lowering
  targets.
- **Pin drift:** regenerating from seeds must re-run the pinned engine after snapshot bumps
  (same discipline as `check_snapshot`).

## Recommendation

> **Historical (fulfilled 2026-07-12):** the RFC was accepted and the SPEC pass happened; the
> "do not implement until the SPEC edit lands" condition is satisfied. Generator, fixture wave,
> and the runner-pin swap are now governed by ROADMAP §14 (A3 DoD), not by this file.

Accept this RFC as the intended direction for corpus growth and small-model gating. Defer
normative wording and ID issuance until the author’s SPEC pass. Do not implement generator or
runner pin changes against `main` until that SPEC edit lands (SPEC-first).
