#!/usr/bin/env python
"""local_eval.py — NON-NORMATIVE local Haiku eval driver (setup + score).

Reproduces the sandboxed local eval used interactively: each committed
``evals/cases/*.json`` fixture becomes a per-fixture temp workspace that a
Claude Code ``Agent(model="haiku")`` episode solves using ONLY the
``transon_authoring`` CLI, then results are scored with the real
``check_evals.score_episode`` (schema-valid + independent re-verify — AD-004).

This is NOT the credentialed §11.8 gate (that is the anthropic-SDK harness in
``scripts/eval_harness.py`` under ``evals/runner.json``). It is an *indicative*
pre-check, and its no-repo-read sandbox is instruction-enforced, not a jail.

The agent fan-out itself is driven by the orchestrating model (see the
``/local-haiku-eval`` command) — a plain script cannot spawn Agent subagents.
This module only does the deterministic halves:

  setup --out DIR [--only PREFIX ...] [--limit N]
      Build one sandbox workspace per fixture (SKILL.md + samples.json + task.md)
      and write DIR/manifest.json. Prints "<id>\\t<workspace>" per fixture.
  score --dir DIR [--json]
      Read each workspace's result.json, score it, print a per-fixture table +
      per-bucket rates (+ optional JSON summary on stdout).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VENV_PY = REPO / ".venv" / "bin" / "python"
PY = str(VENV_PY if VENV_PY.exists() else sys.executable)

BUCKET = {"matched": "authoring", "refuse": "adversarial",
          "matched_correction": "correction"}

TASK_TEMPLATE = """\
# Local eval task (non-interactive CI: never prompt, never create a config file)

Your ENTIRE operating procedure is the skill document at {ws}/SKILL.md — read it
FIRST and follow it exactly, section by section, including its Result section's
exact required AuthoringResult envelope fields.

USER INTENT to fulfil:
{intent}

{samples_line}

STRICT sandbox rules (violating any invalidates the evaluation):
- Your workspace is {ws}. Write EVERY file only inside it.
- For ALL Transon grounding and verification, invoke the CLI exactly as:
    {py} -m transon_authoring <args>
  e.g. metadata ; examples search <query> ; check-samples --samples {ws}/samples.json ;
  verify --template {ws}/template.json --samples {ws}/samples.json . Use absolute paths for flags.
- You may READ only these files in your workspace: {readable}. You must NOT read, cat, grep,
  open, or list ANY file under {repo} (the repository) — no evals/, tests/, src/, docs/, seeds/,
  no example/fixture/answer files. Consult Transon ONLY via the examples-search / metadata CLI.
  Reading any repository answer file is cheating and voids the result.
- No network.

Verify gate: success ONLY when verify reports ok:true AND assurance:"matched"; repair using the
verbatim engine errors/diff up to the default budget; never return an unverified template. If the
capability is genuinely ungroundable, refuse (ok:false, status:"aborted", name the missing
capability; never invent names).

