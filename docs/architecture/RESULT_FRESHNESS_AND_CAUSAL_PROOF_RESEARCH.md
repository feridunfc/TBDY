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

This document is research for future B2/B5/B6. It is not a canonical implementation specification and does not issue qualified lineage.

The governing question is causal:

> What evidence can prove that an exact result population was produced by one exact controller-owned execution whose exact parent state is known?

The answer is not one ETABS field. The strongest defensible proof is a bounded causal enclosure with a predeclared execution scope, exact pre-state, controller-owned execution, execution/status evidence, no intervening state-changing action, complete population reconciliation for the entire declared scope, and immediate result acquisition.

A second governing rule is now explicit:

```text
PARTIAL SUCCESS
!= QUALIFIED RESULT LINEAGE
```

A failed or partial execution attempt may retain diagnostics and readable rows, but it may not salvage a successful subset into a qualified result identity.

---

## 1. Permanent non-equivalences

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

Additional research conclusions:

```text
RunAnalysis ret == 0 != result-generation proof
GetCaseStatus == Finished != result-generation proof
model locked == true != result-generation proof
result table nonempty != result-generation proof
StartDesign ret == 0 != design-result generation proof
GetResultsAvailable == true != design-result generation proof

finished subset from partial attempt != qualified subset identity
readable subset from failed attempt != usable causal result identity
```

These facts become useful only inside a controller-owned causal chain whose entire declared execution scope succeeds.

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

Its existence is explicitly not self-authenticating. `analysis_generation_ref` is an identity input, not proof that a generation occurred.

`AnalysisLineageQualification` is factory-created and fail-closed. Positive qualification requires a verified execution proof coherent across:

```text
source_model_ref
execution_state_ref
analysis_state_ref
analysis_result_ref
analysis_generation_ref
```

B1 exposes no public positive issuer. Existing live/pre-existing results therefore remain unqualified.

P1 conclusion:

```text
B1_SEMANTIC_CHANGE_REQUIRED = NO
```

The required partial-execution fail-closed rule can be represented in a future external B5 attempt/proof artifact: a failed/partial attempt simply never reaches B1 positive issuance.

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

Both `SourceModelIdentity` and `model_fingerprint` identify the verified source-model reference, not physical bytes, current in-memory state, analysis state, or result generation.

`TrustedLiveAcquisitionContext` carries:

```text
verified_session
source_model_identity
evidence_epoch
acquisition_generation_ref
session_provenance_ref
acquisition_context_ref
```

`acquisition_generation_ref` is factual acquisition provenance. It cannot prove an ETABS analysis/design execution.

### 2.3 EvidenceEpoch

Current owner:

`tbdy_engine/features/evidence_epoch.py`

Relevant fields:

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

`AnalysisSystemAssumption` and `AnalysisBasisCompatibility` preserve exact EvidenceEpoch / zone / direction / basis / provenance joins. `AnalysisBasisSnapshot` is a deterministic audit/provenance join and is explicitly not an authority.

Therefore:

```text
AnalysisBasisCompatibility.MATCH
!= AnalysisResultIdentity freshness
```

### 2.6 Current column concrete-design factual result population

Current owners:

```text
tbdy_engine/features/column_design_rebar_evidence.py
tbdy_engine/providers/etabs_concrete_column_design_result_provider.py
tbdy_engine/etabs/oapi/concrete_design.py
```

`FactualColumnDesignResultRow` preserves exact component/section/result values plus:

```text
model_fingerprint
evidence_epoch_id
source_refs
```

`FactualColumnDesignResultPopulation` preserves:

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

The provider validates the live-observed ETABS 23.2 `DesignConcrete.GetSummaryResultsColumn` 14-slot Python COM shape, exact row counts, requested FrameName, explicit source units and before/after unit provenance. These are strong factual ABI/population guarantees, but no field binds rows to a particular `StartDesign` generation.

The current `ColumnDesignResultIdentity` in `column_concrete_design_evidence.py` is a factual component/section/model/EvidenceEpoch binding helper. It is not the future causal product-level `DesignResultIdentity` contemplated by B2/B6.

### 2.7 Exact design-combo selection and definition evidence

Current owners:

```text
tbdy_engine/providers/etabs_concrete_design_combo_selection_probe.py
tbdy_engine/providers/etabs_combo_definition_provider.py
```

