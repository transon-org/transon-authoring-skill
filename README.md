# transon-authoring

A standalone, distributable capability that lets **coding agents and CI** author correct,
engine-valid **[Transon](https://github.com/transon-org/transon)** JSON — grounded in
engine-authoritative metadata, backed by a user-confirmed SampleSet, and blessed by the engine at
`assurance: "matched"` before any template is returned.

- **Contract:** [`docs/SPEC.md`](docs/SPEC.md) + [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) +
  [`docs/ROADMAP.md`](docs/ROADMAP.md) (SPEC-first; requirement IDs append-only from A0)
- **Coverage tracker:** [`docs/traceability.md`](docs/traceability.md)
- **Operating rules for agents:** [`AGENTS.md`](AGENTS.md); harness core in
  [`harness/`](harness/README.md)
- **Engine pin (AD-007):** `transon==0.2.3`, `metadata_version` `"3.0"`

## Status

Pre-A0: SPEC locked for A0–A2 implementation readiness; implementation harness in place. Product
milestones (ROADMAP §14): A0 grounding spine → A1 verification library → A2 measurement spine →
A3 authoring loop → A4 distribution → A5 release.

## Development

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
git config core.hooksPath harness/githooks   # binding gates, once per clone
```

Deterministic harness gates (also bound in pre-commit and CI):

```sh
python3 harness/scripts/check_traceability.py
python3 harness/scripts/check_append_only_ids.py
```
