# PRODUCT-SPINE-COL-1 — A1-P1 hardening report

## Scope identity

- Repository: `feridunfc/TBDY`
- Frozen base: `74d5b6083afed75e44b832336c31755aee482daa`
- Branch: `sprint/col-runtime-1-production-runtime`
- Sprint: `PRODUCT-SPINE-COL-1`
- Supervisor patch: `A1-P1`
- Product claim: first bounded project/application column spine only; not full project runtime, not full column closure, not full TBDY/TS500 compliance.

## Approved write boundary

1. `.github/workflows/product_spine_col_1_validation.yml`
2. `tbdy_engine/application/__init__.py`
3. `tbdy_engine/application/contracts.py`
4. `tbdy_engine/application/project_execution.py`
5. `tbdy_engine/application/column_execution.py`
6. `tests/application/test_product_spine_col_1.py`
7. `docs/audit/product_spine_col_1/report.md`
8. `docs/audit/product_spine_col_1/handoff.json`

No pre-existing engineering authority file is modified.

## A1-P1 contract correction

Production request contracts now contain application intent only:

```text
ProjectExecutionRequest
  project_id
  report_id
  title
  column: ColumnExecutionRequest

ColumnExecutionRequest
  component_id
```

Production request DTOs do **not** contain:

- READY fixture inputs;
- fixture model/epoch identities;
- `RegulatoryCompileInputs`;
- factual design-result populations;
- combo reconciliation;
- combo analysis-basis bindings;
- PMM material-context bindings;
- reviewed policy / PMM / candidate-adequacy artifacts;
- `EtabsVerifiedSession`.

Runtime capability is a bounded execution dependency:

```python
execute_project(request, *, verified_session=verified_session)
```

No raw ETABS model object is exposed by the application API.

## LIVE FND-COL-2 lineage decision

A bounded current-main search found **no accepted existing production seam** that proves:

```text
TrustedLiveAcquisitionContext
→ exact existing factual providers/builders
→ RegulatoryCompileInputs for FND-COL-2
```

`tbdy_engine/regulatory/fnd_col_2_program.py` consumes already-built `RegulatoryCompileInputs`; it does not build them from a trusted live acquisition generation. The current `TrustedLiveAcquisitionContext` owns factual acquisition helpers, but no current-main builder joins that context into the complete FND-COL-2 compile-input contract.

A1-P1 therefore does not invent a provider, identity, or authority. Public LIVE execution stops **before** FND-COL-2X:

```text
TrustedLiveAcquisitionContext
→ ColumnDomainArtifact
   status = FACTUAL_ACQUISITION_BLOCKED
   blocker = LIVE_FND2_INPUT_LINEAGE_NOT_QUALIFIED
→ no FND-COL-2 execution
→ no engineering readiness claim
→ no P8A promotion
→ no FCR/report claim for an unexecuted regulatory instance
```

This blocker is application/integration state, not regulatory FAIL and not a fabricated `READY`, `REANALYSIS_REQUIRED`, `BLOCKED`, or `UNRESOLVED` engineering-readiness result.

## READY fixture proof remains test-only

The READY proof is retained through non-public application composition seams. It is not exported from `tbdy_engine.application` and no production request DTO can carry its authoritative artifacts.

Test-only proof:

```text
test fixture builders
→ private qualified FND-COL-2 composition seam
→ execute_source_bound_fnd_col_2_with_artifact(...)
→ exact ComponentReadinessBinding
→ FND-COL-1
→ reviewed selection policy
→ current PMM policy authorization
→ current candidate-adequacy authorization
→ P8A-B
→ FND-COL-4 canonical selection
→ ENGINE_SELECTED_REBAR
```

The same-object invariant is preserved:

```text
ComponentReadinessBinding.readiness
IS
FndCol2ExecutionArtifact.readiness
```

No serialization/reconstruction occurs between those objects.

## LIVE + READY B2 guard

A private qualified-LIVE proof seam exists only to test the future boundary after FND-COL-2 input lineage becomes legal. When such a qualified FND-COL-2 execution returns `READY`, A1-P1 still stops before P8A design-result promotion:

```text
status = APPLICATION_BLOCKED
blocker = LIVE_DESIGN_RESULT_LINEAGE_NOT_QUALIFIED
```

No live `ENGINE_SELECTED_REBAR` is emitted. This guard remains until B2 design-result lineage is implemented and accepted.

## FCR / BuildingReportModel reuse

A1-P1 retains bounded reuse only after canonical FND-COL-2 artifacts actually exist. The helper:

- passes the existing compiled program + store snapshot to `ProjectCoverageReconciler.reconcile(...)`;
- lets FCR use `AssessmentEngine.reconcile(...)` internally;
- binds the existing canonical readiness quantity to an existing `SliceReportContribution`;
- constructs `BuildingReportModel` without new threshold, governing selection, CheckResult, rebar translation, or product compliance verdict logic.

