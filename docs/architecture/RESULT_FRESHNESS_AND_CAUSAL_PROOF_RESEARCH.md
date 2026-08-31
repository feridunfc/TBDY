# R-LINEAGE-1 — Analysis / Design Result Freshness & Causal-Proof Research

## Status and frozen basis

```text
MODE = RESEARCH ONLY
BASE_GATE = PASS
FROZEN_BASE = 6273c19030ab6ecb7ad2637e3bfc74f88b1da086
BRANCH = research/r-lineage-1-result-freshness-causal-proof
PRODUCTION_CODE_CHANGES = 0
RunAnalysis = NOT_EXECUTED
StartDesign = NOT_EXECUTED
IDENTITY_ISSUER = NOT_IMPLEMENTED
ENGINEERING_CHECK_CHANGES = 0
```

This document is research for future B2/B5/B6. It is not an implementation specification with canonical authority and does not issue qualified lineage.

The governing research question is deliberately causal rather than merely correlational:

> What evidence can prove that an exact result population was produced by one exact controller-owned execution whose exact parent state is known?

The answer is not one ETABS field. The strongest defensible future proof is a bounded causal enclosure: exact pre-state, controller-owned execution attempt, execution/status evidence, no intervening state-changing action, and immediate exact-scope acquisition.

---

## 1. Permanent non-equivalences

The following are preserved without qualification:

```text
SourceModelIdentity != AnalysisStateIdentity
EvidenceEpoch != AnalysisStateIdentity
EvidenceEpoch != AnalysisResultIdentity
model_fingerprint != AnalysisStateIdentity
model_fingerprint != AnalysisResultIdentity
acquisition_context_ref != AnalysisResultIdentity
row hash != analysis generation
random UUID != execution proof

component identity != design result lineage
combo name != design result lineage
ETABS result row existence != qualified DesignResultIdentity
```

Additional research conclusion:

```text
RunAnalysis ret == 0 != result-generation proof
GetCaseStatus == Finished != result-generation proof
model locked == true != result-generation proof
result table nonempty != result-generation proof
StartDesign ret == 0 != design-result generation proof
GetResultsAvailable == true != design-result generation proof
```

Those facts become useful only inside a controller-owned causal chain.

---

## 2. Exact current-repository census at the frozen base

### 2.1 B1 analysis-lineage contracts

Current owner:

`tbdy_engine/integration/etabs_analysis_lineage.py`

`AnalysisStateIdentity` carries:

```text
identity_ref
source_model_ref
execution_state_ref
state_basis_refs
provenance_refs
contract
```

Its identity is derived from source model + execution state + state-basis references. Capture generation is intentionally not state identity.

`AnalysisResultIdentity` carries:

```text
identity_ref
source_model_ref
parent_analysis_state_ref
analysis_generation_ref
result_scope_refs
provenance_refs
contract
```

Its object existence is explicitly not self-authenticating. `analysis_generation_ref` is an identity input, not proof that a generation occurred.

`AnalysisLineageQualification` is factory-created and fail-closed. Positive qualification requires a verified execution proof coherent across:

```text
source_model_ref
execution_state_ref
analysis_state_ref
analysis_result_ref
analysis_generation_ref
```

B1 exposes no public positive issuer. Existing live/pre-existing results therefore remain unqualified.

### 2.2 Source model and factual acquisition provenance

Current owner:

`tbdy_engine/integration/live_etabs_acquisition_context.py`

`SourceModelIdentity` carries:

```text
source_model_ref
model_fingerprint
normalized_model_reference
semantics
model_fingerprint_semantics
```

The module explicitly defines both `SourceModelIdentity` and `model_fingerprint` as identities of the verified source-model reference, not physical bytes, current in-memory state, analysis state, or result generation.

`TrustedLiveAcquisitionContext` carries:

```text
verified_session
source_model_identity
evidence_epoch
acquisition_generation_ref
session_provenance_ref
acquisition_context_ref
```

`acquisition_generation_ref` is UUID-based. It proves one factual acquisition generation exists; it cannot prove an ETABS analysis/design execution.

### 2.3 EvidenceEpoch

Current owner:

`tbdy_engine/features/evidence_epoch.py`

Fields:

```text
epoch_id
model_fingerprint
origin
source_fingerprint
predecessor_epoch_ref
provenance_refs
```

`EvidenceEpoch` is an immutable factual capture generation. It is useful for same-capture joins and stale-acquisition rejection. It is not an analysis/design generation.

### 2.4 FeatureSnapshot

Current owner:

`tbdy_engine/features/snapshot.py`

Relevant provenance fields:

```text
component_type
component_id
identity
features
evidence_by_feature
diagnostics
```

A FeatureSnapshot is a factual/evidence projection. It does not carry causal analysis-generation proof.

### 2.5 Analysis-basis provenance

Current owner:

`tbdy_engine/analysis_basis/contracts.py`

`AnalysisSystemAssumption` carries:

