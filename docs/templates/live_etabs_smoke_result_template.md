# Manual Live ETABS Payload Smoke Result Template

## Run identity

- branch: core-reset-beam-design-kernel
- commit: <commit-hash>
- command: python -m pytest tests/test_beam_etabs_live_smoke_harness.py::test_manual_live_etabs_smoke_is_opt_in -q
- payload filename: <filename-only>
- smoke status: PASS / SKIP / FAIL

## Result details

- BeamCoreResult status: <OK / INVALID_INPUT / FAIL / not-run>
- check count: <number>
- artifact json: engine_report.json
- artifact xlsx: engine_report.xlsx
- failure stage: payload_load / etabs_payload_adapter / canonical_bridge / beam_core / artifact_generation / none

## Capacity-design checks

- beam_shear_capacity_design_ve_le_vr
- beam_shear_capacity_design_ve_le_085_vmax

## Allowed claim after passing selected-payload run only

LIVE_ETABS_SMOKE = MANUALLY_OBSERVED_FOR_SELECTED_MODEL

## Allowed claim when selected-payload run is not performed

LIVE_ETABS_SMOKE = NOT_RUN_ENVIRONMENT_UNAVAILABLE

## Forbidden claims

ETABS_VALIDATED = TRUE
ETABS_BRIDGE = PROVEN_FOR_ALL_MODELS
PRODUCTION_READY = TRUE
RELEASE_READY = TRUE
FULL_CODE_COMPLIANCE_CERTIFIED = TRUE

## Sanitization rule

Do not commit full machine-specific payload paths, proprietary model data, or sensitive project identifiers.
Only record the selected payload filename.