These preserve exact selected combo identity, combo type, definition, nested constituents, leaf names/types and scale factors. They prove exact combo semantics and population, not execution generation.

### 2.8 P8A / W7 exact combo-to-analysis-basis projection

Current owner:

`tbdy_engine/design/columns/column_combo_eligibility_projection.py`

`ComponentReadinessBinding`, `ComboAnalysisBasisBinding` and `ColumnComboEligibilityProjection` preserve the exact semantic join across:

```text
component
+ design combo identity
+ definition fingerprint
+ constituents
+ factual case types
+ reconstruction semantics
+ accepted analysis basis
+ model fingerprint
+ EvidenceEpoch
```

This remains different from positive design-execution qualification.

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

Current production therefore deliberately does not promote same-model/EvidenceEpoch P8A facts into execution lineage.

### 2.10 Current factual analysis-readiness surface — EXISTING

Current public bounded factual owner:

`tbdy_engine.etabs.safety.read_verified_analysis_readiness(...)`

Current implementation path:

```text
EtabsVerifiedSession
→ safety._execute_verified_read(...)
→ private safety helper read_analysis_readiness(...)
→ SapModel.Analyze.GetCaseStatus()
→ AnalysisCaseReadiness
```

The factual DTO preserves:

```text
case_name
readiness
etabs_status_code
return_code
source_api = Analyze.GetCaseStatus
error_code
```

Current status mapping is already bounded:

```text
1 → ANALYSIS_NOT_RUN
2 → ANALYSIS_COULD_NOT_START
3 → ANALYSIS_INCOMPLETE
4 → ANALYSIS_FINISHED
other/unknown → ANALYSIS_UNKNOWN
```

Therefore:

```text
GetCaseStatus factual read surface = EXISTING
```

It must not be labeled wholesale as `MISSING_FUTURE_B5_OAPI` and B5 must not create a duplicate reader merely because B5 is new.

What may still be `NEW_REQUIRED` is only the additional exact execution-scope/status mechanics that B5 proves are absent after reusing the current bounded read surface. Examples include a typed aggregate attempt-scope reconciliation or an exact run-flag factual reader if the accepted B5 design proves that is necessary.

Architecture remains:

```text
gateway = COM / STA / session / transport ownership
OAPI = factual ABI ownership
safety = verified-session factual/state boundary and transaction discipline
B5/B6 controller = future execution authority
```

Neither `RunAnalysis` nor `StartDesign` execution authority is assigned to OAPI or gateway by this research.

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
| `acquisition_generation_ref` | CORRELATION ONLY | acquisition instance label | ETABS execution occurrence |
| `session_provenance_ref` | CORRELATION ONLY | acquisition session provenance | result freshness |
| `source_row_id` / row hash | CORRELATION ONLY | deterministic row identity/payload trace | generation or execution |
| exact component identity | CORRELATION ONLY | correct component binding | design generation |
| exact combo identity | CORRELATION ONLY | correct selected combo identity | design generation |
| exact combo definition fingerprint | CORRELATION ONLY | exact definition equality | execution occurrence |
| factual leaf case types / reconstruction refs | CORRELATION ONLY | exact demand reconstruction semantics | execution occurrence |
| `AnalysisBasisCompatibility.MATCH` | CORRELATION ONLY | accepted basis compatibility | result freshness |
| `RunAnalysis` return 0 | DIAGNOSTIC ONLY alone | execution API reports success | whole declared scope completion/freshness |
| current `read_verified_analysis_readiness` / `GetCaseStatus` | EXISTING FACTUAL READ; DIAGNOSTIC ONLY alone | current per-case readiness/status | which historical invocation produced pre-existing Finished results |
| post-analysis locked state | DIAGNOSTIC ONLY | model currently locked | generation identity |
| result-table availability/nonempty rows | DIAGNOSTIC ONLY | results can currently be read | causal producer |
| `StartDesign` return 0 | DIAGNOSTIC ONLY alone | design execution call reports success | complete fresh result generation |
| `GetResultsAvailable == true` | DIAGNOSTIC ONLY | concrete design results exist | their generation or parent analysis |
| timestamps/file mtimes | UNSAFE | possible chronology clue | causal execution |
| random execution/generation UUID | UNSAFE when used alone | unique label | actual execution |
| caller-provided READY/MATCH/status | UNSAFE | caller assertion | factual or causal proof |
| finished subset of a failed/partial attempt | DIAGNOSTIC ONLY | subset status/rows are observable | any qualified result identity |

