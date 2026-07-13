#!/usr/bin/env python3
"""Observed prompt-cache A/B on ONE fixture against the pinned Anthropic model.

Runs the same fixture through the SAME tool loop twice — cache ON (the shipped
`with_cache_control`) and cache OFF — and reads the REAL token `usage` off the
API for each (input / cache_read / cache_write / output). This is the observed
measurement (not a model): prompt caching is semantically transparent, so both
runs do identical authoring work; only the billed token categories differ.

Costs a small amount of real money (one fixture, two episodes). Needs the
`anthropic` SDK (the `[evals]` extra) and a credential the SDK can resolve
(ANTHROPIC_API_KEY, or an `ant auth login` profile).

    ANTHROPIC_API_KEY=sk-... python scripts/cache_ab.py --fixture seed-matched-flatten-orders
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_evals  # noqa: E402
import eval_harness  # noqa: E402

#: Anthropic Haiku 4.5 pin rates ($/MTok).
_RATES = {"input": 1.00, "cache_read": 0.10, "cache_write": 1.25, "output": 5.00}


def _cost(tok: dict[str, int]) -> float:
    return (
        tok.get("input", 0) / 1e6 * _RATES["input"]
        + tok.get("cache_read", 0) / 1e6 * _RATES["cache_read"]
        + tok.get("cache_creation", 0) / 1e6 * _RATES["cache_write"]
        + tok.get("output", 0) / 1e6 * _RATES["output"]
    )


def _run(fixture: dict[str, Any], runner_cfg: dict[str, Any], repo_root: Path,
         use_cache: bool) -> dict[str, Any]:
    provider = eval_harness.AnthropicProvider(runner_cfg, use_cache=use_cache)
    t0 = time.monotonic()
    episode = eval_harness.run_fixture(fixture, runner_cfg, provider, repo_root)
    dt = time.monotonic() - t0
    score = check_evals.score_episode(fixture, episode)
    return {"episode": episode, "score": score, "seconds": dt}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cache_ab")
    parser.add_argument("--fixture", default="seed-matched-flatten-orders",
                        help="fixture id under evals/cases/ (default: a Haiku-pass one)")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    evals_dir = repo_root / "evals"
    runner_cfg = json.loads((evals_dir / "runner.json").read_text(encoding="utf-8"))
    path = evals_dir / "cases" / f"{args.fixture}.json"
    if not path.exists():
        print(f"cache_ab: no such fixture: {path}", file=sys.stderr)
        return 2
    fixture = json.loads(path.read_text(encoding="utf-8"))

    print(f"# Observed prompt-cache A/B — fixture={args.fixture} "
          f"model={runner_cfg['model_id']}", file=sys.stderr)
    print("# cache OFF run…", file=sys.stderr, flush=True)
    off = _run(fixture, runner_cfg, repo_root, use_cache=False)
    print(f"#   outcome={off['episode']['outcome']} score={off['score']} "
          f"turns={off['episode']['tokens']['turns']} ({off['seconds']:.0f}s)",
          file=sys.stderr, flush=True)
    print("# cache ON run…", file=sys.stderr, flush=True)
    on = _run(fixture, runner_cfg, repo_root, use_cache=True)
    print(f"#   outcome={on['episode']['outcome']} score={on['score']} "
          f"turns={on['episode']['tokens']['turns']} ({on['seconds']:.0f}s)",
          file=sys.stderr, flush=True)

    t_off = off["episode"]["tokens"]
    t_on = on["episode"]["tokens"]
    c_off, c_on = _cost(t_off), _cost(t_on)

    print("\n==== OBSERVED token spend — CACHE OFF vs CACHE ON (real Haiku usage) ====",
          file=sys.stderr)
    print(f"{'category':<14}{'rate/MTok':>11}{'CACHE OFF':>14}{'CACHE ON':>14}",
          file=sys.stderr)
    labels = {"input": ("input", "$1.00"), "cache_read": ("cache_read", "$0.10"),
              "cache_creation": ("cache_write", "$1.25"), "output": ("output", "$5.00")}
    for key, (name, rate) in labels.items():
        print(f"{name:<14}{rate:>11}{t_off.get(key, 0):>14,}{t_on.get(key, 0):>14,}",
              file=sys.stderr)
    print("-" * 53, file=sys.stderr)
    print(f"{'COST':<14}{'':>11}{('$%.4f' % c_off):>14}{('$%.4f' % c_on):>14}",
          file=sys.stderr)
    saved = 0.0 if not c_off else 1 - c_on / c_off
    print(f"scores: OFF={off['score']} ON={on['score']}  "
          f"=> caching saved {saved:.0%} on this fixture (observed)",
          file=sys.stderr, flush=True)

    print(json.dumps({
        "fixture": args.fixture, "model": runner_cfg["model_id"],
        "cache_off": {"tokens": t_off, "cost": round(c_off, 6), "score": off["score"]},
        "cache_on": {"tokens": t_on, "cost": round(c_on, 6), "score": on["score"]},
        "savings_pct": saved,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
