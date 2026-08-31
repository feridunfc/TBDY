# R-LIFE-1 — ETABS Execution Lifecycle Census

**Mode:** STRICT RESEARCH / ARCHAEOLOGY / CAPABILITY CENSUS ONLY  
**Frozen base:** `6273c19030ab6ecb7ad2637e3bfc74f88b1da086`  
**Research branch:** `research/r-life-1-etabs-execution-lifecycle`  
**Production code changed:** NO  
**ETABS mutation / RunAnalysis / StartDesign / Save / SetPresentUnits executed:** NO

## 0. Evidence discipline

This report keeps four evidence classes separate:

- `CURRENT_REPO`: exact source/tests at `6273c190...`.
- `HISTORICAL`: prior branches/reports; reusable mechanics or rejected patterns only.
- `CSI_CONTRACT_CANDIDATE`: ETABS API documentation/type contract; not project ownership and not live causality proof.
- `LIVE_VERIFICATION_REQUIRED`: runtime behavior not established by current source/tests/docs.

Permanent distinctions:

```text
DOCUMENTED CSI METHOD != CURRENT PRODUCTION WRAPPER
ret == 0 != QUALIFIED RESULT IDENTITY
SourceModelIdentity != PHYSICAL SOURCE FILE INTEGRITY
PRE-EXISTING ETABS RESULTS != CAUSALLY PROVEN EXECUTION RESULTS
```

## 1. Executive result

The current repository has a mature read-only factual boundary but no approved execution/file-lifecycle authority:

```text
packages/etabs_gateway
  -> sole attach / COM / STA / bounded-execution owner

tbdy_engine.etabs.safety
  -> verified-session qualification
  -> model identity / units / lock / capability reads
  -> DatabaseTables and Results.Setup reversible state mechanics
  -> Analyze.GetCaseStatus factual readiness

tbdy_engine.etabs.oapi
  -> exact factual read ABI for current consumers
  -> no File.OpenFile / File.Save
  -> no Analyze.SetRunCaseFlag / RunAnalysis / DeleteResults
  -> no DesignConcrete.StartDesign

tbdy_engine.integration.etabs_analysis_lineage
  -> fail-closed analysis identity vocabulary
  -> deliberately no public positive AnalysisResultIdentity issuer
```

Current architecture tests forbid production `RunAnalysis` and `StartDesign`, confine `SetPresentUnits` to a compatibility helper, and forbid execution/file mutation inside the gateway package. Therefore B4A/B4B/B5/B6 require new bounded write capabilities in later approved sprints. R-LIFE-1 implements none of them.

## 2. Exact current-repo capability census

