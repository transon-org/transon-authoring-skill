# SPEC — Transon Authoring Skill (`transon-authoring`)

A standalone, distributable capability that lets **coding agents and CI** in the org author
correct, engine-valid **Transon** JSON — grounded in engine-authoritative metadata, backed by a
**user-confirmed SampleSet**, and blessed by the engine at **`matched`** assurance before any
template is returned. It lives in its own repository, **beside** (not inside) the
`transon-blockly` editor and the `transon` engine.

> **Status:** Draft (pre-A0). This document is the contract for the project — behavior changes
> update this SPEC first, then code (see §12 governance).
>
> **Pre-A0 note:** Until A0 is approved/started, requirement and decision text may be rewritten in
> place to keep the draft coherent. **From A0 onward**, FR/NFR/AC/UC/AD/OQ IDs are append-only:
> never renumber; deprecate in place; new items take the next free number.

**Initial engine pin (A0 baseline):** `transon==0.1.7` with `metadata_version` `"3.0"`
(authoritative evidence: engine repo `pyproject.toml` version `0.1.7`;
`transon-blockly/docs/metadata-snapshot.json` records `engine_version` `0.1.7` and
`metadata_version` `3.0`). See AD-007 / §11.7.

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

Architecture decisions live in **§6**. If the SPEC grows too large, extract `ARCHITECTURE.md`; if
that grows too large, split ADs into `docs/adr/`. Do not create empty ADR files up front.

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
- **G5** — Decoupled from the editor; editor is an optional JSON sink.

## 3. Non-goals

- Not an in-editor chatbot / `AssistantProvider`.
- Not a new DSL, path syntax, or expression language.
- Not a Transon runtime (authors templates; engine executes).
- Not a workflow / no-code platform.
- Not bound by editor engine-free AD-008 (see AD-002).
- Not MCP, hosted HTTP engine, or WASM/Pyodide in v1.
- Not shell-less product/docs agents in v1.
- Not editor in-surface checking/disclosure.
- Not real filesystem/network I/O in `verify` dry-run.
- Not custom `Transformer` subclasses, custom rule/operator/function registries, or non-default
  markers in v1 (AD-017).

## 4. Consumers

| Consumer | Environment | Reach |
|---|---|---|
| Coding agent (Claude Code, Cursor) | shell | `python -m transon_authoring …` |
| CI / migration bot | headless shell | same; pre-confirmed SampleSet fixtures |
| `transon-blockly` | browser | optional sink via import codec |

---

## 5. Architecture

```mermaid
flowchart TD
    intent["NL intent"]
    skill["transon-authoring skill"]
    intent --> skill

    meta["pinned metadata snapshot<br/>+ docs.examples"]
    nl["NL intent sidecar<br/>keyed by example name"]
    samples["SampleSet artifact"]

    skill -->|grounds on| meta
    skill -->|search_examples| meta
    skill -->|NL hints| nl
    skill -->|proposes obligations / cases / waivers| samples

    check["check_samples(samples)"]
    check -->|gaps| ask["user/CI: confirm / defer / abort"]
    ask -->|revise| samples
    samples --> check

    ask -->|confirmed + coverage_complete| draft["draft template"]
    draft --> verify["verify(template, samples)"]
    verify -->|re-runs check_samples| check
    verify --> engine["pinned Transformer profile<br/>validate + sandboxed dry_run + match"]

    engine -->|error/diff| repair["repair; max repair_attempts"]
    repair --> verify
    engine -->|matched| blessed["AuthoringResult success"]
```

**Runtime (AD-006):** Python library is the contract; agents/CI use `python -m transon_authoring`.
No console-script product; no MCP.

---

## 6. Architecture decisions

