"""FR-008 — §11.5 status completion: the failure-envelope test surface.

SPEC FR-008: on exhaustion / defer / abort / reject the skill returns an
``AuthoringResult`` **failure** (§11.5) and never returns unverified JSON as
success. §11.5's producer is the A3 skill (no module subcommand emits
AuthoringResult), so conformance is fixture-based by prescription: "unit tests
that validate fixtures against the schema".

This module is the per-status golden sweep for that prescription — one
engine-grounded golden envelope per §11.5 status (builders shared with
``test_envelopes.py``; embedded Verdict / SampleCheck documents come from the
pinned engine, AD-018), asserting the envelope invariants the SPEC states:

- FR-008 / NFR-005 — every §11.5 status has a schema-valid golden; the golden
  set is exhaustive against both the SPEC's status list and the bundled
  schema enum.
- AC-004 — no-``ok_for_verify`` stops carry no ``template``; §11.5 marks
  ``template`` "only when ok" and the bundled schema REJECTS a failure
  envelope with a template attached.
- AC-012 (FR-023 exits) — defer → ``deferred``, abort → ``aborted``, both
  ``ok: false`` with no template.
- AC-026 — every failure envelope is ``ok: false`` plus a §11.5 ``status``;
  success is ``ok: true`` with ``status: "matched"`` only (AD-004: the
  embedded verdict is a real ``assurance: "matched"`` verdict).
"""

import pytest

from transon_authoring._ingress import load_schema, schema_violations

from test_envelopes import (  # noqa: F401  (real_documents: module-scoped fixture)
    AUTHORING_STATUSES,
    authoring_result_fixtures,
    real_documents,
)

#: Every §11.5 status except the single success row.
FAILURE_STATUSES = tuple(s for s in AUTHORING_STATUSES if s != "matched")

#: AC-004 — the closed status subset for a stop without an ``ok_for_verify``
#: SampleSet: `need-samples` | `deferred` | `aborted` | `samples-rejected`.
AC_004_STATUSES = ("need-samples", "deferred", "aborted", "samples-rejected")


@pytest.fixture(scope="module")
def goldens(real_documents):  # noqa: F811 — pytest fixture, not a redefinition
    """One golden AuthoringResult per §11.5 status (engine-grounded)."""
    return authoring_result_fixtures(real_documents)


# ---------------------------------------------------------------------------
# FR-008 — one schema-valid golden per §11.5 status, exhaustively
# ---------------------------------------------------------------------------


def test_fr_008_golden_set_is_exhaustive_against_spec_and_schema(goldens):
    schema_enum = load_schema("authoring_result.json")["properties"]["status"]["enum"]
    assert set(goldens) == set(AUTHORING_STATUSES)
    assert set(schema_enum) == set(AUTHORING_STATUSES)
    assert len(AUTHORING_STATUSES) == 9  # §11.5 taxonomy is closed at nine


@pytest.mark.parametrize("status", AUTHORING_STATUSES)
def test_fr_008_every_status_has_schema_valid_golden(goldens, status):
    golden = goldens[status]
    assert schema_violations(golden, "authoring_result.json") == []
    assert golden["status"] == status
    assert golden["explanation"].strip()  # NFR-005: actionable, not bare


@pytest.mark.parametrize("status", FAILURE_STATUSES)
def test_fr_008_failure_status_never_claims_success(goldens, status):
    # FR-008: "Never return unverified JSON as success." Structurally: the
    # schema rejects ok: true on every non-"matched" status.
    assert schema_violations(
        dict(goldens[status], ok=True), "authoring_result.json"
    ), f"{status} with ok: true must be schema-invalid"


# ---------------------------------------------------------------------------
# AC-004 — failure envelopes carry no template (§11.5: template "only when ok")
# ---------------------------------------------------------------------------


def test_ac_004_no_ok_for_verify_statuses_are_failure_subset(goldens):
    # AC-004's status set is exactly these four; each golden is a template-free
    # failure envelope.
    assert set(AC_004_STATUSES) < set(FAILURE_STATUSES)
    for status in AC_004_STATUSES:
        assert goldens[status]["ok"] is False
        assert "template" not in goldens[status]


@pytest.mark.parametrize("status", FAILURE_STATUSES)
def test_ac_004_failure_statuses_never_carry_template(goldens, status):
    golden = goldens[status]
    assert "template" not in golden  # golden-set invariant (§11.5 "only when ok")
    # The bundled schema itself encodes the constraint: attaching a template
    # to any failure envelope must be REJECTED.
    assert schema_violations(
        dict(golden, template={"$": "this"}), "authoring_result.json"
    ), f"{status} with a template attached must be schema-invalid"


# ---------------------------------------------------------------------------
# AC-012 — defer → "deferred", abort → "aborted" (FR-023 exits), no template
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["deferred", "aborted"])
def test_ac_012_deferred_and_aborted_envelopes(goldens, status):
    golden = goldens[status]
    assert schema_violations(golden, "authoring_result.json") == []
    assert golden["ok"] is False
    assert golden["status"] == status
    assert "template" not in golden
    # Negatives: neither exit may claim success or carry a template.
    assert schema_violations(dict(golden, ok=True), "authoring_result.json")
    assert schema_violations(
        dict(golden, template={"$": "this"}), "authoring_result.json"
    )


# ---------------------------------------------------------------------------
# AC-026 — failure envelopes: ok false + §11.5 status; success: matched only
# ---------------------------------------------------------------------------


def test_ac_026_failure_envelopes_ok_false_with_status(goldens):
    for status in FAILURE_STATUSES:
        golden = goldens[status]
        assert golden["ok"] is False
        assert golden["status"] in AUTHORING_STATUSES
    # Success is the "matched" row alone: ok true, embedding a REAL
    # pinned-engine verdict at assurance "matched" (AD-004 / AC-013).
    matched = goldens["matched"]
    assert matched["ok"] is True
    assert matched["status"] == "matched"
    assert matched["verdict"]["ok"] is True
    assert matched["verdict"]["assurance"] == "matched"


def test_ac_026_status_is_required_on_failure(goldens):
    # An envelope with ok: false but no status is not a §11.5 failure envelope.
    stripped = {k: v for k, v in goldens["aborted"].items() if k != "status"}
    assert schema_violations(stripped, "authoring_result.json")
