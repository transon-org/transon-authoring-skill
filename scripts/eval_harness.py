"""FR-017 / NFR-010 / OQ-017 — eval harness: raw provider-API tool loop.

Runs a single eval fixture as one episode against a provider (SPEC §11.8
"Harness (OQ-017)"):

- The system prompt is the verbatim bytes of the repo-root ``SKILL.md`` plus
  the fixed :data:`HARNESS_PREAMBLE` (OQ-017a).
- Exactly three tools are exposed (OQ-017b): ``write_file`` (workspace-confined
  relative paths only), ``transon_authoring`` (runs
  ``python -m transon_authoring <argv…>`` with cwd = workspace) and
  ``submit_result`` (records the AuthoringResult and ends the episode).
- ``tool_budget`` from ``evals/runner.json`` caps total tool calls; exceeding
  it, or ending without ``submit_result``, is a bucket-failure outcome — never
  infra (OQ-017c). Provider/transport exceptions are ``infra_error`` (OQ-016d).
- The provider client is injected (:class:`Provider` protocol); the real
  :class:`AnthropicProvider` imports the ``anthropic`` SDK lazily so this
  module stays importable without the optional ``[evals]`` extra (OQ-017d).
  Unit tests use a scripted fake provider (OQ-017e).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol

#: Fixed byte cap applied to captured stdout and stderr of the
#: ``transon_authoring`` tool (OQ-017b: "truncated at a fixed byte cap").
OUTPUT_BYTE_CAP = 65536

#: Fixed harness preamble appended after the verbatim SKILL.md bytes
#: (OQ-017a). Changing this text changes gate identity — treat edits as
#: eval-policy commits (AD-020).
HARNESS_PREAMBLE = """

---

# Eval harness rules

You are running inside an automated evaluation episode with a private
temporary workspace. Rules:

- All file paths are relative to the workspace. Absolute paths and paths
  escaping the workspace are rejected.
- You have exactly three tools:
  - `write_file(path, content)` — write a UTF-8 text file at a
    workspace-relative path.
  - `transon_authoring(argv)` — run `python -m transon_authoring <argv...>`
    with the workspace as the working directory; returns
    `{exit_code, stdout, stderr}`.
  - `submit_result(result)` — submit your single final AuthoringResult object
    and end the episode.
- There is no shell tool and no network access.
- Finish by calling `submit_result` exactly once, with one AuthoringResult
  object per SPEC §11.5. Do not print the result as text instead.
"""

#: The exactly-three tool definitions exposed to the model, in provider
#: tool-use API shape (OQ-017b).
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "write_file",
        "description": (
            "Write a UTF-8 text file at a workspace-relative path. Absolute "
            "paths and paths resolving outside the workspace are rejected."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "transon_authoring",
        "description": (
            "Run `python -m transon_authoring <argv...>` with the workspace "
            "as the working directory. Returns exit_code, stdout and stderr "
            "(both truncated at a fixed byte cap)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "argv": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["argv"],
        },
    },
    {
        "name": "submit_result",
        "description": (
            "Submit the single final AuthoringResult object (SPEC §11.5) and "
            "end the episode. Call exactly once."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"result": {"type": "object"}},
            "required": ["result"],
        },
    },
]


@dataclass
class ToolUse:
    """One tool-use request from the assistant turn."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass
class Turn:
    """One assistant turn: optional text plus zero or more tool-use requests."""

    text: str = ""
    tool_uses: list[ToolUse] = field(default_factory=list)