Historical architecture work also confirms zero supported production `RunAnalysis` and `StartDesign` calls at the frozen architecture stage. No existing supported production route can already issue positive execution lineage.

---

## 4. External ETABS facts relevant to causal proof

Public CSI documentation establishes useful but bounded facts:

1. `cAnalyze.RunAnalysis()` returns zero when the analysis model is successfully run.
2. `cAnalyze.GetCaseStatus()` reports load-case statuses.
3. ETABS Run Analysis may skip cases whose results are already available; therefore a controlled call can coexist with old result generations unless the controller first removes or disproves reusable prior results for the declared scope.
4. ETABS locks a model after analysis; unlocking deletes analysis results because subsequent changes would make them invalid.
5. `cAnalyze.GetRunCaseFlag()` exposes run-selection configuration; if B5 needs this factual surface, it should be added only after reusing current factual reads and proving a gap.
6. `cAnalyze.DeleteResults()` can delete analysis results; this may be relevant to a future authorized B5 but is not used here.
7. `cDesignConcrete.StartDesign()` returns zero on documented successful start and requires analysis results.
8. `cDesignConcrete.GetResultsAvailable()` reports availability only.
9. `cDesignConcrete.GetCode()` retrieves the design code.
10. No reviewed public API mechanism supplies an immutable analysis/design generation identifier that by itself causally binds result rows to a controller execution.

External references reviewed in the original research remain applicable:

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

Exact ETABS 23.2 behavior for the future controlled execution sequence still needs live verification where identified below.

---

## 5. B5 analysis-result qualification research

### 5.1 Declared execution scope is fixed before execution

Before a `RunAnalysis` attempt begins, B5 must establish an immutable exact requested execution scope:

```text
requested_scope_refs = R
```

The scope may be deliberately narrow, but it must be declared before invocation.

Allowed example:

```text
requested scope = {A, B}
A finished
B finished
all required populations reconcile
→ successful attempt may qualify exactly {A, B}
```

Forbidden example:

```text
requested scope = {A, B, C}
A finished
B finished
C failed / unfinished / missing population
→ ATTEMPT = FAILED / PARTIAL
→ NO qualified {A, B}
→ NO qualified AnalysisResultIdentity from this attempt
```

Post-hoc shrinkage of requested scope is not permitted.

### 5.2 Minimum defensible positive chain

Future B5 should issue a QUALIFIED `AnalysisResultIdentity` only when every condition below closes for the entire predeclared scope R:

```text
A. controller owns scratch/execution state S
B. exact AnalysisStateIdentity X is established from S
C. exact state-basis readback for X succeeds immediately before analysis
D. exact requested execution scope R is declared before invocation
E. run/configuration scope is reconciled with R to the extent required by accepted B5 mechanics
F. prior reusable results for R are proven absent or explicitly invalidated under controller control
G. controller creates unique attempt_ref Y and analysis_generation_ref G
H. controller itself invokes RunAnalysis
I. RunAnalysis returns exact success
J. existing bounded factual status read is reused and every required/requested scope in R is ANALYSIS_FINISHED
K. no requested/required scope is failed, incomplete, not-run, unknown, or absent from required status evidence
L. post-run state/lock evidence is consistent with no state drift
M. no analysis-affecting mutation, unlock, second run, or source switch occurs
N. every required result population for every scope in R is acquired within the same exclusive causal window
O. population reconciliation for R is complete with no missing required scope/population
P. AnalysisResultIdentity(parent=X, generation=G, result_scope_refs=R) is built
Q. verified execution proof binds X, G, result identity, exact declared scope R, attempt evidence and provenance
R. only then may AnalysisLineageQualification become QUALIFIED
```

Atomic attempt rule:

```text
RunAnalysis failure
OR any scope in R fails
OR any scope in R is unfinished/unknown/not-run
OR any required population for R is incomplete
→ ATTEMPT = FAILED / PARTIAL
→ NO QUALIFIED AnalysisResultIdentity
→ NO usable causal result identity from the attempt
```

Finished/readable subsets may be retained only as diagnostics/attempt evidence.

### 5.3 Candidate evidence evaluation

