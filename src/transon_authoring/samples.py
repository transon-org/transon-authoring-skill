"""SampleSet coverage/confirmation checking — `check_samples` (SPEC §11.1).

Public module per ARCHITECTURE §10. Implements the §11.1 normative algorithm
(steps 1–7) supporting FR-027 / AC-016 / AC-017:

* step 1 — JSON Schema ``1.0`` validation via the bundled draft 2020-12
  ``sample_set.json`` (OQ-014e), **including** the §11.0 AuthoringTag decoding
  rules: an object containing ``"$transon_authoring"`` that is not exactly a
  known tag, at any nesting level of a case's ``output`` / ``writes`` values,
  is a SampleSet schema failure (gap ``schema_invalid``, "unknown authoring
  tag" message — §11.0 rule 2);
* step 2 — duplicate ``coverage.id`` / ``cases.id`` / ``waivers.id``;
* steps 3–4 — acceptance handling, waivers, and the kind-specific obligation
  table (JSON-pointer targets per RFC 6901, resolved against the satisfying
  case's ``input`` only);
* step 5 — ``coverage_complete``; step 6 — ``confirmed``; step 7 —
  ``ok_for_verify``.

Gaps are emitted in the normative order (§11.1 "Gap order", OQ-013):
(1) ``schema_invalid`` sorted by (JSON instance path, message);
(2) ``duplicate_id`` in document order coverage → cases → waivers;
(3) obligation gaps in ``coverage[]`` order — within one obligation
``obligation_not_accepted``, then ``target_required``/``target_invalid``,
then the kind's ``*_unmet`` code; (4) ``waiver_invalid`` in ``waivers[]``
order; (5) ``case_satisfies_unknown`` in ``cases[]`` order; (6) ``no_cases``;
(7) ``unconfirmed``, then ``fingerprint_mismatch``.

All results are deterministic functions of the SampleSet alone (NFR-002 /
AC-018). This module never sets ``confirmed: true`` on anything (§11.1).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ._ingress import schema_violations
from ._tags import UnknownAuthoringTagError, decode_expected

#: SampleSet members hashed by :func:`content_fingerprint` (§11.1
#: Confirmation): content only — ``intent_nl`` and ``confirmation`` are
#: deliberately excluded.
_FINGERPRINT_KEYS = ("schema_version", "coverage", "waivers", "cases", "includes")

#: Obligation kinds whose structural check needs a JSON-pointer ``target``
#: (§11.1 table). ``mode_choice`` target is a mode label (not a pointer) and
#: ``happy_path`` / ``custom`` targets are ignored — never validated.
_POINTER_KINDS = frozenset(
    ("optional_present", "optional_absent", "list_empty", "list_singleton", "list_many")
)

#: Gap code emitted when an accepted obligation of this kind is unmet.
_UNMET_CODE = {
    "happy_path": "missing_happy_path",
    "optional_present": "optional_present_unmet",
    "optional_absent": "optional_absent_unmet",
    "list_empty": "list_empty_unmet",
    "list_singleton": "list_singleton_unmet",
    "list_many": "list_many_unmet",
    "mode_choice": "mode_choice_unmet",
    "custom": "custom_unmet",
}

#: RFC 6901 §4 array-index token: 0 or a digit sequence without leading zeros.
_ARRAY_INDEX_RE = re.compile(r"^(0|[1-9][0-9]*)$")

#: Sentinel: a JSON pointer failed to resolve (missing key/index at any step).
_MISSING = object()


def content_fingerprint(sample_set: Any) -> str:
    """Hex sha256 fingerprint over the SampleSet content subset (§11.1).

    Normative canonicalization per the OQ-015 resolution (2026-07-11, A2
    standup; ROADMAP §15). This single function is the only implementation and
    the only place the byte-level rules live: ``json.dumps`` of the subset
    ``{schema_version, coverage, waivers, cases, includes}`` with
    ``sort_keys=True``, ``separators=(",", ":")``, ``ensure_ascii=False``,
    ``allow_nan=False``, hashed as UTF-8. An absent ``includes`` key is
    omitted from the subset — it is **not** hashed as ``{}``. Agents/skill
    NEVER recompute this: they acquire the value from
    ``SampleCheck.content_fingerprint`` (OQ-015 acquisition path).

    ``intent_nl`` and ``confirmation`` are deliberately excluded (§11.1
    Confirmation comment): editing human prose or the confirmation itself
    must not invalidate a confirmation.

    Tolerant by design so :func:`check_samples` can report on schema-invalid
    input: if *sample_set* is not an object, or the subset is not strictly
    JSON-serializable (non-string keys, non-finite numbers, non-JSON types),
    returns the empty string instead of raising. Keys missing from the
    document are simply omitted from the subset.
    """
    if not isinstance(sample_set, dict):
        return ""
    subset = {key: sample_set[key] for key in _FINGERPRINT_KEYS if key in sample_set}
    try:
        canonical = json.dumps(
            subset,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _escape_pointer_token(token: str) -> str:
    """RFC 6901 token escaping for building instance paths (~ then /)."""
    return token.replace("~", "~0").replace("/", "~1")


def _gap(code: str, message: str, *, obligation_id: str | None = None,
         case_id: str | None = None) -> dict[str, Any]:
    gap: dict[str, Any] = {"code": code, "message": message}
    if obligation_id is not None:
        gap["obligation_id"] = obligation_id
    if case_id is not None:
        gap["case_id"] = case_id
    return gap


def _unknown_tag_violations(sample_set: Any) -> list[tuple[str, str, str | None]]:
    """§11.0 rule 2 scan over every expectation position: run ``dec`` on each
    case's ``output`` and ``writes`` values; an unknown AuthoringTag anywhere
    inside is a SampleSet schema failure. Returns (instance path of the
    expectation position, message, case_id-if-known) triples. Defensive about
    shape so it can run alongside other schema violations."""
    violations: list[tuple[str, str, str | None]] = []
    if not isinstance(sample_set, dict):
        return violations
    cases = sample_set.get("cases")
    if not isinstance(cases, list):
        return violations
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            continue
        case_id = case.get("id")
        case_id = case_id if isinstance(case_id, str) else None
        positions: list[tuple[str, Any]] = []
        if "output" in case:
            positions.append((f"/cases/{index}/output", case["output"]))
        writes = case.get("writes")
        if isinstance(writes, dict):
            for name, value in writes.items():
                if isinstance(name, str):
                    pointer = f"/cases/{index}/writes/{_escape_pointer_token(name)}"
                    positions.append((pointer, value))
        for pointer, value in positions:
            try:
                decode_expected(value)
            except UnknownAuthoringTagError as exc:
                violations.append((pointer, str(exc), case_id))
    return violations


def _schema_invalid_gaps(sample_set: Any) -> list[dict[str, Any]]:
    """Step 1: bundled-schema violations merged with unknown-tag detections,
    sorted by (JSON instance path, message) (§11.1 gap order 1, OQ-013/014e)."""
    entries: list[tuple[str, str, str | None]] = [
        (pointer, message, None)
        for pointer, message in schema_violations(sample_set, "sample_set.json")
    ]
    entries.extend(_unknown_tag_violations(sample_set))
    entries.sort(key=lambda entry: (entry[0], entry[1]))
    return [
        _gap(
            "schema_invalid",
            f"{pointer or '<root>'}: {message}",
            case_id=case_id,
        )
        for pointer, message, case_id in entries
    ]


def _parse_pointer(target: Any) -> list[str] | None:
    """Parse a §11.1 obligation target as an RFC 6901 JSON pointer.

    Returns the unescaped reference tokens, or ``None`` when invalid: not a
    string, not starting with ``/`` (§11.1 requires a leading slash — the
    empty whole-document pointer is not accepted), or containing a bad
    ``~``-escape (only ``~0`` and ``~1`` exist).
    """
    if not isinstance(target, str) or not target.startswith("/"):
        return None
    tokens: list[str] = []
    for raw in target[1:].split("/"):
        out: list[str] = []
        i = 0
        while i < len(raw):
            ch = raw[i]
            if ch == "~":
                if i + 1 >= len(raw) or raw[i + 1] not in "01":
                    return None
                out.append("~" if raw[i + 1] == "0" else "/")
                i += 2
            else:
                out.append(ch)
                i += 1
        tokens.append("".join(out))
    return tokens


def _resolve(tokens: list[str], document: Any) -> Any:
    """RFC 6901 evaluation; returns :data:`_MISSING` when any step fails
    (missing key, non-index token against an array — incl. leading zeros —
    out-of-range index, or a scalar mid-path)."""
    current = document
    for token in tokens:
        if isinstance(current, dict):
            if token not in current:
                return _MISSING
            current = current[token]
        elif isinstance(current, list):
            if not _ARRAY_INDEX_RE.match(token) or int(token) >= len(current):
                return _MISSING
            current = current[int(token)]
        else:
            return _MISSING
    return current


def _structural_check(kind: str, tokens: list[str], case_input: Any) -> bool:
    """Kind-specific rule from the §11.1 table, against one case's ``input``."""
    value = _resolve(tokens, case_input)
    if kind == "optional_present":
        # Pointer resolves and the final key/index exists; null counts present.
        return value is not _MISSING
    if kind == "optional_absent":
        # Pointer does not resolve; a present null is NOT absent.
        return value is _MISSING
    if value is _MISSING or not isinstance(value, list):
        return False
    if kind == "list_empty":
        return len(value) == 0
    if kind == "list_singleton":
        return len(value) == 1
    # list_many
    return len(value) >= 2