```text
assumption_id
epoch_ref
structural_zone_ref
direction
observed_basis_ref
analysis_evidence_refs
provenance_refs
```

`AnalysisBasisCompatibility` carries:

```text
compatibility_id
epoch_ref
structural_zone_ref
direction
required_basis_ref
analysis_assumption_ref
status
diagnostic_refs
provenance_refs
```

`AnalysisBasisSnapshot` carries deterministic join provenance and is explicitly documented as never an authority. `MATCH` proves basis compatibility at its declared grain; it does not prove when or by which execution the numerical analysis results were produced.

### 2.6 Current column concrete-design factual result population

Current owners:

```text
tbdy_engine/features/column_design_rebar_evidence.py
tbdy_engine/providers/etabs_concrete_column_design_result_provider.py
tbdy_engine/etabs/oapi/concrete_design.py
```

`FactualColumnDesignResultRow` carries:

```text
source_row_id
component_id
unique_name
story
label
assigned_section
design_section
my_option
pmm_combo
location_mm
pmm_area_mm2
error_summary
warning_summary
model_fingerprint
evidence_epoch_id
source_refs
```

`FactualColumnDesignResultPopulation` carries:

```text
model_fingerprint
evidence_epoch_id
expected_component_ids
attempted_component_ids
captured_component_ids
reported_result_row_count
rows
source_refs
```

The provider validates the live-observed ETABS 23.2 `DesignConcrete.GetSummaryResultsColumn` 14-slot Python COM shape, exact row counts, requested FrameName, explicit source units and before/after unit provenance. These are strong factual ABI/population guarantees, but no field binds the rows to a particular `StartDesign` generation.

Important naming warning: the current `ColumnDesignResultIdentity` in `column_concrete_design_evidence.py` is a factual component/section/model/EvidenceEpoch binding helper. It is not the future causal product-level `DesignResultIdentity` contemplated by B2/B6.

### 2.7 Exact design-combo selection and definition evidence

Current owners:

```text
tbdy_engine/providers/etabs_concrete_design_combo_selection_probe.py
tbdy_engine/providers/etabs_combo_definition_provider.py
```

Selected-combo population carries:

```text
row_id
combo_type
combo_name
source_row_ref
model_fingerprint
evidence_epoch_id
session_provenance_ref
selected_signature_name
source_refs
```

Combo-definition evidence carries:

```text
name
combo_type_code
combo_type
constituents[index, cname_type_code, cname_type, name, scale_factor]
nested_combos
raw_get_type_combo
raw_get_case_list
status
```

These facts prove exact combo semantics and population, not execution generation.

### 2.8 P8A / W7 exact combo-to-analysis-basis projection

Current owner:

`tbdy_engine/design/columns/column_combo_eligibility_projection.py`

`ComponentReadinessBinding` carries:

```text
readiness
model_fingerprint
evidence_epoch_id
readiness_ref
provenance_refs
```

`ComboAnalysisBasisBinding` carries:

```text
design_combo_identity
AnalysisBasisEligibilityEvidence
normalized_definition_fingerprint
model_fingerprint
evidence_epoch_id
provenance_refs
```

`ColumnComboEligibilityProjection` additionally preserves:

```text
projection_id
component_id
design_combo_identity
normalized_definition_fingerprint
constituent_facts
combo_pattern
reconstruction_authority
reconstruction_behavior_refs
analysis_basis_status
analysis_basis_ref
component_readiness_status
component_readiness_ref
model_fingerprint
evidence_epoch_id
eligibility_state
blockers
provenance_refs
```

This is the correct exact semantic join for component × combo × definition × leaf case type × reconstruction basis × accepted analysis basis. It remains different from positive design-execution qualification.

### 2.9 Current application blockers

Current owner:

`tbdy_engine/application/column_execution.py`

Public live execution stops on:

```text
LIVE_FND2_INPUT_LINEAGE_NOT_QUALIFIED
```

A test-only seam that assumes qualified FND2 lineage then stops on:

```text
LIVE_DESIGN_RESULT_LINEAGE_NOT_QUALIFIED
```

This is important negative evidence: current production deliberately does not promote same-model/EvidenceEpoch P8A facts into execution lineage.

---

## 3. Historical mechanism census

