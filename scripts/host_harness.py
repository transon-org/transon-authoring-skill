"""FR-017 / NFR-010 / AD-024 / OQ-027 — real-host eval driver + adapter.

Runs one eval fixture as one episode in the **real host agent harness** the
skill ships into (SPEC §11.8 "Harness", AD-024) — the reference host is the
Claude Agent SDK, pinned by ``evals/runner.json`` ``harness = {kind, version}``.
This replaces the raw 3-tool ``messages.create`` loop
(:mod:`eval_harness`, now the OQ-027d non-gating offline smoke fixture) as the
NFR-010 gate harness.

Design (mirrors the OQ-017 :class:`eval_harness.Provider` seam so the gate stays
unit-testable offline, OQ-027e); shared workspace / EpisodeResult / token helpers
live in :mod:`_shared`:

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
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol

from _shared import build_episode_result, new_tokens, prepare_workspace, usage_tokens

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
    when ``status == STATUS_RESULT``. ``step_log``, ``tokens``, ``cost_usd`` and
    ``messages`` are additive telemetry (never scored, AC-034 / FR-035); a host
    that exposes no per-step record leaves ``step_log``/``messages`` empty and
    ``cost_usd`` None.
    """

    status: str
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    step_log: list[dict[str, Any]] = field(default_factory=list)
    tokens: Optional[dict[str, int]] = None
    #: FR-035 — host-reported episode cost (SDK ``ResultMessage.total_cost_usd``).
    cost_usd: Optional[float] = None
    #: FR-035 — the whole host message transcript, serialized (every turn's
    #: assistant text/thinking, tool_use/tool_result), for the EpisodeMessages
    #: artifact. Additive telemetry only.
    messages: list[dict[str, Any]] = field(default_factory=list)


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
    return new_tokens()


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
        cost_usd=outcome.cost_usd,
        messages=outcome.messages,
    )


