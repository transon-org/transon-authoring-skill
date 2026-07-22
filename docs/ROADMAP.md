# ROADMAP — Transon Authoring Skill (`transon-authoring`)

Milestones and their Definitions of Done, open questions (`OQ-*`), risks, and readiness for
`transon-authoring`. Normative: this file is part of the contract.

> **Contract split.** The contract spans three documents: [`SPEC.md`](SPEC.md) (§0–4, §7–9,
> §11–13, §17 — goals, requirements, normative contracts, governance, gates, traceability),
> [`ARCHITECTURE.md`](ARCHITECTURE.md) (§5, §6, §10 — architecture, decision records, package
> layout), and [`ROADMAP.md`](ROADMAP.md) (§14–16, §18 — milestones, open questions, risks,
> readiness). **Section numbers are global and unique across all three**, so a reference such as
> §6 or §11.9 is unambiguous wherever it appears. Requirement IDs (FR/NFR/AC/UC/AD/OQ) are
> append-only and never renumber (§12).

---

## 14. Milestones

- **A0 — Grounding spine.** Repo, package skeleton, pin `transon==0.1.7`, snapshot + provenance +
  drift gate, NL-intents sidecar skeleton, `SKILL.md` stub, §17 matrix stub. *Resolve at start:*
  **OQ-019** (Python floor, needed for `pyproject.toml`), **OQ-021** (sidecar consistency gate),
  **OQ-022** (`search_examples` minimal contract) — each resolved by a SPEC edit before the
  corresponding artifact lands. *DoD:* `python -m transon_authoring metadata` works offline
  against pin; `check_snapshot` green (including OQ-021 sidecar check); no open decisions
  required to start A1. **ID lock on A0 approval.**
- **A1 — Verification library.** Full §11.2–11.6 verify/match/sandbox/CLI (single-shot verify; no
  repair flag); SampleSet schema validation; worker-subprocess timeout; AuthoringTag encoding.
  *Resolve during design, before implementation of the affected part:* **OQ-011** (per-case
  attribution + reporting policy), **OQ-012** (`NO_CONTENT` encoding outside expectations),
  **OQ-013** (deterministic array ordering — prerequisite for AC-018 fixtures), **OQ-014**
  (envelope closure). *DoD:* OQ-011–OQ-014 closed in SPEC; AC-015/016/018/021/023/024/027/028
  green on fixtures (AC-027 = default-profile execution + rejection of reserved profile knobs —
  not “detect custom marker in template JSON”); hand AC-001 path with fixed SampleSet (no skill
  body).
- **A2 — Measurement spine.** `check_samples` complete; config init; `evals/runner.json` +
  targets + seed cases; `check_evals` red/green; trivial skill stub only. *Resolve at standup,
  before the corresponding code:* **OQ-015** (fingerprint canonicalization + acquisition path —
  before `check_samples`), **OQ-016** (eval bucket scoring) and **OQ-017** (eval harness shape) —
  both before `check_evals`; **OQ-018** (`check_samples` edge semantics) and **OQ-023** (AC-011
  traceability split, jointly with A3). *DoD:* OQ-015–OQ-018 closed in SPEC; AD-020 executable;
  NFR-010 gate runs; AD-011 satisfied; A3 unblocked.
- **A3 — Authoring loop.** Full skill body; repair counting per FR-007; §11.5 statuses;
  interactive review loop per FR-030; observability per FR-031/FR-032 (`trace` schema field +
  eval transcripts/attribution); AD-021/FR-029 synthetic-fixture generator + `evals/seeds/`
  provenance + AC-030 regen lint; the v1 fixture wave (~25–30 human-accepted synthetic fixtures);
  the §11.8 eval-policy commit swapping `evals/runner.json` to the small-model pin with the
  baseline reset; the eval-policy commit pinning `runner.json.harness` to the real host (Claude
  Agent SDK) with baseline reset discipline; AC-036 (harness pin + adapter, offline
  deterministic). *Entry:* OQ-023 resolved (A2/A3 boundary for AC-011). *DoD:* FR-029 landed
  (AC-030 green); **authoring target met under the small-model pin**
  (`claude-haiku-4-5-20251001`) on the corpus including the v1 synthetic wave, measured under the
  **real-host harness** pinned in `runner.json.harness`; AC-003/004/010–014/017/019/025/026/031/
  033/034/036 green (AC-031's conversational half by skill-body tests + UC-001 walkthrough — the
  non-interactive eval harness cannot exercise it; AC-025 is the FR-018a lint invariant,
  satisfied vacuously — real-use corpus growth (FR-018b) is ongoing and gates nothing). The live
  authoring-target run depends on the OQ-027f isolation contract being in force in the dispatch
  workflow.
