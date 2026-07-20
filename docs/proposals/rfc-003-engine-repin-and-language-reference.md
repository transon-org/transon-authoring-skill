# RFC-003: Re-pin the engine to 0.2.3 and ground the skill in `get_language_reference()`

- **Status:** **Accepted & absorbed into SPEC (2026-07-20).** Normative wording lives in
  `docs/SPEC.md`: **FR-036** (Language Reference grounding artifact + `language` subcommand),
  **AC-039** (offline serving + drift/major gating), **AD-026** (snapshot-like treatment +
  authority swap), plus the pin bump (AD-007 / §11.7 / §11.9), the AD-018 authority-precedence
  revision, the NFR-012 / AC-032 self-sufficiency tightening (no external-file exemption), the
  NFR-004 / FR-011 reference-drift extension, the §11.6 `language` row, and the §11.8 pin+corpus
  baseline-reset paragraph. This file is historical rationale only; on conflict the SPEC wins.
  Resolved open questions: **R1** = `transon==0.2.3`; **R2** = snapshot (treated like editor
  metadata); **R3** = `language` envelope in §11.6; **R4** = refuse-bucket floor ≥ pre-repin count,
  AD-023 probe audit; **R5** = no external-file exemption remains.
- **Type:** Engine-pin upgrade (AD-007 upgrade-PR policy) + authority-source swap for the
  shipped skill. Changes what the skill cites as Transon authority; does **not** change
  verify/match/sandbox semantics, the SampleSet schema, or the §11.8 scoring rules.
- **Related (normative today):** AD-007 (pin + upgrade policy), AD-018 / NFR-001 (authority
  precedence), NFR-012 / AC-032 (shipped self-sufficiency + `check_parity` lint), FR-009–011
  (snapshot/sync/drift), FR-029 / AC-030 (synthetic regen), FR-033 / AC-035 (engine-freeze),
  §11.8 (gate identity, baseline reset), §14 A5 (entry: baseline reflects shipped skill).

## One-line summary

Move the pin `transon==0.1.7` → `transon==0.2.3`, and replace the skill's citations of the
engine repo file `docs/SPECIFICATION.md` with the engine's packaged, versioned
**Language Reference** obtained through `transon.reference.get_language_reference()` —
exposed to the model as a new `python -m transon_authoring language` subcommand — so the
authority the skill names is reachable on every machine the skill is installed on.

## Problem

Two problems, one upgrade.

**1. Pin staleness (AD-007 risk realized).** Latest engine is 0.2.3. Since 0.1.7:

- **v0.1.8 (R-33):** built-in function library grew (`split` rule, `in`, expanded
  `call.name` / `expr.op` metadata options, new corpus examples). Our snapshot, examples
  corpus, and — critically — our **refuse fixtures premised on absent capabilities**
  (uppercase, epoch→ISO, ref-strip) are stale against it: any capability R-33 added turns
  its refuse fixture factually wrong (the model *should* author it now).
- **v0.2.0 (RFC 0008, R-34/35/36):** packaged author-facing Language Reference
  (`LANGUAGE.md`) with a programmatic export, plus a behavior fix — `NO_CONTENT` identity
  preserved inside deep-copied containers — which touches the OQ-012 `NO_CONTENT`
  semantics our match layer encodes.
- v0.2.1–v0.2.3: docs-only.

**2. The skill cites a file its users don't have.** `SKILL.md` names the engine repo path
`docs/SPECIFICATION.md` as Transon authority (2 sites, AD-018 item 2). On a fresh install
(§11.9: skill files copied to `.claude/skills/` / `.cursor/skills/`; runtime from PyPI per
OQ-020) there is **no engine repo checkout** — the citation dangles for exactly the
audience UC-004 describes. NFR-012 papers over this with a hand-carved exact-string
exemption in `check_parity` (`docs/SPECIFICATION.md` plus a `§`-on-the-same-line
allowance). The engine now ships the authority **inside the pinned wheel**, versioned and
machine-consumable:

