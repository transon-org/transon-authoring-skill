# Traceability — requirement → tests / gates

Working coverage tracker for the matrix in [SPEC §17](SPEC.md). One row per **active** FR/NFR
(FR-013 is deprecated and excluded). Update the row **in the same change** that implements the
requirement: flip Status to `[x]` and list the test files/functions citing the ID.
`harness/scripts/check_traceability.py` enforces that every `[x]` row has at least one test citing
its ID, and that no dead or deprecated IDs are cited anywhere.

Status: `[ ]` not started / partial · `[x]` done (tests green and cited).

| ID | AC(s) | Milestone | Gate / test category | Status | Tests |
|---|---|---|---|---|---|
| FR-001 | AC-001, AC-002 | A3 | authoring evals | [ ] | |
| FR-002 | AC-001, AC-014, AC-017 | A2–A3 | sample-loop + unit | [ ] | |
| FR-003 | AC-021 | A1 | CLI unit | [ ] | |
| FR-004 | AC-001, AC-018 | A1 | verify unit | [ ] | |
| FR-005 | AC-015, AC-023, AC-024 | A1 | sandbox + match unit | [ ] | |
| FR-006 | AC-013, AC-016 | A1 | verify unit | [ ] | |
| FR-007 | AC-019 | A3 | repair unit + evals | [ ] | |
| FR-008 | AC-004, AC-012, AC-026 | A3 | failure envelope unit | [ ] | |
| FR-009 | AC-006, AC-022 | A0 | snapshot gate | [x] | tests/test_metadata.py (test_fr_009_bundled_snapshot_is_grounding_catalog, test_fr_009_get_metadata_is_cached, test_fr_009_resource_bytes_match_repo_file, test_fr_009_missing_resource_raises_with_sync_hint) |
| FR-010 | AC-022 | A0 | examples unit | [ ] | |
| FR-011 | AC-006 | A0 | sync + drift | [x] | tests/test_sync_metadata.py (test_fr_011_sync_is_canonical_and_records_provenance, test_fr_011_sidecar_skeleton_created_when_absent, test_fr_011_existing_sidecar_never_overwritten, test_fr_011_pin_mismatch_exits_2) |
| FR-012 | AC-005 | A4 | parity | [ ] | |
| FR-014 | AC-021 | A1 | CLI unit | [ ] | |
| FR-015 | AC-007, AC-009 | A4 | check_install | [ ] | |
| FR-016 | AC-007 | A4 | check_install | [ ] | |
| FR-017 | AC-008 | A2 | check_evals | [ ] | |
| FR-018 | AC-008, AC-025 | A2–A3 | evals + privacy review | [ ] | |
| FR-019 | AC-009 | A4 | check_install | [ ] | |
| FR-020 | AC-010, AC-017, AC-018 | A2 | check_samples unit | [ ] | |
| FR-021 | AC-011, AC-017 | A2 | schema unit | [ ] | |
| FR-022 | AC-014 | A2 | config unit | [ ] | |
| FR-023 | AC-012 | A3 | sample-loop evals | [ ] | |
| FR-024 | AC-010, AC-011 | A3 | sample-loop evals | [ ] | |
| FR-025 | AC-010, AC-017 | A3 | sample-loop evals | [ ] | |
| FR-026 | AC-021, AC-026 | A1 | schema unit + CLI exit 2 | [ ] | |
| FR-027 | AC-016 | A1 | verify preflight | [ ] | |
| FR-028 | AC-027, AC-028 | A1 | profile-knob reject + timeout worker unit | [ ] | |
| NFR-001 | AC-003, AC-022 | A0+ | authority tests / evals | [ ] | |
| NFR-002 | AC-018 | A1 | determinism unit | [ ] | |
| NFR-003 | AC-020 | A1 | offline CI job | [ ] | |
| NFR-004 | AC-006 | A0 | check_snapshot | [x] | tests/test_check_snapshot.py (test_nfr_004_ac_006_fresh_sync_is_green, test_nfr_004_ac_006_drift_gate, test_nfr_004_stale_provenance_snapshot_hash_is_red, test_nfr_004_oq_021_dangling_sidecar_key_is_red, test_nfr_004_oq_021_uncovered_examples_stay_green_with_count, test_nfr_004_off_pin_root_is_red, test_nfr_004_repo_root_is_green) |
| NFR-005 | AC-026 | A1 | envelope unit | [ ] | |
| NFR-006 | AC-019 | A3 | repair unit | [ ] | |
| NFR-007 | AC-005 | A4 | check_parity | [ ] | |
| NFR-008 | AC-006, AC-007 | A4–A5 | release checklist | [ ] | |
| NFR-009 | AC-007, AC-009 | A4 | check_install | [ ] | |
| NFR-010 | AC-008 | A2 | check_evals | [ ] | |
| NFR-011 | AC-025 | A2 | fixture lint | [ ] | |