Finish by writing your single final AuthoringResult JSON (ALL required envelope fields) to
{ws}/result.json — that file is the graded artifact.
"""


def _fixture_paths(only: list[str], limit: int | None) -> list[Path]:
    paths = sorted((REPO / "evals" / "cases").glob("*.json"))
    if only:
        paths = [p for p in paths if any(p.stem.startswith(pref) for pref in only)]
    return paths[:limit] if limit else paths


def setup(out: Path, only: list[str], limit: int | None) -> int:
    out.mkdir(parents=True, exist_ok=True)
    skill = (REPO / "SKILL.md").read_text(encoding="utf-8")
    manifest = []
    for path in _fixture_paths(only, limit):
        fx = json.loads(path.read_text(encoding="utf-8"))
        fid = fx["id"]
        ws = out / fid
        ws.mkdir(exist_ok=True)
        (ws / "SKILL.md").write_text(skill, encoding="utf-8")
        has_samples = "samples" in fx
        if has_samples:
            (ws / "samples.json").write_text(
                json.dumps(fx["samples"], ensure_ascii=False, indent=2), encoding="utf-8")
            samples_line = (f"A confirmed, coverage-complete SampleSet is provided at "
                            f"{ws}/samples.json . Because samples are supplied, SKIP the "
                            "sample-loop/config steps; study the cases and go straight to "
                            "grounding, drafting, verifying and repairing.")
            readable = "SKILL.md and samples.json"
        else:
            samples_line = ("NO SampleSet is provided. Ground the request against the pinned "
                            "snapshot; if the requested capability cannot be grounded, REFUSE per "
                            "the skill doc 'Ground & refuse' section.")
            readable = "SKILL.md"
        (ws / "task.md").write_text(TASK_TEMPLATE.format(
            ws=ws, intent=fx["intent_nl"], samples_line=samples_line, readable=readable,
            py=PY, repo=REPO), encoding="utf-8")
        manifest.append({"id": fid, "expect": fx["expect"], "ws": str(ws),
                         "samples": has_samples})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"# prepared {len(manifest)} sandbox workspaces under {out}", file=sys.stderr)
    for m in manifest:
        print(f"{m['id']}\t{m['ws']}")
    return 0


def score(dir_: Path, as_json: bool) -> int:
    sys.path.insert(0, str(REPO / "scripts"))
    sys.path.insert(0, str(REPO / "src"))
    from check_evals import score_episode  # noqa: E402
    from transon_authoring._ingress import schema_violations  # noqa: E402

    manifest = json.loads((dir_ / "manifest.json").read_text(encoding="utf-8"))
    tally: dict[str, Counter] = defaultdict(Counter)
    rows, fails = [], []
    for m in manifest:
        fid, expect = m["id"], m["expect"]
        bucket = BUCKET[expect]
        fixture = json.loads((REPO / "evals" / "cases" / f"{fid}.json").read_text())
        rp = Path(m["ws"]) / "result.json"
        if not rp.exists():
            tally[bucket]["missing"] += 1
            rows.append((fid, expect, "NO-RESULT", "")); fails.append((fid, "no result.json"))
            continue
        try:
            submitted = json.loads(rp.read_text(encoding="utf-8"))
        except Exception as exc:
            tally[bucket]["fail"] += 1
            rows.append((fid, expect, "UNPARSEABLE", str(exc)[:40])); fails.append((fid, str(exc)))
            continue
        episode = {"submitted": submitted, "outcome": "submitted", "tool_calls": 1, "error": None}
        sc = score_episode(fixture, episode)
        tally[bucket][sc] += 1
        sv = schema_violations(submitted, "authoring_result.json") if isinstance(submitted, dict) else ["x"]
        status = submitted.get("status") if isinstance(submitted, dict) else "?"
        rows.append((fid, expect, sc.upper(), (f"schema-invalid({len(sv)}) " if sv else "") + f"status={status}"))
        if sc != "pass":
            fails.append((fid, f"score={sc} status={status}"))

    print(f"{'fixture':40} {'expect':18} {'SCORE':11} notes")
    print("-" * 100)
    for fid, expect, sc, note in rows:
        print(f"{fid:40} {expect:18} {sc:11} {note}")
    print("-" * 100)
    summary = {"buckets": {}, "fails": [f[0] for f in fails]}
    for expect, bucket in (("matched", "authoring"), ("refuse", "adversarial"),
                           ("matched_correction", "correction")):
        c = tally[bucket]
        scored = c["pass"] + c["fail"]
        rate = (c["pass"] / scored) if scored else None
        summary["buckets"][bucket] = {"pass": c["pass"], "fail": c["fail"],
                                      "missing": c["missing"], "infra": c["infra"], "rate": rate}
        rstr = f"{c['pass']}/{scored} = {rate:.0%}" if scored else "n/a"
        print(f"{bucket:12} ({expect:18}): pass={c['pass']} fail={c['fail']} "
              f"missing={c['missing']} -> {rstr}")
    print("\nNON-NORMATIVE local eval (not the §11.8 credentialed gate).")
    if fails:
        print(f"\n{len(fails)} non-pass fixture(s): " + ", ".join(f[0] for f in fails))
    if as_json:
        print("\n" + json.dumps(summary, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="local_eval", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="build per-fixture sandbox workspaces + manifest")
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--only", nargs="*", default=[], help="fixture-id prefixes to include")
    s.add_argument("--limit", type=int, default=None)
    sc = sub.add_parser("score", help="score result.json files with check_evals.score_episode")
    sc.add_argument("--dir", type=Path, required=True)
    sc.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    if a.cmd == "setup":
        return setup(a.out.resolve(), a.only, a.limit)
    return score(a.dir.resolve(), a.json)


if __name__ == "__main__":
    sys.exit(main())