| Requested concept | Exact symbol/API found | Current status | Disposition |
|---|---|---|---|
| Run analysis | `SapModel.Analyze.RunAnalysis()` | no production wrapper; production call forbidden by guard | `NEW_REQUIRED` B5 |
| Start concrete design | `SapModel.DesignConcrete.StartDesign()` | no production wrapper; production call forbidden by guard | `NEW_REQUIRED` B6 |
| Start steel design | `SapModel.DesignSteel.StartDesign()` | no production wrapper | only if future steel scope requires it |
| Save | `SapModel.File.Save(FileName)` | no current wrapper | B4A decision; `NEW_REQUIRED` if used |
| SaveAs | exact symbol not found in inspected CSI reference | documented save-to-path capability is `File.Save(FileName)` | do not invent `SaveAs` |
| Open existing model | `SapModel.File.OpenFile(FileName)` | no current wrapper | `NEW_REQUIRED` B4A if selected |
| Initialize model | `SapModel.InitializeNewModel(...)` | no lifecycle wrapper; gateway guard forbids it | not justified merely to clone source |
| New model | CSI `File.New*` template family exists | no lifecycle owner | not required for source-copy lifecycle by default |
| Current model filename | `SapModel.GetModelFilename(bool)` | gateway context reader / safety identity | reusable |
| Current model filepath | `SapModel.GetModelFilepath()` exists in CSI docs | current gateway already uses `GetModelFilename(True)` | optional factual gap only if needed |
| File-path read | `SapModel.File.GetFilePath()` exists in CSI docs | no wrapper observed | optional factual gap |
| Model lock read | `SapModel.GetModelIsLocked()` | gateway/safety | reusable |
| Model lock write | `SapModel.SetModelIsLocked(bool)` | gateway guard forbids it | `NEW_REQUIRED` only if B4B proves need |
| Present units read | `SapModel.GetPresentUnits()` plus safety snapshot | gateway/safety | reusable |
| Present units write | `SapModel.SetPresentUnits(...)` | compatibility-only `engine/unit_context.py`; production reachability guarded | reject for B4/B5/B6 |
| Analysis result clearing | `SapModel.Analyze.DeleteResults(Name, All=False)` | no wrapper | freshness policy gap |
| Create analysis model | `SapModel.Analyze.CreateAnalysisModel()` | no wrapper | CSI says not required before RunAnalysis |
| Case status | `SapModel.Analyze.GetCaseStatus(...)` | safety factual mechanics | reusable |
| Run flags read | `SapModel.Analyze.GetRunCaseFlag(...)` | no wrapper | `NEW_REQUIRED` B5 |
| Run flags write | `SapModel.Analyze.SetRunCaseFlag(Name, Run, All=False)` | no wrapper | `NEW_REQUIRED` B5 |
| Results selection | `SapModel.Results.Setup...` | safety transaction + restoration proof | reusable read-state mechanics |
| DatabaseTables | `SapModel.DatabaseTables...` | safety transaction + OAPI display read | reusable read-state mechanics |
| DB case display selection | `SetLoadCasesSelectedForDisplay` | private safety transaction mechanics | reusable temporary state |
| DB combo display selection | `SetLoadCombinationsSelectedForDisplay` | private safety transaction mechanics | reusable temporary state |
| Concrete design code read | `DesignConcrete.GetCode(ref CodeName)` | CSI contract exists; no dedicated current OAPI wrapper observed | B6 factual gap if needed |
| Concrete design code write | `DesignConcrete.SetCode(...)` | no wrapper | design-state mutation; future policy |
| Concrete design combo write | `DesignConcrete.SetComboStrength(Name, Selected)` | no write wrapper; current repo has factual selected-combo acquisition path | future B6 only if mutation is required |
| Concrete results availability | `DesignConcrete.GetResultsAvailable()` | no lifecycle wrapper observed | B6 postcondition candidate |
| Concrete design section read | `DesignConcrete.GetDesignSection` | current OAPI | reusable |
| Concrete column summary | `DesignConcrete.GetSummaryResultsColumn` | current OAPI/provider | reusable |
| Concrete beam summary | `DesignConcrete.GetSummaryResultsBeam` / `_2` | CSI contract; no shared current consumer proven here | add only for real consumer |
| Concrete design result clearing | no generic `DeleteResults` in inspected `cDesignConcrete` method list | unresolved | `LIVE_VERIFICATION_REQUIRED` / later B6 research |

### Guard-derived current facts

Exact-base executable guards provide stronger evidence than substring archaeology for prohibited owners:

- `tests/etabs/test_oapi_layer1_architecture_guards.py` rejects production `RunAnalysis` / `StartDesign`.
- `packages/etabs_gateway/tests/test_boundary_guards.py` rejects gateway `RunAnalysis`, `StartDesign`, `SetPresentUnits`, `SetModelIsLocked`, `InitializeNewModel`, `OpenFile`, and `Save`.
- gateway public session does not export raw `SapModel`.
- `TrustedLiveAcquisitionContext` has no `sap_model` / `attach_result` raw escape.
- unit mutation is isolated to a compatibility helper and is not lifecycle authority.

## 3. Owner census

### LIFE-CAP-001 — source identity and state

- current owner: gateway context reader + `tbdy_engine.etabs.safety`
- current wrapper: PRESENT
- raw SapModel: internal to bounded callback only
- facts: path, lock, units, version, PID/attach strategy
- future owner: B4A consumes these facts
- limitation: logical/path identity is not physical byte integrity

### LIFE-CAP-002 — scratch creation/copy

- current owner: NONE
- historical owner: proposals only; no accepted complete implementation found
- gateway/OAPI wrapper: NONE
- future owner: B4A
- status: `NEW_REQUIRED`

### LIFE-CAP-003 — open scratch

- CSI candidate: `SapModel.File.OpenFile(FileName)`
- current owner/wrapper: NONE
- source mutation risk: HIGH if session/source isolation is wrong
- future owner: B4A
- status: `NEW_REQUIRED`

### LIFE-CAP-004 — save-to-path

- exact CSI method: `SapModel.File.Save(FileName="")`
- exact `SaveAs`: NOT FOUND in inspected reference
- current owner/wrapper: NONE
- future owner: B4A only if chosen scratch strategy needs it
- source rule: never save to immutable source path in derived-state lifecycle

### LIFE-CAP-005 — analysis-affecting mutation

