# Beam Flexure Limits Engine

## Scope

Pure reinforcement ratio limit kernel.
Given As_required from flexure design, determines whether:
- Moment reinforcement governs (OK)
- Minimum reinforcement governs (MIN_REINFORCEMENT_GOVERNS)
- Section is over-reinforced (OVER_REINFORCED)

## Unit Standard

| Quantity | Unit |
|----------|------|
| Length | mm |
| Stress | MPa |
| Area | cm² |

## Formulas
rho_required = As_required / (bw * d)
rho_min = max(0.8 * fctd / fyd, 0.001)
As_min = rho_min * bw * d
As_max = rho_max * bw * d


## Output Status

| Status | Meaning | As_design_required |
|--------|---------|-------------------|
| OK | rho_min <= rho_required <= rho_max | As_required |
| MIN_REINFORCEMENT_GOVERNS | rho_required < rho_min | As_min |
| OVER_REINFORCED | rho_required > rho_max | As_required |
| INVALID_INPUT | Invalid geometry/material | — |

## Boundary Rules

Equality at limits:
- rho_required == rho_min → OK
- rho_required == rho_max → OK

## Constraints

This kernel:
- Uses no external model adapters
- Does no postprocessing or verification
- Does not compare provided reinforcement
- Produces no reports or UI output

## Claim Limitations

- FLEXURE_RHO_LIMITS_ENGINE = PROVEN
- FULL_TBDY_FLEXURE_LIMITS_CERTIFIED = FALSE
- Formula policy: rho_min = max(0.8*fctd/fyd, 0.001)
- Future code-article benchmarks may refine this policy
