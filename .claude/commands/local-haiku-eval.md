---
description: Run the committed eval corpus locally through the Haiku gate model (non-normative, not the §11.8 gate).
argument-hint: "[optional: --only ec2 stripe | --limit N]"
---

Run a **local, non-normative** Haiku eval over the committed `evals/cases/` corpus: $ARGUMENTS

The procedure is tool-neutral and lives in `harness/commands/local-haiku-eval.md` — follow it
exactly. In short: `python scripts/local_eval.py setup --out $DIR` to build one sandboxed workspace
per fixture, then spawn one `Agent(model="haiku")` episode per workspace (background, in batches),
wait until every workspace has a `result.json`, and finally `python scripts/local_eval.py score
--dir $DIR` to score with the real `check_evals.score_episode` and report per-bucket rates.

This uses `claude-haiku-4-5-20251001` (the NFR-010 pin) but is an INDICATIVE pre-check only — it is
not the credentialed §11.8 gate (`scripts/eval_harness.py` + `evals/runner.json` in the dispatch
workflow), its no-repo-read sandbox is instruction-enforced, and it never updates
`evals/baseline.json`.
