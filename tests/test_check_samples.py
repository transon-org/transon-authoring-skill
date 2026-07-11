"""FR-027 — `check_samples` samples core (SPEC §11.1; supports AC-016, AC-017).

Covers the §11.1 normative algorithm steps 1–7, the kind-specific obligation
table, the normative gap emission order (§11.1 "Gap order", OQ-013), and the
§11.0 decoding rule 2 (unknown AuthoringTag in an expectation position →
`schema_invalid`). Fingerprints in fixtures are always acquired by calling
`content_fingerprint(...)` — never hardcoded (OQ-015 acquisition-path rule).
"""

import copy

from transon_authoring import check_samples
from transon_authoring._ingress import schema_violations
from transon_authoring.samples import content_fingerprint

TAG_KEY = "$transon_authoring"


# ---------------------------------------------------------------------------
# Fixture builders (§11.1 shapes)
# ---------------------------------------------------------------------------


def obligation(oid, kind, *, target=None, acceptance="accepted"):
    ob = {
        "id": oid,
        "kind": kind,
        "description": f"obligation {oid}",
        "acceptance": acceptance,
    }
    if target is not None:
        ob["target"] = target
    return ob


def sample_case(cid, *, input=None, output="out", writes=None, satisfies=()):
    case = {"id": cid, "input": input, "output": output, "satisfies": list(satisfies)}
    if writes is not None:
        case["writes"] = writes
    return case


def waiver(wid, clears, *, acceptance="accepted"):
    return {
        "id": wid,
        "clears_obligation_ids": list(clears),
        "reason": f"waiver {wid}",
        "acceptance": acceptance,
    }


def sample_set(
    *,
    coverage=None,
    cases=None,
    waivers=None,
    includes=None,
    intent_nl=None,
    confirmed=True,
    confirmed_by="user",
    fingerprint=None,
):
    ss = {
        "schema_version": "1.0",
        "coverage": coverage
        if coverage is not None
        else [obligation("happy", "happy_path")],
        "cases": cases
        if cases is not None
        else [sample_case("c1", input={"n": 1}, satisfies=["happy"])],
        "waivers": waivers if waivers is not None else [],
    }
    if includes is not None:
        ss["includes"] = includes
    if intent_nl is not None:
        ss["intent_nl"] = intent_nl
    confirmation = {
        "confirmed": confirmed,
        # §11.1 Confirmation: fingerprint over the canonical content subset.
        "content_fingerprint": content_fingerprint(ss)
        if fingerprint is None
        else fingerprint,
    }
    if confirmed_by is not None:
        confirmation["confirmed_by"] = confirmed_by
    ss["confirmation"] = confirmation
    return ss


def gap_codes(check):
    return [gap["code"] for gap in check["gaps"]]


# ---------------------------------------------------------------------------
# Happy path + result shape (§11.1 SampleCheck)
# ---------------------------------------------------------------------------


def test_fr_027_complete_confirmed_set_is_ok_for_verify():
    ss = sample_set()
    check = check_samples(ss)
    assert check == {
        "schema_version": "1.0",
        "coverage_complete": True,
        "confirmed": True,
        "ok_for_verify": True,
        "gaps": [],
        "content_fingerprint": content_fingerprint(ss),
    }


def test_fr_027_samplecheck_conforms_to_bundled_schema():
    # §11.1 SampleCheck shape, validated against the bundled draft 2020-12 schema.
    for ss in (
        sample_set(),
        sample_set(cases=[], confirmed=False, fingerprint="stale"),
        {"schema_version": "1.0"},  # schema-invalid input
    ):
        assert schema_violations(check_samples(ss), "sample_check.json") == []


# ---------------------------------------------------------------------------
# Step 1 — schema validation, incl. §11.0 rule 2 (unknown AuthoringTag)
# ---------------------------------------------------------------------------


