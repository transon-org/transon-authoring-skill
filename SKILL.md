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

## Procedure (A2 measurement stub)

Given a natural-language intent and (optionally) a path to a SampleSet file:

1. **Gate on samples.** If a SampleSet path is given, run
   `python -m transon_authoring check-samples --samples <path>`. If it does not exit 0
   (`ok_for_verify`), stop: emit an `AuthoringResult` with `ok: false` and the mapped §11.5
   status — `need-samples` for coverage gaps, `samples-rejected` for a failed samples check on a
   schema-valid set, `schema-error` for exit 2. Never draft against an unconfirmed or incomplete
   SampleSet (AD-014). If no SampleSet is given, stop with `status: "need-samples"` — this stub
   does not drive the sample-elicitation loop (that lands in A3).
2. **Ground every name.** Resolve every operator/mode the intent needs against the pinned
   metadata: `python -m transon_authoring metadata` and
   `python -m transon_authoring examples search <query>`. If the intent demands an operator or
   mode that does not exist in the pinned metadata, **refuse**: emit `ok: false`,
   `status: "aborted"`, and an explanation naming the missing capability. Never invent names
   (AC-003, NFR-001).
3. **Draft grounded in snapshot examples.** Write the candidate template JSON to a file
   (grounded in `docs.examples` payloads from the snapshot — copy structure from the closest
   example, don't improvise syntax).
4. **Verify.** Run `python -m transon_authoring verify --template <template> --samples <path>`.
   - Exit 0 with `verdict.ok === true` and `assurance === "matched"` → emit the success
     `AuthoringResult`: `ok: true`, `status: "matched"`, the `template`, and the `verdict`.
   - Anything else → emit `ok: false`, `status: "verify-failed"`, with the returned `verdict`.
     **No repair loop in this stub** — repair counting is A3 behavior (FR-007).

Every final answer is exactly one `AuthoringResult` object per §11.5 (`ok` ⇔
`status: "matched"`; `template` only on success; failures use the §11.5 taxonomy).

## Status: A2 measurement stub

Working entry points: `python -m transon_authoring metadata` / `examples search` /
`check-samples` / `verify` / `validate` / `dry-run` / `init-config`, plus the library calls
(`get_metadata()`, `search_examples()`, `check_samples()`, `verify()`). The procedure above is
the minimal measurable loop for the A2 evals (AD-011). The full authoring loop — sample
elicitation, conversational confirm, repair counting per FR-007 — lands in A3
(FR-001/FR-007/FR-023–025, SPEC §14).