| Mechanism | Classification | What it can establish | What it cannot establish |
|---|---|---|---|
| `AnalysisStateIdentity` | REAL CAUSAL EVIDENCE when built from controlled state | exact parent state identity | that any result was generated from it |
| naked `AnalysisResultIdentity` | CORRELATION ONLY until qualified | exact intended parent/generation/scope labels | occurrence of the generation |
| B1 verified-execution proof primitive | REAL CAUSAL EVIDENCE boundary | structural coherence required for positive qualification | execution facts unless future issuer supplies them truthfully |
| `SourceModelIdentity` | CORRELATION ONLY | verified source-model reference | physical/in-memory state or result generation |
| `model_fingerprint` | CORRELATION ONLY | same bounded source-model reference | analysis/design freshness |
| `EvidenceEpoch` | CORRELATION ONLY | same factual acquisition generation | analysis/design execution generation |
| `acquisition_generation_ref` UUID | CORRELATION ONLY | acquisition instance label | ETABS execution occurrence |
| `session_provenance_ref` | CORRELATION ONLY | acquisition session provenance | result freshness |
| `source_row_id` / row hash | CORRELATION ONLY | deterministic row identity/payload trace | generation or execution |
| exact component identity | CORRELATION ONLY | correct component binding | design generation |
| exact combo identity | CORRELATION ONLY | correct selected combo identity | design generation |
| exact combo definition fingerprint | CORRELATION ONLY | exact definition equality | execution occurrence |
| factual leaf case types / reconstruction refs | CORRELATION ONLY | exact demand reconstruction semantics | execution occurrence |
| `AnalysisBasisCompatibility.MATCH` | CORRELATION ONLY | accepted basis compatibility | result freshness |
| `RunAnalysis` return 0 | DIAGNOSTIC ONLY alone | API reports successful run | all requested result rows were newly generated by this call |
| `GetCaseStatus` | DIAGNOSTIC ONLY alone; causal support inside controlled window | per-case current execution status | which historical invocation produced pre-existing Finished results |
| post-analysis locked state | DIAGNOSTIC ONLY | model currently locked; consistent with completed analysis | generation identity |
| result-table availability/nonempty rows | DIAGNOSTIC ONLY | results can currently be read | causal producer |
| `StartDesign` return 0 | DIAGNOSTIC ONLY alone | design call reports successful start | exact row generation/freshness |
| `GetResultsAvailable == true` | DIAGNOSTIC ONLY | concrete design results exist | their generation or parent analysis |
| timestamps/file mtimes | UNSAFE for qualification | possible chronology clue | causal execution |
| random execution/generation UUID | UNSAFE when used alone | unique label | actual execution |
| caller-provided READY/MATCH/status | UNSAFE | caller assertion | factual or causal proof |

Historical architecture PRs also confirm zero supported production `RunAnalysis` and `StartDesign` calls at the frozen architecture stage. Therefore no existing supported production route can already issue positive execution lineage.

---

## 4. External ETABS facts relevant to causal proof

Public CSI documentation establishes the following useful but bounded facts:

1. `cAnalyze.RunAnalysis()` returns zero when the analysis model is successfully run.
2. `cAnalyze.GetCaseStatus()` reports all load-case statuses; documented status values include Not run, Could not start, Not finished, and Finished.
3. ETABS `Run Analysis` executes cases for which results are not available. Therefore a successful controlled call can coexist with older pre-existing results unless the controller first proves the intended result scope has no reusable prior results.
4. ETABS automatically locks a model after analysis; unlocking deletes analysis results because subsequent changes would make them invalid.
5. `cAnalyze.GetRunCaseFlag()` exposes which cases are marked to run; `SetRunCaseFlag` changes that configuration.
6. `cAnalyze.DeleteResults()` can delete analysis results for cases/all. This may be useful to a future authorized B5 but is not used by this research task.
7. `cDesignConcrete.StartDesign()` returns zero if design is successfully started and fails when analysis results are unavailable.
8. `cDesignConcrete.GetResultsAvailable()` only reports whether concrete design results are available.
9. `cDesignConcrete.GetCode()` retrieves the concrete design code.
10. The public `cDesignConcrete` interface exposes design code, design section, results-available, summary-result and StartDesign APIs, but the reviewed interface exposes no immutable design-generation identifier or design-result timestamp that causally binds rows to a StartDesign invocation.

External references reviewed:

- https://docs.csiamerica.com/help-files/etabs-api-2016/html/4b00dc5d-9b60-e088-1b39-d7f7687145fc.htm
- https://docs.csiamerica.com/help-files/etabs-api-2016/html/a24b2f43-be87-e0ff-587b-068339d9a350.htm
- https://docs.csiamerica.com/help-files/etabs/Menus/Analyze/Run_Analysis.htm
- https://docs.csiamerica.com/help-files/etabs/Menus/Analyze/Lock_Model.htm
- https://docs.csiamerica.com/help-files/etabs-api-2016/html/dc111164-bf67-43f5-df8c-323a5349af48.htm
- https://docs.csiamerica.com/help-files/etabs-api-2016/html/78cae8d6-78d7-b51c-cdc1-5072aafc2683.htm
- https://docs.csiamerica.com/help-files/etabs-api-2016/html/64529069-3cb3-af09-8f79-42bb7f50ff08.htm
- https://docs.csiamerica.com/help-files/etabs-api-2016/html/24b1c2c1-a6b8-f53d-da0f-8a9625279a40.htm
- https://docs.csiamerica.com/help-files/etabs-api-2016/html/0271361b-2be9-36fb-3d48-631ee225776d.htm
- https://docs.csiamerica.com/help-files/etabs-api-2016/html/4444b23f-4ec2-f061-a12d-239e8ca6dfc6.htm

