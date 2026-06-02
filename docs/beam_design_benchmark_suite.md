# Beam Design Benchmark Suite

## Scope

Golden fixture benchmark suite for beam design kernels,
verification layer, and ETABS crosscheck.

## Fixtures

| Fixture | Coverage |
|---------|----------|
| flexure_md_to_as_case_001 | Md→As kernel |
| flexure_limits_case_001 | rho_min/rho_max limits |
| region_flexure_case_001 | Three-region flexure mapping |
| plastic_moment_case_001 | As→Mpr |
| capacity_ve_case_001 | Mpr→Ve_capacity |
| shear_reinforcement_case_001 | V→stirrup spacing |
| verification_case_001 | Provided vs required verification |
| etabs_crosscheck_case_001 | Engine vs ETABS comparison |

## Rules

- Missing fixture must FAIL, not skip
- All tests must be deterministic (50 runs identical)
- No production code may change

## Expected Changed Files
