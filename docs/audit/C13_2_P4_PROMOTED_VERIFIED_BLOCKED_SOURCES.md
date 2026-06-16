# C13.2-P4 Promoted Verified Blocked Sources

## Purpose

C13.2-P4 promotes the C13.2-P3 live-verified blocked source candidates into stable source contract metadata. This is contract promotion only. It does not implement engineering checks, mutate FeatureResolver behavior, mutate CheckEngine behavior, or change report rendering.

## P3 live proof basis

P3 live ETABS proof was accepted on ETABS 23.2.0 using model `C:\tmp\B-BLOK_Revised.EDB`. The promoted candidates were:

- `material_properties` from `Material Properties - Basic Mechanical Properties`, with supporting concrete/rebar material property tables.
- `story_definitions` from `Story Definitions` plus `Tower and Base Story Definitions`.
- `pier_section_properties` from `Pier Section Properties`, with supporting wall/pier mapping context.

## Promoted source contracts

### material_properties

Promoted as a stable source contract for raw material mechanical constants and material metadata only. The required live proof columns are `Material`, `E1`, `G12`, and `U12`. Concrete and rebar data tables remain raw metadata sources; they do not create material compliance checks or TBDY/TS500 pass/fail interpretation.

### story_definitions

Promoted as story metadata source contract. `Story Definitions` provides `Story`/`Name` and `Height`. `Tower and Base Story Definitions` provides `BSElev`. Story elevation support is therefore **derived**, not a direct per-story elevation column.

Policy fields:

- `derived_elevation_supported: true`
- `elevation_is_direct_column: false`
- `base_elevation_column: BSElev`
- Backward compatibility alias: `Tower and Base Story Definition`

This does not unlock drift, torsion, story force, or story-based engineering verdicts.

### pier_section_properties

Promoted as direct pier/wall section geometry and material source contract when `Pier Section Properties` exposes `Story`, `Pier`, width, thickness, and material evidence. A literal `Section`/`PropName`/`WallProp` column is not mandatory when direct geometry exists.

Policy fields:

- `direct_section_geometry_present: true`
- `section_name_column_required: false`
- `section_name_column_present: false`
- `material_present: true`

Supporting context tables include `Area Assignments - Summary`, `Wall Bays`, `Wall Object Connectivity`, `Area Assigns - Pier Labels`, `Area Assigns - Sect Prop`, `Wall Property Def - Specified`, and `Area Section Props - Summary`. These are context/mapping evidence only unless combined with direct pier section geometry.

This does not unlock wall force, pier force, shear capacity, flexure/axial capacity, confinement, detailing, or engineering verdicts.

## Guardrails

- `safe_to_implement_checks_now` remains `false`.
- `check_unlock_allowed` remains `false` for every promoted family and supporting source.
- Excel input/export remains evidence inventory only and is not a production input path.
- No stable engineering check is implemented.
- No FeatureResolver behavior change is made.
- No CheckEngine behavior change is made.
- No report renderer behavior change is made.

## Checks that remain locked

The following remain locked pending later source-to-feature and feature-to-check sprints:

- Material compliance checks.
- Drift and torsion checks.
- Story force checks.
- Pier force checks.
- Wall shear/flexure/axial capacity checks.
- Confinement/detailing checks.
- Any engineering pass/fail verdict.

## Next step

A later C13.2-P5 source-to-feature readiness sprint should map these promoted source contracts to canonical features, direct/derived feature policy, unit normalization, and missing/partial feature status behavior.
