# SPEC — Transon Authoring Skill (`transon-authoring`)

A standalone, distributable capability that lets **coding agents and CI** in the org author
correct, engine-valid **Transon** JSON — grounded in engine-authoritative metadata, backed by a
**user-confirmed SampleSet**, and blessed by the engine at **`matched`** assurance before any
template is returned. It lives in its own repository, **beside** (not inside) the
`transon-blockly` editor and the `transon` engine.

> **Status:** Draft (pre-A0). This document, with `ARCHITECTURE.md` and `ROADMAP.md`, is the
> contract for the project — behavior changes update the contract docs first, then code
> (see §12 governance).
>
> **Pre-A0 note:** Until A0 is approved/started, requirement and decision text may be rewritten in
> place to keep the draft coherent. **From A0 onward**, FR/NFR/AC/UC/AD/OQ IDs are append-only:
> never renumber; deprecate in place; new items take the next free number.

**Initial engine pin (A0 baseline):** `transon==0.1.7` with `metadata_version` `"3.0"`
(authoritative evidence: engine repo `pyproject.toml` version `0.1.7`;
`transon-blockly/docs/metadata-snapshot.json` records `engine_version` `0.1.7` and
`metadata_version` `3.0`). See AD-007 / §11.7.

---

> **Contract split.** The contract spans three documents: [`SPEC.md`](SPEC.md) (§0–4, §7–9,
> §11–13, §17 — goals, requirements, normative contracts, governance, gates, traceability),
> [`ARCHITECTURE.md`](ARCHITECTURE.md) (§5, §6, §10 — architecture, decision records, package
> layout), and [`ROADMAP.md`](ROADMAP.md) (§14–16, §18 — milestones, open questions, risks,
> readiness). **Section numbers are global and unique across all three**, so a reference such as
> §6 or §11.9 is unambiguous wherever it appears. Requirement IDs (FR/NFR/AC/UC/AD/OQ) are
> append-only and never renumber (§12).

---

## 0. Namespace & relationship to other repos

This is a **separate contract** from the editor's `docs/SPEC.md`. IDs here are independent of the
editor's numbering; the two documents are not cross-referenced by ID.

| Repo | Role | Bound by editor AD-008 (engine-free)? |
|---|---|---|
| `transon` (engine) | Owns `get_editor_metadata()`; executes templates; **authoritative** | n/a |
| `transon-blockly` (editor) | Visual editor; engine-free; consumes authored JSON via its import codec | yes |
| **`transon-authoring` (this repo)** | Authoring capability for AI agents; **may embed the engine** | **no** — see AD-002 |

The product name is **`transon-authoring`**. Any earlier editor-dev harness skill of the same name
is temporary and is removed or redirected once this package ships (A4+).

Architecture decisions live in **§6** (`ARCHITECTURE.md`). If §6 grows too large, split ADs into
`docs/adr/`. Do not create empty ADR files up front.

---

## 1. Problem & motivation

Coding agents (Claude Code, Cursor) and CI bots are increasingly asked to produce Transon
templates. Left alone they **hallucinate Transon syntax** because authority is the **running pinned
engine + engine SPECIFICATION + pinned metadata export**, not model memory, generative web docs, or
Context7.

Static validation is also insufficient without a **confirmed SampleSet** whose cases satisfy
**declared coverage obligations**. This project: ground in metadata, craft/confirm samples, then
`verify` to **`matched`**.

---

## 2. Goals

- **G1** — From NL intent → sample loop (propose obligations → cases/waivers → user/CI confirm) →
  engine-valid JSON that `verify` blesses at **`assurance: "matched"`**. Editor "in-surface" is
  **not** part of the output contract (AD-013), subject to the v1 execution profile (AD-017).
- **G2** — Ground generation in the **pinned** metadata snapshot (and engine docs examples), not
  training data. “Current” means **current relative to the pin** (§11.7), not “latest on PyPI.”
- **G3** — **Verify before return**: never return a template unless `verify` yields `matched`.
- **G4** — Single-source skill + Claude Code and Cursor adapters + parity gate.
- **G5** — Decoupled from the editor.

## 3. Non-goals

- Not an in-editor chatbot / `AssistantProvider`.
- Not a new DSL, path syntax, or expression language.
- Not a Transon runtime (authors templates; engine executes).
- Not a workflow / no-code platform.
- Not bound by editor engine-free AD-008 (see AD-002).
- Not MCP, hosted HTTP engine, or WASM/Pyodide in v1.
- Not shell-less product/docs agents in v1.
- Not editor in-surface checking/disclosure.
- Not an editor JSON sink or blockly import handoff in v1.
- Not real filesystem/network I/O in `verify` dry-run (including inside timeout worker subprocesses).
- Not custom `Transformer` subclasses, custom rule/operator/function registries, or non-default
  markers as a **verify execution profile** in v1 (AD-017) — templates always run under `"$"`.

## 4. Consumers

| Consumer | Environment | Reach |
|---|---|---|
| Coding agent (Claude Code, Cursor) | shell | `python -m transon_authoring …` |
| CI / migration bot | headless shell | same; pre-confirmed SampleSet fixtures |

---

## 7. Functional requirements

### Authoring core
- **FR-001** — Given NL intent and a SampleSet with `coverage_complete` and `confirmed`, draft
  candidate JSON grounded in the pinned snapshot (AD-018).
- **FR-002** — Authoring is driven by a **SampleSet** (§11.1): cases, obligations, waivers,
  optional `includes`, confirmation. Required for success.
- **FR-003** — Model-facing operations: `get_metadata`, `search_examples`, `check_samples`,
  `verify` via library / `python -m`. Debug `validate` / `dry_run` are not blessing paths.

### Sample loop
- **FR-020** — `check_samples(samples: SampleSet) -> SampleCheck` (§11.1). Deterministic.
  Returns separate `coverage_complete` and `confirmed` (and `ok_for_verify`).
- **FR-021** — Persist SampleSet with `schema_version` `"1.0"` and all fields in §11.1.
- **FR-022** — Repo config `.transon-authoring.json` (§11.9). First **interactive** use without
  config asks layout; CI/non-interactive never asks.
- **FR-023** — Exits: **confirm** / **defer** / **abort** (§11.5). Sample conversation unbounded
  until one exit; no auto-confirm.
- **FR-024** — Present gaps with proposed waivers/assumptions; user accepts/rejects; persist
  structured waivers that clear obligation ids.
- **FR-025** — Skill proposes `coverage` obligations inside the SampleSet from NL (never as a
  separate free-form inference step inside the library).

### Verification
- **FR-004** — After SampleSet preflight, run engine `validate`.
- **FR-005** — Sandboxed dry-run per case; match via §11.4 (including optional `writes`).
- **FR-006** — Stages: `samples` → `validate` → `dry_run` → `match` only (no engine round-trip).
- **FR-007** — On verify failure, feed verbatim engine errors/diff; repair up to
  **`repair_attempts`** times. **Counting:** `repair_attempts` = max number of **repair** cycles
  after a failed `verify` (default **3**, allowed range **1..10** in `.transon-authoring.json`).
  Total candidates tried ≤ `1 + repair_attempts`. This bound is a **skill-loop** concern: the
  library/`python -m … verify` subcommand performs a **single** deterministic `verify` (NFR-002 /
  AC-018) and does **not** loop or accept `--repair-attempts`. The skill reads `repair_attempts`
  from ProjectConfig when deciding whether to draft another candidate.
- **FR-008** — On exhaustion / defer / abort / reject, return `AuthoringResult` failure (§11.5).
  Never return unverified JSON as success.

### Review
- **FR-030** — **Interactive template review before emission.** In interactive sessions, after
  `verify` yields `ok: true` and `assurance: "matched"`, the skill presents the matched template
  together with its Verdict to the user before emitting the final `AuthoringResult`. Exactly three
  exits:
  - **approve** — the user accepts; the skill emits the success envelope (`status: "matched"`)
    via the §7 `result` command, returning its stdout **verbatim** — never re-typed (FR-034 /
    AC-037).
  - **revise** — the user supplies feedback. NL-only feedback → draft a new candidate under the
    FR-001 grounding rules and re-run `verify`, with a **fresh `repair_attempts` budget** for
    that revision round (each round independently bounded per FR-007/NFR-006). Feedback that
    adds or changes expected input/output behavior → apply as SampleSet edits, which flip
    `confirmed` back via `fingerprint_mismatch` (AC-029) and send the flow through the FR-023
    sample loop (re-confirm) before any redraft.
  - **stop** — the user declines the template and ends the request: `status: "deferred"`
    (stop for now) or `status: "aborted"` (abandon), with **no template** (AC-012 semantics).

  Only matched candidates are ever presented for review — user approval is **additional** to,
  never a substitute for, the AD-004 verify gate. The review loop is unbounded until exactly one
  exit (same discipline as FR-023); never auto-approve; never treat silence as approval.
  Non-interactive/CI runs (AC-014 semantics; direct emission covered by AC-031) have no
  reviewer: the matched result is emitted directly — the §11.8 eval harness is unaffected.

### Grounding & corpus
- **FR-009** — Bundle pinned `get_editor_metadata()` snapshot as the structural grounding catalog.
- **FR-010** — **Authoritative example JSON** is `docs.examples` inside that snapshot (flat corpus:
  `{name, doc, template, data, result, tags}` per engine metadata_version 3.0 / editor
  metadata-contract §2.7). **Do not duplicate** those payloads from the editor codec corpus.
  Freshly authored **NL intents** live in `resources/nl-intents.json` (or `.jsonl`) as
  `{ "schema_version": "1.0", "intents": { "<example-name>": { "nl": string, "notes?": string } } }`
  keyed by stable example `name`. `search_examples` retrieves by NL/sidecar + tags/name over the
  snapshot examples. Provenance for the snapshot covers examples; sidecar has its own content hash
  in provenance. **No editor-only corpus entries in v1.** (Revises OQ-003.)
- **FR-011** — `sync-metadata` regenerates the metadata snapshot **and the Language Reference
  snapshot** (`resources/language-reference.json`, FR-036/AD-026) from the pinned engine and
  records provenance (snapshot + sidecar + reference sha256, the reference carrying its
  `reference_version`).
- **FR-036** — **Language Reference grounding artifact + `language` subcommand (AD-026).**
  `sync-metadata` additionally dumps `get_language_reference()` to `resources/language-reference.json`
  (canonical serialization, FR-011) and records its sha256 + `reference_version` in the snapshot
  provenance; `check_snapshot` drift-checks it against the pinned engine identically to the metadata
  snapshot (NFR-004). The module CLI exposes `python -m transon_authoring language [--section ID |
  --list-sections]` (§11.6), reading the **bundled resource, never importing the engine** (FR-009
  symmetry): no arguments → the full byte-exact `content`; `--list-sections` → the ordered
  `{id, title}` index; `--section ID` → that section's `content`; an unknown `id`, both selectors at
  once, or a bundled `reference_version` **major** above the supported major → §11.6 `schema-error`,
  exit 2 (the major guard is enforced at sync time too, so it cannot land silently). The reference is
  engine-derived grounding treated exactly like the `get_editor_metadata()` snapshot (AD-026).

### Distribution
- **FR-012** — Canonical `SKILL.md` + Claude/Cursor adapters.
- **FR-013** — **Deprecated.** MCP server removed from v1 (§3); ID retained so it is not reused.
- **FR-014** — `python -m transon_authoring` module entry with subcommands in §11.6.
- **FR-037** — **Plugin packaging + catalog reach (AD-009; normative home for OQ-007).** Two halves:
  **(a) Packaging (gating; A5):** a Claude Code plugin form of the shipped skill — a
  `plugin.json` manifest plus a self-hosted `marketplace.json` cataloguing it — laid out per
  §11.9. Marketplace hosts fetch the repo tree at the manifest's `source`, so the plugin's
  `SKILL.md` is a **generated artifact that IS committed**: the maintainer script
  `scripts/sync_plugin.py` regenerates it deterministically from the canonical root `SKILL.md`,
  and it is byte-identical to that file or the gate is red. Single source is preserved by enforced
  identity (NFR-007) — the canonical root file remains the only editable body, and the generated
  copy is never hand-edited. Packaging adds no console-script product (AD-006) and never
  runs `pip` (OQ-020); the grounding recipe stays the §11.6 module entry — **identical in every
  channel** (OQ-029). Runtime acquisition is documented, never encoded in the recipe: the plugin
  manifest's `description` MUST contain the literal string `pip install transon-authoring`. A
  channel-specific command wrapper (an ephemeral runner such as `uv run --with`) MUST NOT appear
  in the shipped body — it forks the recipe and makes offline behavior depend on a prunable cache
  (NFR-003). Verified by `check_install` (AC-040).
  **(b) External catalog submission (ongoing; non-gating):** listing the plugin in third-party
  agent-skill catalogs is outreach driven by real adoption. It **gates no milestone**, places no
  requirement on third-party infrastructure, and no claim of catalog presence or host
  discovery is ever made by CI.

### Installation
- **FR-015** — Install procedures (§11.9): Claude personal/project skill paths; Cursor
  project path (the Cursor personal scope is added by FR-038). Skill + engine versions and the snapshot hash are
  recorded install-time in `.install-manifest.json` (§11.9), never stamped into adapter files —
  the installed body stays byte-identical to the canonical `SKILL.md`.
