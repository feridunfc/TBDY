# C13.3-P2 FeatureSnapshot Artifact Contract

## Purpose

C13.3-P2 creates a report-facing artifact contract for the accepted C13.3-P1 resolver FeatureSnapshot. The sprint makes FeatureSnapshot evidence consumable by future product/report UI work without introducing CheckEngine, CheckResult, Streamlit, existing report renderer integration, or Excel production input.

This is an artifact/report contract sprint only.

## Source of truth

- Repository: `feridunfc/TBDY`
- Branch base: `baseline/c13-3-p1-feature-snapshot-resolver-integration`
- Accepted tag: `c13.3-p1-feature-snapshot-resolver-integration`
- Accepted main head: `ff29377`

## Scope

C13.3-P2 stays within the C13.3-P1 FeatureSnapshot source families:

- `material_properties`
- `story_definitions`
- `pier_section_properties`

It does not expand into force, design, envelope, governing, demand, rebar, or check-result semantics.

## Added artifact API

The report-facing artifact API is implemented under the feature layer:

- `tbdy_engine/features/feature_snapshot_artifacts.py`

Stable API:

```python
build_feature_snapshot_report_payload(snapshot: dict) -> dict

build_feature_snapshot_artifact_manifest(
    *,
    snapshot: dict,
    output_files: list[str],
    generated_at: str | None = None,
) -> dict

render_feature_snapshot_markdown_report(payload: dict) -> str

render_feature_snapshot_html_report(payload: dict) -> str
```

The API consumes the resolver FeatureSnapshot and emits deterministic, check-safe JSON/Markdown/HTML artifacts.

## Report payload contract

The report payload includes:

- `sprint`
- `generated_at`
- `source_contract_baseline`
- `live_etabs_connected`
- `model_path`
- `etabs_version`
- `target_family`
- `feature_record_count`
- `feature_status_counts`
- `readiness_status_counts`
- `source_family_counts`
- `numeric_feature_count`
- `raw_values_preserved`
- `all_numeric_have_units`
- `all_numeric_have_quantity_kind`
- `all_numeric_have_conversion_provenance`
- `unit_policy_closed`
- `safe_to_implement_checks_now`
- `check_unlock_allowed`
- `source_families`
- `blocked_guardrails`
- `representative_features`

Each `source_families` item contains:

- `source_family`
- `feature_record_count`
- `numeric_feature_count`
- `feature_status_counts`
- `readiness_status_counts`
- `source_tables`
- `representative_feature_ids`
- `has_resolved_records`
- `has_partial_records`
- `has_blocked_records`

The payload includes the locked guardrail feature records:

- `material_compliance_locked`
- `story_drift_torsion_force_locked`
- `pier_wall_force_capacity_detailing_locked`

## Artifact manifest contract

`feature_snapshot_artifact_manifest.json` includes:

- `sprint: C13.3-P2`
- `artifact_contract_version`
- `generated_at`
- `source_snapshot_file`
- `output_files`
- `artifact_roles`
- `live_etabs_connected`
- `feature_values_faked`
- `safe_to_implement_checks_now: false`
- `check_unlock_allowed: false`
- `engineering_verdicts_emitted: false`
- `check_results_emitted: false`
- `excel_production_input_used: false`

## Smoke tool

Tool:

```bash
python tools/smoke_c13_3_p2_feature_snapshot_artifacts.py \
  --out local_out/c13_3_p2_feature_snapshot_artifacts \
  --live-etabs \
  --target-family all \
  --max-rows-per-table 25
```

The P2 smoke tool uses the C13.3-P1 resolver-facing API and the existing P1 shared-fetcher live source path. It does not broad-crawl tables and does not fake live values.

No-live mode exits with code `2` and writes safe artifacts with:

- `feature_values_faked: false`
- `live_etabs_connected: false`
- `connection_status: NO_LIVE_REQUESTED`
- `safe_to_implement_checks_now: false`
- `check_unlock_allowed: false`

## Output files

The smoke tool writes:

- `connection_report.json`
- `feature_snapshot.json`
- `feature_snapshot_summary.json`
- `unit_normalization_report.json`
- `readiness_projection_report.json`
- `blocked_check_guardrail_report.json`
- `source_family_projection_report.json`
- `source_table_projection_debug_report.json`
- `feature_snapshot_report_payload.json`
- `feature_snapshot_artifact_manifest.json`
- `feature_snapshot_evidence_report.md`
- `feature_snapshot_evidence_report.html`

## Markdown report contract

`feature_snapshot_evidence_report.md` is deterministic and includes:

- `C13.3-P2 FeatureSnapshot Evidence Report`
- Connection summary
- Snapshot summary
- Source family summary
- Unit metadata summary
- Representative features
- Locked check guardrails
- Explicit non-check disclaimer

It explicitly states:

- This report is source evidence only.
- This report is not an engineering compliance report.
- No TBDY/TS500 check verdicts are emitted.
- CheckEngine is not invoked.
- `safe_to_implement_checks_now` is false.
- `check_unlock_allowed` is false.

## HTML report contract

`feature_snapshot_evidence_report.html` is a simple static HTML artifact. It does not use Streamlit, existing report renderer code, external JavaScript, or external CSS.

The HTML report carries the same source evidence content as the Markdown report.

## Explicit non-goals

C13.3-P2 does not implement:

- CheckEngine logic
- engineering formulas
- TBDY/TS500 compliance verdicts
- pass/fail engineering judgment
- capacity ratios
- utilization ratios
- rebar checks
- drift checks
- beam/column/wall design judgment
- existing report renderer integration
- Streamlit/app integration
- Excel production input

## Guardrails

All generated artifacts preserve:

- `safe_to_implement_checks_now: false`
- `check_unlock_allowed: false`
- `safe_to_use_for_check: false` for feature records
- `engineering_verdicts_emitted: false`
- `check_results_emitted: false`
- `excel_production_input_used: false`

## Remaining blockers before actual checks

Actual engineering checks remain blocked until separate acceptance work closes:

- force/result semantic promotion
- combo/envelope/governing semantics
- design output/rebar semantic review
- CheckResult schema binding
- report acceptance harness for CheckResult
- per-check engineering validation fixtures
