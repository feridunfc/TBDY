# C14.1-P1 TBDY Minimum Rule Lock

This document is the executable-rule boundary for the live beam/column minimum-compliance product. A rule may emit `OK` or `FAIL` only when its clause, formula, comparison, applicability, source evidence, and units are locked here.

| check_id | element_type | required features | formula | comparison | limit | unit | TBDY clause | applicability | evidence source | review status |
|---|---|---|---|---|---:|---|---|---|---|---|
| beam_geometry_min_width | beam | beam_width_mm | bw >= 250 | >= | 250 | mm | 7.4.1.1(a) | supported concrete rectangular beam | Concrete Rectangular.t2 | LOCKED |
| beam_geometry_min_depth | beam | beam_depth_mm | h >= 300 | >= | 300 | mm | 7.4.1.1(b) | supported concrete rectangular beam | Concrete Rectangular.t3 | LOCKED |
| beam_depth_vs_slab_thickness | beam | beam_depth_mm, beam_slab_thickness_mm | h >= 3t | >= | 3t | mm | 7.4.1.1(b) | slab thickness required | depth plus a future explicit slab-thickness source | RULE LOCKED; DATA BLOCKED |
| beam_depth_width_ratio | beam | beam_depth_mm, beam_width_mm | h / bw <= 3.5 | <= | 3.5 | ratio | 7.4.1.1(b) | supported concrete rectangular beam | Concrete Rectangular.t2,t3 | LOCKED |
| beam web detailing trigger | beam | beam_depth_mm, beam_clear_span_mm | h > clear_span / 4 | trigger | 0.25 | ratio | 7.4.1.1(c) | reliable clear span required | connectivity Length and explicit end offsets | RULE LOCKED; CLEAR-SPAN SEMANTICS NO_DATA |
| beam_span_depth_ratio | beam | beam_clear_span_mm, beam_depth_mm | not locked | - | - | ratio | not locked | none | candidate Length/OffsetI/OffsetJ only | BLOCKED |
| beam_material_min_concrete_strength | beam | concrete_fck_mpa | fck >= 25 | >= | 25 | MPa | not locked | none | Concrete Data.Fc | BLOCKED |
| column_geometry_min_dimension | column | column_width_mm, column_depth_mm | min(b,h) >= 300 | >= | 300 | mm | 7.3.1.1 | supported concrete rectangular column | Concrete Rectangular.t2,t3 | LOCKED |
| column_geometry_min_area | column | column_area_mm2 | b*h >= 75000 | >= | 75000 | mm2 | 7.3.1.1 | supported concrete rectangular column | derived from t2,t3 with both evidence chains | LOCKED |
| column_geometry_aspect_ratio | column | column_aspect_ratio | min(b,h)/max(b,h) >= 0.40 | >= | 0.40 | ratio | 7.3.1.2 | supported concrete rectangular column | derived from t2,t3 with both evidence chains | LOCKED |
| column_material_min_concrete_strength | column | concrete_fck_mpa | fck >= 25 | >= | 25 | MPa | not locked | none | Concrete Data.Fc | BLOCKED |

## Clear-span boundary

The product may preserve the transparent candidate `centerline Length - OffsetI - OffsetJ`. The candidate is marked partial evidence. It is not promoted to a governing span until ETABS display-table semantics and the exact governing TBDY span definition are reviewed together.

Therefore `beam_span_depth_ratio` is `BLOCKED`, the beam web detailing trigger is `NO_DATA` rather than `REQUIRED` or `NOT_REQUIRED`, and raw `Length`, `OffsetI`, and `OffsetJ` remain visible in evidence.

## Material boundary

`concrete_fck_mpa` is resolved from the locked C14.0-P1 `Fc` source and unit evidence. The candidate 25 MPa minimum remains visible in the report, but no exact TBDY clause was supplied or independently locked for this sprint. Beam and column material checks therefore emit `BLOCKED`, never a fabricated `OK` or `FAIL`.

## Forbidden inference

The product does not parse section names, infer strength from material names, classify elements from labels, guess units, call `SetPresentUnits`, or use direct APIs as the primary source.
