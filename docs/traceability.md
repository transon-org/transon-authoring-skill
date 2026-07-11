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
| FR-003 | AC-021 | A1 | CLI unit | [x] | tests/test_cli_a1.py (test_fr_003_no_repair_flag, test_ac_021_examples_search_envelope_exit_0, test_ac_021_metadata_still_verbatim_snapshot, test_ac_021_init_config_still_unknown_command) |
| FR-004 | AC-001, AC-018 | A1 | verify unit | [x] | tests/test_verify.py (test_fr_004_validate_failure_verbatim_engine_error_no_case_id, test_fr_004_validate_debug_api_shape, test_fr_004_verdict_never_has_root_writes), tests/test_ac001_path.py (test_ac_001_fr_004_library_verify_matched, test_ac_001_fr_004_cli_verify_exit_0_matched_envelope, test_ac_001_wrong_template_fails_at_match_with_case_ids), tests/test_determinism.py (test_ac_018_deterministic_verdict_matched) |
| FR-005 | AC-015, AC-023, AC-024 | A1 | sandbox + match unit | [x] | tests/test_tags.py (test_fr_005_oq_012_enc_sentinel_is_no_content_ref, test_fr_005_oq_012_enc_injective_sentinel_vs_lookalike_dict, test_fr_005_oq_012_dec_recurses_at_every_nesting_level), tests/test_match.py (test_ac_023_no_content_not_null, test_ac_024_declared_writes_matched, test_fr_005_oq_013_object_key_visit_order_is_code_point_ascending, test_fr_005_oq_011_case_id_on_every_entry), tests/test_sandbox.py (test_ac_015_file_writes_captured_no_fs) |
| FR-006 | AC-013, AC-016 | A1 | verify unit | [x] | tests/test_verify.py (test_fr_006_stage_order_samples_validate_dry_run_match, test_fr_006_dry_run_failures_reported_per_case_in_cases_order, test_fr_006_match_failure_diff_in_normative_order_errors_empty, test_ac_013_success_requires_matched, test_ac_016_zero_cases_fails_samples_stage) |
| FR-007 | AC-019 | A3 | repair unit + evals | [ ] | |
| FR-008 | AC-004, AC-012, AC-026 | A3 | failure envelope unit | [ ] | |
| FR-009 | AC-006, AC-022 | A0 | snapshot gate | [x] | tests/test_metadata.py (test_fr_009_bundled_snapshot_is_grounding_catalog, test_fr_009_get_metadata_is_cached, test_fr_009_resource_bytes_match_repo_file, test_fr_009_missing_resource_raises_with_sync_hint), tests/test_cli_metadata.py (test_a0_dod_metadata_subcommand, test_a0_dod_metadata_path_never_imports_engine) |
| FR-010 | AC-022 | A0 | examples unit | [x] | tests/test_examples.py (test_fr_010_ac_022_exact_name_match_first_and_verbatim, test_fr_010_ac_022_limit_bound_and_validation, test_fr_010_ac_022_deterministic_and_deep_copied, test_fr_010_ac_022_multi_hit_truncated_in_corpus_order, test_fr_010_ac_022_sidecar_enriches_nl_and_is_searchable, test_fr_010_ac_022_score_zero_query_returns_empty_list, test_fr_010_sidecar_loads_committed_file) |
| FR-011 | AC-006 | A0 | sync + drift | [x] | tests/test_sync_metadata.py (test_fr_011_sync_is_canonical_and_records_provenance, test_fr_011_sidecar_skeleton_created_when_absent, test_fr_011_existing_sidecar_never_overwritten, test_fr_011_pin_mismatch_exits_2, test_fr_011_missing_engine_exits_2) |
| FR-012 | AC-005 | A4 | parity | [ ] | |
| FR-014 | AC-021 | A1 | CLI unit | [x] | tests/test_cli_a1.py (test_fr_014_check_samples_ok_exit_0, test_fr_014_check_samples_unconfirmed_exit_1, test_fr_014_verify_matched_exit_0, test_fr_014_verify_failed_stage_exit_1, test_fr_014_validate_ok_exit_0, test_fr_014_dry_run_success_has_result_and_writes) |
| FR-015 | AC-007, AC-009 | A4 | check_install | [ ] | |
| FR-016 | AC-007 | A4 | check_install | [ ] | |
| FR-017 | AC-008 | A2 | check_evals | [ ] | |
| FR-018 | AC-008, AC-025 | A2–A3 | evals + privacy review | [ ] | |
| FR-019 | AC-009 | A4 | check_install | [ ] | |
| FR-020 | AC-010, AC-017, AC-018 | A2 | check_samples unit | [ ] | |
| FR-021 | AC-029, AC-017 | A2 | schema unit | [ ] | |
| FR-022 | AC-014 | A2 | config unit | [ ] | |
| FR-023 | AC-012 | A3 | sample-loop evals | [ ] | |
| FR-024 | AC-010, AC-011 | A3 | sample-loop evals | [ ] | |
| FR-025 | AC-010, AC-017 | A3 | sample-loop evals | [ ] | |
| FR-026 | AC-021, AC-026 | A1 | schema unit + CLI exit 2 | [x] | tests/test_ingress.py (test_fr_026_duplicate_object_keys_rejected, test_fr_026_non_finite_numbers_rejected, test_fr_026_unsupported_schema_version_rejected, test_fr_026_validator_errors_sorted_by_path_then_message), tests/test_schemas.py (test_fr_026_schema_declares_draft_2020_12_and_is_well_formed, test_fr_026_golden_fixture_validates), tests/test_cli_a1.py (test_ac_026_ingress_failures_exit_2_cli_error, test_ac_026_sample_set_schema_invalid_is_cli_error_not_body) |
| FR-027 | AC-016 | A1 | verify preflight | [x] | tests/test_check_samples.py (test_ac_016_schema_invalid_all_flags_false, test_fr_027_exact_gap_emission_order, test_ac_017_flags_independent, test_fr_027_fingerprint_mismatch_gap), tests/test_verify.py (test_fr_027_schema_invalid_sample_set_fails_samples_stage, test_ac_016_unconfirmed_fails_samples_stage) |
| FR-028 | AC-027, AC-028 | A1 | profile-knob reject + timeout worker unit | [x] | tests/test_worker.py (test_fr_028_echo_template_round_trip, test_fr_028_leaked_value_error_maps_to_transformation_error, test_ac_028_timeout_kills_worker, test_ac_028_production_timeout_is_5s), tests/test_sandbox.py (test_ac_015_include_resolved_from_map_only, test_ac_015_no_network_host_socket_blocked), tests/test_cli_a1.py (test_ac_027_reserved_knobs_rejected, test_ac_027_rejection_is_deterministic_stable_text) |
| NFR-001 | AC-003, AC-022 | A0+ | authority tests / evals | [ ] | tests/test_authority.py (test_nfr_001_snapshot_is_sole_source, test_nfr_001_hits_are_snapshot_verbatim, test_nfr_001_no_network_imports_in_product_code) (A0 slice; AC-003 at A3) |
| NFR-002 | AC-018 | A1 | determinism unit | [x] | tests/test_determinism.py (test_ac_018_deterministic_verdict_matched, test_ac_018_deterministic_verdict_dry_run_errors, test_ac_018_deterministic_verdict_match_diff, test_ac_018_deterministic_sample_check_rich_gaps, test_ac_018_cli_verify_deterministic_across_hash_seeds) |
| NFR-003 | AC-020 | A1 | offline CI job | [x] | tests/test_offline.py (test_nfr_003_get_metadata_offline, test_nfr_003_check_samples_offline, test_ac_020_verify_matched_offline, test_ac_020_cli_verbs_offline_with_unroutable_proxies), .github/workflows/ci.yml `offline` job (unshare -rn), tests/test_cli_metadata.py (test_a0_dod_metadata_path_never_imports_engine) |
| NFR-004 | AC-006 | A0 | check_snapshot | [x] | tests/test_check_snapshot.py (test_nfr_004_ac_006_fresh_sync_is_green, test_nfr_004_ac_006_drift_gate, test_nfr_004_stale_provenance_snapshot_hash_is_red, test_nfr_004_oq_021_dangling_sidecar_key_is_red, test_nfr_004_oq_021_uncovered_examples_stay_green_with_count, test_nfr_004_off_pin_root_is_red, test_nfr_004_repo_root_is_green) |
| NFR-005 | AC-026 | A1 | envelope unit | [x] | tests/test_envelopes.py (test_nfr_005_ac_026_schema_error_cli_error_conforms, test_nfr_005_ac_026_profile_rejected_cli_error_conforms, test_nfr_005_ac_026_internal_error_cli_error_conforms, test_nfr_005_ac_026_failing_verdict_envelope_conforms, test_nfr_005_ac_026_authoring_result_fixture_conforms, test_nfr_005_oq_014a_internal_error_status_rejected) |
| NFR-006 | AC-019 | A3 | repair unit | [ ] | |
| NFR-007 | AC-005 | A4 | check_parity | [ ] | |
| NFR-008 | AC-006, AC-007 | A4–A5 | release checklist | [ ] | |
| NFR-009 | AC-007, AC-009 | A4 | check_install | [ ] | |
| NFR-010 | AC-008 | A2 | check_evals | [ ] | |
| NFR-011 | AC-025 | A2 | fixture lint | [ ] | |
