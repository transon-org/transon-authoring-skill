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

## Status: A0 stub

The only working entry point today is `python -m transon_authoring metadata` (plus the library
calls `get_metadata()` / `search_examples()`). `check-samples`, `verify`, and the authoring loop
land across milestones A1–A3 (SPEC §14).