def _episode_result(
    *,
    outcome: str,
    submitted: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
    step_log: Optional[list[dict[str, Any]]] = None,
    tokens: Optional[dict[str, int]] = None,
    cost_usd: Optional[float] = None,
    messages: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Build the §11.8 EpisodeResult dict (identical shape to
    :func:`eval_harness._episode_result`, plus FR-035 ``cost_usd`` /
    ``messages``). Shared builder: :func:`_shared.build_episode_result`.
    ``tool_calls`` is the int step count the scorer reads; ``tool_call_log``
    is the FR-032 transcript record. ``cost_usd`` and ``messages`` are
    additive FR-035 telemetry (never scored, AC-034)."""
    return build_episode_result(
        submitted=submitted,
        outcome=outcome,
        error=error,
        tool_call_log=step_log,
        tokens=tokens,
        cost_usd=cost_usd,
        messages=messages,
        include_fr035=True,
    )


def _install_skill(workspace: Path, repo_root: Path) -> None:
    """Provision the ephemeral workspace with the **shipped installer**
    (ROADMAP §14 A5 ladder step 2 / OQ-027a), so the gate measures the
    installed-from-distribution configuration rather than a harness-authored
    copy of ``SKILL.md``.

    ``--scope project`` is required: the SDK options use
    ``setting_sources=["project"]`` with ``cwd=workspace``, so only the project
    destination (``workspace/.claude/skills/transon-authoring/``) is discovered.
    The installer's source root is ``repo_root`` — the staged file subset the
    eval bundle carries (``SKILL.md``, ``pyproject.toml``,
    ``resources/metadata-snapshot.json``, ``adapters/``, ``install/``), not an
    unpacked sdist: the claim is that the shipped installer provisions the
    workspace, not that the built archive was exercised (that is ladder step 1).

    The install adds ``.install-manifest.json`` beside the skill body; it is
    inert to the host, so this forces no baseline reset.

    Raises on a missing installer or a non-zero installer exit — the caller
    classifies that as ``infra_error`` (OQ-016d), never a fixture failure.
    """
    installer = repo_root / "install" / "claude.py"
    if not installer.is_file():
        raise FileNotFoundError(f"missing shipped installer: {installer}")
    completed = subprocess.run(
        [
            sys.executable,
            str(installer),
            "--scope",
            "project",
            "--repo-root",
            str(repo_root),
            "--target-root",
            str(workspace),
        ],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"install/claude.py exited {completed.returncode}: "
            f"{(completed.stderr or completed.stdout).strip()}"
        )


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
            # Shared workspace setup: :func:`_shared.prepare_workspace`.
            skill_md, prompt = prepare_workspace(fixture, repo_root, workspace)
            _install_skill(workspace, repo_root)
        except Exception as exc:  # workspace/provisioning fault = infra (OQ-016d)
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
    # Balanced-brace scan restricted to TRUE top-level objects: the last
    # depth-0 {...} that parses to an envelope-shaped dict wins (the skill's
    # final answer, if wrapped in prose). Scanning every '{' would let a nested
    # object — e.g. the envelope's own `verdict` (which also carries an "ok"
    # key) — overwrite the correct full-envelope match.
    found: Optional[dict[str, Any]] = None
    depth = 0
    top_start: Optional[int] = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                top_start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and top_start is not None:
                    try:
                        obj = json.loads(text[top_start : i + 1])
                    except ValueError:
                        pass
                    else:
                        if isinstance(obj, dict) and ("status" in obj or "ok" in obj):
                            found = obj
                    top_start = None
    return found


def _sdk_usage(usage: Any) -> Optional[dict[str, int]]:
    """Normalize a ResultMessage usage object/dict into the Turn.usage shape, or
    None. Additive cost telemetry only — never scored (AC-034)."""
    if usage is None:
        return None
    get = usage.get if isinstance(usage, dict) else lambda k, d=0: getattr(usage, k, d)
    tokens = new_tokens()
    tokens.update(usage_tokens(get))
    tokens["turns"] = 1
    return tokens


#: OQ-016d — substrings that mark a provider/credential fault the host may report
#: as ordinary assistant text (the captured case: an invalid key surfaced as the
#: assistant text "Invalid API key · Fix external API key"). Lowercased compare.
#:
#: DELIBERATELY NARROW: only unambiguous CLI/API fault strings that a model
#: authoring JSON transforms would never legitimately emit. Generic capacity words
#: ("quota", "rate limit", "overloaded") and financial phrases ("credit balance
#: …") were REMOVED — they match ordinary assistant prose (e.g. a transform that
#: mentions a rate-limit or quota field), which would wrongly exclude a genuine
#: token-consuming MODEL failure from the denominator (OQ-016d honesty). Those
#: faults prevent the turn from running and so are caught by the zero-token signal
#: in _infra_hint (a real model turn always burns input tokens) — the robust
#: catch-all; these markers are only belt-and-suspenders for the auth case.
_INFRA_MARKERS = (
    "invalid api key",
    "fix external api key",
    "authentication_error",
)


def _infra_hint(
    messages: list[dict[str, Any]], tokens: Optional[dict[str, int]]
) -> Optional[str]:
    """OQ-016d — is this "successful" turn actually a provider/infra fault?

    The Claude Code CLI reports an invalid key as a NORMAL assistant turn that
    ends ``subtype: "success"`` (observed verbatim: two ``api_retry`` system
    messages then the text "Invalid API key · Fix external API key"). Left alone,
    the classifier maps that to ``no_submit`` — i.e. a MODEL failure counted
    against the authoring target — when it is an infra fault that must be
    ``infra_error`` and excluded from the bucket denominator (§11.8 / OQ-016d).
    A dead key would score as the skill failing 150 times.

    Two signals, either sufficient: (1) an explicit fault marker in the turn's
    text; (2) the turn consumed **zero model tokens** — a real model turn always
    burns input tokens, so a "success" with no usage never ran. Takes the
    SERIALIZED message stream (:func:`_serialize_messages`) so it is pure and
    unit-testable without live SDK objects. Returns a reason, or None when the
    turn looks like a genuine model turn."""
    consumed = 0
    if tokens:
        consumed = sum(
            int(tokens.get(key, 0) or 0)
            for key in ("input", "output", "cache_read", "cache_creation")
        )
    texts: list[str] = []
    retried = False
    for message in messages:
        if message.get("subtype") == "api_retry":
            retried = True
        content = message.get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for block in content:
                text = block.get("text") if isinstance(block, dict) else None
                if isinstance(text, str):
                    texts.append(text)
    blob = " ".join(texts).lower()
    for marker in _INFRA_MARKERS:
        if marker in blob:
            return f"provider/credential fault reported by the host ({marker!r})"
    if consumed == 0:
        suffix = " after api_retry" if retried else ""
        return (
            f"the turn consumed no model tokens{suffix} — it never ran "
            "(provider/transport fault, not a model failure)"
        )
    return None


def _classify_terminal(
    subtype: Any,
    structured: Any,
    result_text: Any,
    tokens: Optional[dict[str, int]] = None,
    cost_usd: Optional[float] = None,
    infra_hint: Optional[str] = None,
) -> HostOutcome:
    """Pure host-terminal → :class:`HostOutcome` classification (OQ-027e /
    OQ-016d) — unit-tested offline (the surrounding SDK call is not). ``subtype``
    is the SDK ``ResultMessage.subtype`` (``None`` when the host produced no
    terminal message at all). ``cost_usd`` (SDK ``total_cost_usd``) is carried
    unchanged onto the outcome as additive FR-035 telemetry.

    - ``success`` + a recoverable AuthoringResult → ``STATUS_RESULT``;
    - ``success`` with no parseable result → ``STATUS_NO_RESULT`` (the model
      ended cleanly but submitted nothing valid — a bucket failure);
    - any subtype naming a turn/step-budget stop (``…max_turns…``) →
      ``STATUS_BUDGET``;
    - **every other** terminal subtype (error_during_execution, transport, or
      no ResultMessage at all) is a host/execution fault → ``STATUS_INFRA``,
      never ``no_submit`` (OQ-016d).
    """
    sub = subtype or ""
    if "max_turns" in sub:
        return HostOutcome(
            status=STATUS_BUDGET, error=f"host ended: {sub}", tokens=tokens, cost_usd=cost_usd
        )
    if sub != "success":
        return HostOutcome(
            status=STATUS_INFRA,
            error=f"host ended: {sub or 'no ResultMessage'}",
            tokens=tokens,
            cost_usd=cost_usd,
        )
    payload = (
        structured
        if isinstance(structured, dict)
        else _extract_authoring_result(result_text)
    )
    if isinstance(payload, dict):
        # The episode demonstrably ran (it returned an envelope), so an infra
        # hint never overrides a real answer.
        return HostOutcome(
            status=STATUS_RESULT, result=payload, tokens=tokens, cost_usd=cost_usd
        )
    # OQ-016d — "success" with no envelope is only a MODEL failure (no_submit) if
    # a model turn actually happened. An auth/credit/transport fault that the host
    # dressed up as a successful assistant turn is an INFRA fault: it must not be
    # counted against the authoring target (it is excluded from the denominator).
    if infra_hint:
        return HostOutcome(
            status=STATUS_INFRA,
            error=f"host ended: success, but {infra_hint}",
            tokens=tokens,
            cost_usd=cost_usd,
        )
    return HostOutcome(
        status=STATUS_NO_RESULT,
        error="host ended: success; no parseable AuthoringResult",
        tokens=tokens,
        cost_usd=cost_usd,
    )


#: OQ-027 — the SKILL.md §6 interactive-review "approve" exit, spoken by the
#: driver AS the reviewing user. The shipped skill (FR-030) presents a matched
#: template and waits for approval BEFORE emitting the AuthoringResult; a single
#: autonomous turn never delivers that approval, so the model strands the
#: presented template as its final message. The driver supplies the approval
#: ONCE (see AgentSDKHost) so the eval measures the real present→approve→emit
#: path, leaving the shipped skill unchanged.
#: OQ-027 — the driver speaks this ONCE, as the reviewing user, when turn 1 ended
#: with no AuthoringResult (see _needs_review_followup). It must NOT assert that a
#: correct template exists: turn 1 may have PRESENTED a matched template for review
#: (FR-030 — then it should emit it), but it may equally have produced nothing
#: emittable because the request is not groundable (then it should REFUSE, §2).
#: An earlier version said "Approved — the template is correct, run `result`", which
#: fabricated approval of a non-existent template on refuse fixtures: the model
#: then hunted for template/samples files that never existed and asked for them
#: (no_submit), scoring the adversarial bucket 0.000. This message is therefore
#: neutral about whether a template exists, tells the model the session is
#: non-interactive, and offers BOTH exits — keeping the matched-emit path (run
#: `result`, return stdout verbatim) that drives the authoring bucket.
_REVIEW_APPROVAL = (
    "This is a non-interactive session: produce your FINAL answer now as a single "
    "AuthoringResult — I cannot answer questions, approve anything further, or provide "
    "files, and there is no earlier session to recover. If you have a template that "
    "verified `matched`, emit it by running the section 7 result command "
    "(`python -m transon_authoring result --template <path> --samples <path>`) and "
    "returning its stdout verbatim — never retype or reconstruct the envelope by hand. "
    "If instead the request needs a capability the pinned engine cannot ground (section "
    "2), emit the refusal (`ok: false`, `status: \"aborted\"`) by running "
    "`python -m transon_authoring result --refuse --status aborted --explanation "
    "\"<the missing capability>\"` and returning its stdout verbatim — do NOT hand-write "
    "the refusal envelope. Do not ask me for files or assume prior work."
)


def _needs_review_followup(outcome: HostOutcome) -> bool:
    """OQ-027 — did the first turn end WITHOUT an AuthoringResult, in a way the
    §6 review "approve" exit would resolve? True only when the turn ended
    cleanly but produced no envelope: ``STATUS_NO_RESULT`` (presented for review
    / no parseable result), or ``STATUS_RESULT`` whose payload is not
    envelope-shaped (a bare transon template — no ``ok`` / ``status`` /
    ``schema_version``). NEVER true for an infra/budget failure (a real fault,
    not a review stall) nor for a payload that already looks like an
    AuthoringResult — including a refusal (``ok: false``): those are the model's
    real answer and must not be overridden by an approval. Pure/total."""
    if outcome.status == STATUS_NO_RESULT:
        return True
    if outcome.status == STATUS_RESULT:
        result = outcome.result
        return not (
            isinstance(result, dict)
            and any(k in result for k in ("ok", "status", "schema_version"))
        )
    return False


def _add_tokens(
    a: Optional[dict[str, int]], b: Optional[dict[str, int]]
) -> Optional[dict[str, int]]:
    """Sum two additive token telemetry dicts across a multi-turn episode
    (never scored, AC-034). None is the additive identity."""
    if a is None:
        return b
    if b is None:
        return a
    return {key: int(a.get(key, 0)) + int(b.get(key, 0)) for key in set(a) | set(b)}


def _add_cost(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Sum two host-reported costs across a multi-turn episode (FR-035, additive
    telemetry, never scored). None is the additive identity so an episode where
    no turn reported a cost stays None rather than becoming 0.0."""
    if a is None:
        return b
    if b is None:
        return a
    return a + b


#: Cap a recorded tool-result payload so transcripts stay diagnosable without
#: unbounded blow-up (a `Read`/`Bash` result can be huge). Diagnostic only.
_TOOL_RESULT_MAX = 4000


def _tool_result_value(content: Any) -> Any:
    """Normalize + bound a tool_result payload for the FR-032 transcript record:
    strings are truncated to :data:`_TOOL_RESULT_MAX`; other JSON is encoded
    then truncated. Never scored (AC-034)."""
    if content is None:
        return None
    text = (
        content
        if isinstance(content, str)
        else json.dumps(content, ensure_ascii=False, default=str)
    )
    if len(text) > _TOOL_RESULT_MAX:
        return text[:_TOOL_RESULT_MAX] + f"… (+{len(text) - _TOOL_RESULT_MAX} chars)"
    return text


def _tool_calls_from_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """OQ-027 / FR-032 — build the §11.8 transcript tool-call log from a host
    turn's SDK message stream: one ``{seq, name, input, result}`` (the closed
    `toolCall` shape) per tool_use block, its ``result`` filled from the matching
    tool_result by ``tool_use_id``. Blocks are matched by duck-typing (tool_use →
    ``name`` + ``input`` + ``id``; tool_result → ``tool_use_id``) so this pure
    builder is unit-testable without live SDK objects. Additive telemetry only,
    never scored (AC-034); makes a real-host episode diagnosable without a local
    reproduction (the driver previously left this log empty)."""
    calls: list[dict[str, Any]] = []
    by_id: dict[Any, dict[str, Any]] = {}
    for message in messages:
        content = getattr(message, "content", None)
        if not isinstance(content, list):
            continue
        for block in content:
            tool_use_id = getattr(block, "tool_use_id", None)
            if tool_use_id is not None:  # a tool_result block
                entry = by_id.get(tool_use_id)
                if entry is not None:
                    entry["result"] = _tool_result_value(
                        getattr(block, "content", None)
                    )
                continue
            name = getattr(block, "name", None)
            if name is not None and hasattr(block, "input"):  # a tool_use block
                entry = {
                    "seq": len(calls) + 1,
                    "name": name,
                    "input": getattr(block, "input", None),
                    "result": None,
                }
                calls.append(entry)
                block_id = getattr(block, "id", None)
                if block_id is not None:
                    by_id[block_id] = entry
    return calls


def _serialize_block(block: Any) -> dict[str, Any]:
    """Serialize one SDK content block into a plain, bounded dict for the FR-035
    whole-episode transcript. Duck-typed (matching :func:`_tool_calls_from_messages`)
    so it is unit-testable without live SDK objects: a ``tool_use`` block exposes
    ``name``/``input``, a ``tool_result`` block exposes ``tool_use_id``, a text
    block exposes ``text``, a thinking block exposes ``thinking``. Text / thinking
    / tool-result payloads are length-bounded (:data:`_TOOL_RESULT_MAX`).
    Additive telemetry only, never scored (AC-034)."""
    tool_use_id = getattr(block, "tool_use_id", None)
    if tool_use_id is not None:  # tool_result
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "result": _tool_result_value(getattr(block, "content", None)),
        }
    name = getattr(block, "name", None)
    if name is not None and hasattr(block, "input"):  # tool_use
        return {
            "type": "tool_use",
            "name": name,
            "input": getattr(block, "input", None),
        }
    thinking = getattr(block, "thinking", None)
    if thinking is not None:
        return {"type": "thinking", "thinking": _tool_result_value(thinking)}
    text = getattr(block, "text", None)
    if text is not None:
        return {"type": "text", "text": _tool_result_value(text)}
    # Unknown block kind: keep a bounded best-effort record rather than drop it.
    return {"type": getattr(block, "type", "unknown"), "repr": _tool_result_value(str(block))}