def test_ac_016_schema_invalid_all_flags_false():
    check = check_samples({"schema_version": "1.0"})  # missing required members
    assert check["coverage_complete"] is False
    assert check["confirmed"] is False
    assert check["ok_for_verify"] is False
    assert check["gaps"] and set(gap_codes(check)) == {"schema_invalid"}


def test_ac_016_non_object_input_schema_invalid_empty_fingerprint():
    check = check_samples([])
    assert check["coverage_complete"] is False
    assert check["confirmed"] is False
    assert check["ok_for_verify"] is False
    assert set(gap_codes(check)) == {"schema_invalid"}
    # Documented behavior: no hashable content subset -> empty fingerprint.
    assert check["content_fingerprint"] == ""


def test_ac_016_wrong_schema_version_schema_invalid():
    ss = sample_set()
    ss["schema_version"] = "2.0"
    check = check_samples(ss)
    assert set(gap_codes(check)) == {"schema_invalid"}
    assert check["ok_for_verify"] is False


def test_fr_027_unknown_authoring_tag_in_output_schema_invalid():
    # §11.0 rule 2: object containing "$transon_authoring" that is not a known
    # tag -> SampleSet schema failure, gap schema_invalid ("unknown authoring tag").
    ss = sample_set(
        cases=[sample_case("c1", output={TAG_KEY: "bogus"}, satisfies=["happy"])]
    )
    check = check_samples(ss)
    assert check["coverage_complete"] is False
    assert check["confirmed"] is False
    assert check["ok_for_verify"] is False
    assert gap_codes(check) == ["schema_invalid"]
    assert "unknown authoring tag" in check["gaps"][0]["message"]
    assert "/cases/0/output" in check["gaps"][0]["message"]


def test_fr_027_unknown_tag_detected_recursively_and_in_writes():
    # §11.0: decoding applies recursively at every nesting level of an
    # expected value; writes values are expectation positions too.
    nested = sample_set(
        cases=[
            sample_case(
                "c1", output={"a": [{TAG_KEY: "lit"}]}, satisfies=["happy"]
            )  # LitRef missing "value" -> unknown tag
        ]
    )
    assert gap_codes(check_samples(nested)) == ["schema_invalid"]

    in_writes = sample_set(
        cases=[
            sample_case(
                "c1",
                writes={"log": {TAG_KEY: "NO_CONTENT", "extra": 1}},
                satisfies=["happy"],
            )
        ]
    )
    check = check_samples(in_writes)
    assert gap_codes(check) == ["schema_invalid"]
    assert "/cases/0/writes/log" in check["gaps"][0]["message"]


def test_fr_027_known_tags_in_expectations_are_valid():
    # §11.0 rule 1: NoContentRef / LitRef are legal expectation values,
    # including a LitRef whose literal data is itself a tagged shape.
    ss = sample_set(
        cases=[
            sample_case(
                "c1",
                output={TAG_KEY: "NO_CONTENT"},
                writes={
                    "w1": {TAG_KEY: "lit", "value": {TAG_KEY: "NO_CONTENT"}},
                    "w2": [1, {TAG_KEY: "lit", "value": 2}],
                },
                satisfies=["happy"],
            )
        ]
    )
    check = check_samples(ss)
    assert check["gaps"] == []
    assert check["ok_for_verify"] is True


def test_fr_027_schema_invalid_gaps_sorted_by_instance_path_and_message():
    # §11.1 gap order (1): schema_invalid sorted by (JSON instance path,
    # message) — validator violations and unknown-tag detections merged.
    ss = sample_set(
        coverage=[{"id": "ob1", "kind": "happy_path", "acceptance": "accepted"}],
        cases=[sample_case("c1", output={TAG_KEY: "bogus"}, satisfies=["ob1"])],
    )  # missing coverage[0].description at /coverage/0; unknown tag at /cases/0/output
    check = check_samples(ss)
    assert gap_codes(check) == ["schema_invalid", "schema_invalid"]
    # "/cases/0/output" sorts before "/coverage/0"
    assert "unknown authoring tag" in check["gaps"][0]["message"]
    assert "/cases/0/output" in check["gaps"][0]["message"]
    assert "/coverage/0" in check["gaps"][1]["message"]


