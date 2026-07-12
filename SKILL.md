# transon-authoring

Authors engine-valid [Transon](https://pypi.org/project/transon/) JSON templates and returns one
only after the pinned engine has verified it against a user-confirmed SampleSet to
`assurance: "matched"` — never unverified JSON as success. The contract for every behavior in
this skill is [`docs/SPEC.md`](docs/SPEC.md).

## Authority

Precedence for Transon semantics (AD-018), highest first:

1. Behavior of the **pinned running engine** (`transon==0.1.7`);
2. The engine `docs/SPECIFICATION.md` for that version;
3. The pinned `get_editor_metadata()` snapshot (catalog/examples structure);
4. The NL intent sidecar — **hints only**, never authority.

**Never** model memory, web docs, or Context7 for Transon semantics (NFR-001).

## Pin

`transon==0.1.7`, `metadata_version` `"3.0"`, snapshot at
[`resources/metadata-snapshot.json`](resources/metadata-snapshot.json).

## Procedure

Work through sections 1–6 IN ORDER for every authoring request. Do exactly what each step says.
Never skip a gate. Every final answer is exactly ONE `AuthoringResult` object (section 6).

## 1. Config & samples location

1. Look for `.transon-authoring.json` at the repo root and read it if present. It gives the
   samples `layout` (where SampleSet files live) and the `repair_attempts` budget (§11.9).
2. If it is absent and this is an interactive session, run
   `python -m transon_authoring init-config` once, at the repo root, before any other step
   (FR-022). It writes `.transon-authoring.json` to the current working directory and prints the
   ProjectConfig.
3. In CI or any non-interactive run: never prompt, never wait for input (AC-014). If a config
   must be created there, pass `--layout` plus `--non-interactive`; otherwise proceed without
   creating one.
4. An explicit samples path from the caller — a `--samples` value or a CI fixture path — always
   wins over any config-derived location. When the config is already present or a samples path
   is given, there is no layout prompt (AC-014).

## 2. Ground & refuse

1. Before using ANY Transon operator, rule, or mode name, resolve it against the pinned
   snapshot first:
   - `python -m transon_authoring metadata` — the full pinned catalog;
   - `python -m transon_authoring examples search <query>` — snapshot `docs.examples` hits.
2. Authority order (AD-018), highest first: (1) behavior of the pinned running engine;
   (2) the engine `docs/SPECIFICATION.md` for that version; (3) the pinned snapshot;
   (4) the NL sidecar — hints only. Never use model memory, web docs, or Context7 for Transon
   semantics (NFR-001).
3. If the request needs a capability that cannot be grounded in the pinned snapshot — an
   operator, rule, or mode that does not exist there — REFUSE: stop and emit an
   `AuthoringResult` with `ok: false`, `status: "aborted"`, and an explanation naming the
   missing capability (AC-003). Never invent names. Never guess syntax.

## 3. Sample loop

Protocol summary — the full elicitation protocol lands in the next slice. Drive the sample
conversation until `python -m transon_authoring check-samples --samples <path>` reports BOTH
`coverage_complete: true` AND `confirmed: true` (independent flags — both must come from the
`check-samples` output, never from your own judgment). Do not draft any template until both are
true (AD-014). Confirmation comes only from the user (interactive) or a pre-confirmed CI
fixture — the library never sets `confirmed: true` (AD-016). Conversation exits are
confirm / defer / abort (FR-023); map defer/abort to section 6 statuses.

<!-- sample-loop protocol: FR-023/024/025 -->

## 4. Draft

1. Run `python -m transon_authoring examples search <query>` with words from the intent.
2. Copy the structure of the nearest example's `template` and adapt names and paths to the
   confirmed samples. Never improvise operators, rules, modes, or syntax that are not in the
   pinned snapshot (FR-001, NFR-001).
3. Write the candidate template JSON to a file.

## 5. Verify & repair

1. Run `python -m transon_authoring verify --template <template> --samples <path>`.
2. Success ONLY when the Verdict has `ok: true` AND `assurance: "matched"` (AD-004, AC-013).
   Anything else is a failure — never report or return the template as success.
3. On a failed verify: repair placeholder — the full repair loop (verbatim engine errors fed
   back, up to `repair_attempts` cycles, then `repair-exhausted`) lands in the next slice.
   Until then, stop and report `status: "verify-failed"` per section 6.

<!-- repair protocol: FR-007/NFR-006 -->

## 6. Result

Emit exactly ONE `AuthoringResult` object (§11.5) per answer. `ok: true` if and only if
`status: "matched"`. Include `template` only on success. Failures always set `ok: false`, use a
status from the table below, and never present a template as success (FR-008, AC-026).

| status | when |
|---|---|
| `matched` | verify returned `ok: true` with `assurance: "matched"` — the only success |
| `need-samples` | stopped with incomplete coverage / need more cases (section 3 gate not met) |
| `deferred` | the user chose defer during the sample loop |
| `aborted` | the user chose abort, or you refused because the request cannot be grounded in the pinned metadata (section 2, AC-003) |
| `repair-exhausted` | all `repair_attempts` repair cycles consumed without a matched verdict |
| `samples-rejected` | `check-samples` (or the verify `samples` stage) failed on a schema-valid SampleSet |
| `verify-failed` | validate, dry_run, or match failed and you stopped without scheduling another repair |
| `schema-error` | malformed JSON or unsupported `schema_version` on ingress (CLI exit 2) |
| `profile-rejected` | the request demanded an out-of-profile execution option (non-default marker/transformer): stop WITHOUT calling verify (AC-027) — or the CLI rejected a reserved knob |
