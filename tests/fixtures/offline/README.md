# Offline-guarantee fixtures (NFR-003 / AC-020)

Static, committed inputs for the offline surface checks — `tests/test_offline.py` and the
dedicated `offline` CI job (`.github/workflows/ci.yml`), which runs the §11.6 CLI verbs against
these exact files inside a network-cut namespace (`unshare -rn`).

| File              | Role                                                                     |
| ----------------- | ------------------------------------------------------------------------ |
| `template.json`   | `{"$": "attr", "name": "x"}` — pinned-engine behavior: `{"x": v}` → `v`. |
| `input.json`      | Dry-run input; yields `"hello"` under the template above.                |
| `sample_set.json` | Confirmed, coverage-complete §11.1 SampleSet that MATCHES the template — `check-samples` exits 0 and `verify` reaches `ok: true`, `assurance: "matched"`. |

## Regeneration — only if a future spec change alters canonicalization

`sample_set.json` embeds `confirmation.content_fingerprint`, produced by
`transon_authoring.samples.content_fingerprint()`. The OQ-015 resolution (2026-07-11, A2 standup;
ROADMAP §15) adopted the A1 canonicalization **unchanged** as normative, so no regeneration was
needed — the recorded fingerprint remains valid. Should a future spec change ever alter the
byte-level rule, the recorded fingerprint would stop matching, `check-samples` would fail with
`fingerprint_mismatch`, and these fixtures MUST be regenerated. Recompute with the library (never
by hand):

```sh
.venv/bin/python - <<'EOF'
import json, pathlib
from transon_authoring.samples import content_fingerprint

path = pathlib.Path("tests/fixtures/offline/sample_set.json")
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
purposes; only the fingerprint value comes from the library.
