# C13.3-P3 No-Live Artifact Contract Hardening

## Purpose

C13.3-P3 hardens the C13.3-P2 FeatureSnapshot artifact contract for no-live/offline validation. It also adds a diagnostic-only check preflight contract that explains why actual checks remain locked.

This sprint requires no ETABS.

## Important no-live boundary

This sprint does not perform live verification. It does not add live ETABS requirements, live probes, source discovery, or source family promotion.

All generated acceptance artifacts are fixture-based and explicitly report:

- `live_etabs_requested: false`
- `live_etabs_connected: false`
- `connection_status: NO_LIVE_REQUESTED`
- `feature_values_faked: false`
- `fixture_values_used: true`

## Source of truth

- Repository: `feridunfc/TBDY`
- Branch base: `baseline/c13-3-p2-feature-snapshot-artifact-contract`
- Accepted tag: `c13.3-p2-feature-snapshot-artifact-contract`
- Accepted main head: `dd85d6c`

## Added validator contract

Module:

- `tbdy_engine/features/feature_snapshot_artifact_validator.py`

Stable API:

```python
validate_feature_snapshot_report_payload(payload: dict) -> dict
validate_feature_snapshot_artifact_manifest(manifest: dict) -> dict
scan_for_forbidden_engineering_verdicts(obj_or_text: Any) -> dict
validate_artifact_file_set(output_dir: Path) -> dict
```

Validation results are deterministic and include:

- `validation_status`
- `missing_required_fields`
- `missing_required_files`
- `forbidden_terms_found`
- `guardrail_errors`
- `checked_files`
- `safe_to_implement_checks_now`
- `check_unlock_allowed`
- `engineering_verdicts_emitted`
- `check_results_emitted`
- `excel_production_input_used`

The validator rejects missing artifacts, missing source family counts, missing locked guardrails, enabled check flags, check result flags, Excel production flags, and forbidden engineering verdict terms in generated JSON/MD/HTML artifacts.

## Added schemas

Schemas added:

- `tbdy_engine/schemas/feature_snapshot_report_payload.schema.json`
- `tbdy_engine/schemas/feature_snapshot_artifact_manifest.schema.json`
- `tbdy_engine/schemas/check_preflight_diagnostic.schema.json`

The schemas enforce the minimum P3 guardrails, including disabled check unlock and diagnostic-only behavior.

## Added diagnostic-only check preflight contract

Module:

- `tbdy_engine/features/check_preflight_diagnostics.py`

Stable API:

```python
build_check_preflight_diagnostic_report(report_payload: dict) -> dict
```

The report is diagnostic-only and contains:

- `sprint: C13.3-P3`
- `diagnostic_contract_version`
- `diagnostic_only: true`
- `check_engine_invoked: false`
- `checks_locked: true`
- `safe_to_implement_checks_now: false`
- `check_unlock_allowed: false`
- `source_evidence_only: true`
- `prospective_check_groups`
- `blockers`
- `required_future_contracts`

Prospective groups are future diagnostic entries only:

- `material_compliance`
- `story_drift_torsion_force`
- `pier_wall_force_capacity_detailing`

They do not compute engineering results and do not invoke anything under `tbdy_engine.checks`.

## Added no-live smoke tool

Tool:

```bash
python tools/smoke_c13_3_p3_no_live_artifact_contract.py --out local_out/c13_3_p3_no_live_artifact_contract
```

Optional fixture selection:

```bash
python tools/smoke_c13_3_p3_no_live_artifact_contract.py --out local_out/c13_3_p3_no_live_artifact_contract --fixture minimal
python tools/smoke_c13_3_p3_no_live_artifact_contract.py --out local_out/c13_3_p3_no_live_artifact_contract --fixture p2-compatible
```

The tool creates deterministic fixture FeatureSnapshot data using existing C13.3-P1/P2 contracts, renders JSON/Markdown/HTML artifacts, builds the diagnostic preflight report, validates the artifact set, and writes `artifact_contract_validation_report.json`.

## Added validator CLI

Tool:

```bash
python tools/validate_c13_3_p3_artifact_contract.py --artifact-dir local_out/c13_3_p3_no_live_artifact_contract
```

It returns exit code `0` only when the no-live artifact directory satisfies all P3 guardrails.

## Required no-live outputs

- `connection_report.json`
- `feature_snapshot.json`
- `feature_snapshot_summary.json`
- `unit_normalization_report.json`
- `readiness_projection_report.json`
- `blocked_check_guardrail_report.json`
- `source_family_projection_report.json`
- `feature_snapshot_report_payload.json`
- `feature_snapshot_artifact_manifest.json`
- `feature_snapshot_evidence_report.md`
- `feature_snapshot_evidence_report.html`
- `check_preflight_diagnostic_report.json`
- `artifact_contract_validation_report.json`

## Explicit non-goals

C13.3-P3 does not implement:

- CheckEngine logic
- engineering formulas
- TBDY/TS500 verdicts
- beam/column/wall/slab check execution
- live ETABS calls
- live ETABS source discovery
- new ETABS source family promotion
- Streamlit/app integration
- existing report renderer integration
- Excel production input

## Guardrails preserved

All reports preserve:

- `safe_to_implement_checks_now: false`
- `check_unlock_allowed: false`
- `engineering_verdicts_emitted: false`
- `check_results_emitted: false`
- `excel_production_input_used: false`

## Remaining blockers before actual checks

Actual checks remain blocked until later sprints close:

- force/result semantic promotion
- combo/envelope/governing semantics
- design output/rebar semantic review
- CheckResult schema binding
- report harness for check artifacts
- per-check engineering validation fixtures