# ---------------------------------------------------------------------------
# Step 2 — duplicate ids (document order coverage -> cases -> waivers)
# ---------------------------------------------------------------------------


def test_fr_027_duplicate_ids_in_each_array():
    ss = sample_set(
        coverage=[obligation("ob1", "happy_path"), obligation("ob1", "happy_path")],
        cases=[
            sample_case("c1", satisfies=["ob1"]),
            sample_case("c1", satisfies=[]),
        ],
        waivers=[waiver("w1", []), waiver("w1", [])],
    )
    check = check_samples(ss)
    assert gap_codes(check) == ["duplicate_id", "duplicate_id", "duplicate_id"]
    assert check["gaps"][0]["obligation_id"] == "ob1"
    assert "coverage" in check["gaps"][0]["message"]
    assert check["gaps"][1]["case_id"] == "c1"
    assert "cases" in check["gaps"][1]["message"]
    assert "waivers" in check["gaps"][2]["message"]
    assert check["ok_for_verify"] is False


def test_fr_027_duplicate_id_alone_blocks_ok_for_verify():
    # §11.1 step 7: ok_for_verify needs no schema/duplicate gaps even when
    # coverage_complete and confirmed are both true.
    ss = sample_set(waivers=[waiver("w1", []), waiver("w1", [])])
    check = check_samples(ss)
    assert check["coverage_complete"] is True
    assert check["confirmed"] is True
    assert gap_codes(check) == ["duplicate_id"]
    assert check["ok_for_verify"] is False


# ---------------------------------------------------------------------------
# Steps 3–4 — acceptance and the kind-specific obligation table
# ---------------------------------------------------------------------------


def test_fr_027_proposed_obligation_not_accepted():
    ss = sample_set(
        coverage=[
            obligation("happy", "happy_path"),
            obligation("opt", "optional_present", target="/x", acceptance="proposed"),
        ]
    )
    check = check_samples(ss)
    assert gap_codes(check) == ["obligation_not_accepted"]
    assert check["gaps"][0]["obligation_id"] == "opt"
    assert check["coverage_complete"] is False
    assert check["ok_for_verify"] is False


def test_fr_027_rejected_obligation_ignored():
    ss = sample_set(
        coverage=[
            obligation("happy", "happy_path"),
            obligation("opt", "optional_present", target="/x", acceptance="rejected"),
        ]
    )
    check = check_samples(ss)
    assert check["gaps"] == []
    assert check["coverage_complete"] is True
    assert check["ok_for_verify"] is True


def test_fr_027_happy_path_met_by_satisfies_claim_alone():
    met = sample_set(
        coverage=[obligation("happy", "happy_path")],
        cases=[sample_case("c1", input={"n": 1}, satisfies=["happy"])],
    )
    assert check_samples(met)["coverage_complete"] is True

    unmet = sample_set(
        coverage=[obligation("happy", "happy_path")],
        cases=[sample_case("c1", input={"n": 1}, satisfies=[])],
    )
    check = check_samples(unmet)
    assert gap_codes(check) == ["missing_happy_path"]
    assert check["gaps"][0]["obligation_id"] == "happy"
    assert check["coverage_complete"] is False


def test_fr_027_happy_path_target_is_ignored_not_validated():
    # §11.1 table: happy_path target is "ignored" — even a non-pointer string.
    ss = sample_set(
        coverage=[obligation("happy", "happy_path", target="not a pointer")],
    )
    assert check_samples(ss)["gaps"] == []