- **A4 — Distribution.** Adapters, install/uninstall, parity, install integrity CI (OQ-010 and
  OQ-020 resolved at A4 start). *DoD:* AC-005/007/009/032
  (AC-032: `check_parity` carries the NFR-012 self-sufficiency lint).
- **A5 — Release.** Versioned release notes with pin
  (NFR-008); the **distribution-verification ladder** proving a fresh host works from the
  shipped artifacts, not the checkout:
  1. **Dist smoke (CI job):** build the wheel/sdist, `pip install` the **wheel** (never
     editable) into a fresh venv, run the §11.6 surface offline against the committed
     fixtures — catches packaging gaps (e.g. bundled `resources/` missing from the wheel)
     that editable installs cannot see.
  2. **Distribution-faithful eval provisioning:** the §11.8 harness workspace is installed
     by `install/claude.py --target-root <workspace>` before host auto-activation (OQ-027a),
     so the gate measures the installed-from-distribution configuration; validated first by a
     targeted `--only` probe. The installer's **source root is the staged file subset the eval
     bundle already carries** — `SKILL.md`, `pyproject.toml`, `resources/metadata-snapshot.json`,
     `adapters/`, `install/` — not an unpacked sdist: the claim is that the shipped installer
     provisions the workspace, not that the built archive was exercised (that is ladder step 1's
     job). Installed bytes are byte-identical to canonical and the added
     `.install-manifest.json` is inert to the host, so this forces no baseline reset — any
     `harness.kind`/`version` change still follows §11.8 discipline.
  3. **Cursor headless activation smoke (credentialed dispatch tier, OQ-008):**
     `cursor-agent -p` in an ephemeral workspace whose skill was installed by
     `install/cursor.py --target-root` — confirms a fresh headless Cursor actually
     activates the shipped skill and grounds via the module recipe. Model-invoking,
     therefore never a PR gate; non-gating report unless promoted by an eval-policy
     commit.
  4. **UC-004 human walkthrough (release checklist, NFR-008):** on a machine without the
     repo — `pip install transon-authoring` (from **TestPyPI** first, then PyPI at
     publish), run both installers, confirm the skill activates in real Claude Code and
     real Cursor, author one template; outcome recorded in the release notes.
  5. **Plugin packaging (FR-037a, offline deterministic):** the §11.9 plugin layout, gated by
     `check_install` (AC-040). Structural only — it needs no published package and makes no
     catalog claim.
  *Entry:* the real-host eval baseline reflects the shipped `SKILL.md` at the current pin —
  post-repin metadata + Language Reference snapshots and the packaged-reference authority; re-run it
  before release (this run is the AD-007 repin's pin+corpus baseline reset, §11.8).
  *DoD:* ladder steps 1–5 green/recorded; the `CHANGELOG.md` release record cites skill version,
  engine pin, snapshot hash and each ladder outcome (NFR-008); first PyPI publish per OQ-020;
  AC-040, AC-041, and AC-042 green. **FR-037b (external catalog
  submission) gates nothing** and begins only after the PyPI publish, since a listed skill whose
  runtime is unpublished is inert.

*Improvement-loop note (AD-021 / FR-029):* synthetic corpus growth and the small-model gate swap
are **A3 deliverables** (folded into the A3 DoD above) — the harness they rely on is the A2
deliverable, and the work proceeds in parallel with the skill body. Ordering within A3: SPEC →
generator + seeds + regen lint (FR-029) → v1 fixture wave with human-accepted intents → the
eval-policy commit that swaps `evals/runner.json` to the small model and resets
`evals/baseline.json` (§11.8) → the eval-policy commit that pins `runner.json.harness` to the
real host (deterministic parts offline; live authoring-target run once OQ-027f isolation is in
force) → iterate `SKILL.md` until the authoring target is met under that pin. Later fixture waves
beyond the v1 subset remain ongoing improvement-loop work and do not gate any milestone.

---

## 15. Open questions

- **OQ-001** — **Resolved (2026-07-09):** pinned local engine package only; no HTTP/WASM/MCP.
  Dry-run may use local worker subprocesses for timeout (AD-012/017).
- **OQ-002** — **Resolved (2026-07-09):** standalone repo (AD-001).
- **OQ-003** — **Resolved (2026-07-09):** authoritative example JSON = snapshot `docs.examples`;
  NL intents in sidecar by `name`; no editor codec corpus duplication (FR-010).
- **OQ-004** — **Resolved (2026-07-09):** manual sync + drift now; scheduled PR bot later.
- **OQ-005** — **Resolved (2026-07-09):** no in-surface gate/disclosure (AD-013).
- **OQ-006** — **Resolved (2026-07-09):** authoring ≥80%→95%; adversarial refuse =100%.
- **OQ-007** — **Resolved (2026-07-09):** plain skill then plugin; no MCP. Normative in
  AD-009 / FR-037.
- **OQ-008** — **Resolved (2026-07-19):** Cursor's deterministic CI claim
  stays structural + runtime smoke — the Cursor CLI (`cursor-agent`) still exposes no
  credential-free command to enumerate discovered skills. Its headless mode (`agent -p`) does
  make a **model-invoking activation smoke** possible: allowed only at the credentialed
  dispatch tier (A5 ladder), never as a PR gate, and only it may claim activation.
- **OQ-009** — **Resolved (2026-07-10):** Eval runner normative in AD-020 / §11.8.
- **OQ-010** — **Resolved (2026-07-19):** Claude Code exposes no supported, credential-free,
  deterministic headless command that lists installed skills without invoking the model. CI
  asserts **install integrity + discoverability preconditions** (installed frontmatter parses;
  `name` matches the skill directory; non-empty `description`) and never claims host
  discoverability. Normative in FR-019 / NFR-009 / AC-009.
- **OQ-011** — **Resolved (2026-07-11):** Per-case attribution on `EngineError`/`DiffEntry`;
  fail-fast between stages, report every failure within `dry_run`/`match`; root `Verdict.writes`
  never emitted in v1. Normative in §11.2.
- **OQ-012** — **Resolved (2026-07-11):** Library outputs use normative engine-value encoding
  `enc` (`NoContentRef` / `LitRef` / recursive); non-JSON-representable engine values fail the
  case at `dry_run`. Normative in §11.0 / §11.4.
- **OQ-013** — **Resolved (2026-07-11):** Defined emission order for `gaps[]`/`errors[]`/`diff[]`;
  AC-018 equality is plain structural equality. Normative in §11.0–§11.2.
- **OQ-014** — **Resolved (2026-07-11):** Exit-3 `CliError` envelope; `schema_version` on all
  library envelopes; `PreflightError` / `EngineError.type` closure; bare `--includes` map;
  JSON Schema draft 2020-12 via `jsonschema`. Normative in §11.0 / §11.6.
- **OQ-015** — **Resolved (2026-07-11):** `content_fingerprint` = SHA-256 of the canonical
  hashed subset; agents obtain it only from `SampleCheck.content_fingerprint` via
  `check-samples`. Normative in §11.1.
- **OQ-016** — **Resolved (2026-07-11):** Mechanical scoring rules for matched / refuse /
  matched_correction (reporting-only) / infra_error; `evals/targets.json` and fixture-regression
  baseline shapes. Normative in §11.8.
- **OQ-017** — **Resolved (2026-07-11; harness shape revised 2026-07-14 by OQ-027 / AD-024):**
  Gate harness is the real host (Claude Agent SDK), not a raw API tool loop. The raw loop is a
  non-gating offline smoke fixture. Shared conventions (prompting/tools/budget/CI split) are
  normative in AD-020 / AD-024 / §11.8.
- **OQ-018** — **Resolved (2026-07-11):** SampleSet edge semantics (placeholder fingerprint,
  gap emission, waiver refs, ignored `target` on some kinds, invalid includes fail at
  `dry_run`). Normative in §11.1.
- **OQ-019** — **Resolved (2026-07-11):** Python floor `>=3.10` in `pyproject.toml`; pin-reading
  scripts must not import `tomllib`.
- **OQ-020** — **Resolved (2026-07-19):** the runtime package ships on **public PyPI** as
  `transon-authoring` (same index as the pinned engine); no private index. Skill files install
  from a checkout/release archive via `install/` (§11.9); the installed skill needs only
  `pip install transon-authoring` for its module recipe. Normative in §11.9; first publish is
  an A5 release-checklist item (NFR-008).
- **OQ-021** — **Resolved (2026-07-11):** Sidecar consistency is part of `check_snapshot`
  (dangling keys fail; uncovered examples allowed with count report). Normative in FR-010 /
  NFR-004.
- **OQ-022** — **Resolved (2026-07-11):** Minimal `search_examples` contract (exact-name first,
  bound, deterministic corpus order, snapshot-verbatim hits + optional sidecar `nl`).
  Normative in FR-010 / AC-022.
- **OQ-023** — **Resolved (2026-07-11):** AC-011 split — AC-029 schema half (A2, FR-021);
  AC-011 conversational half only (A3, FR-024).
- **OQ-024** — **Resolved (2026-07-12; absorbs RFC-001):** Synthetic eval corpus from
  `docs.examples` and small-model primary gate (`claude-haiku-4-5-20251001`); stratification
  budget, corpus-pair rule, seed provenance/regen, baseline reset on gate-model swap.
  Normative in AD-021 / FR-029 / §11.8.
- **OQ-025** — **Resolved (2026-07-12):** FR-029 generator applicability predicates (optional
  keys, array scope, empirical `NO_CONTENT`, includes population/eligibility, writes-capable).
  Normative in FR-029.
- **OQ-026** — **Resolved (2026-07-12):** FR-029 coverage extensions (list length variation,
  root key add/delete, `NO_CONTENT` probe count, budget/drop order). Normative in FR-029.
- **OQ-027** — **Resolved (2026-07-14; absorbs RFC-002):** NFR-010 gate runs the skill in the
  real host agent harness (`runner.json.harness`, reference host = Claude Agent SDK);
  skill auto-activates from shipped `SKILL.md`; raw loop demoted to non-gating smoke;
  host→EpisodeResult adapter; isolation contract (ephemeral workspace, no credentials in
  tool sandbox, network egress denied, artifact controls). Normative in AD-024 / §11.8.
- **OQ-028** — **Resolved (2026-07-22):** Cursor gains a personal scope. Cursor discovers
  user-level skills at `~/.cursor/skills/` (the tool-neutral `~/.agents/skills/` is deliberately
  not adopted), so project-only was a product
  choice, not a platform limit, and NFR-007 prefers equal capability over a documented
  exclusion. Normative in FR-038 / AC-041 / §11.9.
- **OQ-029** — **Resolved (2026-07-22):** one §11.6 grounding recipe in every channel;
  runtime acquisition is documented per channel, never encoded in the recipe. `pip install
  transon-authoring` stays the prerequisite, stated in the plugin manifest and — as a
  channel-independent in-band remedy — in the shipped body. `uv run --with`
  rejected: it forks the recipe and its offline behavior depends on a prunable cache (NFR-003).
  No `SessionStart` hook — packaging never runs `pip` (OQ-020). Normative in FR-037a / AC-040.

---

## 16. Risks

- Snapshot rot → drift vs pin (AD-007).
- Pin staleness vs newer engine → upgrade PR policy (AD-007); not silent.
- Verify bypass → AD-019 + samples stage (AC-016).
- Self-approval → fingerprint + library never sets confirmed.
- `file`/`include` → sandbox only (incl. worker); residual trust boundary (AD-017).
- Weak obligations → user confirmation + evals.
- Eval cost/flakiness → majority-of-3 + infra_skip cap.
- Synthetic SampleSet leakage (wrong templates pass thin fixtures) → coverage-driven 3–6 case
  budget + corpus-only fixtures forbidden (AD-021/FR-029).
- Weak synthetic `intent_nl` → mandatory human acceptance before commit (AD-021).
- Gate cliff on small-model swap → explicit baseline reset, targets never lowered (§11.8).
- Seed/pin drift in synthetic fixtures → AC-030 regen lint, same discipline as `check_snapshot`.
- Unsatisfiable or hand-faked big fixtures (a matched fixture no engine template can produce) →
  AD-023 engine-freeze gate (AC-035): case outputs come only from re-executing the author's
  provenance seed template through the pin; engine-absent asks become refuse fixtures.
- Privacy leaks in fixtures → NFR-011.
- Adapter drift → parity gate.
- Dangling references in shipped skill/adapters → NFR-012 + parity lint (AC-032).
- Fabricated/misreported self-trace taken as evidence → AD-022: trace is diagnostic only; the
  mechanical §11.8 transcript is the authoritative record; neither gates.
- Review-loop fatigue (user rubber-stamps or the loop never ends) → three explicit exits,
  no auto-approve, honest `deferred`/`aborted` statuses (FR-030).
- Repair blowup → FR-007 cap.
- False discoverability claims → FR-019 wording.
- Real-host gate harness widens the trust boundary (a full Read/Write/Edit/**Bash** host runs over
  untrusted fixture input inside the credential-holding dispatch workflow: a prompt-injected or
  adversarial fixture could read the provider key, reach the network, or touch repo data) →
  OQ-027f isolation contract (AD-024): ephemeral per-episode workspace, no credentials in the tool
  sandbox, network egress denied post-install, artifact controls — a blocker before the live run.
- Gate cliff / non-transferable scores on a harness swap → harness pin is gate identity; a
  `harness.kind`/`version` change is an eval-policy commit that resets the baseline, targets never
  lowered (§11.8 / OQ-027b).
- Harness measures a **non-shipped configuration** (the gate looks green/red for reasons that don't
  reflect real use) → OQ-027a faithful engagement: install `SKILL.md` **as shipped** and let the
  host **auto-activate** it under its own system prompt — no injected system prompt, no engagement
  preamble, no tool coercion. An indicative run (2026-07-14) caught this: a hand-injected engagement
  made a fixture pass that, under genuine auto-activation, the model would not even route to the
  skill. Corollary risk — the **shipped skill isn't discoverable** (missing frontmatter
  `description`) so the host never activates it → treated as an install-integrity/discoverability
  defect (NFR-009 / OQ-010), fixed in the skill, not masked in the harness.

---

## 18. Readiness

| Milestone | Ready to begin? | Notes |
|---|---|---|
| **A0** | **Yes** | Pin, snapshot, NL sidecar, drift, package skeleton fully specified. Resolve OQ-019/021/022 at start (scoped, non-blocking to begin). |
| **A1** | **Yes** | Single-shot verify, worker timeout, AuthoringTag, profile-knob rejection, obligation semantics closed. OQ-011–014 must close during A1 design (in DoD). |
| **A2** | **Yes** | SampleSet/`check_samples`/evals (AD-020) normative; OQ-009 resolved. Standup decisions closed 2026-07-11 (OQ-015–018, OQ-023). |
| A3 | After A2 green | Skill body (incl. FR-030 review loop) + AD-021/FR-029 improvement-loop deliverables (synthetic corpus, small-model gate swap). Entry: OQ-023 resolved (2026-07-11); OQ-024 resolved (2026-07-12). |
| A4 | **Yes** (after A3; OQ-010/OQ-020 resolved 2026-07-19) | NFR-012/AC-032 self-sufficiency lint lands in `check_parity`. |
| A5 | After A4; entry: eval-baseline rerun | Distribution-verification ladder (dist smoke, distribution-faithful eval provisioning, UC-004 walkthrough, plugin packaging) + release notes/publish; Cursor personal scope (FR-038). OQ-028/OQ-029 resolved 2026-07-22; FR-037b non-gating. |