| Candidate | Necessary? | Sufficient? | Offline-verifiable? | Live verification? | Disposition |
|---|---:|---:|---:|---:|---|
| controller owns scratch | yes | no | architecture can be tested | yes for real lifecycle | REAL CAUSAL PRECONDITION |
| exact pre-call `AnalysisStateIdentity` | yes | no | yes | state readback must be live-proven | REAL CAUSAL PRECONDITION |
| predeclared requested scope R | yes | no | yes | yes for runtime reconciliation | REAL CAUSAL SCOPE BOUNDARY |
| controlled `RunAnalysis` invocation | yes | no | wrapper/control flow yes | yes | REAL CAUSAL EVENT |
| `RunAnalysis` return code 0 | yes | no | controller contract yes | yes | DIAGNOSTIC WITHIN CAUSAL EVENT |
| pre-run no-results / invalidated R | yes for strong generation claim | no | contract yes | yes | REAL CAUSAL DISAMBIGUATOR |
| current bounded per-case readiness read | yes as status evidence | no | existing | execution-transition semantics need live proof | EXISTING FACTUAL SURFACE |
| every requested/required scope == FINISHED | yes | no | aggregation can be tested | yes | WHOLE-SCOPE COMPLETION EVIDENCE |
| post-analysis model locked | recommended | no | API contract yes | yes | INTEGRITY DIAGNOSTIC |
| every required result population for R available/reconciled | yes | no | parsers yes | yes | WHOLE-SCOPE POPULATION EVIDENCE |
| no intervening analysis-affecting mutation | yes | no | reachability yes | yes | REAL CAUSAL CONTINUITY |
| controller-issued generation ref | yes as identity handle | no | yes | no by itself | CORRELATION HANDLE INSIDE PROOF |
| exact parent AnalysisStateIdentity | yes | no | yes | parent state's factual establishment live | REAL CAUSAL BINDING |
| finished subset when another requested scope failed | no authorizing value | no | yes | yes | DIAGNOSTIC ONLY / NO SALVAGE |

### 5.4 The pre-existing-results trap

This chain is unsafe:

```text
attach model with Finished results
→ call RunAnalysis
→ ret=0
→ read results
→ claim all results came from this call
```

B5 must establish, for the entire declared scope R, an accepted causal precondition such as:

```text
fresh controller-created scratch with no prior result generation
OR
pre-run evidence proves required result scope unavailable/not run
OR
controller explicitly invalidates prior result scope and verifies invalidation
```

Which mechanism is accepted should be decided after live ETABS 23.2 verification. A new UUID or EvidenceEpoch cannot repair this ambiguity.

---

## 6. Causal-chain assumptions and UNPROVEN points

Strongest defensible future chain:

```text
Controller owns scratch S
        ↓
State X established + exact readback
        ↓
requested execution scope R declared BEFORE execution
        ↓
required prior results for R absent/inactivated
        ↓
controller issues attempt Y / generation G
        ↓
controller invokes RunAnalysis
        ↓
ret == 0
        ↓
EVERY required/requested scope in R == Finished
        ↓
EVERY required result population for R reconciled completely
        ↓
no intervening analysis-affecting mutation
        ↓
results Z acquired for exactly R
        ↓
Z is bound to G whose parent is X
        ↓
QUALIFIED identity may be issued
```

Any failure before the last step means no qualified result identity exists for that attempt.

Current factual-read reconciliation:

```text
EXISTING:
read_verified_analysis_readiness(...)
→ Analyze.GetCaseStatus factual readiness
```

Remaining live questions are not permission to duplicate that reader. They concern attempt-level execution semantics and any genuinely missing exact scope mechanics.

Assumptions requiring live verification before B5 implementation:

```text
UNPROVEN: exact controlled RunAnalysis status transitions for predeclared multi-case scopes in ETABS 23.2.
UNPROVEN: RunAnalysis overall return behavior when one requested case fails while others finish.
UNPROVEN: dependency effects when one requested case fails and dependent cases/statuses/results exist.
UNPROVEN: whether every requested case reporting Finished always exposes every required result population needed by B5.
UNPROVEN: exact safe mechanism for establishing no reusable prior results on the declared scope.
UNPROVEN: exact lock/status timing relative to RunAnalysis return where B5 uses lock evidence.
UNPROVEN: whether B5 needs GetRunCaseFlag beyond the existing per-case factual readiness surface, and if so the exact bounded factual ABI required.
```