- generic current writer: NONE
- future owner: B4B
- required protocol: `SET -> ret==0 -> READBACK -> equality/tolerance -> mutation manifest`
- status: `NEW_REQUIRED`

### LIFE-CAP-006 — run-case scope

- CSI candidates: `Analyze.GetRunCaseFlag`, `Analyze.SetRunCaseFlag`
- current wrapper: NONE
- future owner: B5
- status: `NEW_REQUIRED`

### LIFE-CAP-007 — analysis execution

- CSI: `Analyze.RunAnalysis`
- current owner/wrapper: NONE
- future owner: B5 only
- status: `NEW_REQUIRED`

### LIFE-CAP-008 — analysis completion/readiness

- CSI: `Analyze.GetCaseStatus`
- current owner: safety factual mechanics
- current mapping: NOT_RUN / COULD_NOT_START / INCOMPLETE / FINISHED / UNKNOWN
- future role: B5 post-run qualification input
- reusable, but not a causal identity issuer

### LIFE-CAP-009 — analysis result invalidation

- CSI candidate: `Analyze.DeleteResults(Name, All=False)`
- current wrapper: NONE
- future owner: explicit B4B/B5 policy decision
- status: `NEW_REQUIRED` if explicit clearing is part of freshness protocol

### LIFE-CAP-010 — trusted analysis identity

- current owner: `tbdy_engine.integration.etabs_analysis_lineage`
- current positive issuer: intentionally NONE
- rule: pre-existing analysis state cannot become trusted `AnalysisResultIdentity`
- future owner: B5 controlled-execution issuer

### LIFE-CAP-011 — concrete design factual state

- current assets: OAPI design-section/summary reads; factual selected-design-combo provider; unit/provenance binding
- missing lifecycle facts: active code and explicit results-available wrapper if B6 needs them
- future owner: B6 factual/OAPI layer as demanded by exact consumers

### LIFE-CAP-012 — concrete design execution

- CSI: `DesignConcrete.StartDesign`
- current wrapper: NONE
- CSI precondition candidate: concrete frames and analysis results must be available
- future owner: B6 only
- status: `NEW_REQUIRED`

## 4. Scratch-model archaeology and reusable assets

No accepted current scratch model controller was found on exact main.

### LIFE-REUSE-001 — DedicatedSTAWorker

Historical `sprint/p1-1-dedicated-sta-worker` @ `b23253b381292e8db2115bac3ece3802b3f16717` established one owned worker thread, serialized calls, timeout/failure/close semantics, and poison-on-running-timeout behavior. Current gateway already embodies this.  
Disposition: `REUSE_AS_IS`.

### LIFE-REUSE-002 — typed gateway contract foundation

Historical `sprint/p1-typed-etabs-gateway-foundation` @ `0ee5d37008d3d5480590af6c11de558c4dbd0f41` established typed model/unit/connection contracts, read-only default, no generic execution, no engineering verdict.  
Disposition: `ADAPT_EXISTING` only through current gateway; do not resurrect placeholder code.

### LIFE-REUSE-003 — verified target qualification

Current safety/gateway provides PID-aware attach, exact model-path qualification, units/lock/context facts, raw COM privacy.  
Disposition: `REUSE_AS_IS`.

### LIFE-REUSE-004 — reversible read-state transactions

Current `DatabaseTablesReadTransaction` and `ResultsSetupReadTransaction` provide snapshot/restore/verify mechanics.  
Disposition: `REUSE_AS_IS`; these do **not** provide model-mutation rollback.

### LIFE-REUSE-005 — analysis readiness fact

Current safety owns factual `Analyze.GetCaseStatus`.  
Disposition: `REUSE_AS_IS` as B5 post-run evidence.

### LIFE-REUSE-006 — analysis causal lineage contract

Historical/current analysis-lineage work (`sprint/id-lineage-1-analysis-lineage` @ `adea99fd5adc5510ed39cffde2b72f8c4908a85d`) establishes no public positive issuer from pre-existing results and reserves trust for future causal execution proof.  
Disposition: `REUSE_AS_IS`; positive issuer belongs B5.

### LIFE-REUSE-007 — immutable analysis-basis snapshot

Historical `sprint/f0-5-analysis-basis-lifecycle` @ `dbb97e554a14807f7d462bde9b9c3d9728cef46e`.  
Reusable: deterministic immutable analysis-basis snapshot/provenance.  
Disposition: `EXTRACT_ONLY`; not a scratch/run implementation.

### LIFE-REUSE-008 — second-order readiness is not execution authority

