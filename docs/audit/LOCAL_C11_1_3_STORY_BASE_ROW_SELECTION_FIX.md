# C11.1.3 Live Story/Base Row Selection Fix

Sprint: `C11_1_3_LIVE_STORY_BASE_ROW_SELECTION_FIX`

## Root cause

The C11.1.2 fixture path passed, but manual live C8.3 still produced `19 RESOLVED / 9 PARTIAL` because story/global rows were selected through placeholder-sensitive logic:

- Story snapshot identity could remain `STORY_SMOKE` with `story: null` even when `--target-story +14.5` was supplied.
- Story drift/torsion row selection used fragile exact string matching and did not robustly normalize story values such as `+14.5`, `14.5000`, and whitespace-padded variants.
- Base reaction selection reused a generic selector rather than a global/base-specific selector. Base Reactions rows generally do not have Story/component identity and must be selected by valid observed FX/FY rows and output-case preference.

## Fix

- Added normalized story comparison helpers.
- Story snapshot now uses the CLI target story as component identity when available:
  - `component_id: +14.5`
  - `identity.story: +14.5`
- Story drift selector now requires real observed columns: `Story`, `OutputCase`, `Direction`, `Drift`.
- Story torsion selector now requires real observed columns: `Story`, `OutputCase`, `Ratio`.
- Base reactions selector is independent of story/component identity and prefers valid numeric rows, with a preference for `Crack_SeisY_UpSoil` when available.
- No fake values were added. No section-name geometry parsing was used as feature value.

## Boundary

- C8/C9/C10 still emit no CheckResult.
- CheckEngine is not called by FeatureResolver, CoverageMatrix, or C10 readiness.
- C11 dry-run remains the only place where CheckResult is emitted.
- Rebar/flexure/shear/capacity remain locked.
