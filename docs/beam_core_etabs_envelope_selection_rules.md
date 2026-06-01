# BeamCore ETABS Envelope Selection Rules

R7A applies these rules only to real `SapModel.Results.FrameForce` rows for one selected frame object and selected combinations.

## Units

FrameForce output units must be known or explicitly declared by environment variables:

- `TBDY_LIVE_ETABS_FORCE_UNIT=kN`
- `TBDY_LIVE_ETABS_MOMENT_UNIT=kNm`
- `TBDY_LIVE_ETABS_LENGTH_UNIT=mm`

Missing or unknown units fail with `force_units`.

## Action rules

### Vd_left_kN

Use `max(abs(V2))` at or nearest the left end station among selected combinations.

### Ve_left_kN

For R7A, use the same governing ETABS combo/envelope shear as `Vd_left_kN`.

Mark:

```text
Ve_source = etabs_results_envelope
```

Do not call this capacity-designed `Ve`.

### Md_left_neg_kNm

Use `max(abs(M3))` among negative `M3` values at or nearest the left end station among selected combinations.

### Md_mid_pos_kNm

Use `max(positive M3)` at or nearest midspan among selected combinations.

### Md_right_neg_kNm

Use `max(abs(M3))` among negative `M3` values at or nearest the right end station among selected combinations.

### axial_kN

Use `max(abs(P))` among selected stations and selected combinations, recording station and combo.

## Failure rules

Missing force results fail with `force_extract`.

Environment overrides may be used for geometry, materials, and reinforcement only.

`Md`, `Vd`, and `Ve` must not be environment-overridden for live smoke success.

Live success requires:

```text
ACTIONS_SOURCE = ETABS_RESULTS
```
