# C13.3-P1 FeatureSnapshot Resolver Integration

## Purpose

C13.3-P1 integrates the accepted C13.3-P0 live FeatureSnapshot proof into a stable resolver-facing API. The goal is to let later product, report, and check orchestration consume the same source-to-feature projection path without rewriting the proof logic.

This sprint remains a FeatureSnapshot and resolver integration sprint only.

## Source of truth

- Repository: `feridunfc/TBDY`
- Branch base: `baseline/c13-3-p0-live-feature-snapshot-proof`
- Accepted tag: `c13.3-p0-live-feature-snapshot-proof`
- Accepted main head: `0cdd35f`

## Resolver-facing API

The stable API is exposed from:

- `tbdy_engine/features/resolver_feature_snapshot.py`

Canonical entry point:

```python
build_feature_snapshot_from_source_rows(
    source_rows_by_family,
    *,
    live_etabs_connected,
    model_path=None,
    etabs_version=None,
    target_family="all",
    generated_at=None,
)
```

The function delegates bounded source-row projection to the accepted C13.3-P0 builder, then hardens the root FeatureSnapshot contract for resolver/product consumption.

## Supported source families

C13.3-P1 stays limited to the accepted C13.3-P0 projected families:

- `material_properties`
- `story_definitions`
- `pier_section_properties`

The sprint does not expand into force, design, demand, envelope, governing, rebar, or check-result semantics.

## Root contract

The resolver-facing FeatureSnapshot root includes:

- `sprint`
- `source_contract_baseline`
- `generated_at`
- `live_etabs_connected`
- `model_path`
- `etabs_version`
- `target_family`
- `feature_records`
- `feature_status_counts`
- `readiness_status_counts`
- `source_family_counts`
- `numeric_feature_count`
- `unit_policy_closed: true`
- `raw_values_preserved: true`
- `safe_to_implement_checks_now: false`
- `check_unlock_allowed: false`

## Feature record contract

Every emitted feature record keeps:

- `feature_id`
- `feature_name`
- `component_type`
- `component_id`
- `source_family`
- `source_tables`
- `source_columns`
- `readiness_status`
- `feature_status`
- `raw_value`
- `raw_unit`
- `normalized_value`
- `normalized_unit`
- `quantity_kind`
- `conversion_provenance`
- `evidence`
- `semantic_guardrails`
- `derived`
- `safe_to_use_for_check: false`
- `check_unlock_allowed: false`
- `unit_policy`

Numeric records must retain raw and normalized unit metadata and conversion provenance. Raw source values are not silently converted at the source-contract level.

## Summary artifacts

The resolver layer exposes deterministic report helpers:

- `summarize_snapshot(snapshot)`
- `unit_normalization_report(snapshot)`
- `readiness_projection_report(snapshot)`
- `blocked_check_guardrail_report(snapshot)`
- `source_family_projection_report(snapshot)`

The P1 smoke tool writes these reports as JSON artifacts.

## Live smoke tool

Tool:

```bash
python tools/smoke_c13_3_p1_feature_snapshot_resolver.py \
  --out local_out/c13_3_p1_feature_snapshot_resolver \
  --live-etabs \
  --target-family all \
  --max-rows-per-table 25
```

No-live mode exits with code `2` and writes no fake live values.

Live mode uses the shared ETABS display table fetcher:

```python
from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table
```

The tool does not broad-crawl tables. It fetches only the bounded exact source tables for the selected C13.3 family.

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

## Source-table diagnostics

`source_table_projection_debug_report.json` includes, per target source table:

- `table_name`
- `source_family`
- `fetch_status`
- `row_count`
- `columns`
- `sample_rows`
- `projected_feature_count`
- `projection_status`
- `projection_blocker`
- `selected_signature`
- `selected_signature_reason`
- `signature_attempts`
- `parser_debug`
- `parser_diagnostics`

This proves whether live ETABS source rows were available after the robust shared fetcher attempts.

## Explicit non-goals

C13.3-P1 does not implement:

- CheckEngine logic
- engineering formulas
- TBDY/TS500 compliance checks
- pass/fail verdicts
- capacity ratios
- utilization ratios
- rebar adequacy checks
- drift compliance checks
- beam/column/wall design verdicts
- report renderer behavior
- Streamlit/app behavior
- Excel production input

## Permanent sprint guardrails

All roots and records keep:

- `safe_to_implement_checks_now: false`
- `check_unlock_allowed: false`
- `safe_to_use_for_check: false` on every feature record

## Remaining blockers before actual checks

Actual engineering checks remain blocked until separate acceptance work closes:

- force/result semantics
- combo/envelope/governing semantics
- design output/rebar semantics
- report acceptance harness
- check result schema binding
- per-check engineering validation fixtures