def test_fr_027_optional_present_pointer_must_resolve():
    cov = [
        obligation("happy", "happy_path"),
        obligation("opt", "optional_present", target="/a/b"),
    ]
    met = sample_set(
        coverage=cov,
        cases=[sample_case("c1", input={"a": {"b": 1}}, satisfies=["happy", "opt"])],
    )
    assert check_samples(met)["coverage_complete"] is True

    unmet = sample_set(
        coverage=cov,
        cases=[sample_case("c1", input={"a": {}}, satisfies=["happy", "opt"])],
    )
    check = check_samples(unmet)
    assert gap_codes(check) == ["optional_present_unmet"]
    assert check["coverage_complete"] is False


def test_fr_027_optional_present_null_counts_as_present():
    # §11.1 table: `null` counts as present (key exists).
    ss = sample_set(
        coverage=[
            obligation("happy", "happy_path"),
            obligation("opt", "optional_present", target="/a"),
        ],
        cases=[sample_case("c1", input={"a": None}, satisfies=["happy", "opt"])],
    )
    check = check_samples(ss)
    assert check["gaps"] == []
    assert check["coverage_complete"] is True


def test_fr_027_optional_absent_present_null_is_not_absent():
    cov = [
        obligation("happy", "happy_path"),
        obligation("abs", "optional_absent", target="/a"),
    ]
    unmet = sample_set(
        coverage=cov,
        cases=[sample_case("c1", input={"a": None}, satisfies=["happy", "abs"])],
    )
    check = check_samples(unmet)
    assert gap_codes(check) == ["optional_absent_unmet"]

    met = sample_set(
        coverage=cov,
        cases=[sample_case("c1", input={"b": 1}, satisfies=["happy", "abs"])],
    )
    assert check_samples(met)["coverage_complete"] is True


def test_fr_027_optional_absent_deep_missing_prefix_is_absent():
    # Resolution failing at any depth means the pointer does not resolve.
    ss = sample_set(
        coverage=[
            obligation("happy", "happy_path"),
            obligation("abs", "optional_absent", target="/a/b/c"),
        ],
        cases=[sample_case("c1", input={}, satisfies=["happy", "abs"])],
    )
    assert check_samples(ss)["coverage_complete"] is True


def test_fr_027_list_length_kinds():
    cov = [
        obligation("empty", "list_empty", target="/xs"),
        obligation("one", "list_singleton", target="/xs"),
        obligation("many", "list_many", target="/xs"),
    ]
    cases = [
        sample_case("c0", input={"xs": []}, satisfies=["empty"]),
        sample_case("c1", input={"xs": [1]}, satisfies=["one"]),
        sample_case("c2", input={"xs": [1, 2, 3]}, satisfies=["many"]),
    ]
    assert check_samples(sample_set(coverage=cov, cases=cases))["gaps"] == []

    # Wrong lengths (and non-arrays) do not meet the list_* rules.
    wrong = [
        sample_case("c0", input={"xs": [1]}, satisfies=["empty"]),
        sample_case("c1", input={"xs": []}, satisfies=["one"]),
        sample_case("c2", input={"xs": [1]}, satisfies=["many"]),
        sample_case("c3", input={"xs": "not-a-list"}, satisfies=["empty", "one", "many"]),
    ]
    check = check_samples(sample_set(coverage=cov, cases=wrong))
    assert gap_codes(check) == [
        "list_empty_unmet",
        "list_singleton_unmet",
        "list_many_unmet",
    ]


def test_fr_027_pointer_tilde_escapes_rfc6901():
    # RFC 6901: ~1 -> "/", ~0 -> "~".
    ss = sample_set(
        coverage=[
            obligation("happy", "happy_path"),
            obligation("opt", "optional_present", target="/a~1b/c~0d"),
        ],
        cases=[
            sample_case("c1", input={"a/b": {"c~d": 1}}, satisfies=["happy", "opt"])
        ],
    )
    assert check_samples(ss)["gaps"] == []