- **AD-001 — Skill package.** Standalone repo/package (`SKILL.md` + resources + library).
- **AD-002 — Engine-dependent.** May/must embed the engine; does not inherit editor AD-008.
- **AD-003 — Engine is authority.** See AD-018 for precedence among engine, SPECIFICATION, snapshot.
- **AD-004 — Verify-before-return.** Success only if `verify` → `ok: true`, `assurance: "matched"`.
  `verify` **re-validates** the SampleSet via `check_samples` and rejects unless
  `ok_for_verify` (AD-019). Structured failure otherwise (§11.5).
- **AD-005 — Single-source, multi-tool.** One `SKILL.md`; Claude + Cursor adapters; parity gate.
- **AD-006 — Library-first; module entry.** APIs: `get_metadata`, `search_examples`,
  `check_samples`, `verify` (+ debug `validate` / `dry_run`). Invoked via
  `python -m transon_authoring` (§11.6).
- **AD-007 — Pin + drift + upgrade.** Depend on **`transon==0.1.7`** initially. Bundle
  `get_editor_metadata()` snapshot with provenance (`engine_version`, `metadata_version`, content
  hash, sync date). **Drift gate** compares the bundle to metadata produced by the **pinned**
  install — it does **not** detect newer PyPI releases. **Staleness/upgrade:** a scheduled or
  manual check against PyPI/latest engine opens a pin-bump PR; humans run `sync-metadata`, update
  `pyproject.toml` pin, refresh NL sidecar as needed, and merge deliberately (OQ-004 still applies
  for automation shape).
- **AD-008 — Ordinary JSON output.** No IR/DSL; no verifier-owned key-order canonicalization.
- **AD-009 — Convention-first install.** Native Claude/Cursor paths (§11.9); no MCP.
- **AD-010 — Eval-driven improvement.** Changes gated by NFR-010 / AD-020.
- **AD-011 — Measurement before skill body.** A2 before A3.
- **AD-012 — In-process pinned engine only.** No HTTP/WASM/MCP.
- **AD-013 — Engine-valid under v1 profile; no editor-surface awareness.** Output may be any
  template valid for the **v1 execution profile** (AD-017), not “any conceivable engine subclass.”
  No in-surface check/disclosure.
- **AD-014 — Samples before draft.** No draft until `coverage_complete` and user/CI confirmation
  are both true (separate flags — AD-016). CI uses pre-confirmed fixtures.
- **AD-015 — Sandboxed `file` / `include`.** In-memory write capture + explicit `includes` map;
  forbid real FS/network in dry-run. Expected writes live on sample cases.
- **AD-016 — Obligations in SampleSet; deterministic `check_samples`.** Model proposes coverage
  obligations; user/CI accepts/rejects them and confirms the SampleSet. `check_samples` only
  checks the artifact — it never parses NL. **`coverage_complete` ≠ `confirmed`.**
- **AD-017 — v1 execution profile.** `verify` / dry-run use only:
  - class `transon.Transformer` (no subclasses);
  - built-in rule/operator/function registries as shipped in the pinned package;
  - default marker `"$"` (`Transformer.DEFAULT_MARKER`);
  - `max_include_depth=50` (engine default);
  - sandboxed `file_writer` + `template_loader` (AD-015);
  - per-case wall-clock timeout **5s** (library-enforced); on timeout → `failed_stage: "dry_run"`.
  Custom markers, custom registries, and subclassed transformers are **out of v1**. Trust boundary:
  `verify` is for **trusted local agents/CI**, not multi-tenant untrusted tenants.
- **AD-018 — Authority precedence.** (1) behavior of the **pinned running engine**;
  (2) engine `docs/SPECIFICATION.md` for that version; (3) pinned `get_editor_metadata()` snapshot
  for catalog/examples structure; (4) NL intent sidecar (hints only). Never LLM memory / web /
  Context7 for Transon semantics (NFR-001).
- **AD-019 — `verify` re-checks SampleSet.** No unforgeable token. `verify` runs `check_samples`
  on the provided SampleSet and requires `ok_for_verify` before validate/dry_run/match.
