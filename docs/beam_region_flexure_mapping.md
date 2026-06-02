# Beam Region Flexure Mapping

## Scope

Maps BeamDemandSet flexure demands to beam design regions
and runs pure flexure design kernels for each region.

## Region Mapping

| Region | Demand | Position |
|--------|--------|----------|
| top_left | Md_left_neg_kNm | Left support |
| bottom_mid | Md_mid_pos_kNm | Mid-span |
| top_right | Md_right_neg_kNm | Right support |

## Pipeline Per Region
Md (from BeamDemandSet)
↓
flexure_md_to_as()
↓
As_required, a, c, z, Mu_check
↓
flexure_limits()
↓
rho_min, rho_max, As_min, As_max
↓
BeamRegionFlexureResult


## Output Status

| Status | Meaning |
|--------|---------|
| OK | All regions OK |
| MIN_REINFORCEMENT_GOVERNS | At least one region governed by minimum reinforcement |
| OVER_REINFORCED | At least one region exceeds rho_max |
| MISSING_DEMAND | Demand value is None for a region |
| PARTIAL | Some regions MISSING_DEMAND, others processed |
| INVALID_INPUT | Identity mismatch or invalid geometry/material |

## Demand Evidence Preservation

Each region result carries:
- combo, station, raw_value, rule from BeamDemandEvidence
- flexure kernel evidence (Mu_check, a, c, z, alpha, beta)
- limit kernel evidence (rho_min formula, As_min, As_max)

## Constraints

This module:
- Uses no external model adapters
- Does no postprocessing or verification
- Does not compare provided reinforcement
- Does not compute Mpr or capacity-design Ve
- Produces no reports or UI output