def test_fr_027_pointer_array_index_resolution():
    cov = [
        obligation("happy", "happy_path"),
        obligation("opt", "optional_present", target="/xs/1"),
    ]
    met = sample_set(
        coverage=cov,
        cases=[sample_case("c1", input={"xs": [10, 20]}, satisfies=["happy", "opt"])],
    )
    assert check_samples(met)["gaps"] == []

    # Out-of-range index and leading-zero token do not resolve (RFC 6901).
    unmet = sample_set(
        coverage=[
            obligation("happy", "happy_path"),
            obligation("opt", "optional_present", target="/xs/01"),
        ],
        cases=[sample_case("c1", input={"xs": [10, 20]}, satisfies=["happy", "opt"])],
    )
    assert gap_codes(check_samples(unmet)) == ["optional_present_unmet"]


def test_fr_027_pointer_resolves_against_input_only():
    # §11.1: resolve against the satisfying case's `input` only — output
    # containing the key does not count.
    ss = sample_set(
        coverage=[
            obligation("happy", "happy_path"),
            obligation("opt", "optional_present", target="/x"),
        ],
        cases=[
            sample_case(
                "c1", input={}, output={"x": 1}, satisfies=["happy", "opt"]
            )
        ],
    )
    assert gap_codes(check_samples(ss)) == ["optional_present_unmet"]


def test_fr_027_target_required_then_unmet():
    ss = sample_set(
        coverage=[
            obligation("happy", "happy_path"),
            obligation("empty", "list_empty"),  # pointer kind, no target
        ],
    )
    check = check_samples(ss)
    assert gap_codes(check) == ["target_required", "list_empty_unmet"]
    assert check["gaps"][0]["obligation_id"] == "empty"
    assert check["gaps"][1]["obligation_id"] == "empty"
    assert check["coverage_complete"] is False


def test_fr_027_target_invalid_then_unmet():
    no_slash = sample_set(
        coverage=[
            obligation("happy", "happy_path"),
            obligation("opt", "optional_present", target="x/y"),
        ],
    )
    check = check_samples(no_slash)
    assert gap_codes(check) == ["target_invalid", "optional_present_unmet"]

    bad_escape = sample_set(
        coverage=[
            obligation("happy", "happy_path"),
            obligation("opt", "optional_present", target="/a~2b"),
        ],
    )
    assert gap_codes(check_samples(bad_escape)) == [
        "target_invalid",
        "optional_present_unmet",
    ]


def test_fr_027_mode_choice_and_custom_attestation_no_structural_check():
    # §11.1 table: no input structural check; met by an accepted satisfies
    # claim on any case or by an accepted waiver; target is a label, not a pointer.
    cov = [
        obligation("mode", "mode_choice", target="variant-b"),
        obligation("cust", "custom"),
    ]
    met = sample_set(
        coverage=cov,
        cases=[sample_case("c1", input=None, satisfies=["mode", "cust"])],
    )
    assert check_samples(met)["gaps"] == []

    unmet = sample_set(
        coverage=cov,
        cases=[sample_case("c1", input=None, satisfies=[])],
    )
    assert gap_codes(check_samples(unmet)) == ["mode_choice_unmet", "custom_unmet"]

    waived = sample_set(
        coverage=cov,
        cases=[sample_case("c1", input=None, satisfies=[])],
        waivers=[waiver("w1", ["mode", "cust"])],
    )
    assert check_samples(waived)["gaps"] == []


def test_fr_027_obligation_met_if_any_satisfying_case_passes():
    ss = sample_set(
        coverage=[obligation("opt", "optional_present", target="/x")],
        cases=[
            sample_case("bad", input={}, satisfies=["opt"]),  # claim fails check
            sample_case("good", input={"x": 1}, satisfies=["opt"]),
        ],
    )
    check = check_samples(ss)
    assert check["gaps"] == []
    assert check["coverage_complete"] is True


# ---------------------------------------------------------------------------
# Step 4 — waivers
# ---------------------------------------------------------------------------


