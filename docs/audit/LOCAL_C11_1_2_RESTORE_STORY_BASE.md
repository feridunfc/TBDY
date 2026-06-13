# C11.1.2 Restore Story/Base Feature Resolution and Constitution Closure

Sprint: `C11_1_2_RESTORE_STORY_BASE_FEATURE_RESOLUTION`

## Executive summary

This patch closes a regression guard around C8.3 live-style FeatureSnapshot status counts after the C11.1 modal aggregation and C11.1.1 identity guard fixes.

The resolver now has explicit regression coverage proving that the C8.3 live-style fixture resolves:

- `story_drift_value`
- `story_drift_max_mm`
- `story_drift_output_case`
- `story_drift_direction`
- `story_torsion_a1_coefficient`
- `base_reaction_fx`
- `base_reaction_fy`
- `base_reaction_x_kN`
- `base_reaction_y_kN`

with `RESOLVED` status and `FULL` evidence.

## Root-cause closure

The safe-value identity guard fix is preserved: values such as `STORY_SMOKE`, `STORY_SAMPLE`, `OKUL`, and `B40x70` do not trigger forbidden check/result semantics. Only forbidden identity keys are rejected.

C11.1 modal aggregation is also preserved: modal cumulative participation features use `max_cumulative` over all available rows rather than a sampled/intermediate row.

For story/base rows, C11.1.2 adds deterministic row selection helpers that prefer target story rows when available and otherwise select rows that actually contain the required observed column. This prevents smoke placeholder identity or row-order changes from turning valid story/base source rows into PARTIAL features.

## Boundary

C8/C9/C10 remain CheckResult-free. CheckEngine execution is still isolated to C11 dry-run only, and only for RUNNABLE rows. Rebar, flexure, shear, and force-demand checks remain locked.