These are public ETABS 2016 API/help references. Exact ETABS 23.2 Python binding behavior for the new causal sequence must be live-verified before B5/B6 rely on it.

---

## 5. B5 analysis-result qualification research

### 5.1 Minimum defensible positive chain

Future B5 should qualify an `AnalysisResultIdentity` only when all of the following are inside one controller-owned causal transaction:

```text
A. controller owns scratch/execution state S
B. exact AnalysisStateIdentity X is established from S
C. exact state-basis readback for X succeeds immediately before analysis
D. intended run/result scope R is reconciled
E. prior reusable results for R are proven absent or explicitly invalidated under controller control
F. controller creates unique attempt_ref Y and analysis_generation_ref G
G. controller itself invokes RunAnalysis
H. RunAnalysis returns exact success
I. GetCaseStatus is successfully read and every qualified scope reports Finished
J. post-run state/lock evidence is consistent with no state drift
K. no analysis-affecting mutation, unlock, second run, or source switch occurs
L. required result populations Z are acquired within the same exclusive window
M. Z's exact result scopes/population are reconciled to the Finished scope set
N. AnalysisResultIdentity(parent=X, generation=G, scopes=Z scopes) is built
O. verified execution proof binds X, G, the result identity, attempt evidence and provenance
P. only then may AnalysisLineageQualification become QUALIFIED
```

No individual fact in the chain is sufficient by itself.

### 5.2 Candidate evidence evaluation

| Candidate | Necessary? | Sufficient? | Offline-verifiable? | Live verification? | Disposition |
|---|---:|---:|---:|---:|---|
| controller owns scratch | yes | no | architecture can be tested | yes for real lifecycle | REAL CAUSAL PRECONDITION |
| exact pre-call `AnalysisStateIdentity` | yes | no | yes | state readback must be live-proven | REAL CAUSAL PRECONDITION |
| controlled `RunAnalysis` invocation | yes | no | wrapper/control flow yes | yes | REAL CAUSAL EVENT |
| `RunAnalysis` return code 0 | yes | no | decoder behavior yes | yes | DIAGNOSTIC WITHIN CAUSAL EVENT |
| pre-run no-results / invalidated required scope | yes for strong generation claim | no | contract yes | yes | REAL CAUSAL DISAMBIGUATOR |
| `GetRunCaseFlag` expected scope | recommended/necessary when run flags control scope | no | contract yes | yes | SCOPE EVIDENCE |
| post-run `GetCaseStatus` Finished | yes for qualified scopes | no | contract yes | yes | SCOPE COMPLETION EVIDENCE |
| post-analysis model locked | recommended | no | API contract yes | yes | INTEGRITY DIAGNOSTIC |
| required result tables available | yes for claimed result kinds | no | parsers yes | yes | AVAILABILITY/POPULATION EVIDENCE |
| no intervening analysis-affecting mutation | yes | no | orchestration reachability yes | yes | REAL CAUSAL CONTINUITY |
| controller-issued generation ref | yes as identity handle | no | yes | no by itself | CORRELATION HANDLE INSIDE PROOF |
| exact parent AnalysisStateIdentity | yes | no | yes | parent state's factual establishment live | REAL CAUSAL BINDING |

### 5.3 The pre-existing-results trap

CSI states that Run Analysis executes cases for which results are not available. Therefore this chain is unsafe:

```text
attach model with Finished results
→ call RunAnalysis
→ ret=0
→ read results
→ claim all results came from this call
```

The call may have reused already-available results. B5 must therefore establish one of these equivalent causal preconditions for every qualified scope:

```text
fresh controller-created scratch with no prior result generation
OR
pre-run status proves result scope not run / results unavailable
OR
controller explicitly deletes/invalidates prior result scope and verifies deletion
```

Which mechanism is accepted should be decided after live ETABS 23.2 verification. A mere new UUID or EvidenceEpoch cannot repair this ambiguity.

---

## 6. Causal-chain assumptions and UNPROVEN points

Strongest defensible future chain:

```text
Controller owns scratch S
        ↓
State X established + exact readback
        ↓
required prior result scope absent/inactivated
        ↓
controller issues attempt Y / generation G
        ↓
controller invokes RunAnalysis
        ↓
ret == 0
        ↓
required cases transition to Finished
        ↓
no intervening analysis-affecting mutation
        ↓
results Z acquired and exact scope reconciled
        ↓
Z is bound to G whose parent is X
```

Assumptions requiring live verification before implementation:

```text
UNPROVEN: exact ETABS 23.2 Python tuple/return behavior for GetCaseStatus/GetRunCaseFlag in the intended runtime.
UNPROVEN: whether every case marked Finished after a controlled run always has every required result API population available and internally complete.
UNPROVEN: exact behavior when RunAnalysis returns nonzero but some cases nevertheless finish and retain readable results.
UNPROVEN: exact dependency effects when one case fails and dependent cases/statuses are present.
UNPROVEN: whether the intended scratch lifecycle can guarantee prior results absent without an unsafe mutation sequence.
UNPROVEN: exact ETABS 23.2 lock/status transition timing relative to RunAnalysis return.
```

The causation itself should not depend on ETABS exposing a generation ID; none was identified in current repo or reviewed public API.

---

## 7. Retry semantics

Permanent principle:

```text
attempt 2 != attempt 1
```

Research recommendation:

```text
execution_request_ref   optional logical parent across retries
attempt_ref             unique per invocation attempt
generation_ref          unique per invocation attempt; never reused after failure
```

For attempt 1 failure:

- preserve the attempt record, return code, pre/post case status, lock/state diagnostics and any readable result observations as diagnostics;
- do not issue a qualified `AnalysisResultIdentity` from that failed attempt;
- do not silently merge its artifacts into attempt 2;
- before retry, re-establish the exact intended parent AnalysisStateIdentity and prove that failed/partial results cannot contaminate the next generation;
- if that cannot be proven, discard/rebuild/reinitialize the scratch under the future authorized B5 policy.

For attempt 2 success:

- new `attempt_ref`;
- new `analysis_generation_ref`;
- new proof record;
- only attempt-2 qualified scopes may populate the new `AnalysisResultIdentity`.

Using one generation UUID for multiple retries would erase the exact causal event and is rejected.

---

## 8. Partial analysis execution

B1 already provides `AnalysisResultIdentity.result_scope_refs`. The recommended first implementation is therefore **not** to redesign B1.

Future B5 should add an execution-attempt evidence artifact outside B1 with at least:

```text
attempt_ref
analysis_generation_ref
parent_analysis_state_ref
requested_scope_refs
run_flag_scope_refs
finished_scope_refs
failed_or_unfinished_scope_refs
pre_status_by_scope
post_status_by_scope
run_return_code
result_population_refs
state_readback_refs
provenance_refs
```

Then:

- `AnalysisResultIdentity.result_scope_refs` contains only scopes causally qualified as finished and actually acquired.
- consumers must require their needed scopes to be contained in the qualified result scope.
- a failed/unqualified scope cannot borrow qualification from another scope in the same invocation.
- if cross-case dependency semantics make a finished subset unsafe, B5 must fail closed until live behavior is understood.

Current recommendation:

```text
B1_SEMANTIC_CHANGE_REQUIRED = NO
```

Conditional future note:

```text
If the product later requires one AnalysisResultIdentity to encode requested + finished + failed scope status simultaneously,
SEMANTIC_CHANGE_REQUIRED.
```

That richer execution-status data belongs more naturally to the B5 attempt/proof artifact, not the existing result identity.

---

## 9. B2/B6 design lineage research

### 9.1 What B2 must define

B2 should define **identity semantics only**, not execute design. Minimum `DesignStateIdentity` research boundary:

```text
design_state_ref
source_model_ref
parent_analysis_result_ref
analysis_lineage_qualification_ref
exact design code/ref
exact design procedure/domain
exact selected design-combo population ref
exact combo-definition population refs
exact combo-analysis-basis binding refs
exact design-section/component population refs
reviewed design options/overwrites that materially affect results
state_basis_refs
provenance_refs
contract
```

The exact field set should remain no broader than factual design-affecting state actually used by B6. Display/query selections and present units must not become design-state identity unless proven to affect design generation.

B2 should also define candidate `DesignResultIdentity` semantics:

```text
design_result_ref
source_model_ref
parent_design_state_ref
parent_analysis_result_ref
design_generation_ref
result_scope_refs
provenance_refs
contract
```

Existence of this object must not self-qualify it. B2 should mirror B1's `identity != qualification` boundary.

### 9.2 Minimum B6 positive design chain

Future B6 should require:

```text
A. QUALIFIED AnalysisResultIdentity A covers every required analysis scope
B. DesignStateIdentity D is exact and parented by A
C. D is re-read/verified immediately before design
D. prior concrete-design results are proven absent/stale or StartDesign overwrite semantics are live-proven for the exact required result scope
E. controller issues unique design attempt_ref Yd and design_generation_ref Gd
F. controller itself invokes DesignConcrete.StartDesign
G. StartDesign returns exact success
H. GetResultsAvailable == true after the controlled call
I. no design-affecting state mutation, new analysis, second design call or source switch occurs
J. W6/current canonical `GetSummaryResultsColumn` ABI acquisition captures the exact full component/result population
K. W7/current P8A exact component × combo × definition × leaf-case × reconstruction × analysis-basis join succeeds
L. acquired rows are bound to D/A/Gd inside the same exclusive causal window
M. only then may a candidate DesignResultIdentity become QUALIFIED
```

