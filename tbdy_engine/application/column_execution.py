{
  "schema_version": "product_spine_col_1.handoff.v2",
  "repository": "feridunfc/TBDY",
  "frozen_base": "74d5b6083afed75e44b832336c31755aee482daa",
  "branch": "sprint/col-runtime-1-production-runtime",
  "sprint": "PRODUCT-SPINE-COL-1",
  "supervisor_patch": "A1-P1",
  "status": "CANDIDATE_COMMIT_PENDING_GITHUB_CI",
  "production_code_modified": true,
  "engineering_authority_modified": false,
  "etabs_run": false,
  "etabs_mutated": false,
  "new_engineering_authority": false,
  "write_set": [
    ".github/workflows/product_spine_col_1_validation.yml",
    "tbdy_engine/application/__init__.py",
    "tbdy_engine/application/contracts.py",
    "tbdy_engine/application/project_execution.py",
    "tbdy_engine/application/column_execution.py",
    "tests/application/test_product_spine_col_1.py",
    "docs/audit/product_spine_col_1/report.md",
    "docs/audit/product_spine_col_1/handoff.json"
  ],
  "production_request_contract": {
    "ProjectExecutionRequest": ["project_id", "report_id", "title", "column"],
    "ColumnExecutionRequest": ["component_id"],
    "contains_fixture_truth": false,
    "contains_RegulatoryCompileInputs": false,
    "contains_EtabsVerifiedSession": false
  },
  "runtime_dependency": "execute_project(request, *, verified_session=EtabsVerifiedSession)",
  "live_fnd2_lineage": {
    "existing_qualified_builder_found": false,
    "public_status": "FACTUAL_ACQUISITION_BLOCKED",
    "blocker": "LIVE_FND2_INPUT_LINEAGE_NOT_QUALIFIED",
    "fnd_col_2x_executed": false,
    "engineering_readiness_claimed": false,
    "fcr_or_report_claimed": false
  },
  "qualified_live_ready_guard": {
    "tested_non_public_seam": true,
    "readiness": "READY",
    "application_status": "APPLICATION_BLOCKED",
    "blocker": "LIVE_DESIGN_RESULT_LINEAGE_NOT_QUALIFIED",
    "p8a_promotion_reached": false,
    "engine_selected_rebar_emitted": false
  },
  "ready_fixture_proof": {
    "production_request_exposed": false,
    "non_public_test_seam_only": true,
    "same_readiness_object_preserved": true,
    "fnd_col_1_executed": true,
    "reviewed_selection_policy_used": true,
    "pmm_policy_authorized_by_existing_owner": true,
    "candidate_adequacy_authorized_by_existing_owner": true,
    "p8a_b_fnd_col_4_executed": true,
    "engine_selected_rebar_emitted_by_existing_owner": true,
    "fcr_building_report_reuse_proven": true
  },
  "required_existing_seams_absent": [
    "TrustedLiveAcquisitionContext -> complete FND-COL-2 RegulatoryCompileInputs builder",
    "accepted project-wide live DesignResultIdentity/design-state lineage",
    "production ColumnPmmMaterialContextBinding constructor/builder",
    "pre-A1 production caller for reconcile_concrete_design_combos"
  ],
  "application_forbidden_edges": [
    "SapModel",
    "DatabaseTables",
    "DesignConcrete",
    "Results.Setup",
    "FrameObj",
    "AreaObj",
    "PropFrame",
    "RunAnalysis",
    "StartDesign",
    "SetPresentUnits",
    "SetModifiers",
    "tools.*"
  ],
  "local_validation": {
    "a1_p1_focused": "11 passed in 2.87s",
    "required_combined_regression": "99 passed in 9.22s",
    "compile_import": "PASS",
    "application_ast_forbidden_edge": "PASS",
    "full_column_suite": "NOT_COMPLETED_LOCAL_TIMEOUT_NO_PASS_CLAIM"
  },
  "candidate_ci_gate": {
    "workflow": "PRODUCT-SPINE-COL-1 Validation",
    "frozen_base_ancestry_required": true,
    "candidate_vs_frozen_base_broad_delta_required": true,
    "final_repository_hygiene_required": true,
    "status": "PENDING_GITHUB_RUN"
  },
  "non_claims": [
    "not full ColumnDomainRuntime closure",
    "not live FND-COL-2 readiness proof",
    "not live design-result qualification",
    "not full project runtime closure",
    "not full TBDY/TS500 compliance",
    "not canonical by self-declaration",
    "not merge-ready by self-declaration"
  ]
}
