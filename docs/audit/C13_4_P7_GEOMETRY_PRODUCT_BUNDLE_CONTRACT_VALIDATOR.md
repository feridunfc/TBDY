# C13.4-P7 Geometry Product Bundle Contract Validator

## 1. Sprint purpose

C13.4-P7 adds an offline validator for the C13.4-P6 geometry product smoke bundle. The validator checks that a generated bundle is complete, internally consistent, scope-safe, deterministic, and reportable.

The validator reads an existing bundle and writes:

```text
geometry_product_bundle_validation.json
```

## 2. Why this sprint is offline

P7 must run on a machine without ETABS. It validates files that already exist on disk. It does not generate artifacts, resolve features, render reports, or execute checks.

The validator does not call:

- ETABS;
- Excel;
- Streamlit;
- live providers;
- FeatureResolver;
- P3 adapter;
- MinimalCheckEngine;
- CheckEngine;
- P4 runner;
- P5 report renderer.

## 3. Input bundle contract

Input is one bundle directory:

```bash
python tools/validate_geometry_product_bundle.py --bundle-dir local_out/c13_4_p6_geometry_product_smoke
```

The bundle must have been produced by the C13.4-P6 product smoke command.

## 4. Required file contract

The validator requires these files:

```text
artifacts/check_results.json
artifacts/adapter_diagnostics.json
artifacts/run_summary.json
artifacts/run_manifest.json
reports/geometry_report.md
product_smoke_summary.json
product_smoke_manifest.json
```

Missing required files are validation errors. JSON files must parse successfully. The Markdown report must be UTF-8 readable.

## 5. Summary JSON validation contract

`product_smoke_summary.json` must contain:

- `status: OK`
- `scope: GEOMETRY_ONLY_PRODUCT_SMOKE`
- `p4.check_result_count` as an integer
- `p4.adapter_diagnostic_count` as an integer
- `p4.check_result_status_counts` as a mapping
- `p5.section_count: 9`
- `p5.table_count: 9`
- `p5.table_names` in exact C13.4-P5 order

The summary status means the product smoke completed. It is not a final building compliance verdict.

## 6. Manifest JSON validation contract

`product_smoke_manifest.json` must contain:

- `runner: C13.4-P6 Geometry Product Smoke`
- `scope: GEOMETRY_ONLY_PRODUCT_SMOKE`
- source steps in this order:
  - `C13.4-P4 Geometry Vertical Slice Runner`
  - `C13.4-P5 Geometry Markdown Report Renderer`
- required guardrails:
  - `geometry_only: true`
  - `orchestration_only: true`
  - `new_engineering_checks_added: false`
  - `etabs_live_fetching_used: false`
  - `excel_production_path_used: false`
  - `streamlit_ui_used: false`
  - `legacy_runtime_used: false`
  - `rebar_flexure_shear_capacity_unlocked: false`
  - `modal_mass_unlocked: false`
  - `final_building_compliance_verdict_emitted: false`

Wrong or missing guardrails are errors.

## 7. P4 artifact consistency rules

The validator checks:

- `check_results.json` is a JSON array;
- `adapter_diagnostics.json` is a JSON array;
- `run_summary.json` is a JSON object;
- `run_manifest.json` is a JSON object;
- `run_summary.check_result_count == len(check_results.json)`;
- `run_summary.adapter_diagnostic_count == len(adapter_diagnostics.json)`;
- product summary P4 counts match run summary counts;
- product summary P4 status counts match run summary status counts;
- CheckResult statuses are canonical:
  - `OK`
  - `FAIL`
  - `NO_DATA`
  - `BLOCKED`
  - `OUT_OF_SCOPE`
  - `WARNING`
- adapter diagnostics do not use `OK` or `FAIL`.

## 8. P5 report validation rules

The report file must start with:

```markdown
# TBDY Geometry Vertical Slice Report — C13.4-P5
```

The report must contain table markers in exact order:

```text
Table name: executive_summary
Table name: geometry_check_summary
Table name: adapter_diagnostics
Table name: beam_geometry_detail
Table name: column_geometry_detail
Table name: evidence_trace_detail
Table name: artifact_manifest
Table name: guardrails
Table name: boundary_notes
```