`GetResultsAvailable`, summary rows, component identity and combo identity are necessary factual pieces, but none is sufficient by itself.

### 9.3 Design freshness gap

The reviewed public concrete-design API exposes `StartDesign`, `GetResultsAvailable`, `GetCode`, `GetDesignSection`, and result summaries but no immutable generation ID. The following behavior is therefore a mandatory live-research gap before B6:

```text
UNPROVEN: whether successful StartDesign deterministically replaces all prior concrete-design results for the requested/current design state.
UNPROVEN: which design-state mutations make GetResultsAvailable false or otherwise invalidate old design results.
UNPROVEN: whether a failed StartDesign can leave a readable partial/previous result population.
UNPROVEN: whether ErrorSummary/WarningSummary or another API can distinguish stale previous rows from rows produced by the current attempt.
```

B6 must not infer freshness merely because rows are readable after StartDesign.

---

## 10. W6 / W7 reconciliation

### W6 proves / contributes

W6's scope established the required factual/negative-contract questions around:

- Python `GetSummaryResultsColumn` ABI;
- explicit return code and exact arrays;
- zero-row handling;
- factual case types;
- reversible DatabaseTables selection state;
- full component population accounting.

Later current P8A production code contains the live-observed ETABS 23.2 14-slot ABI and exact factual population provider. Future B6 should reuse that canonical OAPI/provider path rather than create another decoder.

W6 cannot prove:

```text
which StartDesign generation produced the rows
whether rows are fresh
which qualified AnalysisResultIdentity parented design
positive design-execution qualification
```

### W7 proves / contributes

W7 established the semantic requirement for an exact join:

```text
component
+ exact design combo identity
+ exact combo definition
+ nested/leaf case facts
+ case type
+ reconstruction/sign basis
+ accepted analysis-basis evidence
+ same model fingerprint
+ same EvidenceEpoch
```

Current P8A implements that join through `ComboAnalysisBasisBinding` and `ColumnComboEligibilityProjection`.

W7 cannot prove:

```text
StartDesign occurred
which design generation produced a row
row freshness
qualified DesignResultIdentity
```

Permanent invariant:

```text
W7 exact join != positive design-execution qualification
```

### B2 must add

Canonical `DesignStateIdentity`, candidate `DesignResultIdentity`, and fail-closed qualification vocabulary mirroring B1, with exact parent binding to a QUALIFIED `AnalysisResultIdentity`.

### B6 must add

The controlled StartDesign issuer/execution proof and causal enclosure. B6 should consume, not reinvent, W6 factual acquisition and W7 exact semantic binding.

---

## 11. Pre-existing attached results

Safe classification for an attached model that already contains analysis/design results:

```text
ANALYSIS_RESULTS = UNQUALIFIED
DESIGN_RESULTS = UNQUALIFIED
```

Why:

- `Finished` case status can describe an old run.
- model locked state can describe an old run.
- rows can be nonempty from an old run/design.
- SourceModelIdentity/model fingerprint prove a model reference, not generation.
- EvidenceEpoch proves only acquisition time/generation.
- GetResultsAvailable proves only current availability.
- exact component/combo/definition/basis joins prove semantic correctness of the observed rows, not their producer execution.

No legitimate immutable ETABS analysis/design generation identifier was found in the current repository or reviewed public CSI interface. Therefore attaching after the fact cannot establish the missing causal edge.

A stronger classification would require a verified ETABS mechanism that exposes a trustworthy immutable generation token plus parent-state binding. None is currently established.

---

## 12. Result invalidation matrix

`INVALID` below means prior qualified lineage must not be reused for the new state, even if ETABS happens to retain readable bytes/rows. `QUERY_ONLY` means underlying result generation is not changed but acquisition configuration/provenance may change.

| Operation | Analysis result | Design result | Classification / research note |
|---|---|---|---|
| property mutation | INVALID | INVALID/UNQUALIFIED | analysis-affecting state mutation; locked model normally prevents it until unlock |
| section modifier mutation | INVALID | INVALID/UNQUALIFIED | changes analysis state; downstream design parent changes |
| load mutation | INVALID | INVALID/UNQUALIFIED | changes analysis input state |
| unlock | INVALID | UNQUALIFIED | CSI explicitly states unlock deletes analysis results; any design lineage loses its qualified analysis parent even if design rows remain visible |
| SaveAs without mutation | ETABS results may remain available; old identity does not automatically transfer to new source-model ref | same | copy/path lineage requires explicit future semantics; do not equate copy with same SourceModelIdentity |
| open copy | UNQUALIFIED unless controller has explicit copy lineage and compatible identity semantics | UNQUALIFIED | pre-existing attachment problem reappears |
| RunAnalysis | NEW/MIXED GENERATION RISK | prior design becomes stale for rerun analysis scopes | ETABS may only run cases lacking results; B5 must eliminate mixed-generation ambiguity |
| StartDesign | unchanged analysis generation | NEW/REPLACEMENT BEHAVIOR UNPROVEN | live verification required for overwrite/freshness behavior |
| new analysis run | new analysis generation for rerun scopes | INVALID/UNQUALIFIED | old design cannot parent the new AnalysisResultIdentity |
| design combo change | unchanged analysis generation | INVALID/UNQUALIFIED | design state changed; old design results cannot qualify new state |
| present units change | QUERY_ONLY | QUERY_ONLY | underlying generation unchanged; returned numeric interpretation/provenance may change; capture must bracket exact units |
| Results.Setup selection change | QUERY_ONLY | N/A or query-only | output selection affects acquired population, not result generation |
| DatabaseTables display selection change | QUERY_ONLY | QUERY_ONLY | display/query configuration; must be restored/read back but is not engineering-result generation |