Historical `sprint/stab-1-second-order-analysis-basis-closure` @ `f0f0e20851906db5411cd7717123808c1562db64` proves fail-closed `REANALYSIS_REQUIRED` and no invented fallback.  
Disposition: `EXTRACT_ONLY` as B4/B5 demand signal; it does not own `RunAnalysis`.

### LIFE-REUSE-009 — SourceModelIdentity / EvidenceEpoch

Current `TrustedLiveAcquisitionContext` supplies stable verified source-path identity and acquisition epoch while explicitly not proving physical bytes or analysis freshness.  
Disposition: `REUSE_AS_IS`.

### LIFE-REUSE-010 — factual OAPI reads

Current OAPI owns object/load/combo/concrete-design/DatabaseTables read ABI.  
Disposition: `REUSE_AS_IS` where an exact fact is already wrapped.

### Historical G0 scratch proposals

G0 material proposed source-no-save protection, source fingerprint checks, scratch identity verification, and future wrappers for analysis/design/file lifecycle. No complete accepted current implementation with causal scratch ownership + cleanup + failure recovery was found.  
Disposition: `NEW_REQUIRED` B4A; use G0 only as requirement/oracle material.

## 5. Rejected patterns

- `LIFE-REJECT-001`: public/provider raw SapModel escape.
- `LIFE-REJECT-002`: mutate/analyze/design immutable source in place.
- `LIFE-REJECT-003`: treat SourceModelIdentity as source-file byte integrity.
- `LIFE-REJECT-004`: treat existing `GetCaseStatus == FINISHED` or result rows as causal execution proof.
- `LIFE-REJECT-005`: establish scratch ownership from UUID alone, path alone, filename alone, or hash alone.
- `LIFE-REJECT-006`: let B6 call `RunAnalysis` or become a second analysis owner.
- `LIFE-REJECT-007`: use `SetPresentUnits` as lifecycle normalization.
- `LIFE-REJECT-008`: invent `SaveAs`; exact documented capability found is `File.Save(FileName)`.
- `LIFE-REJECT-009`: issue result identity from `ret == 0` alone.
- `LIFE-REJECT-010`: assume `StartDesign` cannot trigger/re-run analysis without live evidence.
- `LIFE-REJECT-011`: generic mutation rollback as a substitute for scratch isolation.
- `LIFE-REJECT-012`: treat DatabaseTables/Results.Setup restoration as model-mutation rollback.

## 6. Proposed factual state machine

### SOURCE_ATTACHED_READONLY

Controller: current gateway + safety.  
Allowed: identity/version/path/PID, units/lock, factual reads, physical source pre-snapshot.  
Forbidden: save, unlock/mutate, run, design.  
Transition only after causal scratch creation evidence.

### SCRATCH_CREATED

Controller: B4A.  
Required: creation attempt ID, parent SourceModelIdentity, source physical pre-state, scratch path/mechanism, initial scratch hash/size/mtime.  
No claim yet that ETABS opened scratch.

### SCRATCH_OPENED

Controller: B4A.  
Candidate operation: `File.OpenFile(scratch_path)` or a separately proven isolation route.  
Postconditions: ret success; active model path equals scratch; source physical state unchanged; lock read; scratch ownership bundle complete. Only then issue scratch identity.

### SCRATCH_MUTATED_UNANALYZED

Controller: B4B.  
Every write: `SET -> ret -> READBACK -> compare -> manifest`.  
Postcondition: parent analysis/design identities invalid for the derived state.

### SCRATCH_ANALYZED

Controller: B5.  
Candidate sequence: read run flags -> set intended flags -> optional explicit stale-result clearing by approved policy -> `RunAnalysis` -> `GetCaseStatus`.  
Only after ret=0 and all intended cases are qualified FINISHED may B5 issue causal `AnalysisResultIdentity`.

### SCRATCH_DESIGN_READY

Controller: B6 preflight.  
Requires qualified AnalysisResultIdentity, bound design code/state, selected design combinations, eligible concrete population, and no later analysis-affecting mutation.

### SCRATCH_DESIGNED

Controller: B6.  
Candidate operation: `DesignConcrete.StartDesign`.  
Postconditions: ret=0; results available; required result population acquisition complete; analysis identity still valid; source integrity unchanged. Only then issue future `DesignResultIdentity`.

### FAILED_EXECUTION

Entered on scratch/create/open failure, setter nonzero, readback mismatch, RunAnalysis exception/nonzero/partial failure, StartDesign exception/nonzero, result acquisition failure, source-integrity mismatch, or cleanup failure.