- **AD-020 — Eval runner policy (resolves OQ-009).** See §11.8. Committed `evals/runner.json`
  pins provider/model/settings; 3 runs/fixture majority-of-3; population = all committed fixtures;
  ratchet and privacy rules normative.

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
  after a failed `verify` (default **3**, allowed range **1..10** in config). Total candidates
  tried ≤ `1 + repair_attempts`. Diagram “N ≤ 3” means this default. Config overrides the default;
  CLI `--repair-attempts` overrides config for that invocation only.
- **FR-008** — On exhaustion / defer / abort / reject, return `AuthoringResult` failure (§11.5).
  Never return unverified JSON as success.

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
- **FR-011** — `sync-metadata` regenerates snapshot from the pinned engine and records provenance.

### Distribution
- **FR-012** — Canonical `SKILL.md` + Claude/Cursor adapters.
- **FR-013** — **Deprecated (pre-A0; no implementation).** MCP server removed from v1 (§3). Kept
  only so the ID is not reused after A0 lock.
- **FR-014** — `python -m transon_authoring` module entry with subcommands in §11.6.

### Installation
- **FR-015** — Install procedures (§11.9): Claude personal/project skill paths; Cursor
  `.cursor/skills/transon-authoring/`. Pin skill + engine versions in adapter metadata/comments.
- **FR-016** — Idempotent install; uninstall removes **only** files this installer created
  (manifest recorded at install time).

### Improvement
- **FR-017** — Eval-driven loop (AD-010/020).
- **FR-018** — Capture failing cases into evals only after **privacy redaction** and **explicit
  consent** (§11.8). No raw secrets/PII committed.

### Install CI
- **FR-019** — CI install checks:
  - **Claude Code:** structural install at documented path; plus headless listing **if** OQ-010
    resolves positively — until then claim **install integrity**, not “discoverability.”
  - **Cursor:** structural adapter install + `python -m transon_authoring metadata` runtime smoke.
    Do **not** claim Cursor “discovered/ingested” the skill (OQ-008).

### Additional
- **FR-026** — Library and module entry emit/accept only the JSON schemas in §11; reject unknown
  `schema_version` with `status: "schema-error"`.
- **FR-027** — `verify` must call `check_samples` and require `ok_for_verify` (AD-019).
- **FR-028** — Enforce AD-017 resource limits (timeout, include depth) during dry-run.

---

## 8. Non-functional requirements

- **NFR-001 — Authority isolation.** Transon semantics only from AD-018 sources. Context7 only for
  host-tooling APIs.
- **NFR-002 — Deterministic gates.** Same SampleSet + template + pin ⇒ same `SampleCheck` /
  `Verdict`. Sandboxed I/O only.
- **NFR-003 — Offline after install.** No network required for verify/check/metadata once the
  pinned engine and package are installed.
- **NFR-004 — Snapshot drift vs pin.** `check_snapshot` fails if bundle ≠ metadata from pinned
  `transon==…`. Does not track unpinned newer releases (AD-007).
- **NFR-005 — Honest failure.** §11.5 statuses distinguishable from success.
- **NFR-006 — Bounded repair.** Per FR-007; sample loop unbounded until confirm/defer/abort.
- **NFR-007 — Adapter parity.** Claude/Cursor equal capability or documented exclusion.
- **NFR-008 — Versioned releases.** Record skill version, engine pin, snapshot hash.
- **NFR-009 — Install integrity.** FR-015/016/019; wording is **install integrity + runtime
  smoke**, not host “discoverability,” except where OQ-010 enables a Claude listing check.
- **NFR-010 — Eval regression gate.** Targets (OQ-006): authoring ≥80%→95% ratchet; adversarial
  refuse-class =100%. Exact formula and runner: §11.8 / AD-020.
- **NFR-011 — Privacy.** Real-use fixtures require redaction + consent before commit (FR-018).

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
- **AC-009** — CI: Cursor structural install + module smoke; Claude structural install (listing
  only if OQ-010 allows). No false “discoverability” claims.
