# C11.1.4 Live Story/Base Table Extraction Debug and Selector Fix

## Verdict

C11.1.4 stays inside Constitution closure scope. It does not run CheckEngine, does not emit CheckResult, does not emit OK/FAIL outside the C11 dry-run boundary, and does not unlock rebar/flexure/shear/capacity paths.

## Exact root cause

Manual `probe_live_story_base_tables.py` proved that ETABS returned real rows for `Story Drifts`, `Story Max Over Avg Drifts`, and `Base Reactions`:

- `Story Drifts`: 716 parsed rows.
- `Story Max Over Avg Drifts`: 716 parsed rows.
- `Base Reactions`: 96 parsed rows.

The live smoke command still produced 9 PARTIAL story/base features because `tools/smoke_live_feature_resolver.py` capped non-modal display tables to `--max-rows` (default 10). The target story `+14.5` and preferred/base output case rows were outside the first 10 parsed sample rows. Therefore the resolver selectors could not see matching rows even though ETABS returned the full table data.

This was a live-smoke row-capture truncation bug, not an ETABS table extraction failure and not a FeatureSnapshot identity-guard failure.

## Fix

- Added `FULL_ROW_CAPTURE_TABLES` in `tools/smoke_live_feature_resolver.py`.
- Added `_live_table_max_rows()`.
- Live smoke now captures all rows for:
  - `Modal Participating Mass Ratios`
  - `Story Drifts`
  - `Story Max Over Avg Drifts`
  - `Base Reactions`
- Other tables remain capped by `--max-rows` for lightweight smoke output.
- C11.1.4 selector and debug reports remain in `tbdy_engine/features/resolver/live_smoke.py`.

## Manual acceptance expectation

After rerunning live C8.3 with the patched tool:

```powershell
python tools/smoke_live_feature_resolver.py `
  --out local_out/c8_3_live_model_geometry_retrieval `
  --live-etabs `
  --target-component 297 `
  --target-label B1 `
  --target-story "+14.5" `
  --target-section B40x70
```

Expected:

```python
{'RESOLVED': 28}
```

No partials should print in the partial-feature verification command.