```python
transon.reference.get_language_reference() -> {
  "reference_version": ...,   # own semver; minor = additive, major = breaking —
                              # consumers MUST fail loudly on unsupported major
  "engine_version":    ...,
  "format": "markdown",
  "content": ...,             # byte-exact LANGUAGE.md
  "sections": [ {id, title, heading_level, content}, ... ]  # ordered split
}
```

An authority reachable through the already-pinned runtime strictly dominates a citation
into a repo the user never cloned.

## Proposal

**P1 — Re-pin to `transon==0.2.3` (AD-007 upgrade PR).**
SPEC-first: update the pin literal in AD-007 / §11.7 / §11.9 (OQ-020 paragraph) and
`AGENTS.md`; bump `pyproject.toml`; resync the snapshot (`sync_metadata.py`,
`check_snapshot` green; OQ-021: R-33's new examples raise the uncovered-count, allowed);
update the hard-coded `0.1.7` literals in tests (`test_sync_metadata`, `test_package`,
`test_install`, …); confirm `metadata_version` (the `check_install` Cursor smoke asserts
`"3.0"`). The local authority checkout `../transon` sits at the matching tag.

**P2 — Language Reference gets the exact metadata treatment: snapshot + sync + drift +
engine-free read path.**
The reference is a second engine-derived grounding artifact and is handled **identically
to `get_editor_metadata()`**:

- `sync_metadata.py` additionally dumps `get_language_reference()` to
  `resources/language-reference.json` (canonical serialization), and the provenance block
  records its sha256 + `reference_version` alongside the snapshot hash;
- `check_snapshot` compares the bundled reference against the pinned engine's output —
  same drift gate, same red-until-`sync-metadata` discipline (NFR-004 pattern);
- new §11.6 subcommand `python -m transon_authoring language [--section ID]
  [--list-sections]` reads the **bundled resource, never importing the engine** (FR-009
  symmetry): no arguments → full `content`; `--list-sections` → ordered `{id, title}`;
  `--section ID` → that section's `content`; unknown ID → §11.6 schema-error, exit 2;
  unsupported `reference_version` **major** in the bundled document → exit 2, per the
  engine's consumer contract (enforced at sync time too, so it cannot land silently);
- the payoff of snapshotting over a live passthrough: **the authority delta is a
  reviewable diff on every upgrade PR** (AD-007 "not silent"), one mental model for all
  engine-derived grounding, and the whole grounding surface stays engine-import-free.
  Offline per NFR-003.

**P3 — Authority swap in the skill (the NFR-012 payoff).**
- AD-018 item (2): `docs/SPECIFICATION.md` → the packaged Language Reference obtained via
  `get_language_reference()` (surface: the `language` subcommand).
- `SKILL.md`: both `docs/SPECIFICATION.md` citations become the `language` module recipe
  ("run `python -m transon_authoring language --section <id>`…").
- NFR-012 / `check_parity`: **delete the `docs/SPECIFICATION.md` exact-string exemption
  and the `§`-on-`SPECIFICATION.md`-line allowance.** The shipped surface then cites *no
  external file at all* — every authority is a module-recipe invocation. Self-sufficiency
  becomes uniform (this also retires two standing review nits about the exemptions being
  wider than the rule). `language` joins the recipe allowlist.
- Engine `docs/SPECIFICATION.md` remains an AD-018 authority for **maintainers of this
  repo** (design-time), just no longer citable from the shipped surface.

**P4 — Corpus and gate consequences (the expensive half).**
- FR-029 synthetic fixtures re-minted from the new snapshot (AC-030 regen lint forces
  this); intents carry over verbatim; changed case outputs need AD-021 human
  re-acceptance.
- FR-033 constructed seeds re-execute through 0.2.3 (AC-035 engine-freeze); the
  `NO_CONTENT` fix may legitimately change frozen outputs.
- **Refuse-bucket audit vs R-33:** for each refuse fixture premised on a missing engine
  capability, re-probe the 0.2.3 engine; now-satisfiable asks convert to matched fixtures,
  and the adversarial bucket is refilled with genuine 0.2.3 gaps (target stays =100%).
- `SKILL.md` capability claims audited against the new function surface.
- Eval-policy commit: pin + corpus change is gate identity (§11.8) → reset
  `evals/baseline.json`, targets never lowered; one full green real-host gate re-mints the
  baseline. **This run and the A5 entry condition are the same run** — sequencing this RFC
  before the A5 release pays for one gate, not two.

## Tradeoffs

- **Cost:** one full 50×3 real-host gate (~$17 measured) plus targeted probes; human
  re-acceptance for any fixture whose outputs changed.
- **A committed copy of text that also ships in the wheel.** Accepted: the duplication is
  the point — it is what makes authority changes reviewable diffs and keeps the read path
  engine-free; drift between the copies is exactly what the gate exists to catch, and the
  sync/drift/provenance machinery already exists (marginal code is small).
- **Larger prompt surface risk:** the full reference dumped into context would bloat
  episodes; the sectioned lookup exists precisely so the skill can mandate targeted
  `--section` retrieval (mirror the OQ-022 minimal-contract discipline).
- **Refuse-bucket churn:** capability growth shrinks the space of honest refuse fixtures;
  each upgrade needs the audit in P4. That is the correct cost of honest adversarial
  fixtures.

## Migration

1. RFC accepted → absorb into SPEC (governed edit; new IDs from the ledger as needed:
   subcommand FR/AC, AD revision for AD-018, NFR-012 wording, §11.6 table row, §13/§17
   updates; FR-011/NFR-004 gain the reference artifact).
2. P1 re-pin commit (SPEC literals + pyproject + snapshot resync + test literals).
3. P2 sync/drift extension + `language` subcommand over the bundled resource, test-first.
4. P3 skill/authority swap + `check_parity` simplification, test-first (the AC-032
   fixture tests lose the exemption cases and gain a `language`-recipe green case).
5. P4 corpus regen + refuse audit + human acceptance → eval-policy commit (baseline
   reset) → targeted probe → full gate → `--update-baseline`.
6. A5 release proceeds on the fresh baseline (entry condition already satisfied).

## Open questions (resolve at standup, before the affected step)

- **R1 — Target version.** 0.2.3 (latest; docs-only above 0.2.0) vs 0.2.0 (minimal
  behavior floor). Recommendation: **0.2.3** — same runtime behavior, newest packaged
  reference text.
- **R2 — Passthrough vs snapshot — resolved in this draft: snapshot,** treated exactly
  like the editor metadata (sync + drift + provenance + engine-free read path). The
  deciding argument: a live call changes the shipped authority invisibly inside a wheel
  bump, while the snapshot makes every authority change a reviewable diff on the upgrade
  PR (AD-007). Uniformity and FR-009 symmetry come free.
- **R3 — Section-lookup contract.** Exact `language` CLI envelope (mirror OQ-022's
  minimalism: exact-id first, bounded, deterministic order) — settle before P2.
- **R4 — Refuse-bucket refill.** How many genuine 0.2.3 gaps must the adversarial bucket
  hold before the gate run (floor: enough to keep the bucket non-empty and meaningful;
  candidates need the AD-023 probe discipline).
- **R5 — Any external-file exemption left?** Recommendation: none — after P3 the shipped
  surface cites only module recipes; `check_parity` loses both special cases.

## Recommendation

Accept P1–P4 with R1=0.2.3 and R2=snapshot (identical treatment to editor metadata). Run
it as its own upgrade PR after the A4/A5-ladder merges, sequenced so the P4 gate run
doubles as the A5 entry baseline.
