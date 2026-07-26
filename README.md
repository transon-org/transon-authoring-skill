# transon-authoring

[![PyPI](https://img.shields.io/pypi/v/transon-authoring)](https://pypi.org/project/transon-authoring/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An agent skill that authors correct, engine-valid
**[Transon](https://github.com/transon-org/transon)** JSON transformation templates — and never
returns one until the pinned engine has verified it against a user-confirmed set of input/output
samples.

The design point: a template is only reported as success when `verify` yields
`assurance: "matched"`. Unverified JSON is never returned as an answer.

## Install

Two pieces: the **runtime** (the CLI the skill grounds through) and the **skill files** (what your
agent reads). The runtime is always `pip`; pick either channel for the skill files.

**1. Runtime** — into whichever interpreter your agent can reach:

```sh
pip install transon-authoring
```

This pins `transon` transitively. Note `pip install` does **not** install the skill body.

**2a. Skill files — Claude Code plugin:**

```
/plugin marketplace add transon-org/transon-authoring-skill
/plugin install transon-authoring@transon-authoring
```

**2b. Skill files — installers** (from a clone or a release archive), Claude Code and Cursor, project
or personal scope:

```sh
python3 install/claude.py --scope personal      # or --scope project [--target-root DIR]
python3 install/cursor.py --scope personal
```

Idempotent; `--uninstall` removes only the files the installer recorded.

## How it works

1. **Ground** — operators and modes are resolved against the engine's packaged Language Reference
   and a pinned metadata snapshot. Never model memory, never web docs.
2. **Samples first** — no draft until the sample set is complete *and* user-confirmed. The library
   never sets the confirmation flag itself.
3. **Author, verify, repair** — candidates are executed through the pinned engine in a sandbox (no
   real filesystem or network); failures feed a bounded repair loop.
4. **Review** — the result is presented for approval, with explicit approve / revise / stop exits.
5. **Return** — the success envelope is machine-built by the CLI, never hand-written.

```sh
python -m transon_authoring metadata              # the pinned engine snapshot
python -m transon_authoring language --list-sections
python -m transon_authoring verify --template t.json --samples s.json
```

If an agent reports `No module named transon_authoring`, the runtime is missing from *that*
interpreter — re-run step 1 there.

## Documentation

- **Releases:** [`CHANGELOG.md`](CHANGELOG.md) · [release runbook](docs/release-runbook.md)
- **Contract:** [`docs/SPEC.md`](docs/SPEC.md) + [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) +
  [`docs/ROADMAP.md`](docs/ROADMAP.md) — SPEC-first, requirement IDs append-only
- **Coverage:** [`docs/traceability.md`](docs/traceability.md)
- **For contributors and agents:** [`AGENTS.md`](AGENTS.md); harness core in
  [`harness/`](harness/README.md)

Requires Python ≥ 3.10. Install scripts support macOS and Linux (Windows best-effort).

## Development

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
git config core.hooksPath harness/githooks   # binding gates, once per clone
```

Deterministic gates (bound in pre-commit and CI):

```sh
python3 harness/scripts/check_traceability.py
python3 harness/scripts/check_append_only_ids.py
python3 scripts/check_snapshot.py && python3 scripts/check_parity.py && python3 scripts/check_install.py
```

## License

MIT — see [`LICENSE`](LICENSE).