- **AC-010** — Unmet obligations → gap codes; skill presents waivers; user accepts/rejects.
- **AC-011** — Conversational confirm writes `confirmation` + binds `content_fingerprint`.
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
- **AC-026** — Failure envelopes always include `ok: false` and a §11.5 `status`.
- **AC-027** — Custom marker / subclassed Transformer templates are rejected at `validate` or
  profile preflight as out of v1 profile (AD-017) with clear error.
- **AC-028** — Per-case dry-run exceeding 5s fails `dry_run` with timeout error.

### Use cases
- **UC-001** — Claude Code: samples → confirm → author → `verify` → PR with template + SampleSet.
- **UC-002** — Cursor same path; optional handoff to blockly import (no in-surface guarantee).
- **UC-003** — CI batch with pre-confirmed SampleSets + committed config; non-interactive.
- **UC-004** — New engineer installs adapters, first-run layout prompt, authors successfully.

---

## 10. Package layout

```
transon-authoring/
├── SKILL.md
├── pyproject.toml                 # depends on transon==0.1.7 (initial pin)
├── src/transon_authoring/
│   ├── __main__.py                # §11.6
│   ├── verify.py
│   ├── samples.py
│   ├── metadata.py
│   ├── examples.py
│   ├── match.py                   # §11.4
│   └── schemas/                   # JSON Schema documents for SampleSet, etc.
├── resources/
│   ├── metadata-snapshot.json     # get_editor_metadata() pin
│   ├── metadata-snapshot.md       # provenance
│   └── nl-intents.json            # NL sidecar by example name (FR-010)
├── adapters/claude/ … cursor/
├── install/claude.py cursor.py
├── scripts/sync_metadata.py check_snapshot.py check_parity.py check_evals.py check_install.py
├── evals/
│   ├── runner.json                # AD-020 pin
│   ├── targets.json               # NFR-010 rates
│   └── cases/
└── docs/
    ├── SPEC.md
    └── traceability.md            # generated or maintained matrix (§17)
```

---

## 11. Normative contracts

### 11.0 Common types & serialization

```
JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue }

NoContentRef = { "$transon_authoring": "NO_CONTENT" }
  # Only legal as a SampleCase.output (or writes value) marker meaning engine NO_CONTENT.
  # Must not appear in templates as Transon syntax.
```

**Serialization (stdout):** UTF-8 JSON objects; `json.dumps` with `allow_nan=False`,
`separators=(",", ":")` optional for compactness in CI, pretty-print allowed for humans; **object
key order is not significant** for equality of results; parsers MUST reject duplicate object keys
and non-finite numbers (`NaN`/`Infinity`) at ingress.

**Schema versions:** documents carry `schema_version` string. v1 library understands `"1.0"` for
SampleSet, SampleCheck, Verdict, AuthoringResult, ProjectConfig, NlIntents, EvalRunner.

### 11.1 SampleSet & `check_samples`

