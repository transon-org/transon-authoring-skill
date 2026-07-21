"""FR-017 / NFR-010 / AD-020 — committed eval artifacts (SPEC §11.8).

The A2 slice of the eval spine: the committed eval-policy files
(`evals/runner.json` pinned to the OQ-017f values, `evals/targets.json` per
OQ-016e, `evals/baseline.json` per OQ-016f) and the seed fixture corpus under
`evals/cases/` (§11.8 EvalFixture; §14 A2 DoD: ">=3 matched + >=2 refusal
seeds", plus one `matched_correction` seed per the OQ-016c reporting bucket).

Every supplied SampleSet in the seed fixtures is complete and CI-confirmed:
`check_samples` (engine-free, FR-027) must report `ok_for_verify: true`, since
the eval harness hands the SampleSet straight to the skill under test
(OQ-017a). Fixture sample content is grounded in the committed AC-001 fixture
set and the pinned snapshot `docs.examples` payloads — engine-verified at
authoring time, never invented from memory (AD-018 / NFR-001).
"""

import json
from pathlib import Path

import pytest

from transon_authoring import check_samples
from transon_authoring._ingress import load_document, schema_violations

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALS = REPO_ROOT / "evals"
CASES_DIR = EVALS / "cases"
SEEDS_DIR = EVALS / "seeds"

FIXTURE_PATHS = sorted(CASES_DIR.glob("*.json"))


def load_fixtures() -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8")) for path in FIXTURE_PATHS
    ]


# --- committed eval-policy files (AD-020) ------------------------------------


@pytest.mark.parametrize(
    ("file_name", "schema_name"),
    [
        ("runner.json", "eval_runner.json"),
        ("targets.json", "eval_targets.json"),
        ("baseline.json", "eval_baseline.json"),
    ],
)
def test_fr_017_runner_targets_baseline_validate(file_name, schema_name):
    # Full §11.0 ingress: strict parse, schema_version "1.0", bundled-schema
    # validation (raises IngressError on any violation).
    document = load_document(EVALS / file_name, schema_name)
    assert schema_violations(document, schema_name) == []


def test_fr_017_runner_values_are_oq_017f_pin():
    # OQ-017f: the committed runner.json values are gate identity (AD-020);
    # changing any is an explicit eval-policy commit. Current pin: the
    # AD-021/OQ-024a small-model gate (superseding the initial sonnet pin
    # via the 2026-07-12 eval-policy commit) plus the AD-024/OQ-027 real-host
    # `harness` block (2026-07-14 eval-policy commit) pinning the Claude Agent
    # SDK reference host beside the model.
    document = load_document(EVALS / "runner.json", "eval_runner.json")
    assert document == {
        "schema_version": "1.0",
        "provider": "anthropic",
        "model_id": "claude-haiku-4-5-20251001",
        "max_output_tokens": 8192,
        "tool_budget": 32,
        "runs_per_fixture": 3,
        "pass_rule": "majority",
        "seed": None,
        "harness": {"kind": "agent-sdk", "version": "0.2.116"},
    }


def test_oq_024_targets_never_reset():
    # OQ-024g: on a gate-model / harness swap the baseline resets to empty in
    # the same eval-policy commit, but the TARGETS are NEVER reset — the 0.80
    # authoring floor and 1.0 adversarial target stay put, ratchet untouched.
    # (The durable invariant here is the targets; the committed baseline is now
    # populated by the first accepted green gate, see the baseline test below.)
    targets = load_document(EVALS / "targets.json", "eval_targets.json")
    assert targets["authoring_target"] == 0.80
    assert targets["adversarial_target"] == 1.0


def test_fr_017_targets_start_at_the_initial_authoring_target():
    # §11.8 ratchet: T starts at 0.80; adversarial_target is constant 1.0.
    document = load_document(EVALS / "targets.json", "eval_targets.json")
    assert document["authoring_target"] == 0.80
    assert document["adversarial_target"] == 1.0