`StartDesign` invalidation/overwrite behavior remains explicitly `UNPROVEN` for ETABS 23.2 and requires live verification.

---

## 13. Exact result-binding precedence / authority diagram

No hidden equivalence is permitted.

```text
SOURCE / SESSION LAYER
======================
SourceModelIdentity
  └─ identifies verified source reference only

TrustedLiveAcquisitionContext
  ├─ session_provenance_ref
  ├─ acquisition_context_ref
  └─ EvidenceEpoch
       └─ identifies factual capture generation only

                         NOT EQUAL TO
                             │
                             ▼
ANALYSIS CAUSAL LAYER
=====================
controlled execution/scratch state
  ↓
AnalysisStateIdentity X
  ↓
controlled RunAnalysis attempt Y / generation G
  + exact pre-state
  + pre-result absence/invalidation
  + return/status evidence
  + no intervening mutation
  ↓
qualified AnalysisResultIdentity A
  └─ result_scope_refs are exact qualified scopes

                             │
                             ▼
DESIGN STATE / SEMANTIC LAYER
=============================
A (qualified parent analysis)
  + design code
  + component/design-section facts
  + selected combo identities
  + exact combo definitions
  + leaf load cases
  + factual case types
  + sign/reconstruction basis
  + analysis-basis compatibility
  ↓
future DesignStateIdentity D (B2)

                             │
                             ▼
DESIGN CAUSAL LAYER
===================
D
  ↓
controlled StartDesign attempt Yd / generation Gd
  + execution outcome
  + no intervening design-affecting mutation
  + immediate W6 factual acquisition
  ↓
future qualified DesignResultIdentity R (B6)

                             │
                             ▼
ROW / ENGINEERING CONSUMPTION
=============================
R-qualified factual rows
  + exact component identity
  + exact combo identity/definition
  + W7/P8A analysis-basis binding
  ↓
downstream engineering authority
```

Precedence principle:

```text
semantic exactness cannot substitute for causal freshness;
causal freshness cannot substitute for semantic exactness.
Both are required where downstream authority needs both.
```

---

## 14. Required final answers

### 1. What minimum proof should B5 require to issue QUALIFIED AnalysisResultIdentity?

Minimum proof is the complete controller-owned causal enclosure:

```text
controller-owned scratch/execution state
+ exact AnalysisStateIdentity and immediate readback
+ exact required case/run scope
+ proof old reusable results for that scope are absent/invalidated
+ unique attempt_ref + unique analysis_generation_ref
+ controller-owned RunAnalysis invocation
+ exact success return
+ post-run required case statuses == Finished
+ no intervening analysis-affecting mutation/unlock/new run
+ immediate exact-scope result acquisition and population reconciliation
+ result identity parented by the exact AnalysisStateIdentity
+ verified execution proof binding state/result/generation/attempt provenance
```

No smaller set identified in this research safely distinguishes a new controlled generation from pre-existing results.

### 2. What evidence is merely correlation and must never qualify analysis?

Never sufficient alone:

```text
SourceModelIdentity
model_fingerprint
EvidenceEpoch
acquisition_generation_ref
acquisition_context_ref
session_provenance_ref
FeatureSnapshot identity
AnalysisBasisSnapshot
AnalysisBasisCompatibility.MATCH
row/source hash
random UUID
timestamp/file mtime
model locked
case Finished
RunAnalysis ret=0
result row/table existence
```

### 3. What minimum proof should B6 require to issue QUALIFIED DesignResultIdentity?

```text
QUALIFIED parent AnalysisResultIdentity
+ exact B2 DesignStateIdentity and immediate readback
+ proof prior design results cannot be confused with the new generation
+ unique design attempt_ref + generation_ref
+ controller-owned StartDesign
+ exact successful return
+ post-call GetResultsAvailable == true
+ no intervening design-affecting mutation/new analysis/second design
+ W6/current canonical exact factual result acquisition and full population closure
+ W7/current exact component/combo/definition/basis binding
+ result population bound to exact DesignStateIdentity + parent AnalysisResultIdentity + generation
+ verified design-execution proof
```

The exact method for proving prior design-result absence/replacement is still a live ETABS research gap.