def test_ac_010_accepted_waiver_clears_obligation():
    ss = sample_set(
        coverage=[
            obligation("happy", "happy_path"),
            obligation("many", "list_many", target="/xs"),
        ],
        cases=[sample_case("c1", input={"xs": []}, satisfies=["happy"])],
        waivers=[waiver("w1", ["many"])],
    )
    check = check_samples(ss)
    assert check["gaps"] == []
    assert check["coverage_complete"] is True
    assert check["ok_for_verify"] is True


def test_fr_027_proposed_or_rejected_waiver_does_not_clear():
    for acceptance in ("proposed", "rejected"):
        ss = sample_set(
            coverage=[
                obligation("happy", "happy_path"),
                obligation("many", "list_many", target="/xs"),
            ],
            cases=[sample_case("c1", input={"xs": []}, satisfies=["happy"])],
            waivers=[waiver("w1", ["many"], acceptance=acceptance)],
        )
        check = check_samples(ss)
        assert gap_codes(check) == ["list_many_unmet"], acceptance
        assert check["coverage_complete"] is False


def test_fr_027_waiver_dangling_obligation_id_waiver_invalid():
    ss = sample_set(
        waivers=[waiver("w1", ["ghost"])],
    )
    check = check_samples(ss)
    assert gap_codes(check) == ["waiver_invalid"]
    assert "w1" in check["gaps"][0]["message"]
    assert "ghost" in check["gaps"][0]["message"]
    # §11.1 step 7 only excludes schema/duplicate gaps; coverage_complete and
    # confirmed both hold here, so waiver_invalid alone does not block.
    assert check["ok_for_verify"] is True


def test_fr_027_waiver_with_valid_and_dangling_refs_still_clears_valid_ones():
    ss = sample_set(
        coverage=[
            obligation("happy", "happy_path"),
            obligation("many", "list_many", target="/xs"),
        ],
        cases=[sample_case("c1", input={"xs": []}, satisfies=["happy"])],
        waivers=[waiver("w1", ["many", "ghost"])],
    )
    check = check_samples(ss)
    assert gap_codes(check) == ["waiver_invalid"]
    assert check["coverage_complete"] is True


# ---------------------------------------------------------------------------
# Step 4 — case_satisfies_unknown
# ---------------------------------------------------------------------------


def test_fr_027_case_satisfies_unknown_id():
    ss = sample_set(
        cases=[sample_case("c1", satisfies=["happy", "ghost"])],
    )
    check = check_samples(ss)
    assert gap_codes(check) == ["case_satisfies_unknown"]
    assert check["gaps"][0]["case_id"] == "c1"
    assert "ghost" in check["gaps"][0]["message"]
    # Coverage itself is still complete: "happy" is met.
    assert check["coverage_complete"] is True


def test_fr_027_satisfies_referencing_rejected_obligation_is_known():
    # Rejected obligations are ignored for coverage but their ids are known.
    ss = sample_set(
        coverage=[
            obligation("happy", "happy_path"),
            obligation("rej", "custom", acceptance="rejected"),
        ],
        cases=[sample_case("c1", satisfies=["happy", "rej"])],
    )
    assert check_samples(ss)["gaps"] == []


# ---------------------------------------------------------------------------
# Step 5 — no_cases / coverage_complete
# ---------------------------------------------------------------------------


def test_ac_016_zero_cases_no_cases_gap_and_incomplete():
    # Even with every obligation waived, zero cases -> not coverage_complete.
    ss = sample_set(
        coverage=[obligation("happy", "happy_path")],
        cases=[],
        waivers=[waiver("w1", ["happy"])],
    )
    check = check_samples(ss)
    assert gap_codes(check) == ["no_cases"]
    assert check["coverage_complete"] is False
    assert check["ok_for_verify"] is False


# ---------------------------------------------------------------------------
# Step 6 — confirmation
# ---------------------------------------------------------------------------