def test_fr_001_ac_002_corpus_exercises_mode_variant_authoring():
    """FR-001 / AC-002 — a mode/variant intent must drive the skill to the
    CORRECT engine mode and still verify `matched`. The pinned engine's clearest
    mode/variant is the `map` operator's FORM: dict-reconstruction (`key`/`value`)
    vs list (`item`/`items`). The corpus witnesses AC-002 with two matched
    fixtures whose intents force DIFFERENT map forms, both accepted green by the
    §11.8 gate (run 29381271246):

      - syn-map-dict-to-dict-items: "swap keys and values" → dict→dict, requiring
        the `map` key/value mode (seed template `{$:map, key:{$:value},
        value:{$:key}}`) — NOT the list `item` mode;
      - syn-map-dict-to-list: dict→list, a different map form.

    Choosing the wrong mode fails `verify` (the output shape would differ), so a
    `matched` verdict IS proof the skill picked the right engine mode from the
    NL intent. This pins the corpus coverage; the green gate is the behavioral
    proof the skill authors it correctly."""
    dict_mode = load_document(CASES_DIR / "syn-map-dict-to-dict-items.json", "eval_fixture.json")
    list_mode = load_document(CASES_DIR / "syn-map-dict-to-list.json", "eval_fixture.json")
    assert dict_mode["expect"] == "matched" and list_mode["expect"] == "matched"

    # The dict→dict fixture's reference template uses the map dict key/value mode,
    # distinct from the list `item` mode — an unambiguous mode/variant choice.
    seed = json.loads(
        (SEEDS_DIR / "syn-map-dict-to-dict-items.json").read_text(encoding="utf-8")
    )
    tmpl = seed["template"]
    assert tmpl["$"] == "map"
    assert "key" in tmpl and "value" in tmpl, "not the dict key/value map mode"
    assert "item" not in tmpl and "items" not in tmpl, "must NOT be the list map mode"

    # The two fixtures demand different map forms from their (dict) inputs: one
    # reconstructs a dict, the other emits a list — so the corpus genuinely
    # discriminates the mode/variant, not just one shape.
    def first_output(fixture):
        return fixture["samples"]["cases"][0]["output"]
    assert isinstance(first_output(dict_mode), dict)
    assert isinstance(first_output(list_mode), list)


def test_fr_017_baseline_reflects_the_accepted_green_gate():
    # FR-017 / OQ-016f / §11.8: ids enter baseline.json only via an accepted
    # green gate (the --update-baseline rule: majority-passing fixtures), so a
    # populated baseline lists only ids that resolve to committed fixtures.
    document = load_document(EVALS / "baseline.json", "eval_baseline.json")
    ids = document["passing"]
    assert ids, "baseline should be populated by the accepted green gate"
    assert ids == sorted(set(ids)), "passing ids must be sorted + unique"
    stems = {p.stem for p in FIXTURE_PATHS}
    assert set(ids) <= stems, "every baseline id must resolve to a committed fixture"


# --- seed fixtures (§11.8 EvalFixture) ---------------------------------------


def test_fr_017_seed_fixtures_validate():
    assert FIXTURE_PATHS, "evals/cases/ must contain the seed fixtures"
    for path in FIXTURE_PATHS:
        fixture = load_document(path, "eval_fixture.json")
        # Filename = fixture id + ".json" (§11.8 population is the committed
        # evals/cases/ files; ids must be unambiguous on disk).
        assert path.name == fixture["id"] + ".json"
        # All seed fixtures are synthetic: redaction never applied, no
        # real-use consent record needed (NFR-011).
        assert fixture["redacted"] is False
        assert "consent" not in fixture


def test_fr_017_seed_sample_sets_ok_for_verify():
    # Engine-free library check (FR-027): every supplied SampleSet is
    # coverage-complete and CI-confirmed with a current fingerprint, so the
    # harness can hand it straight to the skill under test (OQ-017a).
    fixtures = load_fixtures()
    with_samples = [f for f in fixtures if "samples" in f]
    assert with_samples, "matched seeds must supply SampleSets"
    for fixture in with_samples:
        check = check_samples(fixture["samples"])
        assert check["ok_for_verify"] is True, (fixture["id"], check["gaps"])
        assert check["gaps"] == [], fixture["id"]
        # The library never sets confirmed (§11.1): the committed artifact
        # itself carries the CI attestation.
        assert fixture["samples"]["confirmation"]["confirmed_by"] == "ci"


def test_fr_017_seed_buckets_present():
    # §14 A2 DoD: ">=3 matched + >=2 refusal seeds"; one correction seed for
    # the OQ-016c reporting-only bucket. §11.8: samples required for
    # matched / matched_correction, omitted for refuse seeds.
    fixtures = load_fixtures()
    by_expect: dict[str, list[dict]] = {}
    for fixture in fixtures:
        by_expect.setdefault(fixture["expect"], []).append(fixture)
    assert len(by_expect.get("matched", [])) >= 3
    assert len(by_expect.get("refuse", [])) >= 2
    assert len(by_expect.get("matched_correction", [])) >= 1
    for fixture in by_expect["matched"] + by_expect["matched_correction"]:
        assert "samples" in fixture, fixture["id"]
    for fixture in by_expect["refuse"]:
        assert "samples" not in fixture, fixture["id"]