- **FR-016** — Idempotent install; uninstall removes **only** files this installer created
  (manifest recorded at install time).
- **FR-038** — **Cursor personal scope (resolving OQ-028).** `install/cursor.py` supports
  `--scope personal` at the §11.9 destination `~/.cursor/skills/transon-authoring/`, with the
  same copy / manifest / idempotent-upgrade / uninstall-only-manifest-paths discipline as
  FR-015 and FR-016. The Cursor adapter drops its `personal scope` exclusion, so the two
  adapters reach **equal capability** rather than a documented exclusion (NFR-007). Verified by
  `check_install` (AC-041). Until this lands, four artifacts still assert the superseded
  project-only rule and are part of this slice: `adapters/cursor/adapter.json` (the exclusion),
  the shipped `adapters/cursor/README.md` (its "project scope only" sentence),
  `install/cursor.py` (module docstring + the scope-rejection path), and the tests pinning it —
  `tests/test_adapters.py`, `tests/test_install.py::test_fr015_cursor_personal_scope_exit2`,
  and the `tests/test_check_parity.py` exclusion fixture.

### Improvement
- **FR-017** — Eval-driven loop (AD-010/020/024). Measurement harness is the **real host**
  (Claude Agent SDK reference host pinned in `evals/runner.json`), feeding the OQ-016 scorer
  through the host→EpisodeResult adapter; the raw OQ-017 loop is non-gating offline smoke.
  Scoring, targets, baseline, and lint semantics: §11.8.
- **FR-018** — Capture failing cases into evals only after **privacy redaction** and **explicit
  consent** (§11.8). No raw secrets/PII committed. Two halves:
  **(a) Capture mechanism (gating; A2–A3):** the SKILL.md §3.5 redaction+consent rule plus the
  `check_evals --lint` enforcement that rejects any real-use fixture lacking `redacted: true` +
  a `consent` object (NFR-011, AC-025).
  **(b) Real-use corpus growth (ongoing; non-gating):** committing captured fixtures is driven by
  real usage (typically A4+) and **gates no milestone**. AC-025 is a conditional invariant
  enforced by half (a), satisfied vacuously while no real-use fixture is committed.
