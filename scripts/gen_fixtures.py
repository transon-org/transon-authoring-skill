#!/usr/bin/env python
"""gen-fixtures — synthetic EvalFixture generator (FR-029 / AD-021 / OQ-025).

Maintainer script (SPEC §10 ``scripts/`` — never shipped in the package) that
mints EvalFixtures from pinned-snapshot ``docs.examples`` seeds. The pure core
is :func:`generate`; the CLI (``main``) and the ``check_evals --lint`` AC-030
regen check both call that SAME core, so a fixture regenerates bit-identically
from its seed or the gate is red.

Contract highlights (SPEC FR-029, AD-021, OQ-024/OQ-025, §11.8):

* deterministic — no wall-clock, no randomness; every byte of the output is a
  pure function of (source example, fixture id, intent NL, pinned snapshot,
  pinned engine);
* **case 1 is always the corpus pair**: the example's own ``data`` re-executed
  through the pinned engine under the AD-017 sandbox
  (``transon_authoring.verify.dry_run``) and asserted JSON-equal to the
  example's ``result`` — a failing assert makes the seed ineligible
  (OQ-025d), never a fixture;
* 3–6 cases chosen by which §11.1 coverage kinds apply (OQ-025a/b/c/e), with
  the FR-029 budget rule: packing preferred, fixed drop order
  ``list_singleton`` → ``optional_present`` → ``list_many``, padding to the
  3-case minimum with value-variation customs from the fixed per-JSON-type
  substitution table;
* confirmations are ``confirmed: true`` / ``confirmed_by: "ci"`` with NO
  ``confirmed_at``; the ``content_fingerprint`` comes from the library's
  OQ-015 acquisition path (``check_samples``), never recomputed here;
* the seed template is provenance-only: it lands in
  ``evals/seeds/<fixture-id>.json`` and never inside the fixture object.

Implementation-defined details frozen forever by the AC-030 regen check
(OQ-025 tail): the case id scheme ``c-1..c-n`` (creation order), the
obligation id scheme (``ob-happy``, ``ob-<kind-with-dashes>--<pointer-slug>``,
``ob-no-content``, ``ob-writes``, ``ob-variation-<n>``), the substitution
table below, and the deterministic decisions the SPEC leaves open, recorded
here explicitly:

* the whole-document pointer ``""`` is not a §11.1 target (targets MUST start
  with ``/``), so the pre-order walk excludes the document root itself from
  optional/array candidacy — a root-level array receives no ``list_*`` kinds;
* ``list_singleton``/``list_many`` derivations for a corpus array that is
  empty are underivable and their obligations are not emitted (``list_empty``
  then packs into the corpus-pair case);
* a structural derivation whose dry-run fails under the pinned engine makes
  the seed ineligible (error), never a silent skip; failing value-variation
  candidates are skipped in favour of the next variation index.

Exit codes: 0 minted, 1 generation/verify failure (seed ineligible, AD-004
verify not matched), 2 usage/config errors (unknown example, refusing to
overwrite without ``--force``).
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    from transon_authoring import get_metadata
    from transon_authoring.samples import (
        _parse_pointer,
        _structural_check,
        check_samples,
    )
    from transon_authoring.verify import dry_run, verify
except ImportError:  # pragma: no cover - source-checkout fallback (SPEC §10)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from transon_authoring import get_metadata
    from transon_authoring.samples import (
        _parse_pointer,
        _structural_check,
        check_samples,
    )
    from transon_authoring.verify import dry_run, verify

#: Recorded in every seed doc (FR-029 seed shape ``generator.version``).
GENERATOR_VERSION = "1.0.0"

#: FR-029 budget bounds.
MIN_CASES = 3
MAX_CASES = 6

#: FR-029 fixed drop order (never-dropped kinds are simply not listed).
DROP_ORDER = ("list_singleton", "optional_present", "list_many")

#: §11.0 ``enc`` of the engine NO_CONTENT sentinel (OQ-025c relevance test).
NO_CONTENT_REF = {"$transon_authoring": "NO_CONTENT"}

#: Fixed per-JSON-type substitution table for value-variation cases
#: (FR-029; position-indexed, no randomness). ``null`` leaves are kept —
#: there is no meaningful deterministic alternate for ``null``.
SUBSTITUTION_TABLE: dict[str, list[Any]] = {
    "string": ["variation-alpha", "variation-beta", "variation-gamma"],
    "number": [7, 11, 13],
    "boolean": [True, False],
}

#: Number of value-variation candidates probed for NO_CONTENT relevance
#: (OQ-025c "the value-variation candidates"): exactly the variations the
#: 3-case padding could need (1 case → 3 cases).
PROBE_VARIATIONS = 2

#: Deterministic cap on variation indexes tried while padding; exhausting it
#: makes the seed ineligible (cannot reach the 3-case minimum).
MAX_VARIATION_ATTEMPTS = 16


class GeneratorError(Exception):
    """Seed ineligible / generation impossible (FR-029, OQ-025d)."""


# --------------------------------------------------------------------------
# JSON-pointer + template walking helpers (deterministic, pre-order).
# --------------------------------------------------------------------------


def _escape_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _pointer_string(tokens: list[str]) -> str:
    return "/" + "/".join(_escape_token(t) for t in tokens) if tokens else ""


def _walk_plan(data: Any, optional_names: set[str]) -> list[dict[str, Any]]:
    """Deterministic pre-order walk of the corpus ``data`` (OQ-025a/b).

    Yields one entry per visited child position (the document root itself is
    excluded — the empty whole-document pointer is not a §11.1 target), in
    pre-order; array descent uses index-``0`` segments only. Each entry:
    ``{"tokens", "pointer", "optional", "array", "value"}``.
    """
    plan: list[dict[str, Any]] = []

    def visit(node: Any, tokens: list[str]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                child = tokens + [key]
                plan.append(
                    {
                        "tokens": child,
                        "pointer": _pointer_string(child),
                        "optional": key in optional_names,
                        "array": isinstance(value, list),
                        "value": value,
                    }
                )
                visit(value, child)
        elif isinstance(node, list) and node:
            child = tokens + ["0"]
            plan.append(
                {
                    "tokens": child,
                    "pointer": _pointer_string(child),
                    "optional": False,  # an array index is never a key
                    "array": isinstance(node[0], list),
                    "value": node[0],
                }
            )
            visit(node[0], child)

    visit(data, [])
    return plan


def _template_nodes(template: Any):
    """Pre-order walk over every object node of a template."""
    stack = [template]
    while stack:
        node = stack.pop(0)
        if isinstance(node, dict):
            yield node
            stack = list(node.values()) + stack
        elif isinstance(node, list):
            stack = list(node) + stack


def _attr_default_names(template: Any) -> set[str]:
    """OQ-025a: literal string ``attr`` names carrying a ``default``."""
    return {
        node["name"]
        for node in _template_nodes(template)
        if node.get("$") == "attr"
        and isinstance(node.get("name"), str)
        and "default" in node
    }


def _literal_include_names(template: Any) -> list[str]:
    return [
        node["name"]
        for node in _template_nodes(template)
        if node.get("$") == "include" and isinstance(node.get("name"), str)
    ]


def _resolve_includes(
    template: Any, examples_by_name: dict[str, dict]
) -> dict[str, Any]:
    """OQ-025d: populate includes with every literal include name found in
    the seed template, transitively through included templates, resolved from
    snapshot ``docs.examples`` by name; unresolved names stay absent."""
    includes: dict[str, Any] = {}
    pending = _literal_include_names(template)
    seen: set[str] = set()
    while pending:
        name = pending.pop(0)
        if name in seen:
            continue
        seen.add(name)
        entry = examples_by_name.get(name)
        if entry is None:
            continue  # the corpus result may depend on the miss (OQ-025d)
        includes[name] = deepcopy(entry["template"])
        pending.extend(_literal_include_names(entry["template"]))
    return includes


def _writes_capable(template: Any, includes: dict[str, Any]) -> bool:
    """OQ-025e: a ``file`` rule in the template or any included template."""
    return any(
        node.get("$") == "file"
        for tpl in [template, *includes.values()]
        for node in _template_nodes(tpl)
    )


def _delete_at(data: Any, tokens: list[str]) -> Any:
    """Deep-copied *data* with the key/index at *tokens* removed."""
    out = deepcopy(data)
    parent = out
    for token in tokens[:-1]:
        parent = parent[int(token)] if isinstance(parent, list) else parent[token]
    last = tokens[-1]
    if isinstance(parent, list):
        del parent[int(last)]
    else:
        del parent[last]
    return out


def _set_at(data: Any, tokens: list[str], value: Any) -> Any:
    """Deep-copied *data* with *value* placed at *tokens*."""
    out = deepcopy(data)
    parent = out
    for token in tokens[:-1]:
        parent = parent[int(token)] if isinstance(parent, list) else parent[token]
    last = tokens[-1]
    if isinstance(parent, list):
        parent[int(last)] = deepcopy(value)
    else:
        parent[last] = deepcopy(value)
    return out


def _variation(data: Any, index: int) -> Any | None:
    """Value-variation input ``index`` (FR-029): the corpus ``data`` shape
    with each leaf scalar replaced by a deterministic alternate from
    :data:`SUBSTITUTION_TABLE`, position-indexed over the full pre-order leaf
    sequence. Returns ``None`` when nothing could be substituted."""
    position = 0
    changed = 0

    def substitute(value: Any) -> Any:
        nonlocal position, changed
        if isinstance(value, dict):
            return {k: substitute(v) for k, v in value.items()}
        if isinstance(value, list):
            return [substitute(v) for v in value]
        if isinstance(value, bool):
            kind = "boolean"
        elif isinstance(value, (int, float)):
            kind = "number"
        elif isinstance(value, str):
            kind = "string"
        else:
            return value  # null: kept verbatim
        table = SUBSTITUTION_TABLE[kind]
        slot = (index + position) % len(table)
        if table[slot] == value:
            slot = (slot + 1) % len(table)
        position += 1
        if table[slot] == value:
            return value
        changed += 1
        return table[slot]

    candidate = substitute(data)
    return candidate if changed else None


# --------------------------------------------------------------------------
# Core generation.
# --------------------------------------------------------------------------


class _Engine:
    """Dry-run cache: one sandboxed engine execution per distinct input."""

    def __init__(self, template: Any, includes: dict[str, Any]):
        self._template = template
        self._includes = includes
        self._cache: dict[str, dict] = {}

    def run(self, input_value: Any) -> dict:
        key = json.dumps(input_value, sort_keys=True, separators=(",", ":"))
        if key not in self._cache:
            self._cache[key] = dry_run(self._template, input_value, self._includes)
        return self._cache[key]


def _obligation(
    used_ids: set[str], base: str, kind: str, description: str, target: str | None
) -> dict[str, Any]:
    ob_id = base
    suffix = 2
    while ob_id in used_ids:
        ob_id = f"{base}-{suffix}"
        suffix += 1
    used_ids.add(ob_id)
    obligation: dict[str, Any] = {"id": ob_id, "kind": kind}
    if target is not None:
        obligation["target"] = target
    obligation["description"] = description
    obligation["acceptance"] = "accepted"
    return obligation


def _slug(pointer: str) -> str:
    out = []
    for ch in pointer[1:]:
        if ch == "/":
            out.append("-")
        elif ch.isalnum() or ch in "_-.":
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)


def _build(
    source_example: dict,
    engine: _Engine,
    plan: list[dict[str, Any]],
    dropped: set[str],
    writes_capable: bool,
) -> tuple[list[dict], list[dict]]:
    """One deterministic build pass under a fixed dropped-kinds set.

    Returns ``(coverage, cases)``; raises :class:`GeneratorError` when the
    seed is ineligible (corpus-pair assert, failing structural derivation).
    """
    data = source_example["data"]
    coverage: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    def add_case(input_value: Any, *, context: str) -> dict[str, Any]:
        envelope = engine.run(input_value)
        if not envelope["ok"]:
            raise GeneratorError(
                f"seed {source_example['name']!r}: dry-run failed for the "
                f"{context} input under the pinned engine: "
                f"{envelope['errors'][0]['message']} (FR-029)"
            )
        case: dict[str, Any] = {
            "id": f"c-{len(cases) + 1}",
            "input": deepcopy(input_value),
            "output": envelope["result"],
        }
        if envelope["writes"]:
            case["writes"] = envelope["writes"]
        case["satisfies"] = []
        cases.append(case)
        return case

    def satisfy(obligation: dict[str, Any], case: dict[str, Any]) -> None:
        case["satisfies"].append(obligation["id"])

    def find_satisfying(kind: str, target: str) -> dict[str, Any] | None:
        tokens = _parse_pointer(target)
        for case in cases:
            if _structural_check(kind, tokens, case["input"]):
                return case
        return None

    # Case 1 — the AD-021 corpus pair, re-executed and asserted (OQ-025d).
    corpus_case = add_case(data, context="corpus `data`")
    if corpus_case["output"] != source_example["result"]:
        raise GeneratorError(
            f"seed {source_example['name']!r}: re-executed corpus `data` does "
            "not JSON-equal the snapshot `result` — seed ineligible "
            "(AD-021 / OQ-025d)"
        )
    happy = _obligation(
        used_ids,
        "ob-happy",
        "happy_path",
        "Happy path: the corpus example's own data/result pair re-executed "
        "through the pinned engine (AD-021 corpus pair).",
        None,
    )
    coverage.append(happy)
    satisfy(happy, corpus_case)

    # Structural kinds in walk order (OQ-025a/b), subject to the drop set.
    absent_derivations: list[Any] = []  # NO_CONTENT candidates (OQ-025c)
    empty_derivations: list[Any] = []
    for entry in plan:
        pointer, tokens, value = entry["pointer"], entry["tokens"], entry["value"]
        slug = _slug(pointer)
        if entry["optional"]:
            if "optional_present" not in dropped:
                present = _obligation(
                    used_ids,
                    f"ob-optional-present--{slug}",
                    "optional_present",
                    f"Optional key at {pointer} is present in the input.",
                    pointer,
                )
                coverage.append(present)
                satisfy(present, find_satisfying("optional_present", pointer))
            absent_input = _delete_at(data, tokens)
            absent_derivations.append(absent_input)
            absent = _obligation(
                used_ids,
                f"ob-optional-absent--{slug}",
                "optional_absent",
                f"Optional key at {pointer} is absent from the input.",
                pointer,
            )
            coverage.append(absent)
            case = find_satisfying("optional_absent", pointer)
            if case is None:
                case = add_case(absent_input, context=f"optional_absent {pointer}")
            satisfy(absent, case)
        if entry["array"]:
            empty_input = _set_at(data, tokens, [])
            empty_derivations.append(empty_input)
            empty = _obligation(
                used_ids,
                f"ob-list-empty--{slug}",
                "list_empty",
                f"Array at {pointer} is empty.",
                pointer,
            )
            coverage.append(empty)
            case = find_satisfying("list_empty", pointer)
            if case is None:
                case = add_case(empty_input, context=f"list_empty {pointer}")
            satisfy(empty, case)
            if "list_singleton" not in dropped and len(value) >= 1:
                singleton = _obligation(
                    used_ids,
                    f"ob-list-singleton--{slug}",
                    "list_singleton",
                    f"Array at {pointer} has exactly one element.",
                    pointer,
                )
                coverage.append(singleton)
                case = find_satisfying("list_singleton", pointer)
                if case is None:
                    case = add_case(
                        _set_at(data, tokens, [value[0]]),
                        context=f"list_singleton {pointer}",
                    )
                satisfy(singleton, case)
            if "list_many" not in dropped and len(value) >= 1:
                many = _obligation(
                    used_ids,
                    f"ob-list-many--{slug}",
                    "list_many",
                    f"Array at {pointer} has two or more elements.",
                    pointer,
                )
                coverage.append(many)
                case = find_satisfying("list_many", pointer)
                if case is None:
                    case = add_case(
                        _set_at(data, tokens, [value[0], deepcopy(value[0])]),
                        context=f"list_many {pointer}",
                    )
                satisfy(many, case)

    # NO_CONTENT relevance — empirical, engine-decided (OQ-025c). Candidate
    # order is normative: optional_absent derivations in pointer order, then
    # list_empty derivations in pointer order, then the value-variation
    # candidates in position order.
    candidates = list(absent_derivations) + list(empty_derivations)
    for index in range(PROBE_VARIATIONS):
        variation = _variation(data, index)
        if variation is not None:
            candidates.append(variation)
    for candidate in candidates:
        envelope = engine.run(candidate)
        if envelope["ok"] and envelope["result"] == NO_CONTENT_REF:
            no_content = _obligation(
                used_ids,
                "ob-no-content",
                "custom",
                "NO_CONTENT: an input drives the template to the engine "
                "NO_CONTENT sentinel (empirical relevance, OQ-025c).",
                None,
            )
            coverage.append(no_content)
            case = next((c for c in cases if c["input"] == candidate), None)
            if case is None:
                case = add_case(candidate, context="NO_CONTENT candidate")
            satisfy(no_content, case)
            break

    # writes-capable seeds get the writes custom case (OQ-025e): the
    # satisfying case asserts the sandbox-captured writes map.
    if writes_capable:
        writes_ob = _obligation(
            used_ids,
            "ob-writes",
            "custom",
            "writes: the template is writes-capable; the satisfying case "
            "asserts the sandbox-captured writes map (OQ-025e).",
            None,
        )
        coverage.append(writes_ob)
        case = next((c for c in cases if c.get("writes")), cases[0])
        satisfy(writes_ob, case)

    return coverage, cases


def generate(
    source_example: dict, fixture_id: str, intent_nl: str
) -> tuple[dict, dict]:
    """Mint one EvalFixture + seed provenance doc from a snapshot
    ``docs.examples`` entry (FR-029 / AD-021 / OQ-025).

    Pure core shared by the maintainer CLI and the ``check_evals --lint``
    AC-030 regen check. Deterministic: same (entry, id, intent, pin) ⇒ same
    documents. Raises :class:`GeneratorError` for ineligible seeds.
    """
    template = source_example["template"]
    data = source_example["data"]
    examples_by_name = {e["name"]: e for e in get_metadata()["docs"]["examples"]}
    includes = _resolve_includes(template, examples_by_name)
    engine = _Engine(template, includes)
    optional_names = _attr_default_names(template)
    plan = _walk_plan(data, optional_names)
    writes_capable = _writes_capable(template, includes)

    # FR-029 budget rule: full build first, then the fixed drop order until
    # the 6-case cap fits; never-dropped kinds exceeding the cap ⇒ ineligible.
    drop_sets = [set(DROP_ORDER[:n]) for n in range(len(DROP_ORDER) + 1)]
    coverage: list[dict] | None = None
    cases: list[dict] | None = None
    for dropped in drop_sets:
        coverage, cases = _build(source_example, engine, plan, dropped, writes_capable)
        if len(cases) <= MAX_CASES:
            break
    if cases is None or len(cases) > MAX_CASES:
        raise GeneratorError(
            f"seed {source_example['name']!r}: never-dropped obligations "
            f"exceed the {MAX_CASES}-case budget — seed ineligible (OQ-025d)"
        )

    # Pad to the 3-case minimum with value-variation customs (FR-029).
    variation_number = 0
    index = 0
    while len(cases) < MIN_CASES:
        if index >= MAX_VARIATION_ATTEMPTS:
            raise GeneratorError(
                f"seed {source_example['name']!r}: cannot reach the "
                f"{MIN_CASES}-case minimum — no further value variations are "
                "derivable (FR-029)"
            )
        candidate = _variation(data, index)
        index += 1
        if candidate is None:
            raise GeneratorError(
                f"seed {source_example['name']!r}: cannot reach the "
                f"{MIN_CASES}-case minimum — the corpus data has no "
                "substitutable leaf scalars (FR-029)"
            )
        if any(case["input"] == candidate for case in cases):
            continue
        envelope = engine.run(candidate)
        if not envelope["ok"]:
            continue  # try the next deterministic variation index
        variation_number += 1
        obligation = {
            "id": f"ob-variation-{variation_number}",
            "kind": "custom",
            "description": (
                f"Value variation {variation_number}: the corpus data shape "
                "with leaf scalars replaced from the fixed per-JSON-type "
                "substitution table (FR-029)."
            ),
            "acceptance": "accepted",
        }
        coverage.append(obligation)
        case: dict[str, Any] = {
            "id": f"c-{len(cases) + 1}",
            "input": candidate,
            "output": envelope["result"],
        }
        if envelope["writes"]:
            case["writes"] = envelope["writes"]
        case["satisfies"] = [obligation["id"]]
        cases.append(case)

    samples: dict[str, Any] = {
        "schema_version": "1.0",
        "intent_nl": intent_nl,
        "coverage": coverage,
        "cases": cases,
        "waivers": [],
    }
    if includes:
        samples["includes"] = includes
    # OQ-015 acquisition path: the fingerprint comes from the library's
    # SampleCheck, never hand-computed; determinism forbids confirmed_at.
    samples["confirmation"] = {"confirmed": False, "content_fingerprint": ""}
    fingerprint = check_samples(samples)["content_fingerprint"]
    samples["confirmation"] = {
        "confirmed": True,
        "confirmed_by": "ci",
        "content_fingerprint": fingerprint,
    }
    final_check = check_samples(samples)
    if not final_check["ok_for_verify"]:
        gaps = ", ".join(sorted({gap["code"] for gap in final_check["gaps"]}))
        raise GeneratorError(
            f"seed {source_example['name']!r}: generated SampleSet is not "
            f"ok_for_verify (gaps: {gaps or 'none reported'}) — generator bug "
            "(FR-029)"
        )

    fixture = {
        "schema_version": "1.0",
        "id": fixture_id,
        "expect": "matched",
        "intent_nl": intent_nl,
        "samples": samples,
        "notes": (
            f"Synthetic fixture minted from the pinned snapshot docs.examples "
            f"entry '{source_example['name']}' (AD-021 / FR-029); seed "
            f"provenance at evals/seeds/{fixture_id}.json."
        ),
        "redacted": False,
    }
    seed = {
        "source_example": source_example["name"],
        "template": deepcopy(template),
        "generator": {"version": GENERATOR_VERSION},
    }
    return fixture, seed


# --------------------------------------------------------------------------
# Maintainer CLI.
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gen_fixtures",
        description="Mint a synthetic EvalFixture + seed provenance doc from "
        "a pinned-snapshot docs.examples entry (FR-029 / AD-021). The seed "
        "template stays provenance-only under evals/seeds/. The intent NL is "
        "LLM-drafted and human-accepted BEFORE commit (AD-021) — this tool "
        "only records the accepted text.",
    )
    parser.add_argument("--example", required=True, help="docs.examples entry name")
    parser.add_argument(
        "--fixture-id", required=True, help="fixture id (and both file stems)"
    )
    parser.add_argument(
        "--intent-nl", required=True, help="human-accepted synthetic intent NL"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repo root containing evals/ (default: this script's repo)",
    )
    parser.add_argument(
        "--force", action="store_true", help="overwrite existing fixture/seed files"
    )
    args = parser.parse_args(argv)

    examples_by_name = {e["name"]: e for e in get_metadata()["docs"]["examples"]}
    entry = examples_by_name.get(args.example)
    if entry is None:
        print(
            f"gen-fixtures: config error: example {args.example!r} is not in "
            "the pinned snapshot docs.examples (AD-021)",
            file=sys.stderr,
        )
        return 2

    fixture_path = args.root / "evals" / "cases" / f"{args.fixture_id}.json"
    seed_path = args.root / "evals" / "seeds" / f"{args.fixture_id}.json"
    if not args.force and (fixture_path.exists() or seed_path.exists()):
        print(
            f"gen-fixtures: refusing to overwrite {fixture_path} / {seed_path} "
            "without --force",
            file=sys.stderr,
        )
        return 2

    try:
        fixture, seed = generate(entry, args.fixture_id, args.intent_nl)
    except GeneratorError as exc:
        print(f"gen-fixtures: FAIL: {exc}", file=sys.stderr)
        return 1

    # AD-004 — never record a fixture whose seed template does not verify
    # matched against the generated SampleSet.
    verdict = verify(entry["template"], fixture["samples"])
    if not (verdict["ok"] and verdict.get("assurance") == "matched"):
        print(
            f"gen-fixtures: FAIL: seed template does not verify matched "
            f"against the generated SampleSet (failed stage: "
            f"{verdict.get('failed_stage')!r}) — fixture not written (AD-004)",
            file=sys.stderr,
        )
        return 1

    seed_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    seed_path.write_text(
        json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"gen-fixtures: minted {fixture_path} + {seed_path} "
        f"({len(fixture['samples']['cases'])} cases)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