Hard rules:

```text
failed analysis -> NO qualified AnalysisResultIdentity
failed design -> NO qualified DesignResultIdentity
retry -> NEW execution attempt ID
```

### CLEANED_UP

Controller: B4A lifecycle owner.  
Required: source after-state verified; scratch deleted or intentionally retained-for-audit; cleanup result recorded. Cleanup failure is itself a failure state.

## 7. Source model integrity

### Physical source integrity

B4A must independently snapshot at minimum:

```text
canonical source path
cryptographic content hash
file size
mtime
existence
```

Recommended diagnostic if stable on platform: filesystem/file ID and read-only/ACL summary.

### Logical source identity

Current SourceModelIdentity/safety facts establish reviewed model path and process/session context; they do not prove bytes.

```text
PHYSICAL SOURCE INTEGRITY
!=
SourceModelIdentity
```

### Currently-open path

Current reusable read is `GetModelFilename(True)`. CSI also documents `GetModelFilepath()` and `File.GetFilePath()`. Do not add duplicate wrappers unless later evidence proves current path fact inadequate.

### Silent-write questions

These remain `LIVE_VERIFICATION_REQUIRED`:

- attach to source: any file-byte/mtime effect without explicit save;
- opening scratch: whether switching away from source writes source;
- RunAnalysis: automatic file writes;
- StartDesign: automatic file writes;
- close/switch active-model behavior;
- `File.Save(new_path)` active-model path and result-preservation semantics;
- whether OS-copied `.edb` preserves analysis/design results when opened.

## 8. Scratch ownership

`SCRATCH_IS_OURS = TRUE` needs a causal bundle:

```text
scratch_creation_attempt_id
parent SourceModelIdentity
parent source physical hash before creation
controller-chosen scratch path
scratch creation mechanism
scratch initial hash/size/mtime
controller-issued scratch identity
ETABS model-path readback after open
process/session identity
creation/open timestamps
cleanup state
```

A random UUID, path, filename, or hash alone is insufficient. A true copy may initially have the same hash as source, so hash equality is provenance but not ownership proof.

## 9. Analysis-affecting mutation census

| Family | Classification | Future requirement |
|---|---|---|
| frame/area stiffness modifiers | ANALYSIS_AFFECTING | set + readback + manifest |
| joint restraints | ANALYSIS_AFFECTING | set + readback + manifest |
| frame releases | ANALYSIS_AFFECTING | set + readback + manifest |
| section properties/assignments | ANALYSIS_AFFECTING | set + readback + manifest |
| load patterns/assignments | ANALYSIS_AFFECTING | set + readback + manifest |
| load cases | ANALYSIS_AFFECTING | set + readback + manifest |
| mass source | ANALYSIS_AFFECTING | set + readback + manifest |
| response spectrum functions/cases | ANALYSIS_AFFECTING | set + readback + manifest |
| P-Delta / geometric nonlinearity | ANALYSIS_AFFECTING | set + readback + manifest |
| analysis options / solver / active DOF | ANALYSIS_AFFECTING | set + readback + manifest |
| diaphragms | ANALYSIS_AFFECTING | set + readback + manifest |
| story data | ANALYSIS_AFFECTING or UNKNOWN per exact field | exact-method classification required |
| load combinations | generally not solution input; may change design/result-use state | classify by exact consumer |
| Results.Setup selection | RESULT_SELECTION_ONLY | existing reversible safety transaction |
| DatabaseTables display selection | RESULT_SELECTION_ONLY | existing reversible safety transaction |
| present units | DISPLAY/API-INTERPRETATION STATE | read/preserve; do not mutate |
| concrete design code/combo selection | DESIGN_STATE_AFFECTING | invalidate design identity |
| concrete design section mutation | DESIGN_STATE_AFFECTING; potential analysis coupling depends exact semantics | exact policy/readback required |

Every future analysis-affecting setter requires verified scratch ownership, ret code, readback, comparison rule, mutation-manifest entry, and invalidation of prior analysis/design identities.

## 10. Lock / result invalidation

### Known from current code/tests

- lock state is factually readable;
- read-state selections can be restored exactly;
- pre-existing results cannot issue a trusted positive AnalysisResultIdentity;
- engineering readiness can fail closed as `REANALYSIS_REQUIRED`.

### CSI contract candidates

