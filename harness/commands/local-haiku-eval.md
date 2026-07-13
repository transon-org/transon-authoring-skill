# Local Haiku eval (non-normative)

Run the committed eval corpus through the **gate model** (`claude-haiku-4-5-20251001`) locally: one
sandboxed `Agent(model="haiku")` episode per `evals/cases/*.json` fixture, scored with the real
`check_evals.score_episode` (schema-valid + independent re-verify — AD-004).

**This is NOT the §11.8 gate.** The normative NFR-010 gate is the anthropic-SDK harness
(`scripts/eval_harness.py` + `scripts/check_evals.py`) under `evals/runner.json`, run ×3 with
credentials in the dispatch workflow. This command is an *indicative* pre-check; its no-repo-read
sandbox is **instruction-enforced, not a jail**. It does not update `evals/baseline.json` and does
not close any DoD.

The deterministic halves live in `scripts/local_eval.py` (`setup` / `score`); the Haiku fan-out is
driven by the orchestrating model.

## Run it (Workflow — recommended)

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