- **FR-029** — **Synthetic fixture generator + seed provenance + regen gate (AD-021).** A
  maintainer script (`scripts/` — not shipped in the package) mints EvalFixtures from snapshot
  `docs.examples` seeds: deterministic (no wall-clock/randomness), **3–6 cases per fixture**
  chosen by which §11.1 coverage kinds apply to the seed's input shape (happy path always;
  `list_empty`/`list_singleton`/`list_many` for array inputs; `optional_present`/`optional_absent`
  for optional keys; a `NO_CONTENT`-relevant case where the seed's rule can produce it and a
  `writes` case for writes-capable seeds — these last two are emitted as `kind: "custom"`
  obligations whose `description` names the behavior and whose `target` is omitted); **case 1 is
  always the example's own `data`/`result` pair re-executed through the pinned engine**;
  remaining cases are synthetic inputs run the same way. **Budget rule:** every case — including
  ones satisfying `kind: "custom"` obligations — counts toward the 6-case cap; one case MAY
  satisfy several obligations, and the generator prefers packing obligations into existing cases
  over adding cases. If distinct cases would still exceed six, applicable kinds are dropped
  (their obligations not emitted) in this fixed order until the budget fits:
  `list_singleton`, then `optional_present`, then `list_many` (order extended by OQ-026d — the
  OQ-026 custom kinds drop before all of these); happy path, `list_empty`,
  `optional_absent`, and the `NO_CONTENT`/`writes` custom kinds are never dropped (at most six
  of those can apply, so the cap is always satisfiable). If the applicable kinds yield fewer
  than three distinct cases (e.g. a scalar seed with no arrays, optional keys, `NO_CONTENT`
  relevance, or writes), the generator pads to the 3-case minimum with **value-variation
  cases**: the corpus `data` shape with each leaf scalar replaced by a deterministic alternate
  from a fixed per-JSON-type substitution table (position-indexed, no randomness), outputs
  obtained from the pinned engine as usual, each emitted as a `kind: "custom"` obligation whose
  `description` names it a value variation. Generated confirmations use
  `confirmed: true`, `confirmed_by: "ci"`, no `confirmed_at` (determinism), and the fingerprint
  from the OQ-015 acquisition path. Fixtures are committed under `evals/cases/` **without any
  seed-template field**; provenance is committed at `evals/seeds/<fixture-id>.json` as
  `{ "source_example": string, "template": <Transon JSON>, "generator": { "version": string,
  "notes"?: string } }`. `check_evals --lint` verifies, for every fixture with a seed file:
  (a) **snapshot provenance** — `source_example` names an entry in the pinned snapshot's
  `docs.examples`, the seed `template` JSON-equals that entry's `template`, and case 1's `input`
  JSON-equals that entry's `data` (so a seed cannot smuggle in a template that never originated
  from the corpus, per AD-021); and (b) **regeneration** — the fixture **regenerates
  bit-identically** (§11.1 SampleSet content subset and `content_fingerprint`) from its seed
  under the current pin (AC-030) — the same drift discipline as `check_snapshot`. v1 scope: a tagged
  subset (~25–30 seeds, one per tag family) with the remainder as follow-up waves; the
  should-refuse bucket stays hand-authored (no synthesized refuse intents in v1).
  **Applicability predicates (OQ-025):**
  (a) **optional keys** — a corpus `data` key is *optional* iff the seed template contains an
  `attr` node with a **literal string `name`** and a `default` member (the engine's defaulting
  accessor; `transon` SPECIFICATION §2.2/§4) and the key's **final pointer segment equals that
  literal name**. Candidate pointers are discovered by a deterministic pre-order walk of the
  corpus `data`; every matching pointer yields the `optional_present`/`optional_absent` pair
  (`target` = that pointer). `optional_present` is satisfiable by packing into the happy-path
  case (the corpus `data` carries the key); `optional_absent` inputs delete the key at that
  pointer.
  (b) **array scope** — arrays are discovered by the same deterministic pre-order walk of the
  corpus `data`; **every** array found receives the three `list_*` kinds (subject to the FR-029
  budget/drop order); pointers through array elements use index-`0` segments. The **document root**
  is excluded from array/optional candidacy — §11.1 obligation targets must start with `/`, and the
  whole-document pointer is rejected there — and a corpus array of length **0** yields only the
  `list_empty` kind (`list_singleton`/`list_many` derivations are impossible and their
  obligations are not emitted).
  (c) **`NO_CONTENT` relevance** — empirical, engine-decided; no static rule-shape analysis.
  The generator derives candidate inputs in a fixed order (each `optional_absent` derivation in
  pointer order, then each `list_empty` derivation in pointer order, then the value-variation
  candidates in position order) and executes them through the AD-017 sandbox; the `NO_CONTENT`
  custom obligation is emitted iff some candidate's top-level dry-run result encodes (§11.0
  `enc`) to `NoContentRef` — the first such candidate is the case, and per the FR-029 budget
  rule it MAY simultaneously satisfy the obligation it was derived from.
  (d) **includes population & eligibility** — `SampleSet.includes` is populated with every
  literal `{"$": "include", "name": <string>}` target found in the seed template, transitively
  through included templates, resolved from snapshot `docs.examples` by `name`; a literal
  include name that does not resolve is left absent (the corpus `result` may depend on the miss).
  After building case 1 the generator MUST assert the re-executed output JSON-equals the entry's
  `result`; a seed failing the assert is **ineligible**: the generator errors and the curator
  selects the tag family's next corpus-order candidate. A seed whose never-dropped obligations
  (happy path, `list_empty`, `optional_absent`, customs) alone cannot fit six cases is likewise
  ineligible, preserving FR-029's cap guarantee. A structurally derived obligation input
  (`optional_absent` or `list_*`) whose dry-run **errors** under the pinned engine makes the
  seed ineligible (hard error, curator moves on); a **value-variation** candidate whose dry-run
  errors is skipped in favor of the next deterministic index (padding continues; a seed that
  cannot reach the 3-case minimum is ineligible).
  (e) **writes-capable** — a seed is writes-capable iff its template, or any transitively
  included template, contains a `file` rule invocation; the `writes` custom case asserts the
  case's sandbox-captured `writes` map, not the top-level result alone.
  The value-variation substitution table and the case/obligation id-naming scheme remain
  implementation-defined but are **frozen by the AC-030 regen check** once the first seed lands.
  Seed provenance docs carry no `schema_version` and are validated structurally by
  `check_evals --lint`, not by the §11.0 ingress validator.
  **Wave-2 coverage extensions (OQ-026):**
  (a) **List length variation** — every array discovered by the OQ-025b pre-order walk of the
  corpus `data`, **plus the document root itself when the corpus `data` is a JSON array**, yields
  one `kind: "custom"` *length-variation* obligation (`target` omitted; the `description` names
  the array's pointer) whose case input is the corpus document with that array's **final element
  removed** — derived only when the corpus array has length ≥ 2. Each is emitted iff its dry-run
  under the pinned engine succeeds and is silently skipped otherwise; output comes from the
  pinned engine as usual; the FR-029 packing rule applies (an existing case whose input already
  JSON-equals the derivation satisfies the obligation instead of adding a case).
  (b) **Root key variations** — only when the corpus `data` document is a JSON object:
  (i) *key addition* — for **every `attr` node with a literal string `name`** (a `default`
  member is NOT required) whose name is not discoverable at any pointer of the OQ-025b walk
  (no visited pointer's final segment equals the name), one `kind: "custom"` obligation/case
  pair: the corpus `data` with that key added at the root, its value the **first entry** of the
  FR-029 per-JSON-type substitution-table row keyed by the JSON type of the attr's literal
  `default` when one is present — the first template-pre-order node of that name carrying a
  `default` decides — else the string entry (a non-literal `default`, or a literal whose JSON
  type has no table row, likewise takes the string entry);
  (ii) *key deletion* — for every root-level key not already covered by an `optional_absent`
  obligation, one `kind: "custom"` obligation/case pair: the corpus `data` with that key removed.
  Each root key variation is emitted iff its dry-run succeeds and is silently skipped otherwise —
  never seed ineligibility (contrast the OQ-025d structural hard-error rule); `target` is
  omitted and the `description` names the key; the FR-029 packing rule applies as in (a).
  (c) **`NO_CONTENT` probe count** — the OQ-025c candidate list examines only the **first two**
  value-variation candidates. This freezes the current behavior and supersedes the
  implementation-defined status of the OQ-025 tail **for the probe count only** (the
  substitution table and the id-naming scheme stay implementation-defined, frozen by AC-030).
  (d) **Budget and drop order** — the OQ-026 custom kinds count toward the FR-029 six-case cap,
  are droppable, and drop FIRST, extending FR-029's fixed drop order to: *key deletion*, then
  *key addition*, then *length variation*, then `list_singleton`, then `optional_present`, then
  `list_many`. They are excluded from the never-dropped satisfiability guarantee, which is
  unchanged. Deterministic emission order — after the OQ-025 structural kinds and the
  `NO_CONTENT`/`writes` customs, before value-variation padding: length variations in
  array-discovery order (document root first, then OQ-025b pre-order), then key deletions in
  root-key document order, then key additions in template pre-order discovery order.
- **FR-033** — **Real-world structural fixture pack + engine-freeze gate (AD-023).** Large constructed EvalFixtures (AD-023) are committed under `evals/cases/` as ordinary
  EvalFixtures (§11.8 schema; `redacted: false`; no `consent`; **no seed-template field in the
  fixture**). Their provenance is a **constructed seed** at `evals/seeds/<fixture-id>.json` with the
  shape `{ "origin": "real-world-pack", "source_ref": string, "template": <Transon JSON>,
  "notes"?: string }` — distinct from the FR-029 synthetic seed shape (no `source_example` /
  `generator`). `check_evals --lint` verifies, for every fixture with a constructed seed:
  (a) **engine-freeze** — re-executing the seed `template` through the pinned engine's AD-017
  sandbox on each fixture case's `input` yields output that JSON-equals (§11.4) that case's
  committed `output` (and the captured `writes` for a `writes`-declaring case); (b) **no leakage** —
  the fixture object carries no template/answer field outside its SampleSet `cases` (enforced by the
  closed `eval_fixture.json` schema, `additionalProperties: false`); (c) the SampleSet is
  `ok_for_verify` (FR-027). `source_ref` remains a **required non-empty provenance string** naming
  the documented API/source the payload was constructed from — the AD-023 "constructed, never
  captured" audit trail that backs `redacted: false` / no `consent`. `source_ref` is a provenance
  string, not a repo path (it is not resolved to a filesystem location). Real-world-pack SampleSets SHOULD
  additionally carry edge obligations (empty arrays, missing→`null`) — a review-time authoring
  expectation (§12 maker ≠ checker), not a lint-enforced one. **Enforcement boundary:** the
  engine-freeze gate binds every fixture that **has** a constructed seed, and a real-world-pack
  *matched* fixture MUST carry its seed (that is what engine-freezes it). The lint cannot distinguish
  a seedless matched fixture from an ordinary hand-authored one (`seed-matched-*`), so a matched
  fixture committed **without** a seed is treated as hand-authored — trusted via §12 review, not
  engine-frozen. A genuinely inexpressible transform is authored `expect: "refuse"` with no seed
  (AD-023); a matched real-world fixture that omits its seed is a review defect, never a lint-passed
  faked output. The pack counts in the §11.8 authoring/adversarial denominators and is expected to
  lower the measured authoring rate, corrected by improving `SKILL.md`, never by lowering the §11.8
  targets.
- **FR-034** — **Deterministic result emission (`result` command).** The module CLI (§11.6)
  provides `python -m transon_authoring result --template <path> --samples <path>`: it re-runs
  the §11.4 `verify` of the template against the SampleSet and emits the COMPLETE §11.5
  `AuthoringResult` envelope on stdout — **machine-generated, never hand-written.** A matched
  verdict emits the success envelope (`ok: true`, `status: "matched"`, the verified `template`,
  the verify `verdict`, and `repair_count` = the `--repair-count N` the skill passes — the §11.5
  repairs-consumed count from its §11.9 repair loop, `0` when omitted / a first-try success,
  `N >= 0`); a non-matched verdict emits the failure envelope (`ok: false`, no `template`, the
  verify-derived §11.5 `status` — `samples-rejected` when the SampleSet stage failed, otherwise
  `verify-failed` — with the `verdict` diagnostic); malformed ingress is the §11.6 `schema-error`
  CliError, as for every subcommand. `result` also machine-builds the template-less **refusal**
  envelope — `python -m transon_authoring result --refuse --status <STATUS> --explanation <TEXT>`
  emits `{schema_version, ok: false, status, explanation}` (exit 1) for the §11.5 statuses the
  skill emits DIRECTLY with no verify verdict: `aborted`, `deferred`, `need-samples`,
  `repair-exhausted`, and `profile-rejected` (the skill-level out-of-profile stop — §11.5: the
  skill stops WITHOUT calling verify when the request demands a non-default marker/transformer).
  A bad combination — a status outside that set, an empty `--explanation`, a stray
  `--template`/`--samples`, or `--repair-count` (a matched-success field) — is the §11.6
  `schema-error` CliError (exit 2). The CLI's OWN reserved-knob rejection
  (`--marker`/`--transformer`, AC-027) remains a `CliError` (exit 2), distinct from this
  skill-level `profile-rejected` AuthoringResult; `schema-error` is a CLI ingress error only.
  `SKILL.md` §2/§7 MUST emit `AuthoringResult` by running `result` / `result --refuse` and
  returning stdout verbatim — the authoring model never constructs the envelope itself.
  Determinism (NFR-002) and authority (NFR-001) are unchanged: `result` runs only the pinned
  engine through the AD-017 sandbox.

### Observability
- **FR-031** — **Self-reported session trace (AD-022).** `AuthoringResult`
  MAY carry `trace`: an ordered array of `TraceEntry` (§11.5) — one entry per protocol step the
  skill performed (config, grounding, sample-loop rounds, confirm, draft, each verify/repair
  cycle, review, result), each carrying the verbatim `python -m transon_authoring` invocation
  when one ran and a step-local outcome. The skill body instructs filling it in interactive
  sessions. Diagnostic only: schema-validated when present, ignored by scoring and gates,
  absence never invalidates a result, content never treated as ground truth (AD-022).
- **FR-032** — **Eval episode transcripts + failure attribution (AD-022).**
  Full `check_evals` runs persist one `EpisodeTranscript` per episode (shape in §11.8) under a
  run-artifact directory (`--transcripts-dir`); transcripts are **never committed** to the repo
  (repo hygiene + NFR-011) — the credential-holding dispatch workflow retains them as build
  artifacts. The gate report gains a `failure_modes` aggregation per bucket over runs that
  **failed their bucket's OQ-016 success rule** (plus reported-only `infra_error` runs), keyed
  by the final **scored** harness outcome — closed key set and precedence in §11.8 (harness
  outcome classes, `invalid_submission`, `reverify_failed`, or the submitted §11.5 `status`
  suffixed with `verdict.failed_stage`); the submitted status only ever labels a failure, it is
  never trusted as the score (AD-004). Scoring, targets, baseline, and lint semantics are
  unchanged by the presence or absence of transcripts.
- **FR-035** — **Run-observability artifacts + fixture selector (AD-025).**
  A `check_evals` run with `--transcripts-dir DIR` writes, in addition to the FR-032
  `EpisodeTranscript`s: (a) per episode, `DIR/messages/<fixture-id>.<run-index>.messages.json` — the
  **whole host message transcript** for that episode (ordered turns; each message's class/subtype
  and content blocks, with text/thinking/tool-result payloads length-bounded, §11.8 shape); and (b)
  `DIR/run_summary.json` — a telemetry roll-up over every episode (per-episode and totals: tokens,
  `cost_usd`, `steps` and `steps_by_category` = the tool-call histogram, `turns`, `outcome`,
  `error`; plus per-fixture normalized cost). `--only ID[,ID…]` restricts the provider run to the
  named fixtures (unknown id → config error, exit 2); the `--lint` corpus checks are unaffected and
  always cover the full committed set. All of this is **additive telemetry** — never scored, gating,
  or a determinism input (AD-022/AD-024/AD-025); a run without `--transcripts-dir` produces a
  byte-identical gate report (the AC-034 invariant), and the scored `EpisodeTranscript` files are
  unchanged. Artifacts are **never committed** — written to the git-ignored `evals/_runs/` by
  convention.

### Install CI
- **FR-019** — CI install checks (`check_install`; offline, deterministic):
  - **Claude Code:** structural install at the §11.9 path — installed `SKILL.md` byte-identical
    to the canonical root file, complete `.install-manifest.json`, idempotent re-install,
    uninstall removes only manifest paths — plus the OQ-010 discoverability-precondition lint
    (frontmatter parses; `name` equals the skill directory name; non-empty `description`).
    No headless listing exists (OQ-010): CI claims **install integrity + discoverability
    preconditions**, never “discoverability.”
  - **Cursor:** structural adapter install + `python -m transon_authoring metadata` runtime smoke.
    Do **not** claim Cursor “discovered/ingested” the skill (OQ-008).

### Additional
- **FR-026** — Library and module entry emit/accept only the JSON schemas in §11. Malformed JSON or
  unknown/`unsupported` `schema_version` on ingress → CLI exit **2** and a `schema-error` envelope
  (§11.6); skill-level `AuthoringResult.status === "schema-error"` (§11.5).
- **FR-027** — `verify` must call `check_samples` and require `ok_for_verify` (AD-019).
- **FR-028** — Enforce AD-017 resource limits (timeout, include depth) during dry-run.

---

## 8. Non-functional requirements

- **NFR-001 — Authority isolation.** Transon semantics only from AD-018 sources. Context7 only for
  host-tooling APIs.
- **NFR-002 — Deterministic gates.** Same SampleSet + template + pin ⇒ same `SampleCheck` /
  `Verdict`. Sandboxed I/O only.
- **NFR-003 — Offline after install.** No network required for verify/check/metadata once the
  pinned engine and package are installed (local package import and optional local worker
  subprocesses only).
- **NFR-004 — Snapshot drift vs pin.** `check_snapshot` fails if the bundled metadata snapshot
  **or the bundled Language Reference** (`resources/language-reference.json`, FR-036/AD-026) ≠ the
  pinned `transon==…` engine's `get_editor_metadata()` / `get_language_reference()`, or if either
  provenance hash / the reference's `reference_version` is stale or its major unsupported. Does not
  track unpinned newer releases (AD-007).
- **NFR-005 — Honest failure.** §11.5 statuses distinguishable from success.
- **NFR-006 — Bounded repair.** Per FR-007; sample loop unbounded until confirm/defer/abort.
  The interactive review loop (FR-030) is likewise unbounded until approve/stop; each revision
  round is a new candidate sequence with a fresh `repair_attempts` budget — the machine bound
  applies within a round, never across user-driven rounds.
- **NFR-007 — Adapter parity.** Claude/Cursor equal capability or documented exclusion.
- **NFR-008 — Versioned releases.** Record skill version, engine pin, snapshot hash.
- **NFR-009 — Install integrity.** FR-015/016/019; wording is **install integrity + runtime
  smoke**, not host “discoverability”; the Claude check adds only the OQ-010
  discoverability-precondition lint.
- **NFR-010 — Eval regression gate.** Targets (OQ-006): authoring ≥80%→95% ratchet; adversarial
  refuse-class =100%. Exact formula and runner: §11.8 / AD-020/AD-024. The pinned
  `runner.json.harness` (real host + version) is part of gate identity alongside the model pin;
  a harness change is an eval-policy commit that resets the baseline (§11.8).
- **NFR-011 — Privacy.** Real-use fixtures require redaction + consent before commit (FR-018).
- **NFR-012 — Shipped-skill self-sufficiency.** The shipped skill body (`SKILL.md`) and adapter
  files must be fully operable standalone: every behavior, schema field, status, and gate they rely
  on is stated inline; they contain **no references to repo files at all** — no links or paths into
  `docs/`, `harness/`, `scripts/`, `evals/`, `tests/`, `src/`, or repo-root `resources/`, and no
  `§`-section references — and they name **no external file authority**: Transon authority is
  reached only through `python -m transon_authoring` module recipes (the `metadata` / `examples` /
  `language` subcommands over the bundled snapshots), never by repo path or engine-repo path.
  Requirement-ID annotations for reviewer traceability are allowed **only inside markdown comments**
  (`<!-- … -->`), never in rendered/normative text. Enforced by `check_parity` (AC-032).

---

## 9. Acceptance criteria & use cases

### Acceptance criteria
- **AC-001** — Confirmed complete SampleSet for “flatten each order's line items with the customer
  name” → success `AuthoringResult` with `verdict.assurance === "matched"`.
- **AC-002** — Mode/variant intent → correct engine mode and `matched`.
- **AC-003** — Nonexistent operator/mode with `expect: "refuse"` → no invented name; failure
  envelope; adversarial gate 100%.
- **AC-004** — Without `ok_for_verify` SampleSet → no template; status ∈
  `need-samples`|`deferred`|`aborted`|`samples-rejected`.
- **AC-005** — Claude/Cursor adapters share one `SKILL.md` and same module recipe.
- **AC-006** — Pin/metadata change without sync → drift gate red until `sync-metadata`.
- **AC-007** — Clean install/uninstall idempotent on supported platforms (§11.9).
- **AC-008** — Eval rate below target or fixture regression → gate red (NFR-010).
- **AC-009** — CI: Cursor structural install + module smoke; Claude structural install + the
  OQ-010 frontmatter discoverability-precondition lint (no headless listing exists). No false
  “discoverability” claims.
- **AC-010** — Unmet obligations → gap codes; skill presents waivers; user accepts/rejects.
- **AC-011** — Conversational confirm (skill body, A3) writes `confirmation` and binds
  `content_fingerprint` via the OQ-015 acquisition path. The schema-testable half is AC-029
  (OQ-023 split).
- **AC-012** — Defer → `deferred`; abort → `aborted`; no template.
- **AC-013** — Success ⇒ `verdict.ok && assurance === "matched"` only.
- **AC-014** — CI fixtures with `confirmed` + `coverage_complete`; no layout prompt when config
  present or `--samples` given.
- **AC-015** — Dry-run: no real FS/network; writes captured; includes from map only.
- **AC-016** — Zero cases, malformed SampleSet, `coverage_complete=false`, or unconfirmed →
  `verify` fails at `samples` stage; never `matched`.
- **AC-017** — `coverage_complete` and `confirmed` are independent; both required for
  `ok_for_verify`.
- **AC-018** — Same inputs ⇒ identical `SampleCheck`/`Verdict` semantic content (NFR-002) under
  §11.4/§11.0 equality (object key order insignificant).
- **AC-019** — After `repair_attempts` failed repairs, status `repair-exhausted`; no further tries.
- **AC-020** — With network disabled post-install, `metadata`/`check-samples`/`verify` still work
  (NFR-003).
- **AC-021** — Module subcommands conform to §11.6 (exit codes, stdout JSON envelope).
- **AC-022** — `search_examples` returns snapshot `docs.examples` hits; NL sidecar enriches
  display only.
- **AC-023** — Root engine `NO_CONTENT` does not deep-equal JSON `null` (§11.4).
- **AC-024** — Captured `writes` matched when case declares `writes`; undeclared non-empty writes
  fail match.
- **AC-025** — Eval fixtures from real use lack secrets/PII; consent recorded (NFR-011).
  This is a **conditional invariant** enforced by the `check_evals --lint` capture mechanism
  (FR-018a): any committed fixture sourced from real use MUST carry `redacted: true` + a
  `consent` object, else the lint is red. It is **satisfied vacuously** while the corpus holds
  no real-use fixture — AC-025 does **not** require that a real-use fixture exist.
- **AC-026** — Failure envelopes always include `ok: false` and a §11.5 `status`.
- **AC-027** — `verify` always executes under the AD-017 default profile (base `Transformer`,
  marker `"$"`, built-in registries). Explicit profile-violating requests (reserved CLI flags /
  config fields for non-default marker or transformer class) are rejected with `ProfileError`
  before engine execution; skill-level stop uses `status: "profile-rejected"` (§11.5). A template
  JSON that merely *would* need another marker is **not** detectable as a profile violation — it
  runs under `"$"` and fails or succeeds via normal validate/dry_run/match.
- **AC-028** — Per-case dry-run exceeding 5s fails `dry_run` with timeout error.
- **AC-029** — Persisting a SampleSet (OQ-023 schema half, A2) per FR-021/§11.1 and
  setting `confirmation` with `confirmed: true`, a valid `confirmed_by`, and the
  `content_fingerprint` obtained via the OQ-015 acquisition path yields `check_samples` →
  `confirmed: true`; any subsequent edit to the hashed content subset flips it back via
  `fingerprint_mismatch`.
- **AC-030** — `check_evals --lint` is **red** (FR-029 regen gate) when any committed fixture
  with a matching `evals/seeds/<fixture-id>.json` does not regenerate bit-identically (SampleSet
  content subset and `content_fingerprint`) from its seed under the current pin; when a seed
  file has no matching fixture; or when a seed fails FR-029 snapshot provenance
  (`source_example` absent from the pinned `docs.examples`, seed `template` ≠ that entry's
  `template`, or case 1 `input` ≠ that entry's `data`). A repo whose seeds, fixtures, and
  snapshot agree lints **green**.
- **AC-031** — In an interactive session (FR-030 review loop) a matched
  template is presented with its Verdict before the success envelope is emitted; approve →
  `status: "matched"`; NL-feedback revise → a new draft cycle with a fresh FR-007 budget,
  re-verified and re-presented only when matched; sample-feedback revise → the SampleSet edit
  flips `confirmed` (`fingerprint_mismatch`) and the flow re-enters the FR-023 sample loop
  before redrafting; stop → `deferred`/`aborted` with no template; never auto-approve.
  Non-interactive runs emit `matched` without review.
- **AC-032** — `check_parity` is **red** (NFR-012 self-sufficiency lint) when `SKILL.md` or any
  adapter file references **any** unshipped repo path (`docs/`, `harness/`, `scripts/`, `evals/`,
  `tests/`, `src/`, repo-root `resources/`) — including the engine's `docs/SPECIFICATION.md`, which
  no longer has an exemption — contains a `§`-section reference, or carries requirement-ID citations
  outside markdown comments; a self-contained skill body and adapters, citing Transon authority only
  through `python -m transon_authoring` recipes (including the `language` subcommand), lint **green**.
- **AC-033** — An `AuthoringResult` carrying `trace` validates (FR-031)
  against the §11.5 `TraceEntry` shape and changes no scoring or verify behavior; a result
  without `trace` remains valid; a malformed `trace` fails schema validation like any other
  field.
- **AC-034** — A full `check_evals` run with `--transcripts-dir` (FR-032)
  writes one `EpisodeTranscript` per episode, each carrying the episode's ordered `tool_calls`
  and the `submit_result` payload verbatim (even when schema-invalid); the report's
  `failure_modes` equals a hand-computed histogram over the same **scored** episode results
  under the §11.8 key precedence; the same run without `--transcripts-dir` produces identical
  scoring and gate outcomes.
- **AC-035** — `check_evals --lint` is **red** (FR-033 / AD-023) when a
  committed fixture with a constructed seed (`evals/seeds/<id>.json`, `origin: "real-world-pack"`)
  does not engine-freeze — some case's committed `output` differs from re-executing the seed
  `template` through the pinned engine on that case's `input` (§11.4 equality) — or when the fixture
  object carries a template/answer field outside its SampleSet `cases` (leakage), or when a
  constructed-seed fixture's SampleSet is not `ok_for_verify`, or when the seed omits a non-empty
  `source_ref` provenance string. A real-world pack whose fixtures, seeds, and pinned engine
  agree lints **green**. `source_ref` must be a non-empty provenance string but is not
  resolved to a repo file (see FR-033). The gate binds only fixtures that carry a constructed seed; a matched
  fixture committed without one is treated as hand-authored (trusted via §12 review, not
  engine-frozen), and a genuinely inexpressible transform is authored `expect: "refuse"` with no seed
  (AD-023) — see FR-033's enforcement boundary.
- **AC-036** — **Real-host harness pin + adapter (OQ-027 / AD-024).**
  (a) `evals/runner.json` carries a `harness` block `{ kind, version }` that validates against the
  `eval_runner.json` schema (`kind ∈ {agent-sdk, claude-code}`), and `check_evals` selects the
  driver by `harness.kind`, raising a config error (exit 2) on an unimplemented kind — exactly as
  an unsupported `provider` does.
  (b) The host→EpisodeResult adapter is deterministic and total over host outcomes: a well-formed
  returned `AuthoringResult` → `outcome: "submitted"` with that object as `submitted` (a
  schema-invalid payload still maps to `submitted`, retained verbatim); host end-without-result →
  `no_submit`; pinned step/turn/token budget exceeded → `budget_exceeded`; host/transport/
  credential fault → `infra_error`. Feeding each adapter output through the unchanged
  `score_episode` (OQ-016) yields the same score the equivalent raw-loop EpisodeResult would — the
  scorer, targets, baseline, and lint semantics are byte-for-byte unchanged (AD-024). The adapter
  is unit-tested with a fake host (no live credentials), mirroring the OQ-017e fake-provider tests.
- **AC-037** — **`result` emits a schema-valid AuthoringResult matching the verify outcome;
  `SKILL.md` §7 mandates it (FR-034).** (a) `python -m transon_authoring result --template T
  --samples S` writes exactly one `AuthoringResult` (§11.5 schema) to stdout: when `verify(T, S)`
  returns `ok` with `assurance: "matched"`, the success envelope (`ok: true`, `status: "matched"`,
  `template` = T, `verdict` = the Verdict, `repair_count` = `--repair-count N` (default 0,
  `N >= 0`)), exit 0; otherwise a failure envelope (`ok: false`, no `template`,
  `status: "samples-rejected"` if the samples stage failed else `"verify-failed"`, carrying the
  `verdict`), exit 1; malformed ingress → §11.6 `schema-error` CliError, exit 2.
  `result --refuse --status <STATUS> --explanation <TEXT>` machine-builds the template-less
  refusal envelope `{schema_version, ok: false, status, explanation}` (exit 1) for
  `status ∈ {aborted, deferred, need-samples, repair-exhausted, profile-rejected}`; a status
  outside that set, an empty `--explanation`, a stray `--template`/`--samples`, `--repair-count`
  with `--refuse`, or a negative `--repair-count` → `schema-error` CliError, exit 2.
  (b) `SKILL.md` §2/§7 instruct the model to emit its `AuthoringResult` by running `result`
  (verify-derived) or `result --refuse` (refusal) and returning its stdout verbatim, and forbid
  hand-writing the envelope (skill-body test). A success envelope from `result` re-scores
  identically under the §11.8 OQ-016 scorer — the scorer's independent re-verify (AD-004) is
  unaffected.
- **AC-038** — **Run-observability artifacts are complete, correct, and inert (FR-035 /
  AD-025).** A run with `--transcripts-dir DIR` writes (a) one
  `DIR/messages/<id>.<run>.messages.json` per episode whose ordered `messages` reproduce the host
  turn stream (assistant text/thinking, each dispatched tool call and its result, across every
  turn), and (b) `DIR/run_summary.json` whose per-episode `tokens`, `cost_usd`, `steps`,
  `steps_by_category`, and `totals` equal a hand-computed roll-up over the same episodes, and whose
  per-fixture block divides those totals by that fixture's run count. `--only A,B` runs exactly the
  episodes for fixtures `A` and `B` (an unknown id exits 2). None of it changes the stdout gate
  report, scoring, targets, baseline, or lint: the same run without `--transcripts-dir` is
  byte-identical (extends AC-034), and the scored `EpisodeTranscript` files are unchanged.
- **AC-039** — **`language` serves the bundled Language Reference offline; drift and
  unsupported-major are gated (FR-036 / AD-026).** (a) `python -m transon_authoring language` prints
  `{schema_version, reference_version, engine_version, format, content}` whose `content` is
  byte-exact `get_language_reference().content` for the pinned engine, with no engine import and no
  network (NFR-003); `--list-sections` prints the ordered `{id, title}` index; `--section ID` prints
  that section; an unknown `id`, `--section` with `--list-sections`, or a bundled `reference_version`
  major above the supported major → §11.6 `schema-error` CliError, exit 2. (b) `check_snapshot` is
  **red** when `resources/language-reference.json` differs from the pinned engine's
  `get_language_reference()` canonical dump, when its provenance sha256/`reference_version` are
  stale, or when its `reference_version` major is unsupported — the same drift discipline as the
  metadata snapshot (NFR-004 / AC-006).
- **AC-040** — **Plugin packaging is structurally sound and single-source (FR-037a).** The plugin
  root is the **repo root** (§10), which is also the self-hosted marketplace repo. `check_install`
  is **green** when, at that root: (a) `.claude-plugin/plugin.json` parses and carries `name`,
  `description`, `version`, with `name` equal to the skill directory name `transon-authoring`,
  `version` equal to the `pyproject.toml` project version, and a `description` containing the
  literal string `pip install transon-authoring` (the OQ-029 runtime prerequisite); (b) `.claude-plugin/marketplace.json`
  parses and carries `name`, `owner`, and a `plugins` entry whose `name` matches (a) and whose
  `source` resolves to **the plugin root itself**, not merely to some path inside the repo, so
  that (a) and (c) are present relative to it; (c) `skills/transon-authoring/SKILL.md` exists and
  is **byte-identical** to the canonical root `SKILL.md`; (d) the OQ-010 frontmatter preconditions
  hold there (frontmatter parses; `name` equals the skill directory name; non-empty
  `description`). It is **red** when any of those files is missing or malformed, when the
  manifest names disagree with the skill directory, when `source` resolves anywhere other than the
  plugin root (a marketplace entry pointing at, say, `./docs` fetches no plugin manifest and no
  skill body), when `version` differs from the project
  version, or when the plugin `SKILL.md` differs from canonical by a single byte — the last case
  being the stale-regeneration failure. This extends the NFR-007 single-source surface beyond
  AC-005, which scans only the root `SKILL.md` and `adapters/**`. As with FR-019, the check claims
  **packaging integrity only** — never catalog listing or host discoverability.
- **AC-041** — **Cursor personal scope installs like every other scope (FR-038).**
  `check_install` exercises `cursor/personal` alongside the existing three combinations:
  installed at the §11.9 destination under an overridable home, installed `SKILL.md`
  byte-identical to canonical, complete `.install-manifest.json`, idempotent re-install,
  uninstall removing only manifest paths, and the OQ-010 frontmatter preconditions holding.
  Adapter-scope equality is AC-005's job, not this one. As with FR-019 / AC-009 this is a
  **structural** claim: it asserts the install destination and its integrity, never that Cursor
  discovered or activated the personal-scope skill — no credential-free headless listing exists
  (OQ-008).

### Use cases
- **UC-001** — Claude Code: samples → confirm → author → `verify` → user review (approve) →
  PR with template + SampleSet (FR-030).
- **UC-002** — Cursor same path.
- **UC-003** — CI batch with pre-confirmed SampleSets + committed config; non-interactive.
- **UC-004** — New engineer: `pip install transon-authoring`, installs adapters via `install/`,
  first-run layout prompt, authors successfully.

---

## 11. Normative contracts

### 11.0 Common types & serialization

```
JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue }

# Tagged values allowed ONLY in SampleCase.output and SampleCase.writes values:
NoContentRef = { "$transon_authoring": "NO_CONTENT" }
LitRef = { "$transon_authoring": "lit", "value": JsonValue }

AuthoringTag =
  | NoContentRef                          # means engine NO_CONTENT sentinel
  | LitRef                                # means the literal JsonValue in "value"
```

**Decoding (normative):** When reading an expected `output` / `writes` value:

1. If it is an object with exactly the keys required for a known tag:
   - `NoContentRef` → compare as engine `NO_CONTENT`;
   - `LitRef` → compare as deep-equal to `value` (use this when the literal data is itself
     `{"$transon_authoring": "NO_CONTENT"}` or any other tagged shape).
2. If it is an object containing `"$transon_authoring"` but is **not** a known tag → SampleSet
   schema failure, gap `schema_invalid` (message: unknown authoring tag).
3. Otherwise treat as ordinary `JsonValue` (including objects that happen to use other keys).

Tagged forms MUST NOT appear inside **templates** or **include** map templates (those are plain
Transon JSON; the library does not reject such keys at ingress — a template object using
`"$transon_authoring"` is ordinary data to the engine and is faithfully re-encoded on output).
AuthoringTags appear in exactly two places (OQ-012):

1. **SampleSet expectation values** (`output`, `writes` values), decoded per the rules above.
   **Decoding applies recursively at every nesting level** of an expected value.
2. **Library output positions** that echo raw engine values — the `dry-run` envelope `result` and
   `writes` values, and `DiffEntry.actual` — produced by the **engine-value encoding**
   (normative):

```
enc(v):
  engine NO_CONTENT sentinel                     -> NoContentRef
  array                                          -> [ enc(x) for x in v ]
  object containing the key "$transon_authoring" -> { "$transon_authoring": "lit",
                                                      "value": { k: enc(v[k]) … } }
  other object                                   -> { k: enc(v[k]) … }
  scalar                                         -> v
```

`enc` is injective: in encoded output a bare `NoContentRef` node always denotes the engine
sentinel, and a `LitRef` node always wraps literal data. If a raw engine value is not
JSON-representable (non-string object key, non-finite number, or a non-JSON Python type), the
affected dry-run case fails with a stable library-text `EngineError`
(`type: "TransformationError"`, `engine_type` omitted).

**Serialization (stdout):** UTF-8 JSON objects; `json.dumps` with `allow_nan=False`,
`separators=(",", ":")` optional for compactness in CI, pretty-print allowed for humans; **object
key order is not significant** for equality of results; parsers MUST reject duplicate object keys
and non-finite numbers (`NaN`/`Infinity`) at ingress.

**Schema versions:** documents carry `schema_version` string. v1 library understands `"1.0"` for
SampleSet, SampleCheck, Verdict, AuthoringResult, CliError, ProjectConfig, NlIntents, EvalRunner,
EvalFixture, EpisodeTranscript.

### 11.1 SampleSet & `check_samples`

```
CoverageObligation = {
  id: string,                       # stable within SampleSet
  kind: "happy_path" | "optional_present" | "optional_absent"
      | "list_empty" | "list_singleton" | "list_many" | "mode_choice" | "custom",
  target?: string,                  # JSON pointer (kinds that need structural checks) or
                                    # mode label string for mode_choice; see §11.1 table
  description: string,
  acceptance: "proposed" | "accepted" | "rejected"
}

Waiver = {
  id: string,
  clears_obligation_ids: string[],  # must reference coverage[].id
  reason: string,
  acceptance: "proposed" | "accepted" | "rejected"
}

SampleCase = {
  id: string,
  input: JsonValue,
  output: JsonValue | AuthoringTag,
  writes?: { [name: string]: JsonValue | AuthoringTag },
  satisfies: string[]               # obligation ids this case is claimed to satisfy
}

Confirmation = {
  confirmed: boolean,
  confirmed_by?: "user" | "ci",
  confirmed_at?: string,            # ISO-8601
  note?: string,
  content_fingerprint: string       # see fingerprint recipe below
}

SampleSet = {
  schema_version: "1.0",
  intent_nl?: string,
  coverage: CoverageObligation[],
  cases: SampleCase[],
  waivers: Waiver[],
  includes?: { [name: string]: JsonValue },  # include name → template JSON
  confirmation: Confirmation
}
```

**`content_fingerprint` (OQ-015):** lowercase hex SHA-256 of the UTF-8 encoding of
`json.dumps(subset, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`,
where `subset` is the object containing exactly those of the keys `schema_version`, `coverage`,
`waivers`, `cases`, `includes` that are **present** in the SampleSet document — an absent
`includes` is omitted, **not** hashed as `{}`; `intent_nl` and `confirmation` stay excluded.
Number formatting follows the parsed document: integers serialize with no fraction part, floats
by Python shortest-round-trip `repr` — consistent with §11.4 (`1` ≠ `1.0`); non-finite numbers
are already rejected at ingress (§11.0). Non-ASCII is emitted unescaped and hashed as UTF-8.
**Acquisition path:** agents/skill NEVER compute or reimplement the fingerprint. They obtain it
exclusively from `SampleCheck.content_fingerprint` by running `check-samples` on the
not-yet-confirmed SampleSet (the exit-1 `SampleCheck` still carries the recomputed fingerprint)
and copy that value into `confirmation.content_fingerprint` at confirmation time.
`transon_authoring.samples.content_fingerprint` is the single implementation. The
pre-confirmation placeholder is `""` (OQ-018a).

```
Gap = {
  code: GapCode,
  message: string,
  obligation_id?: string,
  case_id?: string
}

GapCode =
  | "schema_invalid"
  | "missing_happy_path"
  | "optional_present_unmet"
  | "optional_absent_unmet"
  | "list_empty_unmet"
  | "list_singleton_unmet"
  | "list_many_unmet"
  | "mode_choice_unmet"
  | "custom_unmet"
  | "obligation_not_accepted"
  | "waiver_invalid"
  | "unconfirmed"
  | "fingerprint_mismatch"
  | "no_cases"
  | "case_satisfies_unknown"
  | "duplicate_id"
  | "target_invalid"
  | "target_required"
```

```
SampleCheck = {
  schema_version: "1.0",
  coverage_complete: boolean,
  confirmed: boolean,
  ok_for_verify: boolean,
  gaps: Gap[],
  content_fingerprint: string
}
```

**`check_samples` algorithm (normative):**

1. Validate SampleSet against JSON Schema `1.0` (including AuthoringTag decoding rules in §11.0 —
   the §11.0 rule-2 unknown-tag check is procedural in this step, not part of the bundled JSON
   Schema, and reports as a `schema_invalid` **gap** on an otherwise schema-valid document).
   On failure: all flags false; gap `schema_invalid`.
2. Reject duplicate `coverage.id` / `cases.id` / `waivers.id` → `duplicate_id`.
3. Consider only obligations with `acceptance === "accepted"`. If any remain `proposed`,
   gap `obligation_not_accepted` and `coverage_complete=false`. Rejected obligations are ignored.
4. For each accepted obligation, it is **met** if an **accepted** waiver lists its `id` in
   `clears_obligation_ids` (waiver refs must be valid else `waiver_invalid`), **or** some case
   lists its `id` in `satisfies` **and** the kind-specific rule below holds. Unknown ids in
   `satisfies` → `case_satisfies_unknown` (does not meet any obligation).

   **JSON pointer `target`:** when a kind requires a pointer, `target` MUST be a JSON pointer
   string starting with `/` (RFC 6901). Missing/invalid pointer → `target_required` or
   `target_invalid`; obligation unmet. Resolve against that case’s `input` only.

   | kind | `target` | Structural check on a satisfying case’s `input` |
   |---|---|---|
   | `happy_path` | ignored | None beyond schema: case exists with `input` + `output`. A `satisfies` claim alone meets it. |
   | `optional_present` | required pointer | Pointer resolves to a value **and** the final key/index exists (not missing). `null` counts as present. |
   | `optional_absent` | required pointer | Pointer does **not** resolve (missing key/index). Present `null` does **not** count as absent. |
   | `list_empty` | required pointer | Pointer resolves to an array of length `0`. |
   | `list_singleton` | required pointer | Pointer resolves to an array of length `1`. |
   | `list_many` | required pointer | Pointer resolves to an array of length `≥ 2`. |
   | `mode_choice` | optional string (mode/variant label; **not** a pointer) | **No input structural check** — mode is a property of the template under draft, not of sample inputs. Met by an accepted `satisfies` claim on any case (user/CI attestation) or an accepted waiver. |
   | `custom` | optional | **No input structural check.** Met by `satisfies` claim or waiver; `description` is human-only. |

5. `coverage_complete = (no unmet accepted obligations) && (cases.length >= 1)`. If
   `cases.length === 0` → gap `no_cases`.
6. `confirmed = confirmation.confirmed === true
   && confirmation.content_fingerprint === recomputed_fingerprint
   && confirmed_by in {"user","ci"}`. Else gaps `unconfirmed` / `fingerprint_mismatch`.
7. `ok_for_verify = coverage_complete && confirmed && gaps has no schema/duplicate errors`.

All steps are deterministic given the SampleSet alone (NFR-002).

**Gap order (normative, OQ-013):** `gaps[]` is emitted in algorithm-step order: (1)
`schema_invalid`, sorted by (JSON instance path, message); (2) `duplicate_id`, in document order
`coverage` → `cases` → `waivers`; (3) obligation gaps in `coverage[]` document order — within one
obligation `obligation_not_accepted`, then `target_required` / `target_invalid`, then its
`*_unmet` code; (4) `waiver_invalid` in `waivers[]` order; (5) `case_satisfies_unknown` in
`cases[]` order; (6) `no_cases`; (7) `unconfirmed`, then `fingerprint_mismatch`.

**Edge semantics (OQ-018, normative):** (a) pre-confirmation `content_fingerprint` placeholder is
`""`; (b) `fingerprint_mismatch` is emitted alongside `unconfirmed` whenever the recorded
fingerprint differs from the recomputed one, even when `confirmed === false`; (c)
`confirmed: true` with missing/invalid `confirmed_by` → gap `unconfirmed` (message names
`confirmed_by`); (d) a waiver referencing a **rejected** obligation is not `waiver_invalid` — the
clear has no effect; (e) `proposed`/`rejected` waivers never clear and emit no gap; dangling
references are `waiver_invalid` regardless of the waiver's acceptance, and remaining valid refs
of an accepted waiver still clear; (f) `target` on `happy_path`/`mode_choice`/`custom` is
ignored, never validated; (g) an invalid `includes` template fails at the `dry_run` stage
(include-load error on the including case), never at `samples`.

**Skill responsibilities:** propose obligations (`acceptance: "proposed"`); propose cases/waivers;
present gaps; on user approval set obligations/waivers to `accepted` and set `confirmation` with
fresh fingerprint (obtained per the OQ-015 acquisition path). Library never sets
`confirmed: true`.

### 11.2 `verify`

```
EngineError = {
  type: "DefinitionError" | "TransformationError" | "ProfileError" | "TimeoutError" | "PreflightError",
                            # taxonomy bucket; non-engine exceptions leaked by the pinned
                            # engine during dry-run map to "TransformationError" (OQ-014)
  message: string,          # verbatim engine str(exc) when from engine; stable library text otherwise
  engine_type?: string,     # actual Python exception class name when an exception was caught
  path?: string,
  case_id?: string          # SampleCase.id when the error is attributable to one dry-run
                            # case; absent for validate/preflight/profile errors (OQ-011)
}

DiffEntry = {
  path: string,             # JSON pointer
  kind: "missing" | "extra" | "value_mismatch" | "type_mismatch" | "writes_mismatch",
  expected?: JsonValue | AuthoringTag | { "writes": { [name: string]: JsonValue | AuthoringTag } },
  actual?: JsonValue | AuthoringTag | { "writes": { [name: string]: JsonValue | AuthoringTag } },
  case_id: string           # SampleCase.id of the mismatching case (OQ-011)
}

Verdict = {
  schema_version: "1.0",
  ok: boolean,
  assurance?: "matched",
  failed_stage?: "samples" | "validate" | "dry_run" | "match",
  errors: EngineError[],
  gaps?: Gap[],             # when failed_stage === "samples"
  json?: JsonValue,         # candidate on success
  diff?: DiffEntry[],
  writes?: { [name: string]: JsonValue | AuthoringTag }
                            # reserved; never emitted by verify in v1 (OQ-011)
}
```

**Stages:**

1. **`samples`** — parse SampleSet; run `check_samples`; require `ok_for_verify`. Else
   `failed_stage: "samples"` (malformed handled as CLI schema-error per §11.6; semantic rejects
   include zero cases, incomplete coverage, unconfirmed, fingerprint mismatch).
2. **`validate`** — construct `Transformer(candidate)` **only** with AD-017 defaults; call
   `validate()`. There is no JSON-level “custom marker” detector. `ProfileError` occurs only when
   the caller requested a non-default profile via rejected API/CLI/config knobs (AC-027).
   An exception raised by construction/`validate()` that is **not** `DefinitionError` (the pinned
   engine leaks e.g. `TypeError` for `{"$": 5}`) is reported like the dry-run leak closure
   (OQ-014c) but in the “template invalid” class: `type: "DefinitionError"`, `engine_type` = the
   actual Python exception class name, `message` = verbatim `str(exc)`,
   `failed_stage: "validate"`.
3. **`dry_run`** — per case, execute in a **worker subprocess** (AD-017) with
   `transform(input, no_content=Transformer.NO_CONTENT)`, sandboxed delegates, timeout 5s,
   `max_include_depth=50`, `includes` from SampleSet only. Cases execute **sequentially in
   `cases[]` document order**; every case runs even after earlier failures; each failing case
   contributes exactly one `EngineError` carrying its `case_id`. If any case fails,
   `failed_stage: "dry_run"` and `match` is not entered; results of passing cases are not
   included in the `Verdict` (OQ-011).
4. **`match`** — §11.4 comparing outputs and writes (AuthoringTag decoding on expected values).
   All cases are compared; every `DiffEntry` carries `case_id`; entries are grouped by case in
   `cases[]` order. `match` produces no `EngineError`s — a match failure is expressed by `diff`
   alone (OQ-011).

`ok === true` iff all stages pass; then `assurance` is always `"matched"`.

**Array order (normative, OQ-013):** `errors[]`: one element for `validate` failures; one per
failing case in `cases[]` document order for `dry_run`. `diff[]`: cases in `cases[]` order;
within a case, output entries precede the writes entry.

**Diff construction (normative, OQ-013):** output diffs come from a recursive walk of
`dec(expected)` vs `enc(actual)` (§11.0): when both nodes are objects, visit the union of keys in
Unicode code-point ascending order — a key present only in expected emits `missing`, only in
actual emits `extra`, present in both recurses; when both are arrays, visit indices ascending —
pairwise recursion, an index beyond the shorter side emits `missing`/`extra`; when node types
differ (`NoContentRef` counts as its own type; `int` and `float` are distinct types), emit
`type_mismatch` with both snapshots; same-type scalars that differ emit `value_mismatch`. An
emitted entry terminates recursion at that node. `path` is the RFC 6901 JSON pointer within the
case’s **encoded** output document (§11.0; inside a `LitRef` wrapper the pointer traverses
`/value/…` segments of the encoded form) (root = `""`). Writes mismatches emit exactly one entry
per case:
`kind: "writes_mismatch"`, `path: ""`, `expected: {"writes": dec(case.writes ?? {})}`,
`actual: {"writes": {name: enc(content)…}}`.

### 11.3 Execution profile details (AD-017 / AD-015)

| Concern | v1 rule |
|---|---|
| Transformer | Always construct `transon.Transformer` (base class) |
| Marker | Always `"$"` |
| Registries | built-ins from pinned package only |
| `include` | loader resolves `SampleSet.includes[name]` only; miss → dry_run error |
| `file` | capture `(name, content)` in memory; never FS |
| Custom rules/ops/fns | out of scope |
| Include depth | engine `max_include_depth=50` |
| Recursion budget (R-32) | one core frame per template node (at the pinned engine); self-`include` reach ≥75 at CPython default recursion limit; over-depth → include `TransformationError`, never raw `RecursionError` |
| Timeout | 5s wall clock per case via **local worker subprocess** |
| Profile overrides | none; reserved knobs → `ProfileError` / exit 2 |
| Trust | trusted local agent/CI only |

### 11.4 Matching (§5 / FR-005)

Matching compares `dec(expected)` against `enc(actual)` over a common encoded domain (OQ-012):
`dec` maps `NoContentRef` to itself, `LitRef(value)` to `enc(value)` (literal data contains no
sentinel), recurses into plain arrays/objects, and rejects unknown tags per §11.0 rule 2. Rules
1–8 below are the observable consequences and remain normative.

**Deep equality** on JSON values (and `NoContentRef`):

1. **NO_CONTENT:** Decode expected via §11.0. If actual is the engine `NO_CONTENT` sentinel, it
   matches only expected `NoContentRef`. It does **not** match `null`, `false`, `0`, or `""`.
   Expected `LitRef` whose `value` is the NoContentRef object matches only that literal JSON
   object from the engine result (not the sentinel).
2. **null:** matches only `null`.
3. **boolean:** matches same boolean (not numbers).
4. **number:** type-sensitive: Python `int` matches only `int` with equal value; `float` only
   `float`. `1` ≠ `1.0`. Non-finite forbidden at parse.
5. **string:** exact code-point equality.
6. **array:** same length; pairwise equal in order.
7. **object:** same key set (order ignored); each key’s values equal.
8. **writes:** Let `W` be captured map (names → content; encode engine `NO_CONTENT` content as
   `NoContentRef` when returning writes). Decode expected `writes` values per §11.0. If case has
   `writes`: deep-equal `W` to decoded expectations (missing keys / extras → `writes_mismatch`).
   If case omits `writes`: require `W` empty; else fail match.

### 11.5 AuthoringResult & failure taxonomy

**Producer:** `AuthoringResult` is emitted by `python -m transon_authoring result` /
`result --refuse` (FR-034 / AC-037). The skill MUST run that command and return stdout
**verbatim** — it never hand-assembles the envelope. Other module subcommands still return
`SampleCheck` / `Verdict` / debug objects only (§11.6); the skill maps conversation exits
into the `--refuse` statuses when there is no verify verdict.

**Conformance:** JSON Schema at `src/transon_authoring/schemas/authoring_result.json` (and related
schemas). Verified by (1) unit tests that validate fixtures against the schema, and (2) authoring
eval fixtures that assert the skill’s final message/object conforms to `AuthoringResult`
(`expect` outcomes in §11.8).

```
AuthoringResult = {
  schema_version: "1.0",
  ok: boolean,
  status: "matched"
       | "need-samples" | "deferred" | "aborted"
       | "repair-exhausted" | "samples-rejected" | "verify-failed"
       | "schema-error" | "profile-rejected",
  explanation: string,
  template?: JsonValue,           # only when ok
  verdict?: Verdict,
  sample_check?: SampleCheck,
  gaps?: Gap[],
  last_candidate?: JsonValue,
  samples_path?: string,
  repair_count?: number,          # repairs consumed by the skill loop
  trace?: TraceEntry[]            # FR-031 self-reported step log; diagnostic only (AD-022)
}

TraceEntry = {
  seq: integer,                   # 1-based, contiguous, conversation order
  step: "config" | "ground" | "propose" | "present-gaps" | "confirm"
      | "draft" | "verify" | "repair" | "review" | "result",
  summary: string,                # one line: what happened at this step
  command?: string,               # verbatim `python -m transon_authoring …`, when one ran
  outcome?: string                # step-local outcome, e.g. "gaps: 2", "failed_stage: match"
}
```

`trace` is self-reported by the skill and **diagnostic only** (AD-022): consumers MUST NOT use
it for scoring, gating, or as evidence a step actually ran — the mechanical §11.8 transcript is
the authoritative step record in evals. Absence of `trace` never invalidates a result.

| status | When |
|---|---|
| `matched` | skill returns a template with `verdict.ok` and `assurance === "matched"` — in interactive sessions only after FR-030 user approval |
| `need-samples` | stopped with incomplete coverage / need more cases |
| `deferred` | user chose defer — in the sample loop or as an FR-030 review **stop** |
| `aborted` | user chose abort (sample loop or FR-030 review stop), **or the skill aborted after determining the request cannot be grounded in the pinned metadata (refusal — AC-003 / OQ-016b)** |
| `repair-exhausted` | skill consumed all `repair_attempts` without a matched verdict |
| `samples-rejected` | `check_samples` / verify `samples` stage failed on a schema-valid SampleSet |
| `verify-failed` | validate, dry_run, or match failed and the skill stopped without scheduling another repair |
| `schema-error` | malformed JSON or unsupported `schema_version` on ingress |
| `profile-rejected` | user/agent requested an out-of-profile execution option (non-default marker/class); skill stops without calling verify — or CLI rejected the reserved knob (AC-027) |

### 11.6 Module CLI (`python -m transon_authoring`)

**Global:** stdout = one JSON value (result envelope); stderr = human diagnostics only; never put
primary machine result on stderr.

| Subcommand | Inputs | stdout | exit |
|---|---|---|---|
| `metadata` | none | snapshot JSON (`JsonValue`) | 0 |
| `examples search <query>` | query string [`--limit N`, default 10 (OQ-022)] | `{ "schema_version": "1.0", "hits": [ example objects… ] }` | 0 |
| `language` | none **or** `--section ID` **or** `--list-sections` | Language Reference envelope: full `content`, one `section`, or the ordered `{id, title}` list (see language notes) | 0, or 2 on unknown `--section` / both selectors / unsupported major |
| `check-samples` | `--samples PATH` | `SampleCheck` on schema-valid input | 0 if `ok_for_verify` else 1 |
| `verify` | `--template PATH --samples PATH` | `Verdict` on schema-valid inputs | 0 if ok else 1 |
| `result` | `--template PATH --samples PATH [--repair-count N]` **or** `--refuse --status STATUS --explanation TEXT` | complete §11.5 `AuthoringResult`, machine-built (FR-034): verify-derived from the template (`repair_count = N`, default 0), or a template-less refusal (`STATUS ∈ {aborted, deferred, need-samples, repair-exhausted, profile-rejected}`) | 0 if matched, 1 on any failure/refusal envelope, 2 on bad args |
| `validate` | `--template PATH` | `{ "schema_version": "1.0", ok, errors }` debug | 0/1 |
| `dry-run` | `--template PATH --input PATH` [`--includes PATH`] | `{ "schema_version": "1.0", ok, result?, writes?, errors }` | 0/1 |
| `init-config` | `--layout sibling\|central\|custom` [`--pattern STR`] [`--samples-dir STR`] [`--repair-attempts N`] [`--non-interactive`] [`--force`] (flags aligned with §11.9) | `ProjectConfig` | 0/2 |

**Exit codes:** `0` success; `1` semantic check/verify failure on **schema-valid** inputs; `2`
usage / **schema** / config error; `3` internal unexpected error — emits the `CliError`
`internal-error` envelope on stdout (best effort, single write; traceback on stderr only)
(OQ-014).

**Envelope notes (OQ-014):** on `dry-run` success `result` and `writes` are both present (values
per §11.0 `enc`; `writes` may be `{}`); on failure both are omitted and `errors` is non-empty.
The `metadata` subcommand is exempt from `schema_version`: it emits the pinned snapshot document
verbatim (an engine document with its own `metadata_version`), not a library envelope.
`--includes PATH` is a bare JSON object of the `SampleSet.includes` shape (include name →
template JSON), no `schema_version` wrapper; any other JSON value → exit 2 `schema-error`.

The `language` subcommand serves the bundled Language Reference resource
(`resources/language-reference.json`, the canonical dump of `get_language_reference()`) and, like
`metadata`, **never imports the engine** (FR-009 symmetry, NFR-003). Unlike `metadata` it emits a
**library envelope** (carries `schema_version`): no arguments →
`{schema_version, reference_version, engine_version, format, content}` (full byte-exact reference);
`--list-sections` → `{schema_version, reference_version, engine_version, sections: [{id, title}, …]}`
in document order; `--section ID` →
`{schema_version, reference_version, engine_version, section: {id, title, heading_level, content}}`.
`--section` and `--list-sections` are mutually exclusive. An unknown section `id`, both selectors
together, or a bundled document whose `reference_version` **major** exceeds the supported major (1)
→ exit 2 `schema-error` CliError; the unsupported-major guard mirrors the engine's consumer contract
and is enforced at sync time.

**Schema vs semantic failures (FR-026):** If `--samples` or `--template` (or `--input` /
`--includes`) cannot be parsed as JSON, fails SampleSet/template schema validation, or carries an
unsupported `schema_version`:

- exit **`2`**
- stdout: a `CliError` with `status: "schema-error"` and `errors` of `type: "PreflightError"`
  (not a `SampleCheck` / `Verdict` body)

```
CliError = {
  schema_version: "1.0",
  ok: false,
  status: "schema-error" | "profile-rejected" | "internal-error",
  explanation: string,
  errors: EngineError[]      # may be empty for "internal-error"
}
```

`"internal-error"` is CLI-level only and is **not** an `AuthoringResult.status` value (OQ-014).

**`PreflightError` (OQ-014):** the `EngineError.type` for ingress failures detected before any
engine construction — JSON parse failure, duplicate object keys or non-finite numbers (§11.0
ingress), JSON-Schema validation failure, unsupported `schema_version`, unreadable input file.
Message is stable library text; `engine_type` omitted; it appears only in `CliError` envelopes
with `status: "schema-error"` (exit 2). An exception raised during dry-run execution that is
neither `DefinitionError` nor `TransformationError` (the pinned engine leaks e.g. `ValueError`
from `call int`, `ZeroDivisionError` from `expr /`) is reported as
`type: "TransformationError"` — the engine SPECIFICATION §2.4 class “template valid, data
incompatible” — with `engine_type` = the actual Python exception class name and `message` =
verbatim `str(exc)`.

**JSON Schema draft (OQ-014):** all documents under `src/transon_authoring/schemas/` are authored
in **draft 2020-12** (each declares `$schema`); runtime validation uses the `jsonschema` Python
package (runtime dependency `jsonschema>=4.18`); `schema_invalid` gap / `PreflightError`
messages derive from validator errors sorted by (JSON instance path, message) for determinism
(OQ-013). Because message text originates in `jsonschema`, NFR-002's byte-determinism for these
messages is scoped to a **fixed environment** (same `jsonschema` version); cross-version message
drift is possible and acceptable.

If the SampleSet is schema-valid but `ok_for_verify` is false, `check-samples` exits **`1`** with a
normal `SampleCheck`. If schema-valid but verify stages fail, `verify` exits **`1`** with a normal
`Verdict` (`failed_stage` set).

**Exit-2 boundary:** exit 2 covers failures of the **bundled JSON Schema** (plus
parse/version/read failures). The procedural §11.0 rule-2 unknown-AuthoringTag check is a
`schema_invalid` **gap** on a schema-valid document — reported in a normal `SampleCheck` /
`Verdict` with exit **1**, not a `CliError`.

**No repair loop on CLI:** `verify` runs once. There is **no** `--repair-attempts` flag (FR-007).

**Reserved profile knobs:** flags such as `--marker` / `--transformer` are rejected (exit **2**,
`CliError` with `status: "profile-rejected"` and a single `ProfileError`) even if present for
forward-compat parsing.

**Engine errors:** `EngineError.message` is the **exact** `str(exception)` from the engine when
applicable; wrapped in the JSON envelope above (never paraphrased in `message`).

### 11.7 Pin, drift, upgrade

- **Pin:** `transon==0.2.3`, expect `metadata_version == "3.0"`, `engine_version == "0.2.3"` in the
  metadata snapshot, and `reference_version == "1.0"`, `engine_version == "0.2.3"` in the Language
  Reference snapshot (FR-036/AD-026).
- **“Current metadata”** = the metadata snapshot **and Language Reference snapshot** produced from
  that pin by `sync-metadata`, bundled in-repo.
- **Drift:** bundle hash/content vs live `get_editor_metadata()` **and** `get_language_reference()`
  under the pinned install. Drift also covers the NL sidecar (OQ-021 consistency: sidecar keys ⊆
  snapshot example names; provenance sidecar hash current) and the Language Reference
  (`reference_version` major supported; provenance hash current).
- **Newer releases:** not red by drift alone. Upgrade path: bump pin → `sync-metadata` (resyncs
  metadata + Language Reference) → update NL sidecar → re-mint the FR-029 corpus and re-audit the
  refuse bucket (§11.8) → reset `evals/baseline.json` (§11.8) → PR. Optional scheduled notifier
  (OQ-004) opens that PR.

### 11.8 Evals (AD-020; resolves OQ-009)

`evals/runner.json`:
```
{
  "schema_version": "1.0",
  "provider": string,
  "model_id": string,
  "max_output_tokens": integer,
  "tool_budget": integer,
  "runs_per_fixture": 3,
  "pass_rule": "majority",
  "seed": number | null,
  "harness": {                        # AD-024 / OQ-027 — the
                                      # real host that runs the skill; a
                                      # gate-identity field beside the model pin
    "kind": "agent-sdk" | "claude-code",
    "version": string                 # pinned host version (e.g. the
                                      # claude-agent-sdk package version)
  }
}
```

Initial committed values become part of the gate identity; changing them is an explicit
eval-policy commit. The `harness` block is part of gate identity — a change to `harness.kind` or
`harness.version` is an eval-policy commit that resets `evals/baseline.json` in the same commit,
mirroring the gate-model swap below. v1 implements `kind: "agent-sdk"` as the reference host;
`"claude-code"` is admitted by the shape but unimplemented. The harness never sends sampling
parameters; determinism steering lives in the prompt.

**Gate model policy (AD-021 / OQ-024):** the primary NFR-010 gate model is a **small model**;
the normative pin is `provider: "anthropic"`, `model_id: "claude-haiku-4-5-20251001"` (the
harness still sends no sampling parameters). A commit that changes the gate `model_id` is an
eval-policy commit that **MUST in the same commit** reset `evals/baseline.json` to
`{ "schema_version": "1.0", "passing": [] }` — majority results under one model are not
transferable to another; the baseline repopulates via `check_evals --update-baseline` on the
next green run. `evals/targets.json` is **not** reset: `authoring_target` keeps its current
ratchet value, and an expected sub-target rate after a gate-model swap surfaces as a red gate
to fix by improving `SKILL.md`, never by lowering targets.

**Pin + corpus reset (AD-007 repin):** an engine repin is gate identity. The commit that lands a
new pin resyncs the metadata + Language Reference snapshots, re-mints the FR-029 synthetic corpus
(AC-030), re-executes the FR-033 constructed seeds (AC-035), and re-audits the refuse bucket against
the new engine (AD-023 probe discipline: now-satisfiable asks convert to `matched` fixtures with
seeds; the adversarial bucket is refilled with genuine gaps of the new engine and stays non-empty —
floor ≥ the pre-repin refuse count). In the **same commit** it resets `evals/baseline.json` to
`{ "schema_version": "1.0", "passing": [] }`, mirroring the gate-model swap; `evals/targets.json` is
never lowered. The baseline repopulates via `check_evals --update-baseline` on the next green
real-host run — the credentialed A5-entry dispatch, not a per-PR deterministic gate.

**EvalFixture** (`evals/cases/*.json`, schema_version `"1.0"`):
```
EvalFixture = {
  schema_version: "1.0",
  id: string,
  expect: "matched" | "refuse" | "matched_correction",
  intent_nl: string,
  samples?: SampleSet,              # required for expect matched / matched_correction when
                                    # the fixture supplies the SampleSet rather than driving the
                                    # full sample loop
  notes?: string,
  consent?: {                       # required when sourced from real use (NFR-011)
    by: string,
    at: string,                     # ISO-8601
    note: string
  },
  redacted: boolean                 # true if privacy redaction applied
}
```

- **Population:** all committed fixtures under `evals/cases/`.
- **Per-episode scoring (OQ-016):** mechanical scoring over the final `AuthoringResult`
  submitted by the skill under test:
  - **(a) matched-success** (for `expect: "matched"` **and** `expect: "matched_correction"`):
    the submitted `AuthoringResult` validates against the bundled schema, `ok === true`,
    `status === "matched"`, `template` present, `verdict.ok === true` with
    `assurance === "matched"`, **and** the harness independently re-runs
    `python -m transon_authoring verify --template <submitted> --samples <fixture SampleSet>`
    with exit 0 (the skill's claim is never trusted — AD-004).
  - **(b) refuse-success** (for `expect: "refuse"`): the submitted `AuthoringResult` validates
    against the schema, `ok === false`, `template` absent, and
    `status ∈ {need-samples, deferred, aborted, samples-rejected, verify-failed,
    repair-exhausted, profile-rejected}`. `status: "schema-error"` and a missing/invalid
    submission are scored as refuse-**failure** (not infra).
  - **(c) `matched_correction` is reporting-only:** scored with rule (a); its pass rate is
    reported as a separate *correction rate* but gates nothing; its fixtures still participate
    in the fixture-regression rule.
  - **(d) `infra_error`:** provider/API transport failure, harness fault, or provider-side
    refusal-to-serve — never model behavior; excluded from denominators with the 10% cap below.
- **Buckets / denominators:**
  - **should-succeed (authoring rate):** fixtures with `expect: "matched"`.
  - **should-refuse (adversarial 100%):** fixtures with `expect: "refuse"`.
  - **correction (reported, not in either rate above):** fixtures with
    `expect: "matched_correction"` — skill may map a nonexistent name to a real metadata
    operator/mode and still `matched`; tracked separately for diagnostics; neither raises nor
    lowers the refuse invariant.
- **Infra:** `infra_error` runs excluded from denominators but reported; if infra skips &gt; 10% of
  fixtures in a bucket → gate **fail** for that gate.
- **Authoring pass rate:** `#should-succeed fixtures with majority matched / #scored should-succeed`.
- **Adversarial refuse rate:** `#refuse fixtures with majority refuse-success / #scored refuse`
  must be **100%** (no invented operators/modes).
- **Ratchet:** let `T` be declared authoring target (starts 0.80). After release R with achieved
  rate `A`, set `T' = max(T, min(A, 0.95))` by explicit commit to `evals/targets.json`. Never
  decrease `T` silently.
- **`evals/targets.json` (OQ-016e):** `{ "schema_version": "1.0", "authoring_target": number,
  "adversarial_target": 1.0 }` — initial `authoring_target` 0.80; `adversarial_target` constant.
- **Fixture regression:** any previously passing captured fixture (any expect bucket) that fails
  majority → gate fail regardless of aggregate rate. The normative record of "previously
  passing" is the committed `evals/baseline.json` (OQ-016f):
  `{ "schema_version": "1.0", "passing": [fixture ids…] }`; ids are added only by explicit
  `check_evals --update-baseline` commits.
- **Harness (OQ-017 / AD-024 / OQ-027):** the gate runs the skill in the **real
  host agent harness** it ships into — the reference host is the **Claude Agent SDK**, pinned by
  `runner.json.harness = { kind: "agent-sdk", version }`. The driver (`scripts/host_harness.py`,
  behind the optional extra `transon-authoring[evals]`) installs `SKILL.md` as shipped into the
  host's skill path and lets the host **auto-activate** it under its own system prompt (OQ-027a
  faithful engagement — no injection, no preamble), runs one
  episode per `runs_per_fixture` with the host's rich tool suite over a per-episode ephemeral
  workspace (fixture `intent_nl` as the prompt, the fixture's `samples.json` when supplied).
  The **shipped `SKILL.md` MUST carry a discoverable frontmatter `description`** (install-integrity /
  discoverability, NFR-009 / OQ-010) — without it the host cannot recognise it as a skill; a fixture
  `intent_nl` that fails to trigger the skill is a true signal about the shipped description or the
  fixture's realism, fixed in the skill or corpus — never by a harness knob. Each
  episode is driven as a **stateful session** so the driver can answer the shipped skill's §6
  interactive review (FR-030): when the first turn presents the matched template for approval and
  emits no `AuthoringResult`, the driver supplies the review's **approve** exit ONCE — as the
  reviewing user — and reads the follow-up turn, so a single autonomous eval measures the real
  present→approve→emit path *without altering the shipped skill*. The follow-up is bounded to one
  approval and never overrides a genuine authoring or refusal envelope, nor an infra/budget fault
  (`host_harness._needs_review_followup`, unit-tested). The driver then
  maps the host's returned `AuthoringResult` + execution status to the §11.8 EpisodeResult via the
  **deterministic host→EpisodeResult adapter** (OQ-027e status→outcome mapping). `check_evals`
  selects the driver by `harness.kind` (config error, exit 2, on an unimplemented kind). The
  isolation contract (OQ-027f) — ephemeral workspace, no credentials in the tool sandbox, egress
  denied, artifact controls — is a **blocker before the live run** and is enforced by the
  dispatch-workflow environment plus the driver. The retired **raw 3-tool `messages.create` loop**
  (`scripts/eval_harness.py`: `SKILL.md` verbatim + fixed preamble; tools `write_file` /
  `transon_authoring` / `submit_result`; per-episode temp workspace; injected provider) is
  **demoted to a non-gating offline smoke fixture** (OQ-027d) — retained and unit-tested with a
  fake provider, never the gate. Full runs live in a credential-holding dispatch workflow; per-PR
  CI runs `check_evals --lint` + the fake-host / fake-provider unit tests.
- **Transcripts & attribution (FR-032 / AD-022):** full runs write one
  `EpisodeTranscript` JSON per episode to `--transcripts-dir`; **never committed** to the repo
  (repo hygiene + NFR-011) — the dispatch workflow retains the directory as a build artifact:
  ```
  EpisodeTranscript = {
    schema_version: "1.0",
    fixture_id: string,
    run_index: integer,             # 0-based within runs_per_fixture
    model_id: string,
    outcome: "submitted" | "no_submit" | "budget_exceeded" | "infra_error",
                                    # the harness episode outcome: submit_result called /
                                    # episode ended without submit (OQ-017c) / tool budget
                                    # exceeded (OQ-017c) / provider or infra failure (§11.8)
    tool_calls: [ { seq: integer, name: string, input: JsonValue, result: JsonValue } ],
    submitted: JsonValue | null,    # the submit_result payload VERBATIM — possibly
                                    # schema-invalid (retained so OQ-016(b) failures
                                    # stay diagnosable)
    error: string | null
  }
  ```
  Under the real-host harness the four `outcome` values are produced by the host→EpisodeResult
  adapter; `tool_calls` carries the host's reported step record when it exposes one and is
  otherwise `[]` (additive telemetry — transcripts change no scoring).
  The gate report gains `failure_modes`: per bucket, a histogram over the runs that **failed
  that bucket's OQ-016 success rule**, plus reported-only `infra_error` runs. Each failed run
  is keyed by its final **scored** outcome, first match in this precedence wins:
  `infra_error` | `no_submit` | `budget_exceeded` | `invalid_submission` (payload fails the
  bundled AuthoringResult schema — OQ-016(b)) | `reverify_failed` (a submitted `matched` whose
  OQ-016(a) independent re-verify failed — the claim is never trusted, AD-004) | otherwise the
  submitted §11.5 `status`, suffixed with `verdict.failed_stage` when present (e.g.
  `"verify-failed/match"`; in the refuse bucket a key of `"matched"` means an invented success
  where refusal was expected). The submitted status only labels a failure — it is never the
  score itself. Derived mechanically from scored episode results;
  transcripts and `failure_modes` change no scoring, target, baseline, or lint semantics —
  a run without `--transcripts-dir` scores identically.
  **Privacy & retention:** an episode transcript contains only (a) fixture
  content already committed under `evals/cases/` — real-use fixtures having passed the NFR-011
  redaction + consent lint before commit, synthetic fixtures (AD-021) containing no real-use
  data by construction — and (b) library envelopes and gate-model output over that content,
  so no new real-use data can enter a transcript. Access and retention follow the dispatch
  workflow's build-artifact policy (repo CI access; default artifact expiry deletes them);
  transcripts MUST NOT be re-committed to the repo. Capturing a **real-use** failing
  conversation remains governed by FR-018/NFR-011 — the transcript mechanism records eval
  episodes only, never interactive sessions.
- **Whole transcript + telemetry roll-up (FR-035 / AD-025):** the same
  `--transcripts-dir DIR` additionally persists, per episode, the **whole host message transcript**
  and, per run, a **`run_summary.json`** — both additive, non-gating, never committed (a run without
  the directory scores identically). The recommended, git-ignored location is `evals/_runs/`.
  ```
  # DIR/messages/<fixture-id>.<run-index>.messages.json
  EpisodeMessages = {
    schema_version: "1.0",
    fixture_id: string, run_index: integer, model_id: string,
    messages: [ { type: string,             # host message class (system/assistant/user/result)
                  subtype: string | null,   # e.g. init / success / error_max_turns
                  content: [ Block, … ] | string | null } ],   # ordered across every turn
  }
  Block = { type: "text"|"thinking"|"tool_use"|"tool_result"|…,   # verbatim block kind
            text?: string, thinking?: string,                     # bounded
            name?: string, input?: JsonValue,                     # tool_use
            tool_use_id?: string, result?: JsonValue }            # tool_result (bounded)

  # DIR/run_summary.json
  RunSummary = {
    schema_version: "1.0", model_id: string, harness: { kind, version },
    runs_per_fixture: integer,
    episodes: [ { fixture_id, run_index, outcome, error,
                  tokens: { input, output, cache_read, cache_creation, turns },
                  cost_usd: number | null,
                  steps: integer, steps_by_category: { toolName: count, … } } ],
    totals: { episodes, tokens: {…}, cost_usd, steps, steps_by_category: {…},
              outcomes: { submitted, no_submit, budget_exceeded, infra_error },
              errors: integer },
    by_fixture: { <fixture-id>: { runs, fixture_bytes,
                                  cost_usd_total, cost_usd_mean,
                                  tokens_mean: {…}, steps_mean,
                                  cache_read_ratio, cost_usd_per_kb } },
  }
  ```
  Text/thinking/tool-result payloads are length-bounded (diagnosability without unbounded blow-up).
  `--only ID[,…]` scopes the provider run to named fixtures (a cost/diagnostic probe; unknown id →
  exit 2) while the lint still covers the full committed corpus. These artifacts change no scoring,
  target, baseline, or lint semantics — exactly as the FR-032 transcripts.
- **Privacy (NFR-011):** before committing a real-use failure: strip secrets/PII; set
  `redacted: true`; record `consent`; default deny.
- **Synthetic fixtures (AD-021 / FR-029):** fixtures minted from snapshot `docs.examples` are
  ordinary EvalFixtures — same schema, same buckets, same scoring; they carry no `consent`
  (nothing real-use) and `redacted: false`. Their SampleSet outputs come only from the pinned
  engine under the AD-017 profile; the seed template lives at `evals/seeds/<fixture-id>.json`
  (shape in FR-029) and is **never** part of the fixture object, the harness prompt, or the
  episode workspace. `check_evals --lint` enforces seed↔fixture bit-identical regeneration
  (AC-030). Synthetic `intent_nl` is LLM-drafted, human-accepted before commit (AD-021).
- **Real-world structural fixtures (AD-023 / FR-033):** a third fixture class —
  large **constructed** EvalFixtures matched to real API schemas (AWS/Stripe/GitHub/JOLT/JMESPath),
  carrying no real-use data (`redacted: false`, no `consent`; the FR-018 / NFR-011 real-use path is
  unaffected). Same schema, buckets, and scoring as every other fixture. Their case `output`s are
  **engine-frozen** — the pinned engine's actual output for an author-verified template — and their
  provenance is a **constructed seed** (`evals/seeds/`, FR-033 shape) that is never in the fixture
  object or the harness prompt (leakage rule, AD-021); `check_evals --lint` enforces the freeze plus
  no-leakage (AC-035). Intents needing an engine-absent capability are `expect: "refuse"` fixtures
  (AD-023), not unsatisfiable matched ones.

### 11.9 Project config & installation

**`.transon-authoring.json`:**
```
ProjectConfig = {
  schema_version: "1.0",
  layout: "sibling" | "central" | "custom",
  # sibling: "<templateStem>.samples.json" beside template
  # central: "transon-samples/<stem>.samples.json"
  # custom: pattern with placeholders
  pattern?: string,           # required iff layout=custom
  repair_attempts: number,    # default 3, range 1..10
  samples_dir?: string        # for central; default "transon-samples"
}
```

**Placeholders (custom only):** `{stem}` (template file stem), `{dir}` (template directory).
Forbidden: `{..}`, absolute FS escapes, env interpolation. After expansion, path MUST resolve
inside the repo root (no `..` escape).

**Collisions:** `init-config` refuses to overwrite unless `--force`. Sample file write refuses
overwrite unless user/CI confirms or `--force`.

**Write location:** `init-config` writes `.transon-authoring.json` to the
**current working directory** (the skill runs `init-config` at the repo root) and emits the
`ProjectConfig` document on stdout. Interactive prompting (layout only) happens only when stdin
is a TTY and `--non-interactive` is absent; `check-samples`/`verify` never read config and never
prompt.

**Non-interactive:** `--non-interactive` requires all fields on CLI or existing config; else exit 2.

**Install destinations (POSIX; Windows uses equivalent user profile paths):**

| Tool | Project scope | Personal scope |
|---|---|---|
| Claude Code | `<repo>/.claude/skills/transon-authoring/` | `~/.claude/skills/transon-authoring/` |
| Cursor | `<repo>/.cursor/skills/transon-authoring/` | `~/.cursor/skills/transon-authoring/` (FR-038) |

`<repo>` in the table is the **target project root**: installers accept a target root distinct
from the source checkout/archive they run from (default: the checkout root itself), so a project
other than the checkout can receive the skill files.

**Plugin form (FR-037a).** The plugin channel reuses the same canonical body. **This repo is both
the plugin root and the self-hosted marketplace repo**; the layout is relative to the repo root:

```
.claude-plugin/plugin.json          # name, description, version
.claude-plugin/marketplace.json     # name, owner, plugins[] — lists this plugin by name + source
skills/transon-authoring/SKILL.md   # generated from the canonical root SKILL.md; committed
```

Marketplace hosts fetch the tree at the entry's `source`, so the plugin `SKILL.md` MUST be
committed — a generated artifact kept byte-identical to the canonical root file by AC-040, never
edited directly. The maintainer script `scripts/sync_plugin.py` regenerates it (a `sync_metadata`
sibling: it writes a repo artifact and is not shipped in the package); editing the canonical root
file without regenerating turns the gate red. `install/` is unaffected — it copies into a target
project's skill directory and never writes this tree. The plugin `name` MUST equal the skill
directory name `transon-authoring`, and
`plugin.json.version` MUST equal the `pyproject.toml` project version.

This tree is a **repo artifact, not an install destination**: it is outside the FR-015/FR-016
`.install-manifest.json` regime, which governs only files copied into a target project's skill
directory. Users add the marketplace with the host's own command and install by plugin name; no
third-party catalog is required.

**Runtime acquisition (plugin channel).** The grounding recipe is byte-for-byte the native one —
`python -m transon_authoring …` — so the plugin adds no channel-specific command wrapper. The
runtime is acquired separately, exactly as in the native channel: `plugin.json.description` MUST
contain the literal string `pip install transon-authoring` (AC-040). Packaging never runs `pip`
(OQ-020) and declares no console script (AD-006).

Strategy: **copy** adapter files (not symlink) for hermeticity. Record
`.install-manifest.json` listing owned paths + versions. **Upgrade:** re-run install (idempotent
replace of owned files). **Uninstall:** delete only manifest paths.

Supported platforms for install scripts: macOS and Linux (Windows best-effort; not a v1 gate).

**Runtime package distribution (OQ-020):** `install/claude.py` / `install/cursor.py` copy skill
files only and never run `pip`. The runtime (`python -m transon_authoring`) is installed
separately from public PyPI (`pip install transon-authoring`, which pins `transon==0.2.3`
transitively). If `transon_authoring` is not importable at skill-file install time, the installer
prints a stderr hint and still exits 0 (structural install is valid without the runtime).

---

## 12. Governance

- **The contract spans `SPEC.md`, `ARCHITECTURE.md`, and `ROADMAP.md`.** Section numbers are
  global and unique across all three; every rule in this section applies to all three, and "the
  SPEC" below means the contract as a whole.
- SPEC-first; ID lock at A0 start.
- Maker ≠ checker on library/snapshot/adapters/evals.
- Single-source adapters (NFR-007).
- Measurement before skill body (AD-011).
- Traceability matrix (§17) updated in the same change as FR/NFR/AC edits after A0.
- **Normative text is current-state only.** A revision replaces the requirement/decision text in
  place (ID kept). Do not stack dated revision parentheticals or retain superseded designs beside
  the new text — history lives in git. Deprecated IDs remain as one-line stubs. Resolved OQs keep
  a one/two-line decision; superseded narratives are deleted. Session status goes to
  `docs/current-state.md`, not into the contract docs or traceability cells.

---

## 13. Testing & gates

| Gate | Enforces |
|---|---|
| Unit tests (library) | §11 schemas, match, sandbox, preflight |
| `check_snapshot` | NFR-004 / AD-007 — metadata snapshot + Language Reference drift (FR-036) |
| `check_evals` | NFR-010 / AD-020; its `--lint` mode carries the NFR-011 fixture lint (AC-025), the FR-029 seed-regen check (AC-030), and the FR-033 constructed real-world fixture engine-freeze + no-leakage check (AC-035); full runs emit FR-032 transcripts + `failure_modes` plus the FR-035 whole-transcript / `run_summary.json` telemetry (non-gating report artifacts, AC-034 / AC-038) |
| `check_parity` | NFR-007 / AC-005; NFR-012 / AC-032 (shipped self-sufficiency lint) |
| `check_install` | NFR-009 / FR-019 (integrity + smoke); FR-037a / AC-040 (plugin packaging); FR-038 / AC-041 (Cursor personal scope) |
| Authoring evals | should-succeed → matched |
| Adversarial evals | expect refuse =100% |
| Sandbox evals | AC-015/023/024/028 |

---

## 17. Traceability matrix

Every **active** FR/NFR maps to ≥1 AC, milestone, and gate/test category. FR-013 is deprecated and
excluded from active coverage.

| ID | AC(s) | Milestone | Gate / test category |
|---|---|---|---|
| FR-001 | AC-001, AC-002 | A3 | authoring evals |
| FR-002 | AC-001, AC-014, AC-017 | A2–A3 | sample-loop + unit |
| FR-003 | AC-021 | A1 | CLI unit |
| FR-004 | AC-001, AC-018 | A1 | verify unit |
| FR-005 | AC-015, AC-023, AC-024 | A1 | sandbox + match unit |
| FR-006 | AC-013, AC-016 | A1 | verify unit |
| FR-007 | AC-019 | A3 | repair unit + evals |
| FR-008 | AC-004, AC-012, AC-026 | A3 | failure envelope unit |
| FR-009 | AC-006, AC-022 | A0 | snapshot gate |
| FR-010 | AC-022 | A0 | examples unit |
| FR-011 | AC-006 | A0 | sync + drift |
| FR-012 | AC-005 | A4 | parity |
| FR-014 | AC-021 | A1 | CLI unit |
| FR-015 | AC-007, AC-009 | A4 | check_install |
| FR-016 | AC-007 | A4 | check_install |
| FR-017 | AC-008, AC-036 | A2–A3 | check_evals + real-host harness (AD-024) |
| FR-018 | AC-008, AC-025 | A2–A3 | evals + privacy review |
| FR-019 | AC-009 | A4 | check_install |
| FR-020 | AC-010, AC-017, AC-018 | A2 | check_samples unit |
| FR-021 | AC-029, AC-017 | A2 | schema unit |
| FR-022 | AC-014 | A2 | config unit |
| FR-023 | AC-012 | A3 | sample-loop evals |
| FR-024 | AC-010, AC-011 | A3 | sample-loop evals |
| FR-025 | AC-010, AC-017 | A3 | sample-loop evals |
| FR-026 | AC-021, AC-026 | A1 | schema unit + CLI exit 2 |
| FR-027 | AC-016 | A1 | verify preflight |
| FR-028 | AC-027, AC-028 | A1 | profile-knob reject + timeout worker unit |
| FR-029 | AC-030 | A3 | check_evals lint + generator unit |
| FR-030 | AC-031, AC-012 | A3 | skill-body unit + UC-001 walkthrough |
| FR-031 | AC-033 | A3 | schema unit + skill-body unit |
| FR-032 | AC-034 | A3 | check_evals unit |
| FR-033 | AC-035 | A3+ (improvement) | check_evals lint |
| FR-034 | AC-037 | A3+ (improvement) | CLI unit + skill-body |
| FR-035 | AC-038 | A3+ (improvement) | check_evals + host_harness unit |
| FR-036 | AC-039 | A5 | CLI unit + snapshot gate |
| FR-037 | AC-040 | A5 | check_install |
| FR-038 | AC-041 | A5 | check_install |
| NFR-001 | AC-003, AC-022 | A0+ | authority tests / evals |
| NFR-002 | AC-018 | A1 | determinism unit |
| NFR-003 | AC-020 | A1 | offline CI job |
| NFR-004 | AC-006 | A0 | check_snapshot |
| NFR-005 | AC-026 | A1 | envelope unit |
| NFR-006 | AC-019 | A3 | repair unit |
| NFR-007 | AC-005 | A4 | check_parity |
| NFR-008 | AC-006, AC-007 | A4–A5 | release checklist |
| NFR-009 | AC-007, AC-009 | A4 | check_install |
| NFR-010 | AC-008, AC-036 | A2–A3 | check_evals |
| NFR-011 | AC-025 | A2 | fixture lint |
| NFR-012 | AC-032 | A4 | check_parity |