```
CoverageObligation = {
  id: string,                       # stable within SampleSet
  kind: "happy_path" | "optional_present" | "optional_absent"
      | "list_empty" | "list_singleton" | "list_many" | "mode_choice" | "custom",
  target?: string,                  # field/list/mode name when applicable
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
  output: JsonValue | NoContentRef,
  writes?: { [name: string]: JsonValue | NoContentRef },
  satisfies: string[]               # obligation ids this case is claimed to satisfy
}

Confirmation = {
  confirmed: boolean,
  confirmed_by?: "user" | "ci",
  confirmed_at?: string,            # ISO-8601
  note?: string,
  content_fingerprint: string       # hex sha256 over canonical subset: schema_version,
                                    # coverage, waivers, cases, includes
                                    # (see library canonicalization: sort keys, no WS variance)
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

1. Validate SampleSet against JSON Schema `1.0`. On failure: all flags false;
   gap `schema_invalid`.
2. Reject duplicate `coverage.id` / `cases.id` / `waivers.id` → `duplicate_id`.
3. Consider only obligations with `acceptance === "accepted"`. If any remain `proposed`,
   gap `obligation_not_accepted` and `coverage_complete=false`.
4. For each accepted obligation, it is **met** if either:
   - some case lists its `id` in `satisfies` **and** structural side-conditions hold
     (e.g. `list_empty` ⇒ that case’s `input` path/target is an empty array when `target` denotes
     a list path the library can check via a simple JSON pointer in `target`, format
     `json_pointer` starting with `/`; if pointer invalid → `custom_unmet`), or
   - an **accepted** waiver lists the obligation id in `clears_obligation_ids` with valid refs
     (`waiver_invalid` otherwise).
5. `coverage_complete = (no unmet accepted obligations) && (cases.length >= 1)`.
6. `confirmed = confirmation.confirmed === true
   && confirmation.content_fingerprint === recomputed_fingerprint
   && confirmed_by in {"user","ci"}`. Else gaps `unconfirmed` / `fingerprint_mismatch`.
7. `ok_for_verify = coverage_complete && confirmed && gaps has no schema/duplicate errors`.

**Skill responsibilities:** propose obligations (`acceptance: "proposed"`); propose cases/waivers;
present gaps; on user approval set obligations/waivers to `accepted` and set `confirmation` with
fresh fingerprint. Library never sets `confirmed: true`.

### 11.2 `verify`

```
EngineError = {
  type: "DefinitionError" | "TransformationError" | "ProfileError" | "TimeoutError" | "PreflightError",
  message: string,          # verbatim engine str(exc) when from engine; stable library text otherwise
  engine_type?: string,     # Python exception class name when applicable
  path?: string
}

DiffEntry = {
  path: string,             # JSON pointer
  kind: "missing" | "extra" | "value_mismatch" | "type_mismatch" | "writes_mismatch",
  expected?: JsonValue | NoContentRef | { "writes": { [name: string]: JsonValue | NoContentRef } },
  actual?: JsonValue | NoContentRef | { "writes": { [name: string]: JsonValue | NoContentRef } }
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
  writes?: { [name: string]: JsonValue | NoContentRef }
}
```

**Stages:**

1. **`samples`** — parse SampleSet; run `check_samples`; require `ok_for_verify`. Else
   `failed_stage: "samples"` (malformed, zero cases, incomplete coverage, unconfirmed,
   fingerprint mismatch).
2. **`validate`** — `Transformer(candidate)` under AD-017; `validate()`. Profile violations
   (non-default marker detected in construction API misuse, etc.) → `ProfileError`.
3. **`dry_run`** — per case, `transform(input, no_content=Transformer.NO_CONTENT)` with sandboxed
   delegates; timeout 5s; `max_include_depth=50`; `includes` from SampleSet only.
4. **`match`** — §11.4 comparing outputs and writes.

`ok === true` iff all stages pass; then `assurance` is always `"matched"`.

### 11.3 Execution profile details (AD-017 / AD-015)

| Concern | v1 rule |
|---|---|
| Transformer | `transon.Transformer` only |
| Marker | `"$"` only |
| Registries | built-ins from pinned package only |
| `include` | loader resolves `SampleSet.includes[name]` only; miss → dry_run error |
| `file` | capture `(name, content)` in memory; never FS |
| Custom rules/ops/fns | out of scope |
| Depth | engine `max_include_depth=50` |
| Timeout | 5s wall clock per case |
| Trust | trusted local agent/CI only |

### 11.4 Matching (§5 / FR-005)

**Deep equality** on JSON values (and `NoContentRef`):

1. **NO_CONTENT:** If actual is the engine `NO_CONTENT` sentinel, it matches only expected
   `NoContentRef`. It does **not** match `null`, `false`, `0`, or `""`.
2. **null:** matches only `null`.
3. **boolean:** matches same boolean (not numbers).
4. **number:** type-sensitive: Python `int` matches only `int` with equal value; `float` only
   `float`. `1` ≠ `1.0`. Non-finite forbidden at parse.
5. **string:** exact code-point equality.
6. **array:** same length; pairwise equal in order.
7. **object:** same key set (order ignored); each key’s values equal.
8. **writes:** Let `W` be captured map (names → content; `NO_CONTENT` content encoded as
   `NoContentRef` if ever applicable). If case has `writes`: deep-equal `W` to it (missing keys /
   extras → `writes_mismatch`). If case omits `writes`: require `W` empty; else fail match.

### 11.5 AuthoringResult & failure taxonomy

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
  repair_count?: number           # repairs consumed
}
```