- `SetModelIsLocked(bool)` exists;
- `Analyze.DeleteResults(Name, All=False)` explicitly deletes case results;
- `RunAnalysis` creates the analysis model automatically and requires a model file path;
- `DesignConcrete.StartDesign` fails if analysis results are unavailable;
- `DesignConcrete.GetResultsAvailable` reports design-result availability;
- concrete design exposes `GetCode`, `SetCode`, `SetComboStrength`, `SetDesignSection`, and `StartDesign`.

### Not established

Do not promote these to facts:

- unlock itself invalidates/deletes results;
- arbitrary property mutation automatically deletes all analysis results;
- `File.Save(new_path)` preserves analysis/design results;
- opening a copied model preserves analysis/design results;
- design results survive save/open;
- `StartDesign` never invokes/re-runs analysis;
- concrete design has a generic result-delete method analogous to steel.

All are `LIVE_VERIFICATION_REQUIRED` unless later exact evidence proves them.

### Product-level identity invalidation

Regardless of ETABS cache persistence:

- any controlled analysis-affecting mutation invalidates prior AnalysisResultIdentity for the new derived state;
- invalid AnalysisResultIdentity invalidates dependent DesignResultIdentity;
- design-state mutation after design invalidates prior DesignResultIdentity;
- retained ETABS rows do not preserve causal product identity.

## 11. B5 minimum analysis execution contract

CSI candidate surfaces:

1. `Analyze.GetRunCaseFlag`
2. `Analyze.SetRunCaseFlag`
3. `Analyze.RunAnalysis`
4. `Analyze.GetCaseStatus`
5. optionally `Analyze.DeleteResults` if explicit stale-result clearing is adopted

Required future evidence:

```text
execution_attempt_id
scratch identity
analysis-basis identity
mutation-manifest identity
pre-run run flags
intended run-case scope
post-set run-flag readback
RunAnalysis ret/exception
post-run status for every intended case
unexpected/partial status
source-integrity pre/post
post-run scratch state
```

Hard rules:

```text
RunAnalysis ret != 0 -> NO AnalysisResultIdentity
any intended case not FINISHED -> NO AnalysisResultIdentity
retry -> NEW execution_attempt_id
pre-existing FINISHED -> insufficient without controlled causal run
```

CSI says `CreateAnalysisModel` is not necessary before `RunAnalysis`; RunAnalysis creates it if necessary. CSI also says the model must already have a file path.

## 12. B6 minimum design execution contract

Concrete target:

1. require qualified B5 AnalysisResultIdentity;
2. read/bind active concrete design code (`DesignConcrete.GetCode`) if not already supplied by an accepted factual owner;
3. read/bind actual selected design combinations through current factual acquisition path;
4. establish DesignStateIdentity;
5. call `DesignConcrete.StartDesign` — `NEW_REQUIRED`;
6. require ret=0;
7. read `DesignConcrete.GetResultsAvailable` — wrapper gap if adopted;
8. acquire required design result populations through current OAPI/providers;
9. bind results to exact model/analysis/design state;
10. issue DesignResultIdentity only after qualification.

Permanent ownership:

```text
B5 OWNS RunAnalysis
B6 OWNS StartDesign
B6 MUST NOT CALL RunAnalysis
```

CSI says StartDesign fails when analysis results are unavailable. That does **not** prove it can never internally trigger or repeat analysis. Status: `LIVE_VERIFICATION_REQUIRED`.

## 13. Failure / cleanup matrix

| Failure | Identity allowed | Identity forbidden | Mandatory checks | Scratch disposition |
|---|---|---|---|---|
| scratch creation failure | source identity + failed attempt | scratch-open/analysis/design | source physical after==before | delete safely identified partial temp or retain diagnostic |
| scratch open failure | scratch creation record | qualified scratch-open/analysis/design | source integrity + current ETABS path | cleanup/retain with reason |
| mutation ret nonzero | scratch identity | new analysis/design | safe readback + source integrity | retain or cleanup by policy |
| mutation readback mismatch | scratch + failed manifest | analysis/design | exact mismatch evidence | retain preferred for audit |
| RunAnalysis exception/nonzero | scratch/mutation identities | AnalysisResultIdentity/DesignResultIdentity | source integrity + statuses if safe | retain or cleanup by policy |
| partial case failure | same | AnalysisResultIdentity | all intended case statuses | same |
| StartDesign exception/nonzero | valid AnalysisResultIdentity may remain | DesignResultIdentity | source integrity + analysis identity | same |
| result acquisition failure | analysis identity; completed attempt fact may exist | DesignResultIdentity unless completeness met | population completeness | retain if needed |
| cleanup failure | historical qualified facts remain facts | CLEANED_UP claim | source integrity mandatory | record retained scratch/path |

