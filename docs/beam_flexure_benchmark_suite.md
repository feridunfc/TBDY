# Beam Flexure Benchmark Suite

## Purpose

Golden fixture tests for the Md→As flexure kernel.
Each fixture locks the expected numerical result within tight ranges.
Any kernel change that alters these ranges must be intentional and reviewed.

## Fixtures

| Fixture | Description | Md (kNm) | Expected As (cm²) |
|---------|-------------|----------|-------------------|
| case_01 | Typical beam | 400 | 17.0–19.0 |
| case_02 | High moment | 800 | 35.0–40.0 |
| case_03 | Edge – small | 50 | 2.0–3.0 |

## Test Coverage

- Status validation
- Mu_check >= Md
- As_required_cm2 range
- a_mm, c_mm ranges
- neutral_axis_ratio range
- lever_arm_z_mm range
- rho_required range
- iterations range
- Determinism (50 runs identical)
- Evidence completeness

## Adding New Fixtures

1. Create `tests/fixtures/beam_flexure_md_to_as_case_NN.json`
2. Follow the schema: `case_id`, `description`, `input`, `expected`
3. Add test function in `test_beam_flexure_benchmark_suite.py`
4. Run kernel once to get actual values, then tighten ranges

## Gate

```bash
python -m pytest tests/test_beam_flexure_benchmark_suite.py -q

---