def test_ac_016_unconfirmed_gap():
    ss = sample_set(confirmed=False)  # fingerprint correct, confirmed false
    check = check_samples(ss)
    assert check["confirmed"] is False
    assert gap_codes(check) == ["unconfirmed"]
    assert check["ok_for_verify"] is False


def test_fr_027_fingerprint_mismatch_gap():
    ss = sample_set(fingerprint="0" * 64)  # confirmed true, stale fingerprint
    check = check_samples(ss)
    assert check["confirmed"] is False
    assert gap_codes(check) == ["fingerprint_mismatch"]
    assert check["ok_for_verify"] is False
    # The SampleCheck carries the recomputed fingerprint.
    assert check["content_fingerprint"] == content_fingerprint(ss)


def test_fr_027_confirmed_by_missing_is_unconfirmed():
    # §11.1 step 6: confirmed requires confirmed_by in {"user","ci"}.
    ss = sample_set(confirmed_by=None)
    check = check_samples(ss)
    assert check["confirmed"] is False
    assert gap_codes(check) == ["unconfirmed"]
    assert "confirmed_by" in check["gaps"][0]["message"]


def test_fr_027_confirmed_by_ci_is_valid():
    ss = sample_set(confirmed_by="ci")
    check = check_samples(ss)
    assert check["confirmed"] is True
    assert check["ok_for_verify"] is True


def test_fr_027_unconfirmed_then_fingerprint_mismatch_order():
    # §11.1 gap order (7): unconfirmed, then fingerprint_mismatch.
    ss = sample_set(confirmed=False, fingerprint="stale")
    check = check_samples(ss)
    assert gap_codes(check) == ["unconfirmed", "fingerprint_mismatch"]
    assert check["confirmed"] is False


# ---------------------------------------------------------------------------
# AC-017 — flag independence
# ---------------------------------------------------------------------------


def _incomplete_coverage():
    return [
        obligation("happy", "happy_path"),
        obligation("opt", "optional_present", target="/x"),
    ]


def _incomplete_cases():
    return [sample_case("c1", input={}, satisfies=["happy", "opt"])]


def test_ac_017_flags_independent():
    # All four combinations of (coverage_complete, confirmed); ok_for_verify
    # requires both (§11.1 step 7).
    both = check_samples(sample_set())
    assert (both["coverage_complete"], both["confirmed"]) == (True, True)
    assert both["ok_for_verify"] is True

    only_complete = check_samples(sample_set(confirmed=False))
    assert (only_complete["coverage_complete"], only_complete["confirmed"]) == (
        True,
        False,
    )
    assert only_complete["ok_for_verify"] is False

    only_confirmed = check_samples(
        sample_set(coverage=_incomplete_coverage(), cases=_incomplete_cases())
    )
    assert (only_confirmed["coverage_complete"], only_confirmed["confirmed"]) == (
        False,
        True,
    )
    assert only_confirmed["ok_for_verify"] is False

    neither = check_samples(
        sample_set(
            coverage=_incomplete_coverage(),
            cases=_incomplete_cases(),
            confirmed=False,
        )
    )
    assert (neither["coverage_complete"], neither["confirmed"]) == (False, False)
    assert neither["ok_for_verify"] is False


# ---------------------------------------------------------------------------
# Gap emission order (§11.1 "Gap order", OQ-013) — many gaps at once
# ---------------------------------------------------------------------------