## 14. Minimum future production write sets

### B4A — DERIVED-STATE-1

- scratch lifecycle controller;
- physical source integrity snapshot/comparison;
- causal scratch ownership identity;
- one bounded exact file copy/open/save strategy after live proof;
- active-model path readback;
- cleanup/failure disposition.

Likely API gaps: `File.OpenFile`; possibly `File.Save(FileName)` depending chosen strategy.  
Status: `NEW_REQUIRED`.

### B4B — ANALYSIS-STATE-MUTATION-1

- typed domain-bounded mutation commands only;
- verified-scratch precondition;
- lock control only if required;
- per-set ret/readback/tolerance;
- mutation manifest;
- result/design identity invalidation marker.

No generic arbitrary SapModel execution API.  
Status: `NEW_REQUIRED`.

### B5 — ANALYSIS-EXEC-1

- run-flag read/set wrapper;
- controlled RunAnalysis;
- case-status postqualification using current safety semantics;
- optional exact stale-result clearing policy;
- causal execution-attempt proof;
- sole trusted AnalysisResultIdentity issuer.

Status: `NEW_REQUIRED`.

### B6 — DESIGN-EXEC-1

- design-state factual preflight;
- controlled `DesignConcrete.StartDesign`;
- result-availability/completeness qualification;
- causal DesignResultIdentity issuer;
- explicit guard that RunAnalysis is unreachable from B6.

Status: `NEW_REQUIRED`.

## 15. Required final answers

### 1. Exact operations required for B4A

At minimum source/scratch path and lock reads plus a controlled scratch creation/open strategy. CSI exact candidates are `File.OpenFile(FileName)`, `File.Save(FileName)` if save-to-path is chosen, `GetModelFilename(True)` / `GetModelFilepath()`, and `GetModelIsLocked()`. Physical copy/hash/size/mtime is outside CSI. Final strategy still needs live proof.

### 2. Exact operations required for B4B

Only specific analysis-affecting setters required by the approved derived-state plan, each paired with exact readback. `SetModelIsLocked` may be necessary but is not assumed. No generic writer is justified.

### 3. Exact operations required for B5

`Analyze.GetRunCaseFlag`, `Analyze.SetRunCaseFlag`, `Analyze.RunAnalysis`, `Analyze.GetCaseStatus`; optionally `Analyze.DeleteResults` under an explicit freshness policy. Current GetCaseStatus mechanics are reusable.

### 4. Exact operations required for B6

For concrete design: factual `DesignConcrete.GetCode`, actual selected design-combo acquisition, `DesignConcrete.StartDesign`, `DesignConcrete.GetResultsAvailable`, then current `GetDesignSection` / `GetSummaryResultsColumn` reads as required by completeness. StartDesign is B6-only.

### 5. Reusable wrappers/mechanics

Gateway attach/STA/bounded execution; safety identity/unit/lock/capability reads; DatabaseTables and Results.Setup transactions; Analyze.GetCaseStatus; current factual OAPI reads; SourceModelIdentity/EvidenceEpoch; analysis-lineage no-positive-issuer rule.

### 6. Raw SapModel operations needing bounded work

`File.OpenFile`, `File.Save(FileName)` if chosen, `SetModelIsLocked`, `Analyze.GetRunCaseFlag`, `SetRunCaseFlag`, `RunAnalysis`, `DeleteResults`, missing design-state reads such as `DesignConcrete.GetCode`/`GetResultsAvailable`, and `DesignConcrete.StartDesign`. Product code must never receive raw SapModel.

### 7. What can mutate the source model?

Any save to source path; setter operations while source is active; and potentially analysis/design/open/close behavior if ETABS silently writes. Explicit save/set mutation is obvious; silent write behavior is live-verification material. Future architecture should avoid all execution/mutation on source.

### 8. What invalidates analysis results?

Product-level: every analysis-affecting mutation invalidates prior AnalysisResultIdentity regardless of retained ETABS rows. CSI explicitly offers `Analyze.DeleteResults`; ETABS automatic invalidation from unlock/property changes requires live proof.

### 9. What invalidates design results?

Product-level: invalid AnalysisResultIdentity invalidates dependent DesignResultIdentity; design-state mutation after design also invalidates it. ETABS persistence/clearing across save/open or design-state changes requires live proof.

### 10. Can StartDesign cause hidden analysis execution?

Not proven. CSI only proves it fails if analysis results are unavailable. `LIVE_VERIFICATION_REQUIRED`. B6 is permanently forbidden from explicitly calling RunAnalysis.