No immutable ETABS generation ID was identified; causation therefore depends on the controlled enclosure, not a generation field exposed by ETABS.

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
requested_scope_refs    immutable per attempt and fixed before invocation
```

Attempt 1 failure/partial result:

- preserve attempt record, return code, exact requested scope, pre/post case status, lock/state diagnostics and readable rows only as diagnostics;
- do not issue any qualified `AnalysisResultIdentity`;
- do not salvage finished subsets into a smaller qualified identity;
- do not silently merge failed/partial artifacts into attempt 2;
- before retry, re-establish exact intended parent `AnalysisStateIdentity`;
- remove/re-establish any contamination from failed/partial analysis results under future accepted B5 policy.

Attempt 2:

```text
new attempt_ref
new analysis_generation_ref
new immutable requested_scope_refs
new proof record
```

Attempt 2 qualifies only if its entire own predeclared scope succeeds and reconciles completely.

---

## 8. Partial analysis execution — fail closed

Future B5 should add an execution-attempt evidence artifact outside B1 with at least:

```text
attempt_ref
analysis_generation_ref
parent_analysis_state_ref
requested_scope_refs
run_flag_scope_refs if required
pre_status_by_scope
post_status_by_scope
finished_scope_refs
failed_or_unfinished_scope_refs
run_return_code
result_population_refs
population_reconciliation_status
state_readback_refs
provenance_refs
attempt_status
```

This artifact records what happened. It does not authorize subset salvage.

Required semantics:

```text
if RunAnalysis fails:
    attempt_status = FAILED
    qualified_result_identity = NONE

if any requested/required scope fails or is unfinished/unknown/not-run:
    attempt_status = PARTIAL or FAILED
    qualified_result_identity = NONE

if required population reconciliation for requested scope is incomplete:
    attempt_status = PARTIAL or FAILED
    qualified_result_identity = NONE

only if entire predeclared requested scope succeeds and reconciles:
    attempt_status = SUCCESS
    AnalysisResultIdentity.result_scope_refs = exact requested_scope_refs
    positive qualification may proceed