class Provider(Protocol):
    """Provider abstraction (OQ-017d): one API round-trip per call."""

    def create_turn(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Turn: ...


class AnthropicProvider:
    """Anthropic Messages API provider (OQ-017d/f).

    The ``anthropic`` SDK is imported lazily here — it is the optional
    ``transon-authoring[evals]`` extra, never a runtime dependency — so
    importing this module works without the SDK installed.
    """

    def __init__(self, runner_cfg: dict[str, Any]):
        import anthropic  # lazy: optional [evals] extra only (OQ-017d)

        self._client = anthropic.Anthropic()
        self._model = runner_cfg["model_id"]
        self._temperature = runner_cfg["temperature"]
        self._max_tokens = runner_cfg["max_output_tokens"]
        # OQ-017c: seed is passed through only when the provider supports it;
        # the Anthropic Messages API has no seed parameter, so a non-null seed
        # is recorded but not sent (runner.json pins seed: null).
        self._seed = runner_cfg.get("seed")

    def create_turn(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Turn:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system,
            messages=messages,
            tools=tools,
        )
        text_parts: list[str] = []
        tool_uses: list[ToolUse] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(
                    ToolUse(id=block.id, name=block.name, input=dict(block.input))
                )
        return Turn(text="".join(text_parts), tool_uses=tool_uses)


def _confine(workspace: Path, raw_path: str) -> Optional[Path]:
    """Resolve ``raw_path`` inside ``workspace`` or return None (OQ-017b).

    Rejects absolute paths outright, then resolves the joined path and
    requires the resolved workspace to be a prefix of it (path confinement).
    """
    if not raw_path or Path(raw_path).is_absolute():
        return None
    root = workspace.resolve()
    resolved = (root / raw_path).resolve()
    if resolved == root or not resolved.is_relative_to(root):
        return None
    return resolved


def _tool_write_file(workspace: Path, tool_input: dict[str, Any]) -> dict[str, Any]:
    raw_path = tool_input.get("path")
    content = tool_input.get("content")
    if not isinstance(raw_path, str) or not isinstance(content, str):
        return {"error": "write_file requires string 'path' and 'content'"}
    target = _confine(workspace, raw_path)
    if target is None:
        return {
            "error": (
                "path rejected: must be a relative path that stays inside "
                f"the workspace (got {raw_path!r})"
            )
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": raw_path}


def _tool_transon_authoring(
    workspace: Path, tool_input: dict[str, Any]
) -> dict[str, Any]:
    argv = tool_input.get("argv")
    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        return {"error": "transon_authoring requires 'argv' as a list of strings"}
    completed = subprocess.run(
        [sys.executable, "-m", "transon_authoring", *argv],
        cwd=workspace,
        capture_output=True,
        timeout=300,
    )
    return {
        "exit_code": completed.returncode,
        "stdout": completed.stdout[:OUTPUT_BYTE_CAP].decode("utf-8", errors="replace"),
        "stderr": completed.stderr[:OUTPUT_BYTE_CAP].decode("utf-8", errors="replace"),
    }


def _episode_result(
    *,
    submitted: Optional[dict[str, Any]] = None,
    outcome: str,
    tool_calls: int,
    error: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "submitted": submitted,
        "outcome": outcome,
        "tool_calls": tool_calls,
        "error": error,
    }


def run_fixture(
    fixture: dict[str, Any],
    runner_cfg: dict[str, Any],
    provider: Provider,
    repo_root: Path,
) -> dict[str, Any]:
    """Run one fixture as one episode; return an EpisodeResult dict.

    EpisodeResult: ``{"submitted": AuthoringResult|None, "outcome":
    "submitted"|"budget_exceeded"|"no_submit"|"infra_error",
    "tool_calls": int, "error": str|None}``.
    """
    workspace = Path(tempfile.mkdtemp(prefix="transon-eval-"))
    tool_calls = 0
    try:
        try:
            # OQ-017a: system prompt = verbatim SKILL.md bytes + fixed preamble.
            skill_md = (repo_root / "SKILL.md").read_bytes().decode("utf-8")
            system = skill_md + HARNESS_PREAMBLE

            user_message = fixture["intent_nl"]
            if fixture.get("samples") is not None:
                (workspace / "samples.json").write_text(
                    json.dumps(fixture["samples"], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                user_message += (
                    "\n\nA confirmed SampleSet is available at samples.json."
                )
        except Exception as exc:  # workspace/SKILL.md fault = infra (OQ-016d)
            return _episode_result(
                outcome="infra_error",
                tool_calls=tool_calls,
                error=f"harness setup fault: {type(exc).__name__}: {exc}",
            )

        messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
        tool_budget = runner_cfg["tool_budget"]

        while True:
            try:
                turn = provider.create_turn(system, messages, TOOL_SPECS)
            except Exception as exc:  # transport/API fault — never model behavior
                return _episode_result(
                    outcome="infra_error",
                    tool_calls=tool_calls,
                    error=f"{type(exc).__name__}: {exc}",
                )

            if not turn.tool_uses:
                # Model stopped without submit_result: bucket-failure (OQ-017c).
                return _episode_result(outcome="no_submit", tool_calls=tool_calls)

            assistant_content: list[dict[str, Any]] = []
            if turn.text:
                assistant_content.append({"type": "text", "text": turn.text})
            for tool_use in turn.tool_uses:
                assistant_content.append(
                    {
                        "type": "tool_use",
                        "id": tool_use.id,
                        "name": tool_use.name,
                        "input": tool_use.input,
                    }
                )
            messages.append({"role": "assistant", "content": assistant_content})

            tool_results: list[dict[str, Any]] = []
            for tool_use in turn.tool_uses:
                tool_calls += 1
                if tool_calls > tool_budget:
                    # Bucket-failure, not infra (OQ-017c).
                    return _episode_result(
                        outcome="budget_exceeded", tool_calls=tool_calls
                    )
                if tool_use.name == "submit_result":
                    return _episode_result(
                        submitted=tool_use.input.get("result"),
                        outcome="submitted",
                        tool_calls=tool_calls,
                    )
                # A harness fault (tool timeout, OS error) is infra_error per
                # OQ-016d — never a crash of the whole multi-fixture run.
                try:
                    if tool_use.name == "write_file":
                        payload = _tool_write_file(workspace, tool_use.input)
                    elif tool_use.name == "transon_authoring":
                        payload = _tool_transon_authoring(workspace, tool_use.input)
                    else:
                        payload = {"error": f"unknown tool: {tool_use.name}"}
                except Exception as exc:
                    return _episode_result(
                        outcome="infra_error",
                        tool_calls=tool_calls,
                        error=f"harness fault in {tool_use.name}: "
                        f"{type(exc).__name__}: {exc}",
                    )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps(payload, ensure_ascii=False),
                        "is_error": "error" in payload,
                    }
                )
            messages.append({"role": "user", "content": tool_results})
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
