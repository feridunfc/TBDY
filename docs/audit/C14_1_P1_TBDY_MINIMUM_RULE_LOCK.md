# C14.1-P1 TBDY Minimum Rule Lock

A rule may emit `OK` or `FAIL` only when its formula, comparison, applicability, units, source evidence, and TBDY clause are locked here.

| check_id | element | required features | formula | comparison / result | limit | unit | TBDY clause | source | review status |
|---|---|---|---|---|---:|---|---|---|---|
| beam_geometry_min_width | beam | beam_width_mm | bw >= 250 | OK / FAIL | 250 | mm | 7.4.1.1(a) | Concrete Rectangular.t2 | LOCKED |
| beam_geometry_min_depth_absolute | beam | beam_depth_mm | h >= 300 | OK / FAIL | 300 | mm | 7.4.1.1(b) | Concrete Rectangular.t3 | LOCKED |
| beam_geometry_depth_ge_three_times_slab_thickness | beam | beam_depth_mm, adjacent_slab_thickness_mm | h >= 3t | OK / FAIL / NO_DATA / BLOCKED | 3t | mm | 7.4.1.1(b) | explicit beam-slab association required | RULE LOCKED; SOURCE PATH BLOCKED |
| beam_depth_width_ratio | beam | beam_depth_mm, beam_width_mm | h / bw <= 3.5 | OK / FAIL | 3.5 | ratio | 7.4.1.1(b) | Concrete Rectangular.t2,t3 | LOCKED |
| beam_web_reinforcement_detailing_trigger | beam | beam_depth_mm, beam_clear_span_mm | h > clear_span / 4 | REQUIRED / NOT_REQUIRED / NO_DATA / BLOCKED | 0.25 | ratio | 7.4.1.1(c) | Connectivity.Length and End Offsets.OffsetI/OffsetJ candidate | RULE LOCKED; CLEAR-SPAN SEMANTICS BLOCKED |
| beam_span_depth_ratio | beam | beam_clear_span_mm, beam_depth_mm | not locked | BLOCKED | - | ratio | not locked | candidate clear span only | BLOCKED |
| beam_material_min_concrete_strength | beam | concrete_fck_mpa | candidate fck >= 25 | BLOCKED | 25 | MPa | not locked | Concrete Data.Fc | BLOCKED |
| column_geometry_min_dimension | column | column_width_mm, column_depth_mm | min(b,h) >= 300 | OK / FAIL | 300 | mm | 7.3.1.1 | Concrete Rectangular.t2,t3 | LOCKED |
| column_geometry_min_area | column | width and depth evidence | b*h >= 75000 | OK / FAIL | 75000 | mm2 | 7.3.1.1 | derived from both dimensions | LOCKED |
| column_geometry_aspect_ratio | column | width and depth evidence | min/max >= 0.40 | OK / FAIL | 0.40 | ratio | 7.3.1.2 | derived from both dimensions | LOCKED |
| column_material_min_concrete_strength | column | concrete_fck_mpa | candidate fck >= 25 | BLOCKED | 25 | MPa | not locked | Concrete Data.Fc | BLOCKED |

## Beam-depth result separation

The absolute depth, depth-versus-adjacent-slab, and web-detailing trigger are separate results. The absolute 300 mm check executes independently. The adjacent-slab result remains `BLOCKED` because no explicit beam-to-slab association resolver is implemented. Required diagnostic: `BEAM_ADJACENT_SLAB_THICKNESS_NOT_RESOLVED`.

No global slab thickness, nearest slab, arbitrary story slab, property-name parsing, or min/max slab fallback is permitted.

## Clear-span candidate boundary

The candidate chain is reported transparently:

```text
Beam Object Connectivity.UniqueName -> Length
Frame Assignments - End Length Offsets.UniqueName -> OffsetI, OffsetJ
candidate = Length - OffsetI - OffsetJ
```

The candidate remains partial evidence. `beam_clear_span_mm` is not emitted as a resolved design feature. When candidate values exist but semantics are not approved, the detailing trigger is `BLOCKED` with `BEAM_CLEAR_SPAN_SEMANTICS_NOT_LOCKED`. It is `NO_DATA` only when depth or candidate values are genuinely absent. `REQUIRED` and `NOT_REQUIRED` are detailing outcomes, not engineering `FAIL` or `OK` aliases.

## Product status boundary

`engineering_fail` becomes true only when an executable geometry check emits `FAIL`. `BLOCKED`, `NO_DATA`, `OUT_OF_SCOPE`, `REQUIRED`, and `NOT_REQUIRED` never increase engineering fail counts. They reduce coverage to `PARTIAL` where applicable.

## Forbidden inference

The product does not parse section names, infer strength from material names, classify from labels, guess units, call `SetPresentUnits`, use global/nearest slab fallbacks, or promote an unapproved clear-span candidate into a resolved design feature.