def _serialize_content(content: Any) -> Any:
    """Serialize a message's ``content`` (a block list, a bare string, or None)
    for the FR-035 whole-episode transcript. Bounded / additive (AC-034)."""
    if content is None:
        return None
    if isinstance(content, str):
        return _tool_result_value(content)
    if isinstance(content, list):
        return [_serialize_block(block) for block in content]
    return _tool_result_value(content)


def _serialize_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """FR-035 / AD-025 — serialize a host turn's whole SDK message stream into
    plain dicts for the EpisodeMessages artifact: one ``{type, subtype, content}``
    per message, in order, with content blocks bounded (text/thinking/tool-result).
    ``type`` is the SDK message class name (system/assistant/user/result); pure
    and unit-testable without live SDK objects. Additive telemetry only, never
    scored (AC-034) — makes a real-host episode fully diagnosable from the
    committed-out artifact directory without a local reproduction."""
    return [
        {
            "type": type(message).__name__,
            "subtype": getattr(message, "subtype", None),
            "content": _serialize_content(getattr(message, "content", None)),
        }
        for message in messages
    ]


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
        from claude_agent_sdk import (
            ClaudeAgentOptions,
            ClaudeSDKClient,
            ResultMessage,
        )

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
            # Bind the exact pinned Claude Code CLI the SDK drives (gate identity,
            # AD-024 / NFR-002) rather than relying on PATH resolution order. The
            # dispatch workflow sets TRANSON_EVAL_CLI_PATH to the installed
            # binary; unset → None → the SDK's default PATH lookup (as validated
            # locally).
            cli_path=os.environ.get("TRANSON_EVAL_CLI_PATH") or None,
            # tool_budget is the pinned step budget (OQ-017c); max_turns is the
            # SDK's closest bound. Exceeding it → subtype error_max_turns →
            # STATUS_BUDGET below.
            max_turns=cfg["tool_budget"],
        )
        # Drive the host as a stateful session (ClaudeSDKClient) so the driver
        # can answer the skill's §6 interactive review. Only the TERMINAL
        # ResultMessage of each turn classifies it (OQ-027e) — intermediate
        # System/Assistant/User/Stream messages (which may also carry a
        # ``subtype``, e.g. init/thinking) are ignored, else a mid-turn message
        # is mistaken for the outcome. The skill emits the §11.5 AuthoringResult
        # as its final answer; the SDK exposes it as structured_output (when a
        # schema is set) or as result text (the shipped skill's natural output) —
        # the classifier recovers it either way and the scorer re-validates it
        # (AD-004), so a schema-invalid payload still counts as a submission
        # (OQ-016b / OQ-027e).
        async def _turn_outcome() -> HostOutcome:
            terminal = None
            messages: list[Any] = []
            async for message in client.receive_response():
                messages.append(message)
                if isinstance(message, ResultMessage):
                    terminal = message
            usage = _sdk_usage(getattr(terminal, "usage", None))
            # FR-035 — the whole message stream (assistant text/thinking + every
            # tool_use/tool_result) for the EpisodeMessages artifact...
            serialized = _serialize_messages(messages)
            # ...which OQ-016d also reads: a provider/credential fault the host
            # dressed up as a `success` turn must score infra_error, never
            # no_submit (see _infra_hint).
            outcome = _classify_terminal(
                getattr(terminal, "subtype", None),
                getattr(terminal, "structured_output", None),
                getattr(terminal, "result", None),
                usage,
                getattr(terminal, "total_cost_usd", None),
                _infra_hint(serialized, usage),
            )
            # FR-032 — record this turn's tool calls into the transcript log.
            outcome.step_log = _tool_calls_from_messages(messages)
            outcome.messages = serialized
            return outcome

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            outcome = await _turn_outcome()
            # OQ-027 — the shipped skill (FR-030) presents a matched template and
            # WAITS for the reviewing user's approval before emitting the
            # AuthoringResult. This eval is one autonomous turn, so a run that
            # ends by presenting for review has produced no envelope yet. Answer
            # the §6 "approve" exit ONCE, as the user would, then read the
            # follow-up turn — measuring the real present→approve→emit path
            # without altering the skill. Bounded to a single approval: a genuine
            # authoring/refusal answer, or an infra/budget fault, is never
            # overridden (see _needs_review_followup).
            if _needs_review_followup(outcome):
                await client.query(_REVIEW_APPROVAL)
                followup = await _turn_outcome()
                followup.tokens = _add_tokens(outcome.tokens, followup.tokens)
                # FR-035 — episode cost is the sum across both turns.
                followup.cost_usd = _add_cost(outcome.cost_usd, followup.cost_usd)
                # Keep the full tool-call trail across both turns, re-sequenced
                # (FR-032 — the transcript reflects everything the model did).
                combined = outcome.step_log + followup.step_log
                for seq, call in enumerate(combined, 1):
                    call["seq"] = seq
                followup.step_log = combined
                # FR-035 — the whole-message transcript spans both turns in order.
                followup.messages = outcome.messages + followup.messages
                outcome = followup
            return outcome
