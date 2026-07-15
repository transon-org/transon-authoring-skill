"""FR-035 — render a run's observability artifacts as Markdown.

Reads the ``run_summary.json`` a full/subset ``check_evals --transcripts-dir``
run writes (SPEC §11.8 / AD-025) and prints a Markdown digest: measured cost
(the host's ``total_cost_usd`` — never a list-price estimate), token totals with
the prompt-cache ratio, the tool-call histogram (steps by category), per-fixture
normalization, and a per-episode table (the intermediate results).

Optionally folds in the gate ``report.json`` (majority + red reasons) when it
sits beside the summary or is passed with ``--report``.

Used by the dispatch workflows to publish a job summary, and runnable locally
against any ``evals/_runs/<stamp>/`` directory:

    python3 scripts/summarize_run.py evals/_runs/<stamp>

Pure presentation over artifacts that gate nothing (AC-034 / AC-038): this
changes no scoring, target, baseline, or lint semantics.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

#: The four §11.8 harness outcome classes, in report order.
_OUTCOMES = ("submitted", "no_submit", "budget_exceeded", "infra_error")


def _fmt_usd(value: Any) -> str:
    try:
        return f"${float(value):.4f}"
    except (TypeError, ValueError):
        return "n/a"


def _cell(value: Any) -> str:
    """Escape a value for a GitHub-Flavored-Markdown table cell: a literal `|`
    would otherwise be read as a column delimiter and misalign every following
    row. Engine error text is passed through verbatim (SPEC §11.5) and can carry
    `|`, so any interpolated string value must go through this."""
    return str(value).replace("|", "\\|")


def _histogram(mapping: dict[str, int]) -> str:
    if not mapping:
        return "—"
    return ", ".join(
        f"`{name}`={count}"
        for name, count in sorted(mapping.items(), key=lambda kv: (-kv[1], kv[0]))
    )


def render(summary: dict[str, Any], report: dict[str, Any] | None = None) -> str:
    """Render the Markdown digest. Pure — no I/O, so it is unit-testable."""
    totals = summary["totals"]
    tokens = totals["tokens"]
    harness = summary.get("harness") or {}
    prompt_tokens = (
        tokens["input"] + tokens["cache_read"] + tokens["cache_creation"]
    )
    cache_pct = (tokens["cache_read"] / prompt_tokens * 100) if prompt_tokens else 0.0

    lines: list[str] = []
    lines.append(
        f"### Eval run — `{summary['model_id']}` "
        f"({harness.get('kind', '?')} {harness.get('version', '?')}, "
        f"×{summary['runs_per_fixture']})"
    )
    lines.append("")
    lines.append(
        f"- **cost (measured, host `total_cost_usd`):** "
        f"**{_fmt_usd(totals['cost_usd'])}**"
    )
    outcomes = totals["outcomes"]
    lines.append(
        f"- **episodes:** {totals['episodes']} · "
        + " · ".join(f"{k}={outcomes.get(k, 0)}" for k in _OUTCOMES)
        + f" · errors={totals['errors']}"
    )
    lines.append(
        f"- **tokens:** in={tokens['input']:,} out={tokens['output']:,} "
        f"cache_read={tokens['cache_read']:,} cache_write={tokens['cache_creation']:,} "
        f"(prompt cache hit {cache_pct:.1f}%)"
    )
    lines.append(
        f"- **steps:** {totals['steps']} · by category: "
        f"{_histogram(totals['steps_by_category'])}"
    )

    fixtures_report = (report or {}).get("fixtures", {})
    reds = (report or {}).get("red", [])
    if reds:
        lines.append(f"- **red:** {'; '.join(reds)}")

    # Per-fixture normalization.
    lines.append("")
    lines.append("| fixture | bytes | majority | cost | $/episode | steps/ep | cache% |")
    lines.append("|---|--:|---|--:|--:|--:|--:|")
    for fid, fx in sorted(
        summary["by_fixture"].items(), key=lambda kv: kv[1]["fixture_bytes"]
    ):
        majority = (fixtures_report.get(fid) or {}).get("majority", "—")
        lines.append(
            f"| `{_cell(fid)}` | {fx['fixture_bytes']:,} | {_cell(majority)} | "
            f"{_fmt_usd(fx['cost_usd_total'])} | {_fmt_usd(fx['cost_usd_mean'])} | "
            f"{fx['steps_mean']:.1f} | {fx['cache_read_ratio'] * 100:.1f}% |"
        )

    # Per-episode intermediate results.
    lines.append("")
    lines.append("<details><summary>per-episode results</summary>")
    lines.append("")
    lines.append("| fixture | run | outcome | cost | steps | out tok | error |")
    lines.append("|---|--:|---|--:|--:|--:|---|")
    for ep in summary["episodes"]:
        error = ep.get("error") or ""
        if len(error) > 60:
            error = error[:57] + "…"
        lines.append(
            f"| `{_cell(ep['fixture_id'])}` | {ep['run_index']} | {_cell(ep['outcome'])} | "
            f"{_fmt_usd(ep['cost_usd'])} | {ep['steps']} | "
            f"{ep['tokens']['output']:,} | {_cell(error)} |"
        )
    lines.append("")
    lines.append("</details>")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="summarize_run",
        description="Render a check_evals run's FR-035 artifacts as Markdown.",
    )
    parser.add_argument(
        "transcripts_dir",
        type=Path,
        help="the --transcripts-dir a check_evals run wrote (holds run_summary.json)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="gate report.json (majority + red); defaults to <dir>/report.json if present",
    )
    args = parser.parse_args(argv)

    summary_path = args.transcripts_dir / "run_summary.json"
    if not summary_path.is_file():
        print(
            f"summarize-run: no run_summary.json under {args.transcripts_dir} "
            "(was the run given --transcripts-dir?)",
            file=sys.stderr,
        )
        return 1
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    report_path = args.report or (args.transcripts_dir / "report.json")
    report = None
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except ValueError:
            report = None

    print(render(summary, report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
