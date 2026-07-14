---
name: transon-authoring
description: Author engine-valid Transon JSON transformation templates for a described data transform. Use when the user wants to create, generate, write, or fix a Transon template (a Transon transform), or to reshape, flatten, map, project, or restructure JSON data into another JSON shape via the Transon engine — especially when input/output sample pairs are available to verify against.
---

# transon-authoring

Authors engine-valid [Transon](https://pypi.org/project/transon/) JSON templates and returns one
only after the pinned engine has verified it against a user-confirmed SampleSet to
`assurance: "matched"` — never unverified JSON as success.

## Authority

<!-- authority: AD-018 / NFR-001 -->

Precedence for Transon semantics, highest first:

1. Behavior of the **pinned running engine** (`transon==0.1.7`);
2. The engine `docs/SPECIFICATION.md` for that version;
3. The pinned `get_editor_metadata()` snapshot (catalog/examples structure);
4. The NL intent sidecar — **hints only**, never authority.

**Never** model memory, web docs, or Context7 for Transon semantics.

## Pin

`transon==0.1.7`, `metadata_version` `"3.0"`. The pinned snapshot is bundled with the
`transon_authoring` package — print it with `python -m transon_authoring metadata`.

## Procedure

Work through sections 1–7 IN ORDER for every authoring request. Do exactly what each step says.
Never skip a gate. Every final answer is exactly ONE `AuthoringResult` object (section 7).

## 1. Config & samples location

<!-- config: FR-022 / AC-014 -->

**If a samples path was given to you** — a `--samples` value or a provided samples file, as in CI or
a headless/single-turn run — that path IS your SampleSet: **skip this entire section.** Do NOT stat
or read `.transon-authoring.json`, and do NOT run `init-config` — go straight to section 2. The
config-discovery steps below apply ONLY when no samples path was given and you must find where
SampleSet files live.

1. Look for `.transon-authoring.json` at the repo root and read it if present. It gives the
   samples `layout` (where SampleSet files live) and the `repair_attempts` budget.
2. If it is absent and this is an interactive session, run
   `python -m transon_authoring init-config` once, at the repo root, before any other step.
   It writes `.transon-authoring.json` to the current working directory and prints the
   ProjectConfig.
3. In CI or any non-interactive run: never prompt, never wait for input. If a config
   must be created there, pass `--layout` plus `--non-interactive`; otherwise proceed without
   creating one.
4. An explicit samples path from the caller — a `--samples` value or a CI fixture path — always
   wins over any config-derived location. When the config is already present or a samples path
   is given, there is no layout prompt.

## 2. Ground & refuse

<!-- ground & refuse: FR-001 / AD-018 / NFR-001 / AC-003 -->

1. Before using ANY Transon operator, rule, or mode name, resolve it against the pinned
   snapshot first — prefer TARGETED lookups over dumping the whole catalog:
   - `python -m transon_authoring examples search "<query>"` — snapshot `docs.examples` hits, and
     your PRIMARY grounding tool. ALWAYS quote the query as ONE argument
     (`examples search "flatten map"`, never `examples search flatten map`).
   - `python -m transon_authoring metadata` — the full pinned catalog. It is LARGE: do NOT dump it
     wholesale or pipe it to `head` (truncation loses the part you need). Reach for it only to
     confirm a specific operator/rule/mode name exists.
2. Authority order, highest first: (1) behavior of the pinned running engine;
   (2) the engine `docs/SPECIFICATION.md` for that version; (3) the pinned snapshot;
   (4) the NL sidecar — hints only. Never use model memory, web docs, or Context7 for Transon
   semantics.
3. If the request needs a capability that cannot be grounded in the pinned snapshot — an
   operator, rule, or mode that does not exist there — REFUSE: stop and emit an
   `AuthoringResult` with `ok: false`, `status: "aborted"`, and an explanation naming the
   missing capability. Never invent names. Never guess syntax.

## 3. Sample loop

Gate: drive the sample conversation until
`python -m transon_authoring check-samples --samples <path>` reports BOTH
`coverage_complete: true` AND `confirmed: true` (independent flags — both must come from the
`check-samples` output, never from your own judgment). Do not draft any template until both are
true. Confirmation comes only from the user (interactive) or a pre-confirmed CI
fixture — the library never sets `confirmed: true`. Conversation exits are
confirm / defer / abort; map defer/abort to section 7 statuses. Run the protocol below
in order: 3.1 → 3.2 → 3.3, with 3.4 governing every exit.

<!-- sample-loop protocol: FR-023/024/025 -->
<!-- also: AD-014 / AD-016 / AC-010 / AC-011 / AC-012 / OQ-015 -->

### 3.1 Propose

1. Draft the SampleSet YOURSELF from the user's NL intent. Write `coverage` obligations
   (kinds: `happy_path`, `optional_present`, `optional_absent`, `list_empty`, `list_singleton`,
   `list_many`, `mode_choice`, `custom`), each with `acceptance: "proposed"`, plus candidate
   cases in `cases` (each with `input`, `output`, and `satisfies` listing the obligation ids it
   covers), `waivers: []`, and `confirmation: { "confirmed": false, "content_fingerprint": "" }`.
2. Proposing obligations from natural language is YOUR job, inside the SampleSet artifact. The
   library never infers obligations from NL — `check-samples` only checks the artifact.
3. Persist the SampleSet file at the section 1 location.

### 3.2 Present gaps

1. Run `python -m transon_authoring check-samples --samples <path>`.
2. For EVERY entry in `gaps`, present the gap (code + message) to the user together with exactly
   one proposal: either a concrete new/edited case that would meet the obligation, or a proposed
   `Waiver` — `clears_obligation_ids` naming the obligation ids it clears, a `reason`, and
   `acceptance: "proposed"`.
3. The user accepts or rejects each proposed obligation, case, and waiver. Record every decision
   by setting that item's `acceptance` to `"accepted"` or `"rejected"` in the SampleSet. Never
   flip an `acceptance` without an explicit user decision. Persist the file after every change.
4. Repeat from step 1 until `check-samples` reports `coverage_complete: true` — or the user
   exits per 3.4.

### 3.3 Confirm

Only after the user EXPLICITLY confirms the SampleSet — never before, never on their behalf:

1. Run `python -m transon_authoring check-samples --samples <path>` on the not-yet-confirmed
   SampleSet (exit 1 is expected here; the SampleCheck output still carries the recomputed
   fingerprint).
2. Copy `content_fingerprint` from that SampleCheck output VERBATIM into
   `confirmation.content_fingerprint`. NEVER compute, hash, guess, or reconstruct the
   fingerprint yourself.
3. Set `confirmation.confirmed: true` and `confirmation.confirmed_by: "user"`. Persist.
4. Re-run `check-samples`; proceed to section 4 only when it reports `ok_for_verify: true`.

### 3.4 Exits

The loop is unbounded — keep eliciting until exactly one of these three exits happens. Never
auto-confirm; never treat silence, repetition, or loop length as confirmation.

- **confirm** — 3.3 completed with `ok_for_verify: true`; continue to section 4.
- **defer** — the user chooses to stop for now: emit `status: "deferred"`, no template.
- **abort** — the user chooses to abandon the request: emit `status: "aborted"`, no template.

### 3.5 Real user data

<!-- real-data capture: FR-018 / NFR-011 / AC-025 -->

When a case's `input`/`output` (or a failing conversation) comes from real user data and is to
be captured into the project's shared eval-fixture corpus: commit only after privacy redaction
(fixture `redacted: true`) AND explicit recorded consent (fixture `consent` object — `by`, `at`,
`note`). Never commit raw secrets or PII.

## 4. Draft

<!-- draft: FR-001 / NFR-001 -->

1. Run `python -m transon_authoring examples search "<query>"` with words from the intent (quote
   the query as one argument).
2. Copy the structure of the nearest example's `template` and adapt names and paths to the
   confirmed samples. Never improvise operators, rules, modes, or syntax that are not in the
   pinned snapshot.
3. The pinned engine is a STRUCTURAL transformer: its only functions are `str`, `int`, `float`,
   `type` — there is NO length/count, date, string-case, or string split/replace function. When
   the intent seems to need one, do NOT assume it is missing and do NOT refuse yet: first check
   whether it COMPOSES from the primitives you grounded. An `expr` with a `values` list reduces
   its operator across the whole runtime list, which covers most "aggregate" needs (confirm each
   with `verify` before trusting it):
   - Count a list's length: map each element to `1`, then reduce with `+` —
     `{"$": "expr", "op": "+", "values": {"$": "map", "item": 1}}`.
   - Flatten lists: prefer `map` with `items` mode
     (`{"$": "map", "items": <per-element list>}`), which concatenates each element's list and is
     safe on an empty input (yields `[]`). An `expr` `+` over a list of strings concatenates them.
   CAVEAT: an `expr` whose `values` reduce over a runtime list REQUIRES at least one element — an
   empty list raises a `DefinitionError`. So the reduce-count and `expr`-`+` recipes fail `verify`
   whenever a sample case has an empty list (e.g. a zero-count case); handle the empty case
   separately (a `cond`/`switch` on emptiness) or use the empty-safe `map`/`items` form.
   Only refuse (section 2) when the capability is genuinely absent AND cannot be composed this
   way — e.g. formatting an epoch as an ISO date, changing a string's case, or stripping a prefix.
4. Write the candidate template JSON to a file.

## 5. Verify & repair

<!-- verify gate: AD-004 / AC-013 -->

1. Run `python -m transon_authoring verify --template <template> --samples <path>`.
2. Success ONLY when the Verdict has `ok: true` AND `assurance: "matched"`.
   Anything else is a failure — never report or return the template as success.
3. On a failed verify: run the repair protocol 5.1. Never return an unverified template.

<!-- repair protocol: FR-007/NFR-006 -->
<!-- also: FR-003 / AC-019 -->

### 5.1 Repair loop

1. Read `repair_attempts` from `.transon-authoring.json` (section 1); when the config is absent,
   use the default 3 (allowed range 1..10). Enforcing this bound is YOUR job: the library
   `verify` is single-shot — it never loops and has no repair flag.
2. The repair count starts at 0 after the first failed verify.
3. To repair: take the failed Verdict's `errors[]` and `diff[]` arrays and feed them VERBATIM
   into the next candidate draft — quote every engine error and diff entry exactly as returned;
   never paraphrase, reword, or summarize engine errors. Draft the new candidate under
   the section 4 rules and re-run `verify`.
4. Each re-verify after a repair increments the repair count by 1. Total candidates tried is at
   most `1 + repair_attempts`.
5. If a re-verify succeeds (`ok: true`, `assurance: "matched"`), the candidate is matched — go to
   section 6 (Review), and report the repairs consumed in `repair_count`.
6. When the repair count reaches `repair_attempts` and the last verify still failed: STOP — no
   further tries; never loop past the bound. Emit `status: "repair-exhausted"` with
   `ok: false`, `repair_count` set to the repairs consumed (= `repair_attempts`), the last
   failed Verdict in `verdict`, and the last candidate in `last_candidate` (section 7). Never
   return an unverified template.
7. If you stop repairing before the budget is exhausted (without scheduling another repair),
   emit `status: "verify-failed"` instead, with `repair_count` set to the repairs consumed.

## 6. Review

<!-- interactive review: FR-030 / AC-031 / AC-012 -->

In an interactive session, after section 5 verifies a candidate — the Verdict has `ok: true` AND
`assurance: "matched"` — present that matched template TOGETHER WITH its Verdict to the user and
wait for their decision BEFORE emitting the final `AuthoringResult`. Only matched candidates are
ever presented; this review is ADDITIONAL to, never a substitute for, the verify gate. The loop is
unbounded until exactly one of the three exits below happens; never auto-approve; never treat
silence as approval.

- **approve** — the user accepts the template. Continue to section 7 and emit the success envelope
  with `status: "matched"`.
- **revise** — the user supplies feedback. Two kinds, handled differently:
  - NL-only feedback that rewords or restructures the SAME input/output behavior: draft a new
    candidate under the section 4 grounding rules and re-run section 5 verify with a **fresh
    `repair_attempts` budget** for this revision round (each round independently bounded). Re-present
    to the user only when the new candidate verifies matched.
  - Feedback that ADDS or CHANGES expected input/output behavior: apply it as SampleSet edits. Any
    such edit flips `confirmed` back via `fingerprint_mismatch`, sending the flow back through the
    section 3 sample loop to re-confirm before any redraft — so re-enter that sample loop.
- **stop** — the user declines the template and ends the request with NO template: emit
  `status: "deferred"` (stop for now) or `status: "aborted"` (abandon).

Non-interactive/CI runs have no reviewer: emit the matched result directly after section 5, with no
review step.

## 7. Result

<!-- result envelope: FR-008 / AC-012 / AC-026 / AC-027 -->

Emit your `AuthoringResult` by running the module — NEVER by hand-writing the envelope. On a matched
success (you hold a template that verified at `assurance: "matched"`), run:

```
python -m transon_authoring result --template <template-path> --samples <samples-path>
```

and return its stdout **verbatim** as your final message. That command re-verifies and
machine-builds the complete matched envelope (`ok: true`, `status: "matched"`, the `template`, the
`verdict`, `repair_count`), so it is always well-formed. Do NOT reconstruct it yourself, do NOT wrap
it in prose or a code fence, and NEVER answer with the bare template — a reply whose top-level keys
are template keys like `$` / `funcs` / `items` scores as a failure even when the template verifies.

For a refusal or a failure that has NO matched template — you refused in section 2, the sample loop
or review ended in defer/abort, or repairs exhausted — there is no `result` call to make: emit the
failure `AuthoringResult` directly, with `ok: false` and the matching status from the table below.

`ok: true` if and only if `status: "matched"`. Include `template` only on success. Failures always
set `ok: false`, use a status from the table below, and never present a template as success.

Every `AuthoringResult` MUST carry these four fields, always:

- `schema_version`: the string `"1.0"`.
- `ok`: boolean — `true` only when `status` is `matched`.
- `status`: exactly one value from the table below.
- `explanation`: a one-line string stating what happened.

On a matched success you MUST ALSO include: `template` (the verified template JSON), `verdict`
(the exact Verdict object the verify step returned — it carries `ok: true` and
`assurance: "matched"`), and `repair_count` (repairs consumed; `0` if the first candidate
matched). On a failure set `ok: false`, omit `template`, and attach whatever diagnostics apply
(`verdict`, `repair_count`, `last_candidate`, `gaps`, `sample_check`).

Success envelope shape:

```json
{
  "schema_version": "1.0",
  "ok": true,
  "status": "matched",
  "explanation": "Template verified at assurance matched.",
  "template": { "the": "verified template JSON" },
  "verdict": { "schema_version": "1.0", "ok": true, "assurance": "matched", "errors": [] },
  "repair_count": 0
}
```

Refusal / failure envelope shape:

```json
{
  "schema_version": "1.0",
  "ok": false,
  "status": "aborted",
  "explanation": "The requested capability does not exist in the pinned snapshot."
}
```

| status | when |
|---|---|
| `matched` | verify returned `ok: true` with `assurance: "matched"` — the only success; in interactive sessions, only after the section 6 review **approve** |
| `need-samples` | stopped with incomplete coverage / need more cases (section 3 gate not met) |
| `deferred` | the user chose defer during the sample loop, or a section 6 review **stop** (stop for now) |
| `aborted` | the user chose abort (sample loop or a section 6 review **stop**), or you refused because the request cannot be grounded in the pinned metadata (section 2) |
| `repair-exhausted` | all `repair_attempts` repair cycles consumed without a matched verdict |
| `samples-rejected` | `check-samples` (or the verify `samples` stage) failed on a schema-valid SampleSet |
| `verify-failed` | validate, dry_run, or match failed and you stopped without scheduling another repair |
| `schema-error` | malformed JSON or unsupported `schema_version` on ingress (CLI exit 2) |
| `profile-rejected` | the request demanded an out-of-profile execution option (non-default marker/transformer): stop WITHOUT calling verify — or the CLI rejected a reserved knob |

### 7.1 Trace (optional, diagnostic)

<!-- trace: FR-031 / AC-033 (AD-022) -->

In an interactive session you MAY add an ordered `trace` array to the `AuthoringResult`: one
`TraceEntry` per protocol step you performed. Each entry has a 1-based `seq` (contiguous, in
conversation order), a `step` — one of `config`, `ground`, `propose`, `present-gaps`, `confirm`,
`draft`, `verify`, `repair`, `review`, `result` — and a one-line `summary`. When the step ran a
module command, copy that exact python -m transon_authoring invocation into `command` verbatim,
and record a step-local `outcome` (e.g. the reported gap count or the `failed_stage`).

`trace` is DIAGNOSTIC ONLY. It never gates anything, is never treated as evidence that a step
actually ran, and its absence never invalidates a result. Nothing in `trace` may change the
status, `ok`, or `template` of the `AuthoringResult` you emit — decide those solely from the
gates in sections 2–5.