def test_fr_027_exact_gap_emission_order():
    ss = sample_set(
        coverage=[
            obligation("obA", "happy_path"),
            obligation("obA", "happy_path"),  # duplicate coverage id
            obligation("obP", "custom", acceptance="proposed"),
            obligation("obT", "list_empty"),  # missing target
            obligation("obI", "list_many", target="no-slash"),  # invalid target
            obligation("obU", "optional_present", target="/x"),  # unmet
        ],
        cases=[
            sample_case("c1", input={}, satisfies=["obA", "ghost"]),
            sample_case("c1", input={}, satisfies=[]),  # duplicate case id
        ],
        waivers=[
            waiver("w1", ["nope"]),  # dangling ref
            waiver("w1", []),  # duplicate waiver id
        ],
        confirmed=False,
        fingerprint="stale",
    )
    check = check_samples(ss)
    assert gap_codes(check) == [
        "duplicate_id",  # coverage obA
        "duplicate_id",  # cases c1
        "duplicate_id",  # waivers w1
        "obligation_not_accepted",  # obP
        "target_required",  # obT
        "list_empty_unmet",  # obT
        "target_invalid",  # obI
        "list_many_unmet",  # obI
        "optional_present_unmet",  # obU
        "waiver_invalid",  # w1 -> nope
        "case_satisfies_unknown",  # c1 -> ghost
        "unconfirmed",
        "fingerprint_mismatch",
    ]
    assert [g.get("obligation_id") for g in check["gaps"][3:9]] == [
        "obP",
        "obT",
        "obT",
        "obI",
        "obI",
        "obU",
    ]
    assert check["coverage_complete"] is False
    assert check["confirmed"] is False
    assert check["ok_for_verify"] is False


# ---------------------------------------------------------------------------
# Determinism (NFR-002 / AC-018)
# ---------------------------------------------------------------------------


def test_ac_018_deterministic_samplecheck():
    ss = sample_set(
        coverage=[
            obligation("obA", "happy_path"),
            obligation("obP", "custom", acceptance="proposed"),
            obligation("obU", "optional_present", target="/x"),
        ],
        cases=[sample_case("c1", input={}, satisfies=["obA", "ghost"])],
        waivers=[waiver("w1", ["nope"])],
        confirmed=False,
        fingerprint="stale",
    )
    first = check_samples(copy.deepcopy(ss))
    second = check_samples(copy.deepcopy(ss))
    assert first == second
    # check_samples does not mutate its input.
    pristine = copy.deepcopy(ss)
    check_samples(ss)
    assert ss == pristine


# ---------------------------------------------------------------------------
# content_fingerprint (§11.1 Confirmation; provisional OQ-015 canonicalization)
# ---------------------------------------------------------------------------


def test_fr_027_fingerprint_is_sha256_hex():
    fp = content_fingerprint(sample_set())
    assert len(fp) == 64
    assert set(fp) <= set("0123456789abcdef")


def test_ac_011_fingerprint_excludes_intent_nl_and_confirmation():
    # §11.1 Confirmation: intent_nl is deliberately excluded — editing prose
    # or the confirmation itself must not invalidate the fingerprint.
    base = sample_set()
    with_nl = sample_set(intent_nl="flatten the line items")
    unconfirmed = sample_set(confirmed=False, fingerprint="whatever")
    assert content_fingerprint(base) == content_fingerprint(with_nl)
    assert content_fingerprint(base) == content_fingerprint(unconfirmed)


def test_fr_027_fingerprint_covers_content_subset():
    base = sample_set()
    different_cases = sample_set(
        cases=[sample_case("c2", input={"n": 2}, satisfies=["happy"])]
    )
    different_coverage = sample_set(coverage=[obligation("other", "custom")])
    different_waivers = sample_set(waivers=[waiver("w1", [])])
    with_includes = sample_set(includes={"inc": {"$": "this"}})
    fps = {
        content_fingerprint(s)
        for s in (
            base,
            different_cases,
            different_coverage,
            different_waivers,
            with_includes,
        )
    }
    assert len(fps) == 5


def test_fr_027_fingerprint_absent_includes_differs_from_empty_includes():
    # Provisional OQ-015 rule: absent `includes` is omitted from the hashed
    # subset, not hashed as {}.
    assert content_fingerprint(sample_set()) != content_fingerprint(
        sample_set(includes={})
    )


def test_fr_027_fingerprint_matches_samplecheck_field():
    ss = sample_set()
    assert check_samples(ss)["content_fingerprint"] == content_fingerprint(ss)