```

Therefore:

```text
requested {A,B,C}
finished {A,B}
failed {C}
→ diagnostics may retain A/B rows
→ NO qualified {A,B}
→ NO qualified AnalysisResultIdentity
```

A deliberately narrow attempt remains valid only when the narrow scope is declared before execution and the whole narrow scope succeeds.

Current recommendation remains:

```text
B1_SEMANTIC_CHANGE_REQUIRED = NO
```

The B5 attempt/proof artifact owns requested/finished/failed status. B1 identity semantics need not encode partial attempt state because partial attempts never reach positive result identity issuance.

---

## 9. B2/B6 design lineage research

### 9.1 What B2 must define

B2 should define identity semantics only, not execute design.

Minimum `DesignStateIdentity` boundary:

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

Existence must not self-qualify it. B2 should mirror B1's `identity != qualification` boundary.

B2 must also define fail-closed design-attempt qualification semantics so B6 has no incentive to invent them.

### 9.2 Minimum B6 positive design chain

Future B6 should require:

```text
A. QUALIFIED AnalysisResultIdentity A covers every required analysis scope
B. DesignStateIdentity D is exact and parented by A
C. D is re-read/verified immediately before design
D. exact design execution/result scope Rd is declared before StartDesign
E. prior concrete-design results for Rd are proven unable to contaminate the new attempt
F. controller issues unique design attempt_ref Yd and design_generation_ref Gd
G. controller itself invokes DesignConcrete.StartDesign
H. StartDesign returns exact success
I. required factual design-status/availability evidence succeeds
J. no design-affecting state mutation, new analysis, second design call or source switch occurs
K. W6/current canonical factual acquisition captures every required row/population for Rd
L. W7/current P8A exact component × combo × definition × leaf-case × reconstruction × analysis-basis join succeeds for Rd
M. all required populations for Rd reconcile completely
N. acquired rows are bound to D/A/Gd inside the same exclusive causal window
O. only then may a candidate DesignResultIdentity become QUALIFIED
```

Atomic design attempt rule:

```text
StartDesign failure
OR any required/requested design scope fails/is unavailable
OR required result population is partial/incomplete
→ NO qualified DesignResultIdentity
```

Readable design rows from a failed/partial attempt are diagnostics only and may not be salvaged into a smaller qualified design identity.

### 9.3 Design freshness gap

Mandatory live-research gaps before B6 include:

```text
UNPROVEN: whether successful StartDesign deterministically replaces all prior concrete-design results for the declared design scope.
UNPROVEN: which design-state mutations invalidate old concrete-design results.
UNPROVEN: whether a failed/partial StartDesign can leave readable previous or partial rows.
UNPROVEN: exact availability/status behavior needed to prove whole declared design scope completion.
```

B6 must not infer freshness merely because rows are readable after StartDesign.

---

## 10. W6 / W7 reconciliation

### W6 proves / contributes

W6/current assets provide factual/negative-contract infrastructure around:

- canonical `GetSummaryResultsColumn` factual acquisition;
- exact live-observed 14-slot ABI;
- explicit return code and array alignment;
- zero-row handling;
- factual case types;
- reversible DatabaseTables selection state;
- full expected/attempted/captured component population accounting.

Future B6 should reuse that canonical OAPI/provider path rather than create another decoder.

W6 cannot prove:

```text
which StartDesign generation produced rows
whether rows are fresh
which qualified AnalysisResultIdentity parented design
positive design-execution qualification
```

### W7 proves / contributes

W7/current P8A provides the exact semantic join:

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

Canonical `DesignStateIdentity`, candidate `DesignResultIdentity`, fail-closed qualification vocabulary and exact parent binding to a QUALIFIED `AnalysisResultIdentity`.

### B6 must add

Controlled StartDesign execution/proof with whole-declared-scope atomic qualification, consuming rather than reinventing W6 factual acquisition and W7 exact semantic binding.

---

## 11. Pre-existing attached results

Safe classification for an attached model that already contains analysis/design results:

```text
ANALYSIS_RESULTS = UNQUALIFIED
DESIGN_RESULTS = UNQUALIFIED
```

Why:

- `Finished` case status can describe an old run.
- current bounded `GetCaseStatus` factual availability does not identify the historical producer.
- model locked state can describe an old run.
- rows can be nonempty from an old run/design.
- SourceModelIdentity/model fingerprint prove a model reference, not generation.
- EvidenceEpoch proves only acquisition generation.
- `GetResultsAvailable` proves availability only.
- exact component/combo/definition/basis joins prove semantic correctness of observed rows, not their producer execution.

No legitimate immutable ETABS analysis/design generation identifier is established that could retroactively close the causal edge.

---

## 12. Result invalidation matrix

`INVALID` means prior qualified lineage must not be reused for the new state even if ETABS retains readable rows. `QUERY_ONLY` means underlying result generation is not changed but acquisition configuration/provenance may change.

| Operation | Analysis result | Design result | Classification / research note |
|---|---|---|---|
| property mutation | INVALID | INVALID/UNQUALIFIED | analysis-affecting state mutation |
| section modifier mutation | INVALID | INVALID/UNQUALIFIED | changes analysis state; downstream design parent changes |
| load mutation | INVALID | INVALID/UNQUALIFIED | changes analysis input state |
| unlock | INVALID | UNQUALIFIED | unlock deletes/invalidate analysis results; design loses qualified analysis parent |
| SaveAs without mutation | identity transfer UNKNOWN | identity transfer UNKNOWN | copy/path lineage requires explicit future semantics |
| open copy | UNQUALIFIED unless explicit copy lineage exists | UNQUALIFIED | pre-existing attachment problem reappears |
| RunAnalysis full successful declared attempt | candidate NEW generation for exact declared scope after qualification proof | prior design stale for rerun parent | only whole declared scope may qualify |
| RunAnalysis failed/partial attempt | NO QUALIFIED RESULT IDENTITY | prior design must not be promoted against ambiguous/new parent state | finished subset is diagnostics only |
| StartDesign full successful declared attempt | unchanged analysis generation | candidate NEW design generation after full proof | whole declared scope required |
| StartDesign failed/partial attempt | unchanged analysis generation | NO QUALIFIED DESIGN RESULT IDENTITY | readable subset/old rows are diagnostics only |
| new analysis run | new analysis generation only if whole declared attempt qualifies | INVALID/UNQUALIFIED | old design cannot parent new AnalysisResultIdentity |
| design combo change | unchanged analysis generation | INVALID/UNQUALIFIED | design state changed |
| present units change | QUERY_ONLY | QUERY_ONLY | generation unchanged; factual capture provenance may change |
| Results.Setup selection change | QUERY_ONLY | N/A/query-only | query configuration, not execution generation |
| DatabaseTables display selection change | QUERY_ONLY | QUERY_ONLY | query configuration; must restore/read back |

---

## 13. Exact result-binding precedence / authority diagram

```text
SOURCE / SESSION LAYER
======================
SourceModelIdentity
  └─ verified source reference only

