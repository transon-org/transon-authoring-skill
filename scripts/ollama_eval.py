#!/usr/bin/env python3
"""NON-NORMATIVE local eval over an OpenAI-compatible endpoint (e.g. Ollama).

**This is NOT the SPEC §11.8 gate.** The normative NFR-010 gate is
``scripts/check_evals.py`` driving ``eval_harness.AnthropicProvider`` under the
``evals/runner.json`` pin (``claude-haiku-4-5``), run in the credential-holding
dispatch workflow. This command is an *indicative, offline* pre-check: it drives
the **same** ``eval_harness.run_fixture`` tool loop and scores with the **same**
``check_evals.score_episode`` (schema-valid + independent engine re-verify,
AD-004), but against a local OpenAI-compatible model instead of the pinned
provider. It never touches ``evals/baseline.json`` and closes no DoD.

A poor score here reflects the **local model**, not ``SKILL.md`` — small local
models are far weaker than the pinned Haiku at the agentic authoring loop. Use
it for plumbing checks, gross prompt bugs, and free offline iteration.

Live per-episode progress, per-episode wall time, and token counts are printed
to stderr; a machine-readable summary is printed to stdout at the end.

Examples::

    python scripts/ollama_eval.py --model qwen2.5-coder:32b --limit 2
    python scripts/ollama_eval.py --only ec2 stripe --runs 1
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_evals  # noqa: E402  (sibling script; provides score_episode/_majority)
import eval_harness  # noqa: E402  (sibling script; run_fixture + providers)

#: fixture ``expect`` value → report bucket name (mirrors SPEC §11.8 buckets).
_BUCKET = {
    "matched": "authoring",
    "refuse": "adversarial",
    "matched_correction": "correction",
}

#: Anthropic Haiku 4.5 pin rates ($/MTok) — the billed §11.8 gate model. Local
#: Ollama tokens are free; these rates are applied to the *real measured token
#: structure* to compare cached vs uncached spend on the normative path.
_HAIKU = {"input": 1.00, "cache_read": 0.10, "cache_write": 1.25, "output": 5.00}


def cache_comparison(episode_tokens: list[dict[str, int]]) -> dict[str, Any]:
    """Compute uncached vs prompt-cached token spend from real per-episode token
    structure, at Haiku rates. Model (stated): in this re-send-heavy tool loop
    every input token is either **written once** or **re-read**, so input splits
    with no leftover "regular" input (conservation: write + read == total in):

    - ``cache_write`` = each episode establishes its full final prefix once
      (``Σ last_input``); the ~constant system+tools block ``S`` is shared, so it
      is written once, not per-episode → subtract ``(N-1)·S``.
    - ``cache_read``  = everything re-read = ``total_input - cache_write``
      = within-episode prefix re-reads + the shared system re-read each episode.

    Prompt caching is semantically transparent, so the *token structure* is the
    same whether or not ``cache_control`` is sent — only the billing differs.
    """
    eps = [t for t in episode_tokens if t.get("turns", 0) > 0]
    N = len(eps)
    total_in = sum(t["input"] for t in eps)
    total_out = sum(t["output"] for t in eps)
    sum_last = sum(t["last_input"] for t in eps)
    firsts = sorted(t["first_input"] for t in eps)
    S = firsts[len(firsts) // 2] if firsts else 0  # median shared system prefix
    cache_write = max(sum_last - (N - 1) * S, 0)
    cache_read = max(total_in - cache_write, 0)

    def cost(inp: int, cr: int, cw: int, out: int) -> float:
        return (
            inp / 1e6 * _HAIKU["input"]
            + cr / 1e6 * _HAIKU["cache_read"]
            + cw / 1e6 * _HAIKU["cache_write"]
            + out / 1e6 * _HAIKU["output"]
        )

    uncached = {"input": total_in, "cache_read": 0, "cache_write": 0, "output": total_out}
    cached = {"input": 0, "cache_read": cache_read, "cache_write": cache_write, "output": total_out}
    uncached["cost"] = cost(total_in, 0, 0, total_out)
    cached["cost"] = cost(0, cache_read, cache_write, total_out)
    return {
        "episodes": N,
        "shared_system_prefix_S": S,
        "uncached": uncached,
        "cached": cached,
        "savings_pct": (
            0.0 if not uncached["cost"] else 1 - cached["cost"] / uncached["cost"]
        ),
    }


def load_fixtures(
    evals_dir: Path, only: list[str] | None, limit: int | None
) -> list[dict[str, Any]]:
    fixtures = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((evals_dir / "cases").glob("*.json"))
    ]
    if only:
        prefixes = tuple(only)
        fixtures = [f for f in fixtures if f["id"].startswith(prefixes)]
    if limit is not None:
        fixtures = fixtures[:limit]
    return fixtures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ollama_eval",
        description="NON-NORMATIVE local eval over an OpenAI-compatible endpoint "
        "(not the §11.8 gate; baseline never touched).",
    )
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--model", default="qwen2.5-coder:32b")
    parser.add_argument("--runs", type=int, default=1, help="episodes per fixture")
    parser.add_argument("--limit", type=int, default=None, help="cap fixture count")
    parser.add_argument(
        "--only", nargs="*", default=None, help="keep only ids with these prefixes"
    )
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--tool-budget", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    evals_dir = repo_root / "evals"
    runner_full = json.loads((evals_dir / "runner.json").read_text(encoding="utf-8"))
    max_tokens = args.max_tokens or runner_full["max_output_tokens"]
    tool_budget = args.tool_budget or runner_full["tool_budget"]
    # run_fixture only reads runner_cfg["tool_budget"]; the provider carries the
    # model/max_tokens. Mirror the other keys for parity.
    runner_cfg = {
        "provider": "openai",
        "model_id": args.model,
        "max_output_tokens": max_tokens,
        "tool_budget": tool_budget,
        "seed": None,
    }

    fixtures = load_fixtures(evals_dir, args.only, args.limit)
    provider = eval_harness.OpenAICompatibleProvider(
        args.base_url, args.model, max_tokens, timeout=args.timeout
    )

    print(
        f"# NON-NORMATIVE local eval — model={args.model} endpoint={args.base_url}",
        file=sys.stderr,
    )
    print(
        f"# {len(fixtures)} fixture(s) x {args.runs} run(s); tool_budget={tool_budget} "
        f"max_tokens={max_tokens}. NOT the §11.8 gate; baseline untouched.",
        file=sys.stderr,
        flush=True,
    )

    results: list[dict[str, Any]] = []
    totals = {"input": 0, "output": 0}
    episode_tokens: list[dict[str, int]] = []
    t_start = time.monotonic()
    for i, fixture in enumerate(fixtures, 1):
        scores: list[str] = []
        fx_tokens = {"input": 0, "output": 0}
        for j in range(args.runs):
            t0 = time.monotonic()
            episode = eval_harness.run_fixture(fixture, runner_cfg, provider, repo_root)
            dt = time.monotonic() - t0
            score = check_evals.score_episode(fixture, episode)
            scores.append(score)
            tok = episode.get("tokens") or {}
            episode_tokens.append(dict(tok))
            for key in ("input", "output"):
                fx_tokens[key] += int(tok.get(key, 0) or 0)
                totals[key] += int(tok.get(key, 0) or 0)
            note = f" [{episode['error']}]" if episode.get("error") else ""
            print(
                f"[{i}/{len(fixtures)}] {fixture['id']} run {j + 1}/{args.runs}: "
                f"{episode['outcome']} -> {score.upper()}  "
                f"({dt:.0f}s, {tok.get('turns', 0)} turns, "
                f"in={tok.get('input', 0):,} out={tok.get('output', 0):,}){note}",
                file=sys.stderr,
                flush=True,
            )
        results.append(
            {
                "id": fixture["id"],
                "expect": fixture["expect"],
                "bucket": _BUCKET.get(fixture["expect"], fixture["expect"]),
                "scores": scores,
                "majority": check_evals._majority(scores),
                "tokens": fx_tokens,
            }
        )
    wall = time.monotonic() - t_start

    # Per-bucket rates (infra excluded from the denominator, §11.8).
    by_bucket: dict[str, list[str]] = defaultdict(list)
    for r in results:
        by_bucket[r["bucket"]].append(r["majority"])
    bucket_rates: dict[str, dict[str, Any]] = {}
    for bucket, majors in by_bucket.items():
        scored = [m for m in majors if m != "infra"]
        passed = sum(1 for m in scored if m == "pass")
        bucket_rates[bucket] = {
            "pass": passed,
            "scored": len(scored),
            "infra": sum(1 for m in majors if m == "infra"),
            "total": len(majors),
            "rate": (passed / len(scored)) if scored else None,
        }

    print("\n==== NON-NORMATIVE local eval results ====", file=sys.stderr)
    for r in results:
        print(
            f"{r['id']:<50} {r['expect']:<18} {r['majority'].upper():<6} "
            f"{'/'.join(r['scores'])}",
            file=sys.stderr,
        )
    print("-" * 92, file=sys.stderr)
    for bucket in sorted(bucket_rates):
        b = bucket_rates[bucket]
        rate = "n/a" if b["rate"] is None else f"{b['rate']:.0%}"
        print(
            f"{bucket:<12}: pass={b['pass']} scored={b['scored']} "
            f"infra={b['infra']} total={b['total']} -> {rate}",
            file=sys.stderr,
        )
    print(
        f"\ntotal tokens: in={totals['input']:,} out={totals['output']:,}  "
        f"wall={wall / 60:.1f} min  (NON-NORMATIVE — not the §11.8 gate)",
        file=sys.stderr,
        flush=True,
    )

    # Cache comparison: real measured token structure priced at Haiku gate rates,
    # uncached vs prompt-cached (the token STRUCTURE is caching-invariant; only
    # the billing category changes). This is the normative-path cost delta the
    # caching fix buys — Ollama itself is free and ignores cache_control.
    cmp = cache_comparison(episode_tokens)
    u, c = cmp["uncached"], cmp["cached"]
    print(
        "\n==== token spend by category — UNCACHED vs PROMPT-CACHED "
        "(priced at Haiku 4.5 rates; local Ollama tokens are free) ====",
        file=sys.stderr,
    )
    print(
        f"{'category':<14}{'rate/MTok':>11}{'UNCACHED tok':>16}{'CACHED tok':>16}",
        file=sys.stderr,
    )
    rate_label = {
        "input": "$1.00", "cache_read": "$0.10", "cache_write": "$1.25", "output": "$5.00",
    }
    for cat in ("input", "cache_read", "cache_write", "output"):
        print(
            f"{cat:<14}{rate_label[cat]:>11}{u[cat]:>16,}{c[cat]:>16,}",
            file=sys.stderr,
        )
    print("-" * 57, file=sys.stderr)
    print(
        f"{'COST':<14}{'':>11}{('$%.4f' % u['cost']):>16}{('$%.4f' % c['cost']):>16}",
        file=sys.stderr,
    )
    print(
        f"episodes={cmp['episodes']}  shared_system_prefix≈{cmp['shared_system_prefix_S']:,} tok  "
        f"=> caching saves {cmp['savings_pct']:.0%} on this corpus",
        file=sys.stderr,
        flush=True,
    )

    print(
        json.dumps(
            {
                "non_normative": True,
                "model": args.model,
                "buckets": bucket_rates,
                "tokens": totals,
                "cache_comparison_haiku_rates": cmp,
                "wall_seconds": round(wall, 1),
                "fixtures": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
