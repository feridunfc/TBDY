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


## R6 live COM provider skeleton

COM provider is gated and manual-only. Normal tests do not require ETABS, Windows COM, or a machine-specific model path.

Required manual environment:

```powershell
$env:TBDY_RUN_LIVE_ETABS_SMOKE="1"
$env:TBDY_LIVE_ETABS_COM_PROVIDER="1"
$env:TBDY_LIVE_ETABS_MODEL_PATH="<path-to-selected-model.edb>"
$env:TBDY_LIVE_ETABS_BEAM_NAME="<selected-beam>"
```

Manual targeted COM provider command:

```powershell
python -m pytest tests/test_beam_etabs_live_com_provider.py::test_manual_live_etabs_com_provider_is_opt_in -q
```

Prepared-not-run claim:

```text
LIVE_ETABS_COM_PROVIDER = PREPARED_NOT_RUN
```

Skeleton-only claim if selected beam extraction is not implemented:

```text
LIVE_ETABS_COM_PROVIDER = SKELETON_ONLY
```

Manual pass claim for one selected model only:

```text
LIVE_ETABS_COM_SMOKE = MANUALLY_OBSERVED_FOR_SELECTED_MODEL
```

Manual failure claim:

```text
LIVE_ETABS_COM_SMOKE = FAILED_WITH_STAGE_RECORDED
```

Forbidden claims remain:

```text
ETABS_VALIDATED = TRUE
ETABS_BRIDGE = PROVEN_FOR_ALL_MODELS
PRODUCTION_READY = TRUE
RELEASE_READY = TRUE
FULL_CODE_COMPLIANCE_CERTIFIED = TRUE
```

## R7A single beam FrameForce bridge

R7A is an opt-in live ETABS bridge proof for exactly one selected frame object. It must use real `SapModel.Results.FrameForce` rows for live acceptance. Default tests remain ETABS-free.

Required manual environment:

```powershell
$env:TBDY_RUN_LIVE_ETABS_SMOKE="1"
$env:TBDY_LIVE_ETABS_COM_PROVIDER="1"
$env:TBDY_LIVE_ETABS_USE_OPEN_MODEL="1"
$env:TBDY_LIVE_ETABS_BEAM_NAME="B1"
$env:TBDY_LIVE_ETABS_COMBOS="G+Q,EX"
$env:TBDY_LIVE_ETABS_FORCE_UNIT="kN"
$env:TBDY_LIVE_ETABS_MOMENT_UNIT="kNm"
$env:TBDY_LIVE_ETABS_LENGTH_UNIT="mm"
```

Manual command:

```powershell
python -m pytest tests/test_beam_etabs_single_beam_frameforce_runner.py::test_manual_live_etabs_single_beam_frameforce_is_opt_in -q
```

If manual run is skipped:

```text
CORE_RESET_SPRINT_R7A = NOT_ACCEPTED_AS_LIVE
SINGLE_BEAM_FRAMEFORCE_RUNNER = IMPLEMENTED_NOT_RUN
```

If manual run passes and report confirms actions source:

```text
CORE_RESET_SPRINT_R7A = PROVISIONALLY_ACCEPTABLE_PENDING_REVIEW
LIVE_ETABS_CONNECTION = OBSERVED
LIVE_ETABS_FRAMEFORCE_EXTRACTION = OBSERVED
ETABS_TO_BEAMCORE_BRIDGE = OBSERVED_FOR_SELECTED_MODEL
SINGLE_BEAM_FRAMEFORCE_RUNNER = MANUALLY_RUN
ACTIONS_SOURCE = ETABS_RESULTS
```

## R7B live ETABS story beam batch FrameForce bridge

R7B extends R7A from one selected frame object to a selected-story batch. It discovers ETABS frame objects on the exact selected story, extracts real `SapModel.Results.FrameForce` rows for at least two selected combos, applies the documented envelope rules per beam, and runs the existing BeamCore path for at least three accepted beams.

Default tests remain ETABS-free.

Manual command:

```powershell
python -m pytest tests/test_beam_etabs_story_beam_batch_runner.py::test_manual_live_etabs_story_beam_batch_is_opt_in -q
```

If manual run is skipped:

```text
CORE_RESET_SPRINT_R7B = NOT_ACCEPTED_AS_LIVE
STORY_BEAM_BATCH_RUNNER = IMPLEMENTED_NOT_RUN
```

If manual run passes and report confirms actions_source = etabs_results for at least 3 beams and at least 2 combos:

```text
CORE_RESET_SPRINT_R7B = PROVISIONALLY_ACCEPTABLE_PENDING_REVIEW
LIVE_ETABS_STORY_BATCH_CONNECTION = OBSERVED
LIVE_ETABS_STORY_BATCH_FRAMEFORCE_EXTRACTION = OBSERVED
ETABS_TO_BEAMCORE_BATCH_BRIDGE = OBSERVED_FOR_SELECTED_STORY
STORY_BEAM_BATCH_RUNNER = MANUALLY_RUN
ACTIONS_SOURCE = ETABS_RESULTS
MIN_BEAMS_PROCESSED = 3
MIN_COMBOS_USED = 2
```

Forbidden claims remain: ETABS validation, all-model bridge proof, design-engine validation, production readiness, release readiness, and code-compliance proof.