### 11. State/readback evidence available today

Exact model path, lock, units, PID/attach strategy/version, DatabaseTables selection, Results.Setup selection, case status/readiness, load/case/combo factual inventory, object facts, concrete design section/column summary, SourceModelIdentity and EvidenceEpoch.

### 12. Claims still requiring LIVE ETABS verification

Source silent writes; scratch open/switch semantics; copy/save preservation of analysis/design results; unlock/mutation automatic invalidation; RunAnalysis partial/failure persistence; StartDesign hidden analysis; concrete design freshness/clearing; cleanup/reopen semantics; physical source before/after for every transition.

### 13. Minimum production write set per later sprint

B4A: scratch lifecycle + source integrity + bounded file strategy.  
B4B: exact typed mutation writers + readback/manifest/invalidation.  
B5: run flags + RunAnalysis + status qualification + causal AnalysisResultIdentity issuer.  
B6: design-state preflight + StartDesign + completeness + causal DesignResultIdentity issuer.

## 16. Stop-condition findings

Research revealed future gaps that R-LIFE-1 must not implement:

```text
File.OpenFile wrapper                  NEW_REQUIRED (B4A)
File.Save(FileName) wrapper if used   NEW_REQUIRED (B4A)
analysis mutation writers              NEW_REQUIRED (B4B)
Analyze.Get/SetRunCaseFlag wrappers    NEW_REQUIRED (B5)
Analyze.RunAnalysis wrapper            NEW_REQUIRED (B5)
Analyze.DeleteResults wrapper if used  NEW_REQUIRED (B4B/B5 policy)
DesignConcrete.StartDesign wrapper     NEW_REQUIRED (B6)
AnalysisResultIdentity positive issuer NEW_REQUIRED (B5)
DesignResultIdentity/freshness issuer  NEW_REQUIRED (B6)
```

No implementation was performed.

## 17. Evidence ledger

### Current exact base

- `packages/etabs_gateway/src/etabs_gateway/connection.py`
- `packages/etabs_gateway/src/etabs_gateway/context_reader.py`
- `packages/etabs_gateway/tests/test_boundary_guards.py`
- `tbdy_engine/etabs/safety.py`
- `tbdy_engine/etabs/_safety_legacy.py`
- `tbdy_engine/etabs/oapi/*`
- `tbdy_engine/engine/unit_context.py`
- `tbdy_engine/integration/live_etabs_acquisition_context.py`
- `tbdy_engine/integration/etabs_analysis_lineage.py`
- `tests/etabs/test_oapi_layer1_architecture_guards.py`

### Historical repository

- `sprint/p1-typed-etabs-gateway-foundation` @ `0ee5d37008d3d5480590af6c11de558c4dbd0f41`
- `sprint/p1-1-dedicated-sta-worker` @ `b23253b381292e8db2115bac3ece3802b3f16717`
- `sprint/f0-5-analysis-basis-lifecycle` @ `dbb97e554a14807f7d462bde9b9c3d9728cef46e`
- `sprint/id-lineage-1-analysis-lineage` @ `adea99fd5adc5510ed39cffde2b72f8c4908a85d`
- `sprint/stab-1-second-order-analysis-basis-closure` @ `f0f0e20851906db5411cd7717123808c1562db64`
- `sprint/single-production-execution-authority` @ `5ccad11f559b82a92bbc39f68225757cd1085923` — application execution authority, not ETABS RunAnalysis ownership
- G0 archaeology reports — requirements/oracles only

### CSI contract candidate surfaces inspected

`cFile.OpenFile`, `cFile.Save`, `cFile.GetFilePath`, `cSapModel.GetModelFilename`, `cSapModel.GetModelFilepath`, `GetModelIsLocked`, `SetModelIsLocked`, `InitializeNewModel`, `cAnalyze.CreateAnalysisModel`, `DeleteResults`, `GetCaseStatus`, `GetRunCaseFlag`, `SetRunCaseFlag`, `RunAnalysis`, and concrete design `GetCode`, `GetResultsAvailable`, `SetCode`, `SetComboStrength`, `Get/SetDesignSection`, `GetSummaryResultsColumn`, `GetSummaryResultsBeam`, `StartDesign`.

## 18. Final research state

```text
R-LIFE-1
= READY_FOR_SUPERVISOR_REVIEW

MERGE_READY
= NOT DECLARED

CANONICAL
= NOT DECLARED

PRODUCTION IMPLEMENTATION
= NONE

LIVE ETABS MUTATION / RUN / DESIGN
= NONE
```
