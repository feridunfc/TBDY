# Live ETABS Story Beam Batch Result Template

## Run identity

- branch:
- commit:
- selected story:
- selected combos:
- run status: PASS / FAIL / SKIP

## Required observations

- ETABS connection observed:
- SapModel access observed:
- selected story observed:
- beams discovered:
- beams processed:
- BeamCore checks executed:
- BeamCoreResult produced:
- ACTIONS_SOURCE = ETABS_RESULTS:

## Required artifacts

- story_beam_batch_summary.json:
- story_beam_batch_summary.md:

## Allowed claim after manual pass

CORE_RESET_SPRINT_R7B = PROVISIONALLY_ACCEPTABLE_PENDING_REVIEW
LIVE_ETABS_STORY_BATCH_CONNECTION = OBSERVED
LIVE_ETABS_STORY_BATCH_FRAMEFORCE_EXTRACTION = OBSERVED
ETABS_TO_BEAMCORE_BATCH_BRIDGE = OBSERVED_FOR_SELECTED_STORY
STORY_BEAM_BATCH_RUNNER = MANUALLY_RUN
ACTIONS_SOURCE = ETABS_RESULTS
MIN_BEAMS_PROCESSED = 3
MIN_COMBOS_USED = 2

## Forbidden claims

ETABS_VALIDATED = TRUE
DESIGN_ENGINE_VALIDATED = TRUE
ETABS_BRIDGE = PROVEN_FOR_ALL_MODELS
PRODUCTION_READY = TRUE
RELEASE_READY = TRUE
CODE_COMPLIANCE_PROVEN = TRUE