The public LIVE lineage-blocked path does not fabricate FCR/report closure for an FND-COL-2 instance that was never executed.

# CURRENT SYMBOL TRACE

The table distinguishes current production symbols from A1-P1 callers. `NONE FOUND` means no pre-A1 production caller/constructor was found in the exact frozen source tree; tests do not convert that into production reachability.

| Capability | CURRENT FILE | CURRENT SYMBOL | PRE-A1 CALLER | A1 CALLER | OUTPUT TYPE | A1 CONSUMER |
|---|---|---|---|---|---|---|
| FND-COL-1 | `tbdy_engine/regulatory/column_longitudinal_rebar.py` | `evaluate_column_longitudinal_layouts(...)` | **NONE FOUND in production**; existing direct callers were tests | private `_execute_column_domain_with_ready_fixture_for_test(...)` only | `ColumnLongitudinalLayoutAuthorityResult` | existing `compose_canonical_column_longitudinal_selection(...)` |
| FND-COL-2X typed artifact | `tbdy_engine/regulatory/fnd_col_2_program.py` | `execute_source_bound_fnd_col_2_with_artifact(...)` | production wrapper `execute_source_bound_fnd_col_2(...)` consumes `.snapshot`; typed-artifact direct callers otherwise tests | **PUBLIC LIVE CALLER: NONE**; `execute_column_domain(...)` stops before FND-COL-2X. **TEST-ONLY QUALIFIED CALLERS:** `_execute_column_domain_with_qualified_live_fnd2_for_test(...)` and `_execute_column_domain_with_ready_fixture_for_test(...)`, both through common private composition seam `_execute_fnd2(...)` | `FndCol2ExecutionArtifact` | `_execute_fnd2(...)` constructs and returns the typed execution/readiness path for those test-only callers |
| Component readiness binding | `tbdy_engine/design/columns/column_combo_eligibility_projection.py` | `ComponentReadinessBinding` | **no production constructor found**; existing P8A-B/selection contracts consume the type and tests construct it | **PUBLIC LIVE CALLER: NONE**; public execution stops before FND-COL-2X. For test-only qualified composition, `_execute_fnd2(...)` constructs `ComponentReadinessBinding(...)` inline when typed readiness exists | `ComponentReadinessBinding` | existing P8A-B composition through the test-only READY path |
| P8A combo reconciliation | `tbdy_engine/design/columns/column_concrete_design_evidence_authority.py` | `reconcile_concrete_design_combos(...)` | **NONE FOUND in production**; current direct callers are tests | **no public LIVE A1 caller**; test fixture supplies an existing `ConcreteDesignComboReconciliation` to the private test-only seam | `ConcreteDesignComboReconciliation` | existing combo-eligibility projection inside P8A-B |
| P8A factual design-result capture | `tbdy_engine/providers/etabs_concrete_column_design_result_provider.py` + `tbdy_engine/integration/live_etabs_acquisition_context.py` | `capture_concrete_column_design_results(...)`; `TrustedLiveAcquisitionContext.capture_column_design_results(...)` | trusted acquisition context is an existing production caller of the factual provider | **not called by public A1-P1 downstream promotion**; B2 lineage guard blocks it from becoming promoted application truth | `FactualColumnDesignResultPopulation` | existing `promote_etabs_required_rebar(...)` inside P8A-B when legally supplied |
| Reviewed selection policy | `tbdy_engine/design/columns/column_longitudinal_selection_policy_factory.py` | `build_reviewed_column_longitudinal_selection_policy_input()` | **NONE FOUND in production** before A1; tests only | private READY test-only seam | `ColumnLongitudinalSelectionPolicyInput` | existing P8A-B composition |
| PMM numerical-policy authorization | `tbdy_engine/regulatory/column_pmm_authority.py` | `authorize_pmm_numerical_policy(...)` | **NONE FOUND in production** before A1; tests only | private READY test-only seam | `ValidatedPmmNumericalPolicy` | existing FND-COL-4 selector through P8A-B |
| Candidate-adequacy authorization | `tbdy_engine/regulatory/column_candidate_adequacy_authority.py` | `authorize_candidate_adequacy_policy(...)` | **NONE FOUND in production** before A1; tests only | private READY test-only seam | `ValidatedCandidateAdequacyPolicy` | existing FND-COL-4 selector through P8A-B |
| PMM material context | `tbdy_engine/design/columns/column_pmm_assessment.py` | `ColumnPmmMaterialContextBinding` | **no production constructor/builder found**; tests construct it | **no public LIVE A1 caller**; private READY fixture proof consumes test-built current type | `ColumnPmmMaterialContextBinding` | existing PMM assessment/selector |
| P8A-B production composition | `tbdy_engine/design/columns/column_longitudinal_production_composition.py` | `compose_canonical_column_longitudinal_selection(...)` | **NONE FOUND in production** before A1; direct callers were tests | private READY test-only seam | `ColumnLongitudinalCanonicalSelectionResult` | A1 `ColumnDomainArtifact.longitudinal_selection` |
| FND-COL-4 canonical selection | `tbdy_engine/design/columns/column_longitudinal_selection.py` | `select_canonical_column_longitudinal_rebar(...)` | existing production caller: `compose_canonical_column_longitudinal_selection(...)` | unchanged indirect call through existing P8A-B | `ColumnLongitudinalCanonicalSelectionResult` / existing `CanonicalEngineSelectedRebar` | A1 `selected_rebar` property only projects existing result |
| Assessment/FCR | `tbdy_engine/coverage/project_reconciliation.py` + `tbdy_engine/regulatory/kernel.py` | `ProjectCoverageReconciler.reconcile(...)`; `AssessmentEngine.reconcile(...)` | FCR had **no production caller found** before A1; `AssessmentEngine.reconcile(...)` already has several bounded production callers in existing regulatory/integration slices | `_build_closure_and_report(...)` only after canonical FND-COL-2 artifacts exist | `ProjectCoverageReconciliation` + `StructuralAssessment` | `BuildingReportModel` construction |
| Building report truth | `tbdy_engine/product_reports/unified_building_report.py` | `BuildingReportModel(...)` | **no production constructor found** before A1; production exporters/projections consume a model and tests construct it | `_build_closure_and_report(...)` only after canonical FND-COL-2/FCR artifacts exist | `BuildingReportModel` | returned in bounded `ProjectExecutionArtifact` |