TrustedLiveAcquisitionContext
  ├─ session_provenance_ref
  ├─ acquisition_context_ref
  └─ EvidenceEpoch
       └─ factual capture generation only

                         NOT EQUAL TO
                             │
                             ▼
ANALYSIS CAUSAL LAYER
=====================
controller-owned execution/scratch state
  ↓
AnalysisStateIdentity X
  ↓
predeclared requested scope R
  ↓
controlled RunAnalysis attempt Y / generation G
  + exact pre-state
  + old-result disambiguation
  + execution return evidence
  + EXISTING bounded GetCaseStatus readiness facts
  + ALL R finished
  + ALL required R populations reconciled
  + no intervening mutation
  ↓
SUCCESS only
  ↓
qualified AnalysisResultIdentity A
  └─ result_scope_refs == exact predeclared R

if any part of R fails/incomplete:
  ↓
FAILED/PARTIAL ATTEMPT EVIDENCE ONLY
  ↓
NO AnalysisResultIdentity qualification

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
  + reconstruction basis
  + analysis-basis compatibility
  ↓
future DesignStateIdentity D (B2)

                             │
                             ▼
DESIGN CAUSAL LAYER
===================
D
  ↓
predeclared design scope Rd
  ↓
controlled StartDesign attempt Yd / generation Gd
  + execution outcome
  + no intervening design-affecting mutation
  + immediate W6 factual acquisition
  + W7 exact semantic joins
  + ALL required Rd populations reconciled
  ↓
SUCCESS only
  ↓
future qualified DesignResultIdentity R (B6)

partial/failed design attempt
  ↓
ATTEMPT EVIDENCE ONLY
  ↓
NO qualified DesignResultIdentity
```

Precedence:

```text
semantic exactness cannot substitute for causal freshness;
causal freshness cannot substitute for semantic exactness;
partial success cannot substitute for whole declared execution success.
```

---

## 14. Required final answers

### 1. What minimum proof should B5 require to issue QUALIFIED AnalysisResultIdentity?

```text
controller-owned scratch/execution state
+ exact AnalysisStateIdentity and immediate readback
+ immutable requested execution scope declared before RunAnalysis
+ proof old reusable results for the entire requested scope are absent/invalidated
+ unique attempt_ref + unique analysis_generation_ref
+ controller-owned RunAnalysis invocation
+ exact success return
+ reuse current bounded read_verified_analysis_readiness/GetCaseStatus facts
+ every required/requested scope == ANALYSIS_FINISHED
+ no failed/incomplete/unknown/not-run requested scope
+ no intervening analysis-affecting mutation/unlock/new run
+ immediate acquisition of every required result population for the entire requested scope
+ complete population reconciliation for the entire requested scope
+ result identity parented by exact AnalysisStateIdentity with result_scope_refs equal to the exact predeclared scope
+ verified execution proof binding state/result/generation/attempt/scope provenance
```

Any failure/partial outcome issues no qualified result identity.

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
finished subset from a partial attempt
```

### 3. What minimum proof should B6 require to issue QUALIFIED DesignResultIdentity?

```text
QUALIFIED parent AnalysisResultIdentity
+ exact B2 DesignStateIdentity and immediate readback
+ immutable design execution/result scope declared before StartDesign
+ proof prior design results cannot contaminate the declared scope
+ unique design attempt_ref + generation_ref
+ controller-owned StartDesign
+ exact successful return
+ required factual design status/availability evidence
+ no intervening design-affecting mutation/new analysis/second design
+ W6/current canonical exact factual result acquisition
+ complete population closure for the entire declared design scope
+ W7/current exact component/combo/definition/basis binding
+ result population bound to exact DesignStateIdentity + parent AnalysisResultIdentity + generation
+ verified design-execution proof
```

A partial/failed StartDesign issues no qualified `DesignResultIdentity`.

### 4. Which existing B1 contracts can be reused unchanged?

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