def check_samples(sample_set: Any) -> dict[str, Any]:
    """Check a SampleSet per the §11.1 normative algorithm; return a
    ``SampleCheck`` dict (FR-027 support; AC-016 / AC-017).

    Steps 1–7 exactly, gaps in the normative order (module docstring).
    ``coverage_complete`` and ``confirmed`` are computed independently;
    ``ok_for_verify`` requires both plus the absence of ``schema_invalid`` /
    ``duplicate_id`` gaps (step 7).

    On schema-invalid input (bundled-schema failure or unknown AuthoringTag
    in an expectation position, §11.0 rule 2) the algorithm stops after
    step 1: all flags false, ``gaps`` holds only the sorted ``schema_invalid``
    entries, and ``content_fingerprint`` is still the :func:`content_fingerprint`
    of the document (empty string when no hashable content subset exists).

    Purely deterministic (NFR-002); never mutates *sample_set*; never touches
    the engine, filesystem, or network.
    """
    fingerprint = content_fingerprint(sample_set)
    schema_gaps = _schema_invalid_gaps(sample_set)
    if schema_gaps:
        return {
            "schema_version": "1.0",
            "coverage_complete": False,
            "confirmed": False,
            "ok_for_verify": False,
            "gaps": schema_gaps,
            "content_fingerprint": fingerprint,
        }

    coverage = sample_set["coverage"]
    cases = sample_set["cases"]
    waivers = sample_set["waivers"]

    # Step 2 — duplicate ids, document order coverage -> cases -> waivers.
    duplicate_gaps: list[dict[str, Any]] = []
    for label, items, id_field in (
        ("coverage", coverage, "obligation_id"),
        ("cases", cases, "case_id"),
        ("waivers", waivers, None),
    ):
        seen: set[str] = set()
        for item in items:
            item_id = item["id"]
            if item_id in seen:
                message = f'duplicate id "{item_id}" in {label}'
                if id_field == "obligation_id":
                    duplicate_gaps.append(
                        _gap("duplicate_id", message, obligation_id=item_id)
                    )
                elif id_field == "case_id":
                    duplicate_gaps.append(_gap("duplicate_id", message, case_id=item_id))
                else:
                    duplicate_gaps.append(_gap("duplicate_id", message))
            seen.add(item_id)

    known_ids = {ob["id"] for ob in coverage}

    # Waiver reference validation (§11.1 step 4: refs must point at
    # coverage[].id) and the set of obligations cleared by accepted waivers.
    # Per-reference granularity: each dangling ref is one waiver_invalid gap
    # (waivers[] order); the remaining valid refs of an accepted waiver still
    # clear their obligations.
    waiver_gaps: list[dict[str, Any]] = []
    cleared: set[str] = set()
    for entry in waivers:
        for obligation_id in entry["clears_obligation_ids"]:
            if obligation_id not in known_ids:
                waiver_gaps.append(
                    _gap(
                        "waiver_invalid",
                        f'waiver "{entry["id"]}" clears unknown obligation id'
                        f' "{obligation_id}"',
                    )
                )
            elif entry["acceptance"] == "accepted":
                cleared.add(obligation_id)

    # Steps 3–4 — obligations in coverage[] document order.
    obligation_gaps: list[dict[str, Any]] = []
    any_proposed = False
    any_unmet_accepted = False
    for ob in coverage:
        acceptance = ob["acceptance"]
        if acceptance == "rejected":  # step 3: rejected obligations ignored
            continue
        obligation_id = ob["id"]
        kind = ob["kind"]
        if acceptance == "proposed":
            any_proposed = True
            obligation_gaps.append(
                _gap(
                    "obligation_not_accepted",
                    f'obligation "{obligation_id}" is proposed, not accepted',
                    obligation_id=obligation_id,
                )
            )
            continue
        # acceptance == "accepted"
        if obligation_id in cleared:  # met by an accepted waiver
            continue
        met = False
        target_gap: dict[str, Any] | None = None
        if kind in _POINTER_KINDS:
            if "target" not in ob:
                target_gap = _gap(
                    "target_required",
                    f'obligation "{obligation_id}" (kind "{kind}") requires a'
                    " JSON pointer target",
                    obligation_id=obligation_id,
                )
            else:
                tokens = _parse_pointer(ob["target"])
                if tokens is None:
                    target_gap = _gap(
                        "target_invalid",
                        f'obligation "{obligation_id}" target'
                        f" {json.dumps(ob['target'], ensure_ascii=False)} is not"
                        ' a valid JSON pointer (RFC 6901, must start with "/")',
                        obligation_id=obligation_id,
                    )
                else:
                    met = any(
                        obligation_id in case["satisfies"]
                        and _structural_check(kind, tokens, case["input"])
                        for case in cases
                    )
        else:
            # happy_path / mode_choice / custom: no input structural check —
            # a satisfies claim on any case meets the obligation (§11.1 table).
            met = any(obligation_id in case["satisfies"] for case in cases)
        if target_gap is not None:
            obligation_gaps.append(target_gap)  # then unmet below (gap order 3)
        if not met:
            any_unmet_accepted = True
            obligation_gaps.append(
                _gap(
                    _UNMET_CODE[kind],
                    f'obligation "{obligation_id}" (kind "{kind}") is unmet: no'
                    " accepted waiver and no satisfying case",
                    obligation_id=obligation_id,
                )
            )

    # Step 4 — unknown ids in satisfies, cases[] order (meets no obligation).
    unknown_claim_gaps: list[dict[str, Any]] = []
    for case in cases:
        for obligation_id in case["satisfies"]:
            if obligation_id not in known_ids:
                unknown_claim_gaps.append(
                    _gap(
                        "case_satisfies_unknown",
                        f'case "{case["id"]}" satisfies unknown obligation id'
                        f' "{obligation_id}"',
                        case_id=case["id"],
                    )
                )

    # Step 5 — coverage_complete.
    no_cases_gaps: list[dict[str, Any]] = []
    if len(cases) == 0:
        no_cases_gaps.append(_gap("no_cases", "SampleSet has no cases"))
    coverage_complete = (
        not any_unmet_accepted and not any_proposed and len(cases) >= 1
    )

    # Step 6 — confirmation. Conjunct-wise gaps: `unconfirmed` when the
    # confirmed flag / confirmed_by attestation fails, `fingerprint_mismatch`
    # when the recorded fingerprint differs from the recomputed one.
    confirmation = sample_set["confirmation"]
    confirmed_flag = confirmation["confirmed"] is True
    by_valid = confirmation.get("confirmed_by") in ("user", "ci")
    fingerprint_match = confirmation["content_fingerprint"] == fingerprint
    confirmation_gaps: list[dict[str, Any]] = []
    if not confirmed_flag:
        confirmation_gaps.append(
            _gap("unconfirmed", "confirmation.confirmed is not true")
        )
    elif not by_valid:
        confirmation_gaps.append(
            _gap(
                "unconfirmed",
                'confirmation.confirmed_by must be "user" or "ci"',
            )
        )
    if not fingerprint_match:
        confirmation_gaps.append(
            _gap(
                "fingerprint_mismatch",
                "confirmation.content_fingerprint does not match the"
                " recomputed content fingerprint",
            )
        )
    confirmed = confirmed_flag and by_valid and fingerprint_match

    # Normative gap order (§11.1 "Gap order", OQ-013). No schema_invalid here:
    # step-1 failure returns early above.
    gaps = (
        duplicate_gaps
        + obligation_gaps
        + waiver_gaps
        + unknown_claim_gaps
        + no_cases_gaps
        + confirmation_gaps
    )

    # Step 7 — ok_for_verify.
    has_blocking = any(gap["code"] == "duplicate_id" for gap in gaps)
    return {
        "schema_version": "1.0",
        "coverage_complete": coverage_complete,
        "confirmed": confirmed,
        "ok_for_verify": coverage_complete and confirmed and not has_blocking,
        "gaps": gaps,
        "content_fingerprint": fingerprint,
    }
