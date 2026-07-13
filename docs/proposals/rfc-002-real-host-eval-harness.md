# RFC-002: Eval gate on the real host harness (`claude -p` / Agent SDK)

- **Status:** **Draft (proposed 2026-07-13).** Not yet normative. If accepted, it
  revises locked decisions and lands via a governed `docs/SPEC.md` edit
  (maker ≠ checker): **OQ-017** (harness shape — reopened), **AD-020 / §11.8**
  (eval runner + harness), **FR-017** (improvement loop), and the
  `evals/runner.json` shape. On conflict the SPEC wins until then.
- **Type:** Measurement-architecture proposal for the NFR-010 gate. Does **not**
  change Transon semantics, `verify`, `check_samples`, or the SampleSet schema.
- **Related (normative today):** OQ-017 (raw provider tool loop), AD-020 / §11.8
  (eval policy), AD-021 (small-model gate), FR-017, NFR-010.

## One-line summary

Stop driving the NFR-010 eval with a bespoke 3-tool `messages.create` loop
(`scripts/eval_harness.py`) and instead run the skill in the **real host agent
harness** it actually ships into — Claude Code headless (`claude -p`) or the
Claude Agent SDK — **pinned** for reproducibility. Measure the skill where it
runs; stop reinventing an agent loop in CI.

## Problem

The gate harness (OQ-017 / §11.8) is a hand-rolled raw tool loop: `SKILL.md`
verbatim as the system prompt, **exactly three tools** (`write_file`,
`transon_authoring`, `submit_result`), a 32-call `tool_budget`, and a bare
`while` loop over `messages.create`. The shipped product, however, is a **Claude
Code / Cursor skill** — its production host is always a *rich* agent harness
(Read/Write/Edit/Bash/Glob/Grep, a mature loop, no artificial 3-tool cap).

So the gate measures the skill in a configuration **that never ships**, and one
strictly *harder* than production. Consequences:

- **False negatives.** A gate failure need not mean a real-world failure.
- **Misprediction.** The gate does not predict production success — the thing a
  gate exists to do.
- **Maintenance + brittleness.** `eval_harness.py` reimplements — less robustly —
  loop management and tool-call parsing that Claude Code and the Agent SDK
  already do well.

### Evidence (measured 2026-07-13)

The same fixture, same model (`claude-haiku-4-5`), same scorer
(`check_evals.score_episode`), two harnesses:

| harness | tools | loop / budget | submission | `seed-matched-flatten-orders` |
|---|---|---|---|---|
| local-haiku (`Agent(model=haiku)`, general-purpose) | full suite (Read/Bash/Edit/…) | Claude Code agent loop, no cap | writes `result.json` | **pass** (and 44/44 in that run) |
| raw `eval_harness` (the §11.8 gate) | 3 (`write_file`/`transon_authoring`/`submit_result`) | bare loop, 32-call cap | `submit_result` tool call | **fail** — `budget_exceeded` at 33 turns |

The gate harness fails a fixture the real host authors correctly. The earlier
"100% local" number came from the *Agent* harness and was therefore never a
valid proxy for the gate — which is why local optimism (100%) and the normative
run (0.72) diverged.

*(Independent finding from the same session: prompt caching cuts input spend
~81% on real cached calls because every turn re-sends the growing transcript.
This is **harness-agnostic** — `claude -p` re-sends context every turn too — so
the caching win survives this proposal.)*

## Proposal

Make the NFR-010 gate run the skill in the **real host harness**, version-pinned:

1. **Driver.** Replace the bespoke loop with either Claude Code headless
   (`claude -p --output-format json …` with the skill installed) or the Claude
   Agent SDK (`query(prompt, options)`), whichever gives a cleaner pinned,
   scriptable episode. The Agent SDK is the likely sweet spot: a real tool suite
   **and** a pinnable package version.
2. **Pin for reproducibility.** `evals/runner.json` gains a `harness` block
   pinning the host + version (e.g. `{ "kind": "agent-sdk", "version": "x.y.z" }`)
   alongside the model pin, so gate identity stays reproducible — the one real
   objection to using the host, solved the same way the model is solved: pin it.
3. **Scoring unchanged.** Keep `check_evals.score_episode` (schema-valid +
   independent engine re-verify, AD-004). The host writes/returns an
   `AuthoringResult`; scoring is provider- and harness-agnostic already.
4. **Retire or demote the raw loop.** The 3-tool/budget loop is either deleted or
   kept only as an offline smoke fixture — no longer the gate.

## Tradeoffs

| Concern (why OQ-017 chose the raw loop) | Resolution under this proposal |
|---|---|
| **Reproducibility / pinning** | Pin the harness version in `runner.json`, exactly as the model is pinned. Realistic *and* reproducible. |
| **Isolation** ("measure SKILL.md, not the host") | The host *is* production reality; "SKILL.md alone in a bare loop" measures a config that never ships. Isolation was isolating the wrong thing. |
| **Host-neutrality** (Cursor too) | Name Claude Code / the Agent SDK the **reference** host for the gate, or run the gate per-host. Both real hosts are rich harnesses; neither resembles the bare loop, so the current design serves neutrality poorly anyway. |
| **Minimal CI deps** | The full run already lives in a credential-holding dispatch workflow; add the Agent SDK / Claude Code there. Per-PR CI keeps the credential-free lint. |

## Migration

Already landed on branch `eval-harness-ollama-observability` and reusable
regardless of driver: per-episode **token counting**, the `check_evals`
**live progress** line, and **prompt caching on by default**. Remaining work if
accepted: swap the driver, add the `runner.json` harness pin, **re-baseline**
`evals/baseline.json` under the new harness (a §11.8 eval-policy commit, like the
model-pin swap), and delete/demote `eval_harness.py`.

## Open questions

- **OQ-R1 — Driver:** `claude -p` (headless Claude Code) vs the Claude Agent SDK.
  Agent SDK favoured for pinnability + a defined tool set; confirm it can install
  the skill and return the `AuthoringResult` cleanly.
- **OQ-R2 — Harness pin shape** in `runner.json` and how a host upgrade is treated
  (eval-policy commit + baseline reset, mirroring the model-pin rule).
- **OQ-R3 — Cursor parity:** reference host only, or a second gate lane.
- **OQ-R4 — Keep the raw loop** as a non-gating smoke, or delete outright.

## Recommendation

Accept the direction; resolve OQ-R1–R4 at design standup; land via a governed
SPEC edit revising OQ-017 / AD-020 / §11.8 / FR-017. This deletes a pile of
brittle bespoke code, makes the gate predict production, and ends the
"reinvent Claude in CI" problem this RFC is named for.