| status | When |
|---|---|
| `matched` | success |
| `need-samples` | stopped with incomplete coverage / need more cases |
| `deferred` | user defer |
| `aborted` | user abort |
| `repair-exhausted` | used all repair_attempts |
| `samples-rejected` | verify/check failed samples stage |
| `verify-failed` | validate/dry_run/match failed and skill stopped without repair left mapping |
| `schema-error` | bad schema_version / JSON |
| `profile-rejected` | outside AD-017 |

### 11.6 Module CLI (`python -m transon_authoring`)

**Global:** stdout = one JSON value (result envelope); stderr = human diagnostics only; never put
primary machine result on stderr.

| Subcommand | Inputs | stdout | exit |
|---|---|---|---|
| `metadata` | none | snapshot JSON (`JsonValue`) | 0 |
| `examples search <query>` | query string | `{ "hits": [ example objects… ] }` | 0 |
| `check-samples` | `--samples PATH` | `SampleCheck` | 0 if `ok_for_verify` else 1 |
| `verify` | `--template PATH --samples PATH` [`--repair-attempts N`] | `Verdict` | 0 if ok else 1 |
| `validate` | `--template PATH` | `{ ok, errors }` debug | 0/1 |
| `dry-run` | `--template PATH --input PATH` [`--includes PATH`] | `{ ok, result, writes, errors }` | 0/1 |
| `init-config` | `--layout sibling\|central\|custom` [`--pattern STR`] [`--non-interactive`] | `ProjectConfig` | 0/2 |

**Exit codes:** `0` success; `1` check/verify failure; `2` usage/schema/config error; `3` internal
unexpected error.

**Engine errors:** `EngineError.message` is the **exact** `str(exception)` from the engine when
applicable; wrapped in the JSON envelope above (never paraphrased in `message`).

### 11.7 Pin, drift, upgrade

- **A0 pin:** `transon==0.1.7`, expect `metadata_version == "3.0"`,
  `engine_version == "0.1.7"` in snapshot.
- **“Current metadata”** = metadata from that pin after `sync-metadata`, bundled in-repo.
- **Drift:** bundle hash/content vs live `get_editor_metadata()` under the pinned install.
- **Newer releases:** not red by drift alone. Upgrade path: bump pin → sync → update NL sidecar →
  PR. Optional scheduled notifier (OQ-004) opens that PR.

### 11.8 Evals (AD-020; resolves OQ-009)

`evals/runner.json`:
```
{
  "schema_version": "1.0",
  "provider": string,
  "model_id": string,
  "temperature": 0,
  "max_output_tokens": number,
  "tool_budget": number,
  "runs_per_fixture": 3,
  "pass_rule": "majority",
  "seed": number | null
}
```
Initial committed values are chosen at A2 standup and become part of the gate identity; changing
them is an explicit eval-policy commit.

- **Population / denominator:** all fixtures under `evals/cases/` with
  `expect: "matched" | "refuse"`. Infra failures (`infra_error`) excluded from denominator but
  reported; if infra skips &gt; 10% of fixtures → gate **fail**.
- **Authoring pass rate:** `#fixtures with majority matched success / #scored should-succeed`.
- **Adversarial:** fixtures with `expect: "refuse"` must not invent operators/modes; structured
  failure required. Fixtures may instead use `expect: "matched_correction"` when a real metadata
  operator is the intended recovery — counted separately, not in the 100% refuse bucket.
