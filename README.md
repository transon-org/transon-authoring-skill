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

## Quality and verification

Three independent layers: deterministic checks on every commit, behavioural measurement against a
real agent host, and end-to-end verification of what actually ships.

### Deterministic — every commit, offline, no model calls

| | |
|---|---|
| **707 tests** (pytest) | schemas, matching, sandbox, preflight, CLI surface, installers, gates |
| **`check_snapshot`** | the bundled metadata snapshot and Language Reference match the pinned engine exactly; stale provenance is red |
| **`check_parity`** | Claude/Cursor adapters stay at equal capability; exactly one `SKILL.md` in the repo; the shipped body cites no repo paths, no spec sections, no requirement IDs |
| **`check_install`** | installs into throwaway roots for all four tool/scope combinations, asserts byte-identical bodies, complete manifests, idempotent re-install, uninstall touching only recorded paths |
| **`check_evals --lint`** | fixture privacy, seed/fixture regeneration agreement, engine-freeze of constructed fixtures |
| **`check_traceability` / `check_append_only_ids`** | every requirement maps to tests that cite its ID; requirement IDs are append-only and never renumbered |
| **Offline job** | the whole §11.6 surface runs under `unshare -n` — no network, ever, on the authoring path |
| **Dist smoke** | the built **wheel** is installed into a fresh venv and exercised offline, catching packaging gaps an editable install cannot see |

### Behavioural — measured against a real host, not a mock

The skill is evaluated by running it inside the **actual agent host it ships into** (Claude Code via
the Agent SDK, pinned in `evals/runner.json`), auto-activated from the installed `SKILL.md` with no
injected prompt and no tool coercion — so the measurement reflects real use rather than a rigged
harness.

- **54 committed fixtures** — 48 authoring, 5 adversarial (must refuse), 1 correction — run
  **3× each**, scored by majority.
- Scoring is mechanical and independent: a fixture passes only if the emitted envelope is
  schema-valid **and** an independent re-verification against the engine agrees.
- Measured against a **small model** (`claude-haiku-4-5-20251001`) on purpose: the bar is that the
  skill carries the discipline, not that a large model compensates for a vague one.
- Targets: authoring **≥ 0.80** (ratcheting), adversarial refusal **= 1.00** — a single wrong answer
  in the adversarial bucket fails the gate.

Last accepted full run (54 × 3): **authoring 1.000, adversarial 1.000, correction 1.000.** Fixtures
that pass become a regression baseline, so a later change that breaks one is red even if the
aggregate rate still clears target.

### End-to-end — what ships, not what's in the tree

Verified from the published artifacts rather than the checkout: the wheel installed from PyPI; skill
files installed by the shipped installers into throwaway projects; the eval workspace provisioned by
running the real installer; and a live check in **both** Claude Code and Cursor — from prompts that
never name the skill — each reaching a verified `assurance: "matched"` result. Full record in
[`CHANGELOG.md`](CHANGELOG.md).

### What is deliberately *not* claimed

- **Not that a host will discover or activate the skill.** No credential-free command exists to
  enumerate installed skills in either host, so CI asserts install integrity and frontmatter
  preconditions only. Activation evidence comes from live runs, and is reported as such.
- **The eval baseline predates a few later, additive edits to the skill body** — none of which trips
  a baseline-reset condition. The gap is recorded in [`CHANGELOG.md`](CHANGELOG.md) rather than
  papered over.
- **The real-host eval is credentialed and dispatch-only**, not a per-PR gate: pull requests run the
  deterministic layer plus offline fake-host tests.
- The adversarial bucket is **5 fixtures** — a floor, not a broad safety evaluation.

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
