# Beam ETABS Crosscheck

## Scope

Compares Beam Engine outputs against ETABS design output.
This layer is diagnostic only.
ETABS is not the source of truth for BeamDesignResult.

## Inputs

- BeamFlexureRegionDesignResult (engine)
- ShearReinforcementDesignResult (engine)
- ETABSDesignOutput (external)

## Outputs

- ETABSComparisonResult
- ETABSComparisonItem list

## Status Thresholds

| Status | Rule | Default |
|--------|------|---------|
| CLOSE | difference ≤ threshold | 5% |
| MODERATE | difference ≤ threshold | 20% |
| LARGE | difference > moderate | >20% |
| INCOMPLETE | missing data | — |

## Boundary Rule

ETABS comparison never mutates:
- BeamDesignResult
- BeamFlexureRegionDesignResult
- ShearReinforcementDesignResult
- BeamVerificationResult

ETABS disagreement does not mean engine failure.
