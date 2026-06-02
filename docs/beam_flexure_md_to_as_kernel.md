# Beam Flexure Md→As Kernel

## Scope

Single-reinforced rectangular concrete section.
Given Md, compute As_required via deterministic binary search.

## Unit Standard

| Quantity | Unit |
|----------|------|
| Length | mm |
| Force | N |
| Moment (input) | kNm |
| Moment (calculation) | Nmm |
| Stress | MPa (N/mm²) |
| Area | mm² |

## Algorithm

### Fundamental Equations
a = As * fyd / (alpha * fcd * bw)
z = d - a / 2
Mu = As * fyd * z
c = a / beta


### Binary Search

1. Validate inputs (Md >= 0, bw > 0, d > 0, fcd > 0, fyd > 0, alpha > 0, beta > 0)
2. Md = 0 → As = 0, status NO_TENSION_REINFORCEMENT_REQUIRED
3. Initial upper bound: As_high = Md / (fyd * 0.9d) * 2.0
4. Double As_high until Mu(As_high) >= Md
5. Binary search: 0.1% tolerance, max 200 iterations
6. Result on safe side: Mu_check >= Md

### Coefficients

| Parameter | Value | Source |
|-----------|-------|--------|
| alpha | 0.85 | TS500 equivalent compression block |
| beta | 0.85 | TS500 (c = a / 0.85) |

## Output Status

| Status | Meaning |
|--------|---------|
| OK | Success, Mu_check >= Md |
| INVALID_INPUT | Negative/zero geometry or material |
| NO_TENSION_REINFORCEMENT_REQUIRED | Md <= 0 |
| NO_CONVERGENCE | Upper bound not found within 100 doublings |

## Constraints

This kernel:
- Uses no external model adapters
- Does no postprocessing or verification
- Does not compute rho_min/rho_max
- Does not compute Mpr or capacity-design Ve
- Produces no reports or UI output
