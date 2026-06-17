# C13.3-P0 Live FeatureSnapshot Proof

## Purpose

C13.3-P0 is the first post-contract FeatureSnapshot proof sprint after the
C13.2-P5 contract/source-readiness closure. It consumes the closed source
contracts and `source_feature_readiness_matrix.yaml` policy and proves only a
minimal source-to-feature projection path.

The sprint covers a deliberately small subset:

- `material_properties`
- `story_definitions`
- `pier_section_properties`

## Boundary

This sprint does not implement CheckEngine behavior. It does not implement
TBDY/TS500 engineering formulas. It does not produce engineering verdicts,
design verdicts, utilization verdicts, or compliance decisions.

The only allowed feature statuses are data/readiness statuses:

- `RESOLVED`
- `PARTIAL`
- `BLOCKED_SEMANTIC_REVIEW`
- `BLOCKED_NEEDS_LIVE_PROBE`
- `LOCKED_CHECK_NOT_ALLOWED`
- `OUT_OF_SCOPE_UNSUPPORTED`

The root guardrails remain:

```yaml
safe_to_implement_checks_now: false
check_unlock_allowed: false
unit_policy_closed: true
```

Each feature record also carries:

```yaml
check_unlock_allowed: false
safe_to_use_for_check: false
```

## Unit policy

Raw ETABS source values are preserved with raw unit context. They are not
silently converted at the source-contract level.

The FeatureSnapshot proof may produce normalized display values, but every
numeric normalized value carries:

- `raw_value`
- `raw_unit`
- `normalized_value`
- `normalized_unit`
- `quantity_kind`
- `conversion_provenance`

Default display units follow the C13.2-P5 unit policy:

| Quantity | Display unit |
| --- | --- |
| Force | kN |
| Moment | kN.m |
| Global length/elevation | m |
| Section dimensions | mm |
| Deformation/displacement | mm |
| Drift | ratio or percent, explicitly labelled |
| Stress/material strength | MPa |
| Reinforcement area | mm2 |

## Implemented proof path

`tbdy_engine/features/source_feature_snapshot_builder.py` builds a
FeatureSnapshot-shaped payload from bounded source rows. It creates feature
records for materials, stories, and pier section properties while preserving raw
and normalized unit metadata.

`tools/smoke_c13_3_p0_live_feature_snapshot.py` provides the smoke CLI:

```bash
python tools/smoke_c13_3_p0_live_feature_snapshot.py \
  --out local_out/c13_3_p0_live_feature_snapshot \
  --live-etabs \
  --target-family all \
  --max-rows-per-table 25
```

The tool writes:

- `connection_report.json`
- `feature_snapshot.json`
- `feature_snapshot_summary.json`
- `unit_normalization_report.json`
- `readiness_projection_report.json`
- `blocked_check_guardrail_report.json`

If `--live-etabs` is not provided, it writes a diagnostic connection report,
keeps the snapshot disconnected, and does not fake live values.

## Material proof

Material rows project material identity and direct raw source fields such as
`E1`, `G12`, `U12`, `Fc`, and `Fy` when present. Missing fields become `PARTIAL`.
Material compliance concepts remain `LOCKED_CHECK_NOT_ALLOWED`.

## Story proof

Story rows project story identity and height as direct source features. Story
elevation is represented as a derived feature using `BSElev` plus cumulative
story heights.

The derivation policy is explicit:

```yaml
derived_elevation_supported: true
elevation_is_direct_column: false
base_elevation_column: BSElev
```

Drift, torsion, and story-force result semantics remain locked or blocked for
semantic review.

## Pier section proof

Pier section rows project pier identity, story, width, thickness, and material.
The proof records that direct section geometry is present and that a literal
`Section` column is not required.

Pier/wall force, capacity, and detailing concepts remain locked or blocked for
semantic review.

## Remaining blockers before checks

The following blockers remain before engineering checks can be implemented:

1. Design force/result semantics.
2. Pier forces semantic review.
3. Rebar/design output interpretation.
4. Combo/envelope/governing semantics.
5. CheckEngine acceptance harness not yet implemented.

## Validation

Required validation commands:

```bash
python -m compileall -q tbdy_engine tests tools
pytest tests/c13_3_p0 -q
pytest tests/c13_2_p5 -q
pytest tests/c13_2_p4 -q
pytest tests/c13_2_p3 -q
pytest tests/c13_2_p2 -q
pytest tests/contracts -q
python tools/validate_c13_2_p5_contract_closure.py
python tools/validate_c13_2_p2_verified_source_contracts.py
python tbdy_engine/tools/validate_contract_constitution.py
```