### 4. Which existing B1 contracts can be reused unchanged?

Reuse unchanged:

```text
AnalysisStateIdentity
AnalysisResultIdentity
AnalysisLineageQualificationStatus
AnalysisLineageQualification
build_analysis_state_identity
build_analysis_result_identity
build_unqualified_analysis_lineage
B1 identity != qualification rule
B1 source/state/result/generation coherence rules
```

The private verified-execution proof can remain the final B1 qualification seam if B5 supplies a richer controller-owned execution record and is the only bounded trusted issuer.

### 5. Which B1 semantics, if any, need extension?

For the recommended B5 path:

```text
B1_SEMANTIC_CHANGE_REQUIRED = NO
```

B5 needs a new attempt/execution evidence artifact and a bounded positive issuer, not a redefinition of `AnalysisStateIdentity` or `AnalysisResultIdentity`.

Conditional future exception:

```text
cross-SaveAs qualified lineage transfer
or one result identity carrying requested/failed/finished scope state
→ SEMANTIC_CHANGE_REQUIRED
```

Neither is required for the minimum B5/B6 plan.

### 6. What exactly should B2 define before B6?

B2 should define:

1. `DesignStateIdentity` with exact parent `AnalysisResultIdentity` and exact design-affecting state basis;
2. `DesignResultIdentity` identity shape with parent design state, parent analysis result, generation and exact result scopes;
3. design-lineage qualification status/object with `identity != qualification` semantics;
4. a private/factory-only positive qualification seam analogous to B1;
5. fail-closed non-equivalences preventing component/combo/model/EvidenceEpoch/row hashes from masquerading as design lineage;
6. exact list of design-affecting state facts B6 must re-read before StartDesign.

B2 must not run design or infer freshness.

### 7. How should retries be represented?

```text
logical request_ref may remain common
attempt_ref is always unique per invocation
generation_ref is always unique per invocation
failed attempt never emits qualified result identity
retry must re-establish parent state and eliminate partial-result contamination
```

Attempt 2 is never attempt 1 with a rewritten status.

### 8. How should partial execution be represented?

Keep B1 unchanged. Add a B5 execution-attempt artifact with requested/finished/failed scopes and exact status evidence. `AnalysisResultIdentity.result_scope_refs` contains only causally qualified, acquired successful scopes. Consumers must prove required-scope inclusion. If ETABS dependency behavior makes a subset ambiguous, fail closed.

### 9. How should stale pre-existing ETABS results be classified?

```text
UNQUALIFIED
```

for both analysis and design unless a controller-owned causal proof exists. Current ETABS factual APIs do not provide a trustworthy immutable generation token that can retroactively establish that edge.

### 10. Which evidence gaps require live ETABS verification?

At minimum:

```text
ETABS 23.2 GetCaseStatus Python shape/status behavior before/after RunAnalysis
GetRunCaseFlag behavior and exact scope reconciliation
RunAnalysis behavior when some/all required results already exist
RunAnalysis nonzero return with partial Finished cases/results
case dependency behavior under partial failure
lock timing/state after RunAnalysis
result API availability/completeness for Finished scopes
safe pre-run result invalidation/no-results establishment
StartDesign overwrite/freshness behavior with pre-existing design results
GetResultsAvailable transitions around design-state changes and failed/successful StartDesign
design-result behavior after new analysis
which design-state changes invalidate prior concrete-design results
partial/failed StartDesign residual rows
```

### 11. Which W6/W7 assets should future workers explicitly reuse?

Reuse W6/current assets:

```text
canonical DesignConcrete.GetSummaryResultsColumn OAPI wrapper/provider
exact live-observed 14-slot ABI
strict return/array-length validation
explicit unit provenance
zero-row negative contract
full expected/attempted/captured population accounting
DatabaseTables restoration discipline
factual case-type acquisition discipline
```

Reuse W7/current assets:

```text
exact (design_combo_type, combo_name) identity
selected-combo population
normalized combo-definition fingerprint
nested constituent/leaf evidence
factual case types
response-spectrum/static reconstruction semantics
ComboAnalysisBasisBinding
ColumnComboEligibilityProjection
same model_fingerprint / EvidenceEpoch joins
no component-to-combo MATCH broadcast
same-name cross-type ambiguity blocking
```

Do not ask W6 or W7 to prove design execution generation; that is B6's causal responsibility.

---

## 15. Recommended future sprint boundaries

### B5

Own only controlled analysis execution, attempt evidence, positive B1 issuance and exact-scope acquisition qualification. Do not redesign engineering checks.

### B2

Own only design-state/result identity vocabulary and fail-closed qualification semantics. No StartDesign.

### B6

Own controlled design execution and positive design-result qualification, reusing W6 factual acquisition and W7 exact semantic joins.

---

## 16. Research disposition

```text
READY_FOR_SUPERVISOR_REVIEW
```

This research does not declare any contract canonical and does not claim merge readiness.