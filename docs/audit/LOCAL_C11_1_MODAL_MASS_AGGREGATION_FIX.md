# C11.1 Modal Mass Aggregation Fix

C11.1 fixes modal participating mass feature resolution so `modal_sum_ux` and `modal_sum_uy` represent cumulative participation over all available modal rows.

## Scope

Allowed:
- FeatureResolver modal cumulative aggregation.
- C11 dry-run check input correction for `modal_mass_participation`.
- Evidence/report metadata for selected modal aggregation.

Forbidden and unchanged:
- No live ETABS call inside CheckEngine.
- No provider call inside CheckEngine.
- No FeatureResolver call inside CheckEngine.
- No rebar/flexure/shear/capacity unlock.
- No legacy runner/runtime/archx imports.

## Semantic fix

- `modal_sum_ux`: `max_cumulative` over `Modal Participating Mass Ratios / SumUX`.
- `modal_sum_uy`: `max_cumulative` over `Modal Participating Mass Ratios / SumUY`.
- `modal_mass_participation`: CheckEngine uses `min(modal_sum_ux, modal_sum_uy)` against `0.90` with `value_over_minimum`.

This prevents the false negative where an intermediate row such as Mode 10 (`SumUX=0.7235`, `SumUY=0.7503`) was used even though later modes exceed 0.90.

## Evidence metadata

Resolved modal features record aggregation metadata in evidence `source_row`:
- `aggregation_method=max_cumulative`
- selected mode/row index
- selected cumulative value
- mode count
- source rows considered count
- first/last/max mode diagnostics

## Manual rerun sequence

After regenerating C8.3 live FeatureSnapshot on the ETABS machine, rerun C9, C10, and C11 dry-run exactly as before. The CheckEngine remains limited to the three C11 runnable rows.
