# R9C–R15 Final Files — Revised Package

This package has been rebuilt from the R9C–R15 file set and corrected according to the latest audit notes.

## Fixes applied

- R13 verification contract mismatch fixed:
  - `VerificationCheck`
  - `STATUS_PASS`
  - `STATUS_FAIL`
  - `STATUS_UNKNOWN`
  - `STATUS_NOT_APPLICABLE`
  - `overall_status`
- `BeamProvidedReinforcement` updated to final R13 shape:
  - `top_left_As_cm2`
  - `bottom_mid_As_cm2`
  - `top_right_As_cm2`
  - `stirrup`
- `demand_processor.py` station-range stage behavior fixed for explicit length inputs.
- Boundary scan conflict around `FrameForce` in the demand processor test is handled as the `RawFrameForceRow` dataclass-name exception.
- Flexure benchmark fixtures no longer use iteration-count as a golden engineering criterion.
- R13/R15 tests aligned with the corrected final contracts.
- `__pycache__` and `*.pyc` files removed from the package.

## Local validation run in the package workspace

```text
python -m compileall tbdy_engine: PASS
python -m pytest tests -q: 195 passed
```

## Main acceptance claims after applying and rerunning in repo

```text
R9C_R15_PACKAGE = ACCEPTABLE_PENDING_REPO_GATE
COMPILE = PASS
TEST_GATE_EXPECTED = PASS
R13_FILE_SET = CONSISTENT
R15_BENCHMARK = ALIGNED_NO_ITERATION_GOLDEN
```

Re-run in the target repo after copying files:

```powershell
python -m compileall tbdy_engine
python -m pytest tests -q
```
