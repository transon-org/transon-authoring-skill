"""Shared helpers for maintainer scripts under ``scripts/`` (SPEC §10).

Stdlib-only — never imports ``transon_authoring`` — so dispatch-bundle
consumers (``summarize_run``, ``scan_transcripts``) keep working without the
package installed. Eval-policy-adjacent strings move here verbatim.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Optional

#: The additive per-episode token telemetry keys (FR-035 / AC-034).
TOKEN_KEYS = ("input", "output", "cache_read", "cache_creation", "turns")

#: The four §11.8 harness outcome classes, in report order.
OUTCOME_KEYS = ("submitted", "no_submit", "budget_exceeded", "infra_error")

#: Appended after fixture ``intent_nl`` when a SampleSet is present
#: (eval_harness / host_harness ``run_fixture`` — gate-identity string).
SAMPLES_PROMPT_SUFFIX = "\n\nA confirmed SampleSet is available at samples.json."

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent


def ensure_src() -> None:
    """Insert ``<repo>/src`` on ``sys.path`` only when ``transon_authoring`` is
    not already importable (SPEC §10 source-checkout fallback).

    Prefer an already-installed package (editable or wheel) over the checkout
    tree — same as the prior try/except ImportError pattern.
    """
    try:
        import transon_authoring  # noqa: F401
    except ImportError:  # pragma: no cover - source-checkout fallback
        src = str(_REPO_ROOT / "src")
        if src not in sys.path:
            sys.path.insert(0, src)


def import_sibling(name: str) -> Any:
    """Import a sibling module under ``scripts/`` (lazy; monkeypatchable).

    Tries a normal import first; on ``ImportError`` inserts this directory
    on ``sys.path`` and retries — same pattern the gate scripts used before
    this module existed.
    """
    try:
        return importlib.import_module(name)
    except ImportError:  # pragma: no cover - invoked outside scripts/
        scripts = str(_SCRIPTS_DIR)
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        return importlib.import_module(name)


def new_tokens() -> dict[str, int]:
    """Empty per-episode provider token usage dict (FR-035 telemetry)."""
    return {
        "input": 0,
        "output": 0,
        "cache_read": 0,
        "cache_creation": 0,
        "turns": 0,
    }


def usage_tokens(get) -> dict[str, int]:
    """Normalize provider usage via a ``get(key, default)`` callable into the
    four ``*_tokens`` fields (no ``turns`` — callers set that)."""
    return {
        "input": int(get("input_tokens", 0) or 0),
        "output": int(get("output_tokens", 0) or 0),
        "cache_read": int(get("cache_read_input_tokens", 0) or 0),
        "cache_creation": int(get("cache_creation_input_tokens", 0) or 0),
    }


def prepare_workspace(
    fixture: dict[str, Any], repo_root: Path, workspace: Path
) -> tuple[str, str]:
    """Read ``SKILL.md``, optionally write ``samples.json``, build the prompt.

    Returns ``(skill_md, prompt)``. Raises on I/O faults — callers classify
    those as ``infra_error`` (OQ-016d).
    """
    skill_md = (repo_root / "SKILL.md").read_bytes().decode("utf-8")
    prompt = fixture["intent_nl"]
    if fixture.get("samples") is not None:
        (workspace / "samples.json").write_text(
            json.dumps(fixture["samples"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        prompt += SAMPLES_PROMPT_SUFFIX
    return skill_md, prompt


def build_episode_result(
    *,
    outcome: str,
    submitted: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
    tool_calls: Optional[int] = None,
    tool_call_log: Optional[list[dict[str, Any]]] = None,
    tokens: Optional[dict[str, int]] = None,
    cost_usd: Optional[float] = None,
    messages: Optional[list[dict[str, Any]]] = None,
    include_fr035: bool = False,
) -> dict[str, Any]:
    """Build a §11.8 EpisodeResult dict.

    When *include_fr035* is False (raw loop), the dict matches
    ``eval_harness._episode_result`` exactly. When True (real host), also
    carries ``cost_usd`` and ``messages``.
    """
    log = tool_call_log if tool_call_log is not None else []
    count = tool_calls if tool_calls is not None else len(log)
    result: dict[str, Any] = {
        "submitted": submitted,
        "outcome": outcome,
        "tool_calls": count,
        "error": error,
        "tool_call_log": log,
        "tokens": tokens if tokens is not None else new_tokens(),
    }
    if include_fr035:
        result["cost_usd"] = cost_usd
        result["messages"] = messages if messages is not None else []
    return result


def cache_ratio(tokens: dict[str, Any]) -> tuple[int, float]:
    """Return ``(prompt_tokens, cache_read_ratio)`` for FR-035 roll-ups.

    ``prompt_tokens = input + cache_read + cache_creation``; ratio is
    ``cache_read / prompt_tokens`` (0.0 when prompt_tokens is 0).
    """
    prompt = int(tokens.get("input", 0) or 0) + int(
        tokens.get("cache_read", 0) or 0
    ) + int(tokens.get("cache_creation", 0) or 0)
    ratio = (int(tokens.get("cache_read", 0) or 0) / prompt) if prompt else 0.0
    return prompt, ratio


def report_failures(prog: str, failures: list[str], noun: str) -> int:
    """Print ``{prog}: FAIL: …`` lines + a count summary; return 0 or 1."""
    for message in failures:
        print(f"{prog}: FAIL: {message}", file=sys.stderr)
    if failures:
        print(f"{prog}: {len(failures)} {noun}", file=sys.stderr)
        return 1
    return 0


def examples_by_name(metadata: dict[str, Any]) -> dict[str, dict]:
    """Index ``metadata["docs"]["examples"]`` by ``name``."""
    return {entry["name"]: entry for entry in metadata["docs"]["examples"]}