- **Ratchet:** let `T` be declared authoring target (starts 0.80). After release R with achieved
  rate `A`, set `T' = max(T, min(A, 0.95))` by explicit commit to `evals/targets.json`. Never
  decrease `T` silently.
- **Fixture regression:** any previously passing captured fixture that fails majority → gate fail
  regardless of aggregate rate.
- **Privacy (NFR-011):** before committing a real-use failure: strip secrets/PII; record
  `consent: { by, at, note }` in fixture metadata; default deny.

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

**Non-interactive:** `--non-interactive` requires all fields on CLI or existing config; else exit 2.

**Install destinations (POSIX; Windows uses equivalent user profile paths):**

| Tool | Project scope | Personal scope |
|---|---|---|
| Claude Code | `<repo>/.claude/skills/transon-authoring/` | `~/.claude/skills/transon-authoring/` |
| Cursor | `<repo>/.cursor/skills/transon-authoring/` | n/a (project-only in v1) |

Strategy: **copy** adapter files (not symlink) for hermeticity. Record
`.install-manifest.json` listing owned paths + versions. **Upgrade:** re-run install (idempotent
replace of owned files). **Uninstall:** delete only manifest paths.

Supported platforms for install scripts: macOS and Linux (Windows best-effort; not a v1 gate).

---

## 12. Governance

- SPEC-first; ID lock at A0 start.
- Maker ≠ checker on library/snapshot/adapters/evals.
- Single-source adapters (NFR-007).
- Measurement before skill body (AD-011).
- Traceability matrix (§17) updated in the same change as FR/NFR/AC edits after A0.

---

## 13. Testing & gates

| Gate | Enforces |
|---|---|
| Unit tests (library) | §11 schemas, match, sandbox, preflight |
| `check_snapshot` | NFR-004 / AD-007 |
| `check_evals` | NFR-010 / AD-020 |
| `check_parity` | NFR-007 / AC-005 |
| `check_install` | NFR-009 / FR-019 (integrity + smoke) |
| Authoring evals | should-succeed → matched |
| Adversarial evals | expect refuse =100% |
| Sandbox evals | AC-015/023/024/028 |

---

## 14. Milestones

- **A0 — Grounding spine.** Repo, package skeleton, pin `transon==0.1.7`, snapshot + provenance +
  drift gate, NL-intents sidecar skeleton, `SKILL.md` stub, §17 matrix stub. *DoD:*
  `python -m transon_authoring metadata` works offline against pin; `check_snapshot` green;
  no open decisions required to start A1. **ID lock on A0 approval.**
- **A1 — Verification library.** Full §11.2–11.6 verify/match/sandbox/CLI; SampleSet schema
  validation used by verify preflight. *DoD:* AC-015/016/018/021/023/024/027/028 green on
  fixtures; hand AC-001 path with fixed SampleSet (no skill body).
- **A2 — Measurement spine.** `check_samples` complete; config init; `evals/runner.json` +
  targets + seed cases; `check_evals` red/green; trivial skill stub only. *DoD:* AD-020
  executable; NFR-010 gate runs; AD-011 satisfied; A3 unblocked.
- **A3 — Authoring loop.** Full skill body; repair counting per FR-007; §11.5 statuses.
  *DoD:* authoring target met; AC-003/004/010–014/017/019/025/026 green.
- **A4 — Distribution.** Adapters, install/uninstall, parity, install integrity CI; resolve
  OQ-010. *DoD:* AC-005/007/009.
- **A5 — Editor sink + release.** UC-002 demo; versioned release notes with pin.

---

## 15. Open questions

- **OQ-001** — **Resolved (2026-07-09; rev 2026-07-10):** in-process pin only; no HTTP/WASM/MCP.
- **OQ-002** — **Resolved (2026-07-09):** standalone repo (AD-001).
- **OQ-003** — **Resolved (2026-07-09; rev 2026-07-10):** authoritative example JSON =
  snapshot `docs.examples`; NL intents in sidecar by `name`; no editor codec corpus duplication
  (FR-010).
