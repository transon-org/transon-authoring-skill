# AC-001 hand-path fixtures (AC-001 / FR-004 / UC-001; §14 A1 DoD)

Static, committed inputs for `tests/test_ac001_path.py` — the §14 A1 DoD item "hand AC-001 path
with fixed SampleSet (no skill body)". They demonstrate the full authoring-verification path
end-to-end for the AC-001 intent, *"flatten each order's line items with the customer name"*,
through both the library API (`check_samples`, `verify`) and the §11.6 CLI verbs. Everything here
was hand-authored (no skill body) and **engine-verified against the pinned `transon==0.1.7`
at fixture-authoring time** (AD-018/NFR-001) — the template semantics were established by running
the engine, never assumed.

| File                  | Role                                                                 |
| --------------------- | -------------------------------------------------------------------- |
| `sample_set.json`     | Confirmed, coverage-complete §11.1 SampleSet: 6 accepted obligations spanning kinds (`happy_path`, `list_many`, `list_empty` ×2, `optional_present`, `optional_absent`) and 4 hand-written cases covering them. |
| `template.json`       | Hand-written Transon template satisfying every case: `chain` → `attr orders` → per-order `set`/`map` over `line_items` building rows with `customer_name`/`order_id`/`sku`/`qty`/optional `note` → outer `join` (with `default: []`) flattening per-order lists. `verify` yields `ok: true`, `assurance: "matched"`. |
| `template_wrong.json` | Deliberately wrong variant — the per-line-item object **drops `customer_name`** — proving verification is real, not vacuous: `verify` fails at `match` with `missing` diff entries at `…/customer_name` carrying `case_id` `c-two-orders` / `c-note-present`. |

## Regeneration — required if OQ-015 changes canonicalization

`sample_set.json` embeds `confirmation.content_fingerprint`, produced by
`transon_authoring.samples.content_fingerprint()` — currently the **provisional-internal
canonicalization pending OQ-015** (open; resolves at the A2 standup). If OQ-015 lands a different
byte-level rule, the recorded fingerprint stops matching, `check-samples` starts failing with
`fingerprint_mismatch`, and this fixture MUST be regenerated. Recompute with the library (never
by hand):

```sh
.venv/bin/python - <<'EOF'
import json, pathlib
from transon_authoring.samples import content_fingerprint

path = pathlib.Path("tests/fixtures/ac001/sample_set.json")
ss = json.loads(path.read_text(encoding="utf-8"))
ss["confirmation"]["content_fingerprint"] = content_fingerprint(ss)
path.write_text(
    json.dumps(ss, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
    encoding="utf-8",
)
print(ss["confirmation"]["content_fingerprint"])
EOF
```

Note on `confirmed: true`: the library never sets it (§11.1) — this fixture is a hand-authored
document whose confirmation was recorded by the fixture author (acting as "user") for test
purposes; only the fingerprint value comes from the library (the OQ-015 acquisition-path rule).