Missing or out-of-order markers are validation errors.

## 9. Forbidden scope validation

`product_smoke_summary.json` must not contain these forbidden terms:

- `final_building_compliance`
- `beam_flexure`
- `beam_shear`
- `rebar_adequacy`
- `capacity_design`
- `governing_combo_selection`
- `force_envelope_selection`
- `SCWB`
- `PMM`
- `drift`
- `modal_mass`
- `ETABS_live_fetching`
- `Excel_production_path`
- `legacy_runtime_execution`

`product_smoke_manifest.json` is allowed to contain these terms inside `forbidden_scope` because the manifest declares excluded scope.

## 10. Warning policy for extra files

The bundle may contain the validator output file:

```text
geometry_product_bundle_validation.json
```

Any other non-contract extra file produces a warning, not an error. Warnings do not fail the bundle.

## 11. Determinism policy

The validation JSON is deterministic:

- fixed required file order;
- fixed check names;
- stable error and warning ordering;
- `indent=2`;
- `sort_keys=True`;
- `ensure_ascii=False`;
- final newline;
- no timestamps;
- no random IDs;
- no machine-specific metadata except the bundle path.

## 12. Legacy boundary statement

The validator module is:

```text
tbdy_engine/product/bundle_validator.py
```

It must not import:

- `tbdy_engine.design`
- `tbdy_engine.adapters.check_adapter`
- `tbdy_engine.engine.topology`
- `tbdy_engine.runtime`
- `tbdy_engine.runner_v2`
- `tbdy_engine.archx`

It must also not import or call:

- `MinimalCheckEngine`
- `build_geometry_check_inputs_from_feature_snapshot`
- P4 product runner APIs
- P5 report renderer APIs

The existing boundary audit already scans:

```text
tbdy_engine/product/*.py
```

P7 tests additionally check the validator and CLI source text for forbidden imports and lower-pipeline calls.

## 13. Explicitly excluded engineering scope

P7 excludes:

- ETABS live fetching;
- Excel production input;
- Streamlit UI;
- feature resolving;
- P3 adapter execution;
- MinimalCheckEngine execution;
- CheckEngine execution;
- P4 runner execution;
- P5 report rendering;
- beam flexure;
- beam shear;
- rebar adequacy;
- capacity design;
- governing combo selection;
- force envelope selection;
- SCWB;
- column PMM;
- drift compliance;
- modal mass checks;
- column area checks;
- column aspect ratio checks;
- final building compliance verdict.

## 14. Acceptance outputs

Required commands:

```bash
python -m compileall -q tbdy_engine tools tests
python tbdy_engine/tools/validate_contract_constitution.py
python tools/audit_legacy_boundary.py
pytest -q tests/c13_4_p1
pytest -q tests/c13_4_p2
pytest -q tests/c13_4_p3
pytest -q tests/c13_4_p4
pytest -q tests/c13_4_p5
pytest -q tests/c13_4_p6
pytest -q tests/c13_4_p7
python tools/run_geometry_product_smoke.py --feature-snapshot tests/fixtures/c13_4_p4/geometry_feature_snapshots.json --out local_out/c13_4_p7_source_product_smoke
python tools/validate_geometry_product_bundle.py --bundle-dir local_out/c13_4_p7_source_product_smoke
```

Connector implementation note: this patch was authored through the GitHub connector. Local acceptance commands were not executed in this session, so no PASS is claimed here.

Current recorded status:

| Command | Status |
| --- | --- |
| `python -m compileall -q tbdy_engine tools tests` | NOT_RUN_IN_CONNECTOR_SESSION |
| `python tbdy_engine/tools/validate_contract_constitution.py` | NOT_RUN_IN_CONNECTOR_SESSION |
| `python tools/audit_legacy_boundary.py` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p1` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p2` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p3` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p4` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p5` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p6` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p7` | NOT_RUN_IN_CONNECTOR_SESSION |
| P6 product smoke command | NOT_RUN_IN_CONNECTOR_SESSION |
| P7 bundle validator CLI | NOT_RUN_IN_CONNECTOR_SESSION |
