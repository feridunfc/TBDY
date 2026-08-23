# VS-4A — Cast-in-Place RC Structural-System Baseline Policy

## Scope

VS-4A is the bounded pre-analysis structural-system policy slice for cast-in-place reinforced-concrete A-series systems in TBDY 2018 Table 4.1 (A11–A33). It does not implement the post-analysis MDEV/Mo calculations of §§4.3.2.4, 4.3.4.5, 4.3.4.6 or 4.3.4.7; those remain a later VS-4B concern.

Frozen base: `f774726513a81edaadb2a5d897539575538e0cd0`

Branch: `sprint/vs-4a-rc-system-baseline-policy`

## Ownership and composition

`tbdy_engine/regulatory/structural_system.py` owns reviewed input contracts, Table 4.1 source-bound derivations, shared pre-eligibility regulatory quantities, formal check projections, and the immutable `VS4A_REGISTRY`.

`tbdy_engine/regulatory/vs4a_program.py` is the single composition path. `structural_system.py` must not expose `compile_vs4a_program` or a second orchestration path.

The F0 compiler and engine remain the only compiler/execution path. VS-4A does not create a parallel engine, formula DSL, reporter authority, or CheckResult aggregation layer.

## Shared regulatory-quantity DAG

The pre-analysis decision graph is:

```text
reviewed row / DTS / BYS / A16 context
        |
        +--> RC_TABLE_4_1_BYS_ELIGIBILITY_STATE
        +--> RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY_STATE
        +--> RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY_STATE
        +--> RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY_STATE
                         |
                         v
             RC_PREANALYSIS_SYSTEM_ELIGIBILITY
                         |
                         v
             RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY
                         |
                         v
               RC_ANALYSIS_BASIS_COMPATIBILITY
```

The four formal eligibility CheckResults consume those same shared eligibility quantities. They are projections only. They do not recalculate BYS, DTS, A31 or A16 engineering rules, and `RC_PREANALYSIS_SYSTEM_ELIGIBILITY` never aggregates CheckResults.

## Lifecycle semantics

`RC_PREANALYSIS_SYSTEM_ELIGIBILITY` resolves applicable source-bound prerequisites to `ELIGIBLE`, `INELIGIBLE`, or `BLOCKED`; non-applicable subchecks remain `NOT_APPLICABLE` at their own quantity.

Directional baseline resolution is:

- `INELIGIBLE` → baseline `INVALID`.
- `BLOCKED` → baseline `UNRESOLVED`.
- `ELIGIBLE` + post-analysis qualification required → baseline `PROVISIONAL`.
- `ELIGIBLE` + no pending post-analysis qualification → baseline `RESOLVED`.

Analysis-basis compatibility is:

- pre-eligibility `INELIGIBLE` → `AnalysisBasisStatus.INVALID`;
- pre-eligibility `BLOCKED` → `AnalysisBasisStatus.UNRESOLVED`;
- resolved baseline + exact reviewed row/R/D assumption → `MATCH`;
- resolved baseline + mismatch → `REANALYSIS_REQUIRED`;
- provisional/unresolved baseline → `UNRESOLVED`.

Therefore a numerically matching analysis assumption cannot override an ineligible or unresolved system declaration.

## Reviewed evidence contracts

Contracts named `Reviewed` fail closed on missing review/provenance references. In particular:

- `ReviewedDirectionalRcSystemDeclaration` requires non-empty declaration review and provenance refs;
- `ReviewedSeismicClassificationContext` requires non-empty DTS/BYS review and provenance refs;
- `ReviewedOrthogonalRcSystemDeclaration` requires non-empty orthogonal review and provenance refs;
- `A16SpecialContext` requires non-empty roof-connection review refs and provenance refs;
- analysis assumptions require non-empty analysis evidence refs.

`UNREVIEWED` A16 roof-connection state is not treated as a failed physical condition. It produces `BLOCKED`, then an unresolved baseline and `AnalysisBasisStatus.UNRESOLVED`.

## F0.9 authority

`tbdy_engine/regulatory/sources/tbdy2018.py` binds exact TBDY 2018 anchors to normalized claims and approved review records. Table 4.1 rows use separate row claims/anchors. Every executable VS-4A derivation/check has an approved implementation binding and exact implementation fingerprint for `tbdy_engine.regulatory.structural_system`.

Changing the evaluator module without updating the reviewed fingerprint must fail the F0.9 compiler gate.

## Deferred work

VS-4A does not compute MDEV/Mo, wall-distribution ratios, §4.3.4.5/6/7 post-analysis fallback results, or downstream reanalysis execution. It only states when the baseline is provisional and therefore cannot be treated as a final compatible analysis basis.