- **OQ-004** — **Resolved (2026-07-09):** manual sync + drift now; scheduled PR bot later.
- **OQ-005** — **Resolved (2026-07-09; rev 2026-07-10):** no in-surface gate/disclosure (AD-013).
- **OQ-006** — **Resolved (2026-07-09):** authoring ≥80%→95%; adversarial refuse =100%.
- **OQ-007** — **Resolved (2026-07-09; rev 2026-07-10):** plain skill then plugin; no MCP.
- **OQ-008** — **Resolved (2026-07-10):** Cursor = structural + runtime smoke; no ingest claim.
- **OQ-009** — **Resolved (2026-07-10):** Eval runner normative in AD-020 / §11.8.
- **OQ-010** — *(open; A4 only)* Claude Code headless skill listing. Until resolved, CI asserts
  **install integrity** only for Claude (FR-019 / AC-009). Does **not** block A0–A3.

---

## 16. Risks

- Snapshot rot → drift vs pin (AD-007).
- Pin staleness vs newer engine → upgrade PR policy (AD-007); not silent.
- Verify bypass → AD-019 + samples stage (AC-016).
- Self-approval → fingerprint + library never sets confirmed.
- `file`/`include` → sandbox only; residual in-process trust boundary (AD-017).
- Weak obligations → user confirmation + evals.
- Eval cost/flakiness → majority-of-3 + infra_skip cap.
- Privacy leaks in fixtures → NFR-011.
- Adapter drift → parity gate.
- Repair blowup → FR-007 cap.
- False discoverability claims → FR-019 wording.

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
| FR-017 | AC-008 | A2 | check_evals |
| FR-018 | AC-008, AC-025 | A2–A3 | evals + privacy review |
| FR-019 | AC-009 | A4 | check_install |
| FR-020 | AC-010, AC-017, AC-018 | A2 | check_samples unit |
| FR-021 | AC-011, AC-017 | A2 | schema unit |
| FR-022 | AC-014 | A2 | config unit |
| FR-023 | AC-012 | A3 | sample-loop evals |
| FR-024 | AC-010, AC-011 | A3 | sample-loop evals |
| FR-025 | AC-010, AC-017 | A3 | sample-loop evals |
| FR-026 | AC-021, AC-026 | A1 | schema unit |
| FR-027 | AC-016 | A1 | verify preflight |
| FR-028 | AC-027, AC-028 | A1 | profile + timeout unit |
| NFR-001 | AC-003, AC-022 | A0+ | authority tests / evals |
| NFR-002 | AC-018 | A1 | determinism unit |
| NFR-003 | AC-020 | A1 | offline CI job |
| NFR-004 | AC-006 | A0 | check_snapshot |
| NFR-005 | AC-026 | A1 | envelope unit |
| NFR-006 | AC-019 | A3 | repair unit |
| NFR-007 | AC-005 | A4 | check_parity |
| NFR-008 | AC-006, AC-007 | A4–A5 | release checklist |
| NFR-009 | AC-007, AC-009 | A4 | check_install |
| NFR-010 | AC-008 | A2 | check_evals |
| NFR-011 | AC-025 | A2 | fixture lint |

---

## 18. Readiness

| Milestone | Ready to begin? | Notes |
|---|---|---|
| **A0** | **Yes** | Pin, snapshot, NL sidecar, drift, package skeleton fully specified. |
| **A1** | **Yes** | Verify/match/sandbox/CLI/profile normative; no blocking OQ. |
| **A2** | **Yes** | SampleSet/`check_samples`/evals (AD-020) normative; OQ-009 resolved. |
| A3 | After A2 green | Skill body only. |
| A4 | After A3; needs OQ-010 decision for Claude listing depth | Non-blocking for A0–A3. |
| A5 | After A4 | Optional editor sink demo. |
