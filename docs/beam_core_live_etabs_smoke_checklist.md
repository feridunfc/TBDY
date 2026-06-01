# BeamCore Manual Live ETABS Smoke Checklist

## Purpose

Manual live ETABS smoke is only a validation smoke for one selected model. It is not production certification, not release approval, and not full code-compliance certification.

This checklist documents how a future operator should run the opt-in live smoke path after the static BeamCore integration chain has already passed.

## Preconditions

Before attempting a manual live ETABS smoke, confirm all items below:

- Windows machine with ETABS installed.
- Valid ETABS model path is available.
- Required environment variable: TBDY_RUN_LIVE_ETABS_SMOKE=1
- Optional environment variable: TBDY_LIVE_ETABS_MODEL_PATH=<path>
- Working branch: core-reset-beam-design-kernel
- Git working tree is clean before the manual smoke.
- P6 readiness gate has been accepted.
- R1 opt-in live ETABS smoke harness has been accepted.
- Normal local and CI tests remain ETABS-free.

## Manual command placeholder

Default local/CI command remains safe because the manual test is skipped unless explicitly opted in:

python -m pytest tests/test_beam_etabs_live_smoke_harness.py -q

Future dedicated manual live test command:

python -m pytest tests/test_beam_etabs_live_smoke_harness.py::test_manual_live_etabs_smoke_is_opt_in -q

## Expected outputs

- engine_report.json
- engine_report.xlsx
- BeamCoreResult status
- beam_shear_capacity_design_ve_le_vr
- beam_shear_capacity_design_ve_le_085_vmax

## Failure reporting

Record ETABS version, model path, branch, commit hash, command executed, exception or failure message, and whether failure happened before payload extraction, during adapter mapping, during BeamCore evaluation, or during artifact generation.

## Claim boundaries

Allowed after a successful manual smoke on one selected model:

LIVE_ETABS_SMOKE = MANUALLY_OBSERVED_FOR_SELECTED_MODEL

Forbidden even after one successful manual smoke:

ETABS_VALIDATED = TRUE
PRODUCTION_READY = TRUE
RELEASE_READY = TRUE
FULL_CODE_COMPLIANCE_CERTIFIED = TRUE

Also forbidden unless separately proven in a later sprint:

ETABS_BRIDGE = PROVEN
LIVE_ETABS_SMOKE = TRUE

## Rollback / no-merge rule

Manual live smoke success alone does not permit merge to main.
Manual live smoke success alone does not permit production release.
Manual live smoke failure must not be hidden by editing BeamCore calculators, report writers, adapters, or artifact writers in the same sprint.

## Normal test safety

Default tests must not require ETABS installed, Windows COM, comtypes, SapModel, live ETABS table-reader calls, live ETABS tables, or ETABS model files.


## R2 manual payload smoke gate

R2 adds a manual payload-path smoke gate. It remains skipped by default.

Required explicit flag:

```powershell
$env:TBDY_RUN_LIVE_ETABS_SMOKE = "1"
```

Required manual payload path:

```powershell
$env:TBDY_LIVE_ETABS_PAYLOAD_PATH = "<path-to-selected-live-export-payload.json>"
```

Manual selected-payload command:

```powershell
python -m pytest tests/test_beam_etabs_live_smoke_harness.py::test_manual_live_etabs_smoke_is_opt_in -q
```

Allowed result categories:

- PASS for selected payload/model
- SKIP when the explicit payload path is absent or unavailable
- FAIL with recorded failure stage

Allowed claim after a passing selected-payload run only:

```text
LIVE_ETABS_SMOKE = MANUALLY_OBSERVED_FOR_SELECTED_MODEL
```

Forbidden claims always remain:

```text
ETABS_VALIDATED = TRUE
ETABS_BRIDGE = PROVEN_FOR_ALL_MODELS
PRODUCTION_READY = TRUE
RELEASE_READY = TRUE
FULL_CODE_COMPLIANCE_CERTIFIED = TRUE
```

## R3 selected-payload manual smoke

R3 uses an operator-provided selected payload JSON. It remains opt-in and is skipped unless both environment inputs are present.

Required explicit flag:

```powershell
$env:TBDY_RUN_LIVE_ETABS_SMOKE = "1"
```

Required selected payload path:

```powershell
$env:TBDY_LIVE_ETABS_PAYLOAD_PATH = "<path-to-selected-payload.json>"
```

Manual selected-payload command:

```powershell
python -m pytest tests/test_beam_etabs_live_smoke_harness.py::test_manual_live_etabs_smoke_is_opt_in -q
```

If the selected-payload run passes, record the result using:

```text
docs/templates/live_etabs_smoke_result_template.md
```

Allowed claim after a passing selected-payload run only:

```text
LIVE_ETABS_SMOKE = MANUALLY_OBSERVED_FOR_SELECTED_MODEL
```

Allowed claim if no selected-payload run is performed:

```text
LIVE_ETABS_SMOKE = NOT_RUN_ENVIRONMENT_UNAVAILABLE
```

Forbidden claims remain:

```text
ETABS_VALIDATED = TRUE
ETABS_BRIDGE = PROVEN_FOR_ALL_MODELS
PRODUCTION_READY = TRUE
RELEASE_READY = TRUE
FULL_CODE_COMPLIANCE_CERTIFIED = TRUE
```
