# C13.4-P0 Live Semantic Source Review

## Purpose

C13.4-P0 performs live semantic source review only. It fetches bounded sample rows from already-known ETABS display-table candidates and classifies whether the source rows expose enough semantic columns to plan future diagnostic/check input contracts.

This sprint does not implement checks and does not promote sources to check-ready status.

## Source of truth

- Repository: `feridunfc/TBDY`
- Branch base: `baseline/c13-3-p3-no-live-artifact-contract-hardening`
- Accepted tag: `c13.3-p3-no-live-artifact-contract-hardening`
- Accepted main head: `f362618344e664abe5b712520fdda043f69f3e45`

## Scope

Target semantic review families:

- `base_reactions`
- `story_drifts`
- `story_max_over_avg_drifts`
- `pier_forces`
- `frame_forces`
- `design_outputs`
- `rebar_outputs`
- `combo_semantics`

The tool uses bounded exact candidate table names that were already represented in table registry/source-readiness history. It does not broad-crawl arbitrary ETABS tables and does not invent source names.

## Added module

Module:

- `tbdy_engine/features/semantic_source_review.py`

Stable API includes:

```python
classify_semantic_source_table(...)
build_semantic_source_review_report(...)
build_combo_semantic_review(...)
build_force_result_semantic_review(...)
build_design_output_semantic_review(...)
build_rebar_role_semantic_review(...)
scan_semantic_outputs_for_forbidden_verdicts(...)
```

The classifier detects semantic column groups only:

- combo/case columns
- station/location columns
- direction columns
- object identity columns
- force component columns
- design output columns
- rebar role columns
- unit columns

It does not compute forces, envelopes, governing rows, design values, or engineering checks.

## Added live smoke tool

Tool:

```bash
python tools/smoke_c13_4_p0_live_semantic_source_review.py \
  --out local_out/c13_4_p0_live_semantic_source_review \
  --live-etabs \
  --target-family all \
  --max-rows-per-table 25
```

No-live mode:

```bash
python tools/smoke_c13_4_p0_live_semantic_source_review.py \
  --out local_out/c13_4_p0_no_live_semantic_source_review
```

No-live mode exits with code `2` and writes only a safe `connection_report.json`. It does not write fake semantic rows.

## Output files in live mode

- `connection_report.json`
- `semantic_source_review_summary.json`
- `semantic_source_inventory_report.json`
- `combo_semantic_review_report.json`
- `force_result_semantic_review_report.json`
- `drift_story_semantic_review_report.json`
- `design_output_semantic_review_report.json`
- `rebar_role_semantic_review_report.json`
- `semantic_source_sample_rows.json`
- `forbidden_verdict_scan_report.json`

## Guardrails

Every generated report preserves:

- `safe_to_implement_checks_now: false`
- `check_unlock_allowed: false`
- `diagnostic_only: true`
- `check_engine_invoked: false`
- `engineering_verdicts_emitted: false`
- `check_results_emitted: false`
- `excel_production_input_used: false`
- `feature_values_faked: false`

## Explicit non-goals

C13.4-P0 does not:

- implement CheckEngine logic
- call CheckEngine
- compute engineering formulas
- emit TBDY/TS500 verdicts
- produce CheckResult payloads
- choose governing rows
- compute envelopes
- select design combinations
- interpret rebar/design outputs for final detailing
- integrate existing report renderer
- integrate Streamlit/apps
- use Excel as production input
- mutate source contract YAMLs

## Semantic blockers expected from this sprint

The sprint is intended to identify blockers for future contracts, especially:

- combo/governing row policy
- envelope policy
- design output role policy
- rebar role policy
- unit metadata policy for result/design tables
- object identity mapping policy

These are planning diagnostics only. They do not unlock check use.
