# C13.2-P3 Blocked Source Live Proof

## Purpose

C13.2-P3 is a targeted live ETABS proof sprint for foundational source families that remained blocked after C13.2-P1/P2. It produces evidence reports only. It does not update stable catalogs, schemas, FeatureResolver, CheckEngine, report rendering, Streamlit, runtime, archx, or runner_v2.

## Target families

The only target source families are:

1. `material_properties`
2. `story_definitions`
3. `pier_section_properties`

No other source family is probed by this sprint unless a later sprint explicitly expands the scope.

### C13.2-P3 story definition combined proof note

`story_definitions` includes the exact expected table `Tower and Base Story Definition(s)`. The probe treats `Story Definitions` and `Tower and Base Story Definition(s)` as a combined evidence pair: `Story/Name` + `Height` from `Story Definitions` plus `BSElev` from `Tower and Base Story Definition(s)` is enough for `VERIFIED_LIVE_CANDIDATE`, but it remains evidence-only and does not update stable contracts.

## Why broad probing is forbidden

C13.2-P0 established that broad keyword probing can match too many ETABS display tables and create live timeout risk. C13.2-P3 therefore uses exact expected table names first and applies a candidate cap before any fallback keyword-selected table can be fetched. Weak generic terms such as `Material`, `Story`, `Area`, `Wall`, `Section`, `Properties`, or `Summary` are not enough by themselves to create fetch candidates.

## No-live behavior

When `--live-etabs` is not supplied, the probe:

- exits with code `2`
- creates the output directory
- writes `connection_report.json`
- writes `c13_2_p3_blocked_source_probe_summary.json`
- sets `live_etabs_connected: false`
- sets `probe_passed: false`
- sets `safe_to_implement_checks_now: false`
- does not attempt COM/ETABS access

This path is intentionally testable without ETABS.

## Live behavior

When `--live-etabs` is supplied, the probe:

- connects to a running ETABS instance through the existing ETABS connection helper
- reads available display table names
- prefers exact expected table names
- uses bounded fallback candidates only when exact matches are unavailable
- caps selected candidates by `--max-candidate-tables-per-family`
- fetches at most `--max-rows-per-table` rows per selected table
- writes per-family match, header, sample, summary, and promotion recommendation artifacts

## Promotion criteria

A family can become `VERIFIED_LIVE_CANDIDATE` only when live selected tables prove the required observed-data semantics:

- `material_properties`: `Material/Name`, `E1`, `G12`, and `U12`-like columns are required. Material inventory tables such as `Material List by Story`, `Material List by Object Type`, and `Material List by Section Prop` are context only and must not prove material mechanical constants.
- `story_definitions`: direct proof can use `Story/Name`, `Height`, and `Elevation`-like columns from `Story Definitions`. Combined proof is also accepted when `Story Definitions` proves `Story/Name` + `Height` and `Tower and Base Story Definition(s)` proves `BSElev`; in that case outputs must record `derived_elevation_supported: true` and `elevation_is_direct_column: false`.
- `pier_section_properties`: direct pier section geometry proof can come from `Pier Section Properties` when it proves `Story`, `Pier`, at least one width column (`Width Bottom` or `Width Top`), and at least one thickness column (`Thickness Bottom` or `Thickness Top`). A literal `Section`/`PropName`/`WallProp` column is not required for this direct geometry proof; the probe records `section_name_column_present: false` when absent. `Material` is supporting proof only and is recorded as `material_present`.

### C13.2-P3 Hotfix 2 wall/pier evidence note

The bounded exact target list for `pier_section_properties` also includes supporting/context tables: `Wall Bays`, `Wall Object Connectivity`, `Area Assigns - Pier Labels`, `Area Assigns - Sect Prop`, `Wall Property Def - Specified`, and `Area Section Props - Summary`. These tables may support wall/pier mapping, object connectivity, property labels, or area-to-pier/section context, but they are not direct pier section geometry proof by themselves.

`Pier Assignments`, `Wall Object Connectivity`, `Area Assigns - Pier Labels`, and `Area Assigns - Sect Prop` remain `PARTIAL_CONTEXT_ONLY` unless combined with direct `Pier Section Properties` geometry evidence. No wall/pier geometry, wall/pier mapping, force, shear, flexure, capacity, detailing, or design check is unlocked by this sprint.

`VERIFIED_LIVE_CANDIDATE` is not stable contract promotion. A later human-reviewed sprint must decide whether to promote any candidate into stable catalogs/contracts.

## Why `safe_to_implement_checks_now` remains false

P3 collects source evidence only. It does not interpret engineering formulas, force envelopes, design outputs, capacity design, rebar, flexure, shear, or pass/fail criteria. Therefore `safe_to_implement_checks_now` remains false in every output path.

## Stable contract statement

C13.2-P3 does not update:

- `tbdy_engine/catalogs/table_registry.yaml`
- `tbdy_engine/catalogs/etabs_feature_source_contract.yaml`
- `tbdy_engine/catalogs/feature_family_map.yaml`
- `tbdy_engine/catalogs/check_catalog.yaml`
- `tbdy_engine/catalogs/feature_catalog.yaml`

## Checks statement

C13.2-P3 does not implement engineering checks and does not emit `CheckResult`. Hotfix 2 explicitly does not unlock any wall/pier check; all `check_unlock_allowed` values remain `false`.

## Local no-live command

```powershell
python tools/probe_c13_2_p3_blocked_sources.py --out local_out/c13_2_p3_no_live
```

Expected no-live result:

- exit code `2`
- `connection_report.json` written
- `c13_2_p3_blocked_source_probe_summary.json` written
- `safe_to_implement_checks_now: false`

## Live command

```powershell
python tools/probe_c13_2_p3_blocked_sources.py `
  --out local_out/c13_2_p3_live `
  --live-etabs `
  --target-family all `
  --max-candidate-tables-per-family 5 `
  --max-rows-per-table 25
```

Live output must be reviewed manually before any later promotion sprint.


## Hotfix 3: Story tower/base plural live alias

Live ETABS may expose the tower/base elevation table as `Tower and Base Story Definitions` while earlier offline evidence and tests used the singular `Tower and Base Story Definition`. C13.2-P3 accepts both exact aliases and keeps exact matching bounded.

For `story_definitions`, the probe selects `Story Definitions` together with either `Tower and Base Story Definition` or `Tower and Base Story Definitions`. If `Story Definitions` proves `Story`/`Name` plus `Height`, and the tower/base table proves `BSElev`, the family is reported as `VERIFIED_LIVE_CANDIDATE` with `derived_elevation_supported: true`, `elevation_is_direct_column: false`, `base_elevation_column: BSElev`, and `check_unlock_allowed: false`.

This is evidence only. It does not promote stable contracts, does not implement checks, and does not change `safe_to_implement_checks_now: false`.
