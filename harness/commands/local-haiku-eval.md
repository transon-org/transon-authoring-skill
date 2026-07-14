# Local Haiku eval (non-normative)

Run the committed eval corpus through the **gate model** (`claude-haiku-4-5-20251001`) locally.
Two paths, and they are NOT interchangeable — pick by whether you need artifacts.

**This is NOT the §11.8 gate.** The normative NFR-010 gate is the real-host harness
(`scripts/host_harness.py` — Agent SDK, AD-024/OQ-027 — driven by `scripts/check_evals.py`) under
`evals/runner.json`, run ×3 with credentials in the dispatch workflow. Neither path below updates
`evals/baseline.json` or closes a DoD.

## Path A — real host (SAME artifacts as CI). **Preferred.**

`evals/runner.json` already pins `model_id: claude-haiku-4-5-20251001` — the exact gate model — so
running `check_evals` **locally** IS a local Haiku eval, executed through the same `AgentSDKHost`
the dispatch uses. It therefore emits the **identical FR-035 artifact set** (SPEC §11.8 / AD-025):

    python scripts/check_evals.py --only <id[,id…]> --transcripts-dir evals/_runs/<stamp> --root .
    python scripts/summarize_run.py evals/_runs/<stamp>          # measured cost / steps / per-episode

    evals/_runs/<stamp>/<id>.<run>.json                   # EpisodeTranscript (FR-032)
    evals/_runs/<stamp>/messages/<id>.<run>.messages.json # WHOLE host transcript (FR-035)
    evals/_runs/<stamp>/run_summary.json                  # tokens, MEASURED cost, steps-by-category
    evals/_runs/<stamp>/report.json                       # majority + red

Byte-for-byte the layout the dispatch uploads as `eval-transcripts`. `evals/_runs/` is git-ignored.
Needs a funded `ANTHROPIC_API_KEY`. On Apple silicon the repo `.venv` is x86_64 and the SDK's CLI
fails under Rosetta — use a native arm64 venv (`uv venv --python 3.11` + `uv pip install -e
".[evals]"`) and activate it so the model's Bash resolves `python -m transon_authoring`.

Omit `--only` for the whole corpus. A subset that omits a whole bucket makes the aggregate
red-by-construction — expected: the telemetry, not the verdict, is the point of a probe.

## Path B — subagent fan-out (fast, but produces NO cost/transcripts)

One sandboxed `Agent(model="haiku")` episode per fixture, scored with the real
`check_evals.score_episode` (schema-valid + independent re-verify — AD-004). Parallel and cheap to
orchestrate, but the Agent tool exposes **no token usage, no cost, and no message stream** to the
driver, so this path **cannot** emit the FR-035 whole-transcript / `run_summary.json` artifacts —
only pass/fail scores. Use it as a quick indicative pre-check; use Path A whenever you need cost,
transcripts, or CI-comparable numbers. Its no-repo-read sandbox is **instruction-enforced, not a
jail**. The deterministic halves live in `scripts/local_eval.py` (`setup` / `score`).

## Run Path B (Workflow — recommended)

Pick a fresh empty temp dir `$DIR` outside the repo (e.g. under the session scratchpad), then invoke
the bundled workflow — it does setup → parallel Haiku fan-out → score in one run, and returns the
scored report:

    Workflow(name: "local-haiku-eval", args: { repo: "<repo root abs path>", dir: "$DIR" })

Optional `args`: `only: ["ec2", "stripe"]` (id-prefix filter) and `limit: N`. The workflow's
`parallel()` fan-out runs every fixture's episode concurrently with the runner's automatic
concurrency cap (~`min(16, cores−2)`) and retries transient failures — no hand-managed waves. Relay
the returned report (per-fixture PASS/FAIL table + per-bucket authoring/adversarial/correction
rates) and call out any non-pass fixtures. `.claude/workflows/local-haiku-eval.js` is the script.

## Manual fallback (no Workflow)

1. **Set up workspaces.** `python scripts/local_eval.py setup --out "$DIR"` (optionally `--only …`
   / `--limit N`). It writes one workspace per fixture (`SKILL.md` + `task.md` + `samples.json` when
   supplied) and `$DIR/manifest.json`, and prints `<fixture-id>\t<workspace>` per fixture.
2. **Fan out.** For EACH workspace spawn `Agent(model="haiku", subagent_type="general-purpose",
   run_in_background: true)` with:
   > Read `<workspace>/task.md` IN FULL first and do EXACTLY what it says, following the `SKILL.md`
   > in that same workspace. Your workspace is `<workspace>`. Write your graded `result.json` there.
   > Do not read any file outside your workspace except via the `transon_authoring` CLI.
   Background agents run in parallel; launch them all at once (wave ~8–16 if you hit Haiku 429
   throttling or CPU contention from the many `python -m transon_authoring` subprocesses).
3. **Wait.** `deadline=$((SECONDS+1800)); while [ "$(ls "$DIR"/*/result.json 2>/dev/null | wc -l)" -lt N ] && [ $SECONDS -lt $deadline ]; do sleep 10; done` (N = fixture count).
4. **Score.** `python scripts/local_eval.py score --dir "$DIR"` (add `--json` for a machine summary).

## Notes

- `model: "haiku"` resolves to `claude-haiku-4-5-20251001` — the exact NFR-010 gate pin.
- Leak check (optional): each workspace should hold only `SKILL.md`, `task.md`, `samples.json?`,
  `template.json?`, `result.json`, and possibly `metadata.json` — the agent's own
  `transon_authoring metadata` CLI dump (allowed grounding), never a copied repo answer file.
- A matched fixture the model fails is a valid, useful result (drives SKILL.md improvement); a
  refuse fixture must require a genuinely engine-absent capability (AD-023).
- Re-score a prior run without re-running the episodes: just run `score --dir "$DIR"` again.
