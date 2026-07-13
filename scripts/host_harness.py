"""FR-017 / NFR-010 / AD-024 / OQ-027 — real-host eval driver + adapter.

Runs one eval fixture as one episode in the **real host agent harness** the
skill ships into (SPEC §11.8 "Harness", AD-024) — the reference host is the
Claude Agent SDK, pinned by ``evals/runner.json`` ``harness = {kind, version}``.
This replaces the raw 3-tool ``messages.create`` loop
(:mod:`eval_harness`, now the OQ-027d non-gating offline smoke fixture) as the
NFR-010 gate harness.

Design (mirrors the OQ-017 :class:`eval_harness.Provider` seam so the gate stays
unit-testable offline, OQ-027e):

- :class:`Host` is an injected protocol: given the skill body, the fixture
  prompt and an ephemeral workspace, run one episode and report a
  :class:`HostOutcome` — a host-native execution status plus the returned
  ``AuthoringResult`` (verbatim) and additive telemetry.
- :func:`to_episode_result` is the **deterministic host→EpisodeResult adapter**
  (OQ-027e / AC-036b): it maps a :class:`HostOutcome` to the exact §11.8
  EpisodeResult dict that :func:`check_evals.score_episode` (OQ-016) already
  scores — the scorer, targets, baseline and lint semantics are unchanged.
- :func:`run_fixture` has the same ``(fixture, runner_cfg, host, repo_root)``
  signature as :func:`eval_harness.run_fixture`, so :mod:`check_evals` drives
  either harness uniformly.
- :class:`AgentSDKHost` is the concrete reference host. It lazily imports the
  optional ``transon-authoring[evals]`` ``claude-agent-sdk`` package so this
  module stays importable without it, and is **never** touched by the offline
  tests (they inject a fake :class:`Host`). Its live behaviour is exercised only
  in the credential-holding dispatch workflow under the OQ-027f isolation
  contract — it is unverified by the deterministic gates.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol

#: Host-native execution statuses the adapter accepts (OQ-027e). These are the
#: four mutually exclusive ways an episode in any real host can end; every
#: concrete :class:`Host` classifies its run into exactly one of them.
STATUS_RESULT = "result"  # host returned an AuthoringResult object
STATUS_NO_RESULT = "no_result"  # host ended without returning one
STATUS_BUDGET = "budget"  # pinned step/turn/token budget exceeded
STATUS_INFRA = "infra"  # host / transport / credential fault

#: status → §11.8 EpisodeResult ``outcome`` (OQ-027e / AC-036b). Total over the
#: statuses above; any other status is a programming error (see the adapter).
_STATUS_TO_OUTCOME = {
    STATUS_RESULT: "submitted",
    STATUS_NO_RESULT: "no_submit",
    STATUS_BUDGET: "budget_exceeded",
    STATUS_INFRA: "infra_error",
}


@dataclass
class HostOutcome:
    """What a real host reports for one episode, before adapter classification.

    ``result`` is the returned ``AuthoringResult`` **verbatim** (kept even when
    schema-invalid, so OQ-016b failures stay diagnosable) and is only meaningful
    when ``status == STATUS_RESULT``. ``step_log`` and ``tokens`` are additive
    telemetry (never scored, AC-034); a host that exposes no per-step record
    leaves ``step_log`` empty.
    """

    status: str
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    step_log: list[dict[str, Any]] = field(default_factory=list)
    tokens: Optional[dict[str, int]] = None


class Host(Protocol):
    """Injected real-host abstraction (OQ-027e). One episode per call."""

    def run_episode(
        self,
        *,
        skill_md: str,
        prompt: str,
        workspace: Path,
        runner_cfg: dict[str, Any],
    ) -> HostOutcome: ...


def _new_tokens() -> dict[str, int]:
    return {
        "input": 0,
        "output": 0,
        "cache_read": 0,
        "cache_creation": 0,
        "turns": 0,
    }


def to_episode_result(outcome: HostOutcome) -> dict[str, Any]:
    """OQ-027e / AC-036b — the deterministic host→EpisodeResult adapter.

    Maps a :class:`HostOutcome` to the §11.8 EpisodeResult dict
    (``{submitted, outcome, tool_calls, error, tool_call_log, tokens}``) that
    :func:`check_evals.score_episode` already scores unchanged. Pure and
    total over :data:`_STATUS_TO_OUTCOME`; feeding its output through the
    unchanged scorer yields the same verdict the equivalent raw-loop
    EpisodeResult would (AC-036b).
    """
    mapped = _STATUS_TO_OUTCOME.get(outcome.status)
    if mapped is None:  # defensive — a Host returned an unknown status
        return _episode_result(
            outcome="infra_error",
            error=f"host reported unknown status {outcome.status!r}",
            step_log=outcome.step_log,
            tokens=outcome.tokens,
        )
    # A schema-invalid payload still maps to ``submitted`` with the raw payload
    # retained (OQ-016b / OQ-027e); the scorer re-validates it (AD-004).
    submitted = outcome.result if outcome.status == STATUS_RESULT else None
    return _episode_result(
        submitted=submitted,
        outcome=mapped,
        error=outcome.error,
        step_log=outcome.step_log,
        tokens=outcome.tokens,
    )


def _episode_result(
    *,
    outcome: str,
    submitted: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
    step_log: Optional[list[dict[str, Any]]] = None,
    tokens: Optional[dict[str, int]] = None,
) -> dict[str, Any]:
    """Build the §11.8 EpisodeResult dict (identical shape to
    :func:`eval_harness._episode_result`). ``tool_calls`` is the int step count
    the scorer reads; ``tool_call_log`` is the FR-032 transcript record."""
    log = step_log if step_log is not None else []
    return {
        "submitted": submitted,
        "outcome": outcome,
        "tool_calls": len(log),
        "error": error,
        "tool_call_log": log,
        "tokens": tokens if tokens is not None else _new_tokens(),
    }


def _install_skill(workspace: Path, skill_md: str) -> None:
    """Install ``SKILL.md`` into the ephemeral workspace as a project skill so
    the host discovers it via ``setting_sources`` (OQ-027f(i): the workspace is
    the *only* thing mounted — no repo checkout)."""
    skill_dir = workspace / ".claude" / "skills" / "transon-authoring"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")


def run_fixture(
    fixture: dict[str, Any],
    runner_cfg: dict[str, Any],
    host: Host,
    repo_root: Path,
) -> dict[str, Any]:
    """Run one fixture as one episode in the injected real ``host``; return an
    EpisodeResult dict (§11.8), via the OQ-027e adapter.

    Enforces the driver's share of the OQ-027f isolation contract: an
    **ephemeral per-episode workspace** confined as the host ``cwd`` (i), with
    only the installed skill and the fixture ``samples.json`` inside it, torn
    down after the episode (iv). The pinned engine is reached via the ambient
    package install, never copied here (OQ-027f(i)).

    Credential-withholding (ii) and egress-deny (iii) are the **dispatch-workflow
    environment's** responsibility, not this driver's, and deliberately so: the
    Agent SDK runs the model's tools and the model-API call in the *same*
    subprocess, so the driver cannot both authenticate the API and hide the key
    from the model's Bash by scrubbing the process env — a naive scrub would
    break authentication. Withholding therefore needs an env-layer control (a
    key-scoped API proxy / a sandbox that denies egress), which is why (ii)/(iii)
    are environment-enforced. This driver's part of the bargain is narrow: it
    never *adds* the provider key to the host tool environment itself.
    """
    workspace = Path(tempfile.mkdtemp(prefix="transon-host-eval-"))
    try:
        try:
            # SKILL.md is measured verbatim, exactly as the raw loop did
            # (OQ-017a) — the real host just loads it as a skill.
            skill_md = (repo_root / "SKILL.md").read_bytes().decode("utf-8")
            _install_skill(workspace, skill_md)

            prompt = fixture["intent_nl"]
            if fixture.get("samples") is not None:
                (workspace / "samples.json").write_text(
                    json.dumps(fixture["samples"], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                prompt += "\n\nA confirmed SampleSet is available at samples.json."
        except Exception as exc:  # workspace/SKILL.md fault = infra (OQ-016d)
            return _episode_result(
                outcome="infra_error",
                error=f"harness setup fault: {type(exc).__name__}: {exc}",
            )

        try:
            outcome = host.run_episode(
                skill_md=skill_md,
                prompt=prompt,
                workspace=workspace,
                runner_cfg=runner_cfg,
            )
        except Exception as exc:  # host/transport/credential fault (OQ-016d)
            return _episode_result(
                outcome="infra_error",
                error=f"{type(exc).__name__}: {exc}",
            )
        return to_episode_result(outcome)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


# Host tools the skill needs in production (a rich harness, AD-024). No network
# or web tool is granted — the skill grounds only through the local pinned
# engine (NFR-001 / NFR-003), reachable via Bash `python -m transon_authoring`.
_AGENT_SDK_ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Skill"]


def _extract_authoring_result(text: Any) -> Optional[dict[str, Any]]:
    """Best-effort recovery of the AuthoringResult the skill emitted as its final
    message text (the skill ships emitting the §11.5 envelope; the SDK exposes it
    as ``ResultMessage.result``). Prefers a whole-text JSON parse, then a fenced
    ```json``` block, then a balanced-brace scan for the last object that parses
    and looks like an envelope (`status`/`ok`). Returns None if nothing parses —
    the adapter then scores it ``no_submit`` (OQ-027e). Pure/deterministic."""
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    try:
        whole = json.loads(stripped)
        if isinstance(whole, dict):
            return whole
    except ValueError:
        pass
    import re

    for block in reversed(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)):
        try:
            obj = json.loads(block)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    # Balanced-brace scan: last top-level {...} that parses to an envelope-shaped
    # dict wins (the skill's final answer, if wrapped in prose).
    found: Optional[dict[str, Any]] = None
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        depth = 0
        for end in range(start, len(text)):
            if text[end] == "{":
                depth += 1
            elif text[end] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : end + 1])
                    except ValueError:
                        pass
                    else:
                        if isinstance(obj, dict) and ("status" in obj or "ok" in obj):
                            found = obj
                    break
    return found


def _sdk_usage(usage: Any) -> Optional[dict[str, int]]:
    """Normalize a ResultMessage usage object/dict into the Turn.usage shape, or
    None. Additive cost telemetry only — never scored (AC-034)."""
    if usage is None:
        return None
    get = usage.get if isinstance(usage, dict) else lambda k, d=0: getattr(usage, k, d)
    tokens = _new_tokens()
    tokens["input"] = int(get("input_tokens", 0) or 0)
    tokens["output"] = int(get("output_tokens", 0) or 0)
    tokens["cache_read"] = int(get("cache_read_input_tokens", 0) or 0)
    tokens["cache_creation"] = int(get("cache_creation_input_tokens", 0) or 0)
    tokens["turns"] = 1
    return tokens


class AgentSDKHost:
    """Claude Agent SDK reference host (OQ-027a). **Live-unverified**: exercised
    only in the credential-holding dispatch workflow under the OQ-027f isolation
    sandbox; the deterministic gates inject a fake :class:`Host` instead.

    The ``claude-agent-sdk`` package is imported lazily (optional
    ``transon-authoring[evals]`` extra, OQ-027a) so importing this module never
    requires it.
    """

    def __init__(self, runner_cfg: dict[str, Any]):
        # Fail fast with a clear message if the extra is missing; the config
        # error is surfaced as exit 2 by check_evals (AC-036a).
        try:
            import claude_agent_sdk  # noqa: F401  (presence check only)
        except ImportError as exc:  # pragma: no cover - needs the extra absent
            raise RuntimeError(
                "the 'agent-sdk' harness needs the claude-agent-sdk package — "
                "install the optional extra: pip install 'transon-authoring[evals]' "
                "(SPEC §11.8 / OQ-027a)"
            ) from exc
        self._runner_cfg = runner_cfg

    def run_episode(
        self,
        *,
        skill_md: str,
        prompt: str,
        workspace: Path,
        runner_cfg: dict[str, Any],
    ) -> HostOutcome:  # pragma: no cover - live SDK path, dispatch-only
        import asyncio

        # ``skill_md`` is part of the Host protocol but intentionally unused
        # here: OQ-027a faithful engagement means the host discovers and
        # auto-activates the skill exactly as a real session would — the driver
        # already installed it into workspace/.claude/skills/…/SKILL.md
        # (run_fixture), and the Claude Code system prompt (preset below) drives
        # activation. We do NOT inject SKILL.md as the system prompt.
        return asyncio.run(
            self._run_episode_async(prompt=prompt, workspace=workspace)
        )

    async def _run_episode_async(
        self, *, prompt: str, workspace: Path
    ) -> HostOutcome:  # pragma: no cover - live SDK path, dispatch-only
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

        cfg = self._runner_cfg
        options = ClaudeAgentOptions(
            cwd=str(workspace),  # OQ-027f(i): confine the host to the workspace
            # OQ-027a faithful engagement: use Claude Code's OWN system prompt
            # (preset) so the installed skill auto-activates by its frontmatter
            # description exactly as in a real session — no injected SKILL.md,
            # no engagement preamble. (Whether a given intent triggers the skill
            # is then a real signal about the shipped description, not a harness
            # knob.)
            system_prompt={"type": "preset", "preset": "claude_code"},
            setting_sources=["project"],  # discover workspace/.claude/skills/…
            skills="all",
            allowed_tools=_AGENT_SDK_ALLOWED_TOOLS,
            permission_mode="dontAsk",  # headless: deny anything not pre-approved
            model=cfg["model_id"],
            # tool_budget is the pinned step budget (OQ-017c); max_turns is the
            # SDK's closest bound. Exceeding it → subtype error_max_turns →
            # STATUS_BUDGET below.
            max_turns=cfg["tool_budget"],
        )
        # Only the TERMINAL ResultMessage classifies the episode — intermediate
        # System/Assistant/User/Stream messages (which may also carry a
        # ``subtype``, e.g. init/thinking) must be ignored, else a mid-episode
        # message is mistaken for the outcome.
        terminal = None
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                terminal = message
        if terminal is None:
            return HostOutcome(
                status=STATUS_NO_RESULT, error="host produced no ResultMessage"
            )
        subtype = getattr(terminal, "subtype", None) or ""
        tokens = _sdk_usage(getattr(terminal, "usage", None))
        if "max_turns" in subtype:
            return HostOutcome(
                status=STATUS_BUDGET, error=f"host ended: {subtype}", tokens=tokens
            )
        # The skill emits the §11.5 AuthoringResult as its final answer; the SDK
        # exposes it as structured_output (when a schema is set) or as result
        # text (the shipped skill's natural output). Recover it either way; the
        # scorer re-validates it (AD-004), so a schema-invalid payload still
        # counts as a submission (OQ-016b / OQ-027e).
        structured = getattr(terminal, "structured_output", None)
        payload = (
            structured
            if isinstance(structured, dict)
            else _extract_authoring_result(getattr(terminal, "result", None))
        )
        if isinstance(payload, dict):
            return HostOutcome(status=STATUS_RESULT, result=payload, tokens=tokens)
        return HostOutcome(
            status=STATUS_NO_RESULT,
            error=f"host ended: {subtype or 'no result'}; no parseable AuthoringResult",
            tokens=tokens,
        )
