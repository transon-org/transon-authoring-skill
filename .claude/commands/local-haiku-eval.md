---
description: Run the committed eval corpus locally through the Haiku gate model (non-normative, not the §11.8 gate).
argument-hint: "[optional: --only ec2 stripe | --limit N]"
---

Run a **local, non-normative** Haiku eval over the committed `evals/cases/` corpus: $ARGUMENTS

The procedure is tool-neutral and lives in `harness/commands/local-haiku-eval.md` — follow it
exactly. Preferred path: pick a fresh temp dir `$DIR` outside the repo and invoke the bundled
workflow, which does setup → parallel Haiku fan-out → score in one run:

    Workflow(name: "local-haiku-eval", args: { repo: "<repo root abs path>", dir: "$DIR" })

(pass `only: [...]` / `limit: N` from $ARGUMENTS when given). The workflow
(`.claude/workflows/local-haiku-eval.js`) fans out one sandboxed `Agent(model="haiku")` episode per
fixture in parallel with the runner's automatic concurrency cap, then scores with the real
`check_evals.score_episode`; relay its returned report. If a workflow can't be run, use the manual
`scripts/local_eval.py setup`/spawn/wait/`score` fallback in the harness body.

This uses `claude-haiku-4-5-20251001` (the NFR-010 pin) but is an INDICATIVE pre-check only — not the
credentialed §11.8 gate (`scripts/eval_harness.py` + `evals/runner.json`), its no-repo-read sandbox
is instruction-enforced, and it never updates `evals/baseline.json`.