## Required seam absences explicitly preserved

A1-P1 does **not** fill these gaps with new authority:

1. No current production builder from `TrustedLiveAcquisitionContext` to complete FND-COL-2 `RegulatoryCompileInputs` was found.
2. No accepted project-wide `DesignResultIdentity` / design-state lineage seam exists yet.
3. No current production constructor for `ColumnPmmMaterialContextBinding` was found.
4. P8A combo reconciliation is a current authority but no pre-A1 production caller was found.
5. Several reviewed FND-COL-1/FND-COL-4 policy factories/authorizers are current code but were not pre-A1 production-root reachable.

These are migration facts, not permission to invent A1 substitutes.

## Forbidden-edge proof

Application static tests parse every `tbdy_engine/application/*.py` AST and reject direct use/import of:

```text
SapModel
DatabaseTables
DesignConcrete
Results.Setup
FrameObj
AreaObj
PropFrame
RunAnalysis
StartDesign
SetPresentUnits
SetModifiers
tools.*
```

The production application layer uses only the typed verified-session/acquisition-context boundary; it never dereferences raw ETABS API surfaces.

No ETABS analysis/design/save/property/combo/unit mutation is introduced.

## Local validation — A1-P1

Completed locally against the exact frozen source snapshot plus the bounded A1-P1 write set:

- `tests/application/test_product_spine_col_1.py`: **11 passed**.
- Required combined A1-P1 regression set — application + FND-COL-2X + selection-policy factory + P8A-B + FND-COL-4 PMM + FND-COL-1 + FCR + unified BuildingReportModel: **99 passed in 8.59s**.
- `python -m compileall -q tbdy_engine tests`: **PASS**.
- application import/signature check: **PASS**; `execute_project(request, *, verified_session=...)` confirmed.
- AST forbidden-edge proof: included in the 11 focused tests and **PASS**.

Full `python -m pytest -q tests/design/columns` was attempted. It did not complete within the local command execution budget; no failure signature was emitted before termination. Therefore **FULL_COLUMN_SUITE_PASS is NOT CLAIMED**.

## Candidate CI evidence

The validated code candidate head `7b01a2f787f91b4ff1feb632ad2723a6b163f2ac` completed `PRODUCT-SPINE-COL-1 Validation` in GitHub Actions run `33293139582` with overall workflow result **SUCCESS**. The focused A1-P1 suite reported **11 passed** and the required authority regression reported **88 passed**.

The repository-wide broad suites are not claimed as passing: both candidate and frozen base exited `2` with the same **9 inherited collection signatures**. The zero-new-failure delta reported **0 new** and **0 changed/missing inherited** signatures. Final repository hygiene reported **PASS**.

This evidence applies to the validated code candidate head above; later audit-only documentation commits do not retroactively become the validated code candidate.

## Non-claims

- no full `ColumnDomainRuntime` completion claim;
- no live FND-COL-2 readiness claim;
- no live design-result qualification claim;
- no `DesignResultIdentity` claim;
- no derived analysis-state implementation;
- no STAB/PR #164 adoption;
- no P8B/transverse reinforcement closure;
- no full mandatory-code closure;
- no project compliance PASS;
- no canonical or merge-ready self-declaration.
