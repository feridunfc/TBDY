# FND-COL-2 Downstream Eligibility Boundary

Status: architecture boundary for supervisor review

Scope: FND-COL-2 only. This document records the semantic boundary before any downstream P8A integration change.

## 1. Three different authorities

FND-COL-2 must keep the following three concepts separate.

### Analysis-basis compatibility

`AnalysisBasisStatus.MATCH` means only that the analysis basis required by the consuming F0 rule instance is compatible with the analysis basis represented by the bound evidence for that scope.

It does **not** mean that all column design-demand prerequisites are complete. In particular, a component may legitimately have:

```text
status = BLOCKED
second_order_treatment = MOMENT_MAGNIFICATION_REQUIRED
analysis_basis_status = MATCH
```

That state means the analysis basis itself is compatible while the current FND-COL-2 column design-demand path is not ready for downstream reinforcement promotion because the required second-order/moment-magnification treatment is not closed.

### Full column design-demand readiness

`ColumnDesignDemandReadiness` is a stronger, component-scoped result. A downstream consumer may regard the current FND-COL-2 demand state as ready only when the canonical readiness result itself is `READY` and all of its required closures have been resolved.

A component-level readiness result is still not a per-combination P8A authorization.

### P8A reinforcement-promotion eligibility

P8A eligibility is a separate downstream authority. The existing P8A contract requires eligibility at the combination grain. FND-COL-2 currently emits a component-scoped regulatory artifact and therefore cannot, by itself, prove the per-combination analysis-basis eligibility required by P8A.

Consequently:

- component-level `AnalysisBasisStatus.MATCH` MUST NOT be converted directly into P8A `AnalysisBasisEligibilityEvidence`;
- component-level FND-COL-2 `READY` MUST NOT be treated as sufficient per-combination P8A eligibility without an additional typed projection backed by exact combination-grain evidence;
- FND-COL-2 does **not** close `LIVE_BLOCKED_ANALYSIS_BASIS_EVIDENCE_REQUIRED`;
- this branch makes no `ETABS_REQUIRED_REBAR` or `ENGINE_SELECTED_REBAR` authority change.

## 2. Smallest later cutover seam

The minimum downstream seam for a later, separately approved P8A cutover is a typed projection at component x combination grain. Conceptually:

```text
ColumnDesignDemandReadiness (COMPONENT)
        |
        | requires component readiness == READY
        v
ColumnComboEligibilityProjection (COMPONENT x COMBO)
        |
        | additionally requires exact combo-grain analysis-basis evidence
        v
P8A AnalysisBasisEligibilityEvidence
```

A future `ColumnComboEligibilityProjection` should carry, at minimum:

```text
component_id
combo_ref
component_readiness_ref
combo_analysis_basis_evidence_ref
eligibility_state
provenance_refs
authority
```

Its rules are intentionally strict:

1. it may reference component readiness, but it may not infer combination eligibility from component `MATCH`;
2. it must bind exact combination-grain analysis-basis evidence;
3. it must remain non-authorizing unless both the component readiness and the combination-specific prerequisite are resolved;
4. only a later supervisor-approved P8A cutover may adapt this projection into `AnalysisBasisEligibilityEvidence`.

## 3. Current branch non-goals

FND-COL-2 stops before that downstream projection. This branch does not modify P8A production code, does not promote reinforcement, does not create `ETABS_REQUIRED_REBAR`, and does not create `ENGINE_SELECTED_REBAR`.

The purpose of FND-COL-2 is limited to source-bound column design-demand readiness and its F0.9 regulatory authority package.
