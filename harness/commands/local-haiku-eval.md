# Local Haiku eval (non-normative)

Run the committed eval corpus through the **gate model** (`claude-haiku-4-5-20251001`) locally, the
way it was done interactively: one sandboxed `Agent(model="haiku")` episode per
`evals/cases/*.json` fixture, scored with the real `check_evals.score_episode` (schema-valid +
independent re-verify — AD-004).

**This is NOT the §11.8 gate.** The normative NFR-010 gate is the anthropic-SDK harness
(`scripts/eval_harness.py` + `scripts/check_evals.py`) under `evals/runner.json`, run ×3 with
credentials in the dispatch workflow. This command is an *indicative* pre-check; its no-repo-read
sandbox is **instruction-enforced, not a jail**. It does not update `evals/baseline.json` and does
not close any DoD.

`Agent` subagents can only be spawned by the orchestrating model, so a plain script can't do the
fan-out — this command drives it, delegating the deterministic halves to `scripts/local_eval.py`.

## Procedure

1. **Set up sandbox workspaces.** Pick a fresh temp dir `$DIR` outside the repo (e.g. under the
   session scratchpad). Run:
   `python scripts/local_eval.py setup --out "$DIR"`
   (optionally `--only ec2 stripe github` or `--limit N` for a subset). It writes one workspace per
   fixture (`SKILL.md` + `task.md` + `samples.json` when the fixture supplies one) and
   `$DIR/manifest.json`, and prints one `<fixture-id>\t<workspace>` line per fixture.

2. **Fan out one Haiku episode per fixture.** For EACH workspace, spawn
   `Agent(model="haiku", subagent_type="general-purpose", run_in_background: true)` with this prompt
   (substituting the absolute `<workspace>` path):
   > You are an automated agent under evaluation. Read `<workspace>/task.md` IN FULL first and do
   > EXACTLY what it says, following the `SKILL.md` in that same workspace. Your workspace is
   > `<workspace>`. Write your graded `result.json` there. Do not read any file outside your
   > workspace except via the `transon_authoring` CLI.
   All of these run **in parallel** — `run_in_background: true` agents execute concurrently across
   turns, and multiple `Agent` calls in one message start together. Spawn them all to run at once
   for maximum parallelism. The limit is not the Agent tool but (a) Haiku provider rate limits — a
   very wide simultaneous burst can hit 429s and back off, and (b) CPU contention from many
   concurrent `python -m transon_authoring` subprocesses — so if you see throttling, cap concurrency
   by launching in waves of ~8–16 (still parallel within each wave). For a guaranteed concurrency
   cap with deterministic fan-out, run it as a Workflow instead: `parallel(fixtures.map(f => () =>
   agent(<sandbox prompt>, {model: "haiku", agentType: "general-purpose"})))` (the Workflow runner
   caps concurrency at ~min(16, cores−2) automatically).

3. **Wait for completion.** Run a background waiter that exits when every workspace has a
   `result.json`, with a deadline — e.g.:
   `deadline=$((SECONDS+1800)); while [ "$(ls "$DIR"/*/result.json 2>/dev/null | wc -l)" -lt N ] && [ $SECONDS -lt $deadline ]; do sleep 10; done; echo done`
   (N = the fixture count from step 1). Do not poll the individual agent notifications.

4. **Score + report.** Run:
   `python scripts/local_eval.py score --dir "$DIR"`
   It prints a per-fixture PASS/FAIL/NO-RESULT table and per-bucket rates (authoring / adversarial /
   correction), using the real `score_episode` (matched ⇒ schema-valid + independent re-verify;
   refuse ⇒ a §11.5 refusal status). Add `--json` for a machine summary. Report the rates and list
   any non-pass fixtures.

## Notes

- `model: "haiku"` resolves to `claude-haiku-4-5-20251001` — the exact NFR-010 gate pin.
- Leak check (optional): each workspace should contain only `SKILL.md`, `task.md`, `samples.json?`,
  `template.json?`, `result.json`, and possibly `metadata.json` — the agent's own
  `transon_authoring metadata` CLI dump (allowed grounding), never a copied repo answer file.
- A matched fixture the model fails is a valid, useful result (drives SKILL.md improvement); a
  refuse fixture must require a genuinely engine-absent capability (AD-023).
- To score fixtures a previous run already produced (without re-running the agents), just re-run
  step 4 against the same `$DIR`.