### 5. Which B1 semantics, if any, need extension?

```text
B1_SEMANTIC_CHANGE_REQUIRED = NO
```

B5 needs an external attempt/execution evidence artifact and bounded positive issuer. Partial/failed attempts never produce a qualified result identity, so B1 need not encode salvage/subset semantics.

A future request to encode failed/partial attempt status inside `AnalysisResultIdentity` itself, or to transfer qualification across unrelated SourceModelIdentity semantics, would require a separately reviewed semantic change.

### 6. What exactly should B2 define before B6?

B2 should define:

1. `DesignStateIdentity` with exact parent QUALIFIED `AnalysisResultIdentity` and exact design-affecting state basis;
2. `DesignResultIdentity` identity shape with parent design state, parent analysis result, generation and exact result scopes;
3. design-lineage qualification status/object with `identity != qualification` semantics;
4. private/factory-only positive qualification seam analogous to B1;
5. fail-closed non-equivalences preventing component/combo/model/EvidenceEpoch/row hashes from masquerading as design lineage;
6. exact design-affecting state facts B6 must re-read before StartDesign;
7. atomic attempt rule: partial/failed design execution issues no qualified `DesignResultIdentity`.

### 7. How should retries be represented?

```text
logical request_ref may remain common
attempt_ref is unique per invocation
generation_ref is unique per invocation
requested_scope_refs are immutable per attempt and declared before invocation
failed/partial attempt never emits qualified result identity
retry gets a new attempt_ref and generation_ref
retry must re-establish parent state and eliminate contamination
```

### 8. How should partial execution be represented?

In the external attempt/proof artifact only.

```text
requested scope fixed before execution
+ exact finished/failed/unfinished statuses
+ exact result-population diagnostics
+ attempt status FAILED/PARTIAL
→ NO qualified AnalysisResultIdentity
```

No finished-scope salvage is allowed from the same failed/partial attempt.

A deliberately narrow scope is allowed only if declared before execution and that entire scope succeeds.

### 9. How should stale pre-existing ETABS results be classified?

```text
UNQUALIFIED
```

for both analysis and design unless a controller-owned causal proof exists.

### 10. Which evidence gaps require live ETABS verification?

At minimum:

```text
controlled RunAnalysis transition behavior for predeclared multi-case scopes
RunAnalysis nonzero return with some cases Finished
case dependency behavior under partial failure
whether every requested Finished case exposes every required result population
safe pre-run result invalidation/no-results establishment
whether B5 needs additional run-flag factual mechanics beyond the current bounded readiness read
exact GetRunCaseFlag ABI if that gap is proven necessary
lock timing/state where B5 chooses to use lock evidence
StartDesign overwrite/freshness behavior with pre-existing design results
GetResultsAvailable/status transitions around design-state changes and failed/successful StartDesign
which design-state changes invalidate prior concrete-design results
partial/failed StartDesign residual/previous row behavior
whole-declared-design-scope completion evidence
```

Not a gap:

```text
basic bounded per-case GetCaseStatus factual readiness read
```

That current read surface already exists in `tbdy_engine.etabs.safety.read_verified_analysis_readiness(...)` and should be reused.

### 11. Which W6/W7 assets should future workers explicitly reuse?

Reuse W6/current:

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

Reuse W7/current:

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

Do not ask W6 or W7 to prove design execution generation; that remains B6's causal responsibility.

---

## 15. Recommended future sprint boundaries

### B5

Own controlled analysis execution, immutable predeclared attempt scope, attempt evidence, atomic whole-scope positive B1 issuance and exact-scope acquisition qualification. Reuse current factual status reads. Do not redesign engineering checks.

### B2

Own design-state/result identity vocabulary and fail-closed qualification semantics, including the atomic no-partial-qualification rule. No StartDesign.

### B6

Own controlled design execution and atomic whole-scope positive design-result qualification, reusing W6 factual acquisition and W7 exact semantic joins.

Architecture ownership remains:

```text
gateway = COM/STA/session/transport
OAPI = factual ABI
B5/B6 controller = execution authority
```

---

## 16. Research disposition

```text
PARTIAL_EXECUTION_CONFLICT_RESOLVED = YES
CURRENT_STATUS_READ_RECONCILED = YES
READY_FOR_SUPERVISOR_REVIEW
```

This research does not declare any contract canonical and does not claim merge readiness.
