# TBDY ENGINE CANONICAL ARCHITECTURE CONSTITUTION

**Constitution version:** `2.0-draft`  
**Baseline audited:** `46ed7f087290393786bd06feef3a7598a67805fd`  
**Baseline state:** Wall Inventory + Wall Packs A/B/C merged  
**Pending ratification:**
- B1 registration/composition implementation
- ETABS Safety Foundation exact implementation

> **FROZEN CONSTITUTIONAL RULE**
>
> All implementation workers MUST conform to this constitution.
>
> If a requested task conflicts with a MUST/MUST NOT rule, the worker MUST
> stop and report the conflict rather than silently creating a parallel
> architecture.

This document distinguishes four kinds of statements:

- **FROZEN CONSTITUTIONAL RULE** — normative architecture. Implementations MUST conform unless this constitution is amended through Section 30.
- **CURRENT IMPLEMENTATION** — behavior verified on the audited baseline only. It is descriptive, not automatically normative.
- **LEGACY DEBT** — accepted existing behavior that violates or bypasses a constitutional rule and MUST be migrated, not copied.
- **PENDING IMPLEMENTATION RATIFICATION** — semantics are frozen, but the exact class, module, function, or API shape is intentionally not frozen until the relevant implementation sprint is reviewed.

The conformance classifications used in this document are:

- `CONFORMING`
- `PARTIALLY_CONFORMING`
- `LEGACY_DEBT`
- `PENDING_IMPLEMENTATION`
- `NOT_IMPLEMENTED`

---

## 1. Status and scope

### FROZEN CONSTITUTIONAL RULE

This document is the normative architecture constitution for TBDY Engine. It governs the boundaries by which ETABS evidence becomes factual features, derived engineering quantities, check execution, formal results, assessment, and reporting.

The constitution governs, at minimum:

1. ETABS session acquisition and display-table acquisition.
2. Raw factual evidence and canonical tables.
3. Raw result evidence and result-row identity.
4. Feature resolution and factual `FeatureSnapshot`.
5. Reviewed load-family binding, result selection, `EngineeringQuantity`, and `SelectionTrace`.
6. Regulatory/project context grains.
7. Coverage/readiness.
8. Typed `CheckInput` and `CheckExecutionContext`.
9. `CheckEngine` and pure evaluators.
10. Canonical `CheckResult`.
11. Assessment/reconciliation.
12. Reporter behavior.
13. Registration and composition.
14. Units and provenance.
15. Compatibility and migration of legacy authorities.
16. Parallel-worker ownership and integration rules.

The audited baseline is exactly `46ed7f087290393786bd06feef3a7598a67805fd`. Unmerged work from B1 Beam + Column Canonicalization and ETABS Safety Foundation is not accepted implementation evidence for this document.

The semantics of registration/composition and ETABS session safety are frozen here. Their exact implementation shapes are **PENDING IMPLEMENTATION RATIFICATION**.

### Product target

**PRODUCT TARGET: FULL TBDY ENGINE.**

TBDY Engine is NOT constitutionally a screening-only engine. Partial vertical slices MAY be useful and MAY be reported as partial/domain results, but they MUST NOT be promoted to full-code compliance.

Until every mandatory TBDY domain applicable to the assessed scope has:

- authoritative source/context,
- implemented formal checks,
- complete Coverage,
- canonical Assessment,

the product-level gate MUST report:

```text
full_tbdy_compliance_status = NOT_EVALUATED
```

A successful wall, beam, material, modal, or other partial slice MUST NOT be promoted to `FULL TBDY PASS`.

### CURRENT IMPLEMENTATION

The accepted wall path is the strongest current reference implementation. Beam/column geometry has part of the same canonical execution machinery. Material and result-based domains still contain product/report-owned authority. ETABS acquisition has usable connection/fetch foundations but does not yet satisfy the complete safety constitution.

### Integration boundary

Changes cross the constitutional boundary when they introduce or change any owner of:

- raw evidence,
- feature facts,
- reviewed shared context,
- candidate result binding/selection,
- derived engineering quantities,
- coverage/readiness,
- regulatory applicability,
- limits,
- engineering comparison/formula authority,
- verdict/status,
- formal result construction,
- assessment completeness,
- reporting.

Any such change MUST be evaluated against this constitution before merge.

---

## 2. Product objective

### FROZEN CONSTITUTIONAL RULE

TBDY Engine MUST produce engineering conclusions that are deterministic, auditable, reproducible, fail-closed, and attributable to explicit source evidence and explicit reviewed policy/context.

The product objective is not merely to produce a report that looks correct. The product MUST be able to answer, for every formal check result:

- What source evidence was used?
- What units did the source evidence use?
- Which factual features were resolved?
- What reviewed building/system/direction/reference truth was consumed?
- What candidate result rows existed?
- Which exact load-family/case/combo binding was reviewed and frozen?
- If rows were selected, why were they included or excluded?
- Was the required evidence capture complete?
- Which `EngineeringQuantity`, if any, was derived by selection?
- Which execution context/policy was required?
- Which check owned applicability?
- Which rule/limit/formula produced the comparison?
- Which canonical result object recorded the conclusion?
- Whether all expected checks were present exactly once?
- Whether the reporter merely serialized the already-decided result?

A product output that cannot answer those questions MUST NOT be treated as complete canonical engineering evidence.

### Decision ownership

- Acquisition owns retrieval fidelity and source/session state evidence.
- Feature resolution owns factual interpretation only.
- Reviewed context authorities own reviewed building/system/direction/reference truth at their proper grain.
- Result binding/selection owns deterministic candidate binding and derived `EngineeringQuantity` only.
- Coverage owns availability/readiness only.
- `CheckEngine` owns regulatory decisions.
- Assessment owns structural reconciliation only.
- Reporter owns presentation only.

No layer MAY silently inherit another layer's authority.

---

## 3. Constitutional principles

### FROZEN CONSTITUTIONAL RULE

The following principles are constitutional invariants.

1. **One authority per decision.** The same engineering decision MUST NOT be independently recomputed by multiple production paths.
2. **Facts before rules.** Source evidence and factual features MUST be separated from regulatory interpretation.
3. **Reviewed context at true grain.** Building, structural-system, direction, story/reference, component, and check-execution truth MUST live at the grain at which it is true.
4. **One execution boundary.** Formal engineering execution MUST cross through typed `CheckInput` plus explicit `CheckExecutionContext`.
5. **One regulatory authority.** `CheckEngine` MUST be the sole production authority for check applicability, limits, comparison/formula orchestration, ratio semantics, status, and formal `CheckResult` creation.
6. **One formal result DTO.** There MUST be one canonical `CheckResult` type. Parallel “formal” dictionaries or DTOs MUST NOT become independent authorities.
7. **Fail closed.** Missing mandatory fact, unit, context, identity, reviewed binding, or complete result capture MUST produce a blocked/not-runnable state, not a guessed pass/fail.
8. **Provenance is data.** Source identity and transformation evidence MUST travel with the facts/results they support.
9. **Selection is not compliance.** Result-row selection MUST NOT decide PASS/FAIL.
10. **Coverage is not compliance.** Coverage/readiness MUST NOT decide engineering status.
11. **Assessment is not engineering.** Assessment MUST reconcile expected versus observed formal results and MUST NOT recompute check formulas.
12. **Reporting is not engineering.** Reporter code MUST NOT own thresholds, ratios, regulatory row selection, unit inference, or statuses.
13. **No hidden state.** ETABS state mutation/acquisition MUST be explicit, bounded, observable, and serialized through the canonical acquisition owner where mutation is required.
14. **No heuristic authority.** Name, magnitude, default-unit, lexical, first-match, or similar heuristics MUST NOT become authoritative input to canonical engineering execution.
15. **Delete duplicate authority last.** Migration MUST first establish canonical equivalence and acceptance, then remove legacy decision code.
16. **Generalize semantics, not data bags.** Shared contracts SHOULD encode shared invariants while domain facts and policies remain typed and domain-specific.
17. **Full-code gate remains explicit.** Partial domain success MUST NOT imply full TBDY compliance.

### Fail-closed default

Where this constitution does not explicitly grant decision authority, a layer MUST NOT invent it. If canonical execution cannot determine the required input or policy through an authorized source, it MUST block.

---

## 4. Canonical end-to-end architecture

### FROZEN CONSTITUTIONAL RULE

TBDY Engine has two legitimate canonical evidence lanes that converge at the typed execution dependency boundary. They MUST NOT be forced into a false single representation.

### 4.1 Factual lane

```text
ETABS acquisition
    -> Raw Evidence / CanonicalTable
    -> FeatureResolver
    -> FeatureSnapshot
```

`FeatureSnapshot` is factual only. This lane is appropriate for geometry, material facts, assignments, topology, reviewed factual references, and other source facts.

### 4.2 Result lane

```text
ETABS acquisition
    -> Raw Result Evidence
       (source-specific identity + payload + RuntimeCaptureStatus)
    -> ReviewedLoadFamilyBinding / exact reviewed binding authority
    -> ResultSelectionPolicy
    -> EngineeringQuantity + SelectionTrace
```

This lane is required when a formal check depends on selecting or deriving a governing quantity from candidate result rows, modes, cases, combinations, stories, directions, stations, steps, or envelopes.

A selected raw factual row/component MAY be represented as factual evidence where it remains a source fact. A policy-derived governing engineering demand MUST NOT be disguised as a raw factual `FeatureSnapshot` merely to make the architecture look uniform.

### 4.3 Convergence boundary

The two lanes converge as typed dependencies:

```text
factual FeatureSnapshot
    +
derived EngineeringQuantity / selection evidence
    +
reviewed/shared typed contexts
    -> Coverage
    -> typed CheckInput + CheckExecutionContext
    -> CheckEngine
    -> canonical CheckResult
    -> Assessment
    -> Reporter
```

A check MAY consume only factual dependencies, only a derived engineering quantity plus reviewed context, or both, depending on its frozen contract.

### 4.4 Boundary ownership

| Boundary | Owner | MUST NOT own | Fail-closed trigger |
|---|---|---|---|
| ETABS -> raw evidence | acquisition/provider | code limits, verdicts | session/source ambiguity, failed fetch |
| raw evidence -> factual feature | resolver | applicability, pass/fail | missing/ambiguous factual mapping or unit |
| raw result -> exact binding | reviewed binding authority | regulatory verdict | missing/unreviewed binding |
| bound result -> `EngineeringQuantity` | `ResultSelectionPolicy` | regulatory limit/status | incomplete required capture, unresolved policy |
| typed dependencies -> runnable check | Coverage + input adapter | engineering verdict | missing feature/quantity/context/readiness |
| runnable check -> formal result | CheckEngine | presentation | unresolved mandatory policy, invalid input |
| result set -> assessment | Assessment | engineering recomputation | missing/duplicate expected results |
| assessment/result -> output | Reporter | calculations/selection/status | malformed canonical artifact |

A layer MAY add diagnostics, but diagnostics MUST NOT secretly become a second decision authority.

---

## 5. Authority matrix

### FROZEN CONSTITUTIONAL RULE

The following matrix is authoritative.

| Decision / artifact | Sole or primary owner | Explicitly prohibited owners |
|---|---|---|
| ETABS instance/session attachment | ETABS acquisition boundary | reporter, evaluator, feature resolver |
| ETABS read/display state transaction | ETABS acquisition boundary | domain resolver, reporter |
| raw table payload | provider/acquisition | CheckEngine, reporter |
| canonical table normalization | canonical table/provider layer | reporter |
| factual feature value | FeatureResolver | CheckEngine policy layer may consume but MUST NOT fabricate source facts |
| building/system/direction/reference truth | reviewed context authority at the correct grain | component feature bag, reporter, hidden global |
| source unit identity | acquisition/evidence | reporter, evaluator |
| explicit unit conversion | authorized factual normalization using explicit unit metadata | magnitude/name heuristic |
| result-row identity | raw result evidence layer | reporter |
| capture completeness | result acquisition/evidence | result selector, reporter MUST consume but not invent |
| reviewed exact load/case/combo binding | reviewed binding authority | runtime regex/name matcher |
| result candidate selection / derived quantity | `ResultSelectionPolicy` | reporter, product check builder, pure evaluator |
| selection audit trail | `SelectionTrace` | `CheckResult` status logic |
| feature/dependency availability | Coverage | CheckEngine status logic |
| execution context readiness | Coverage + `CheckExecutionContext` validation | hidden globals/defaults |
| regulatory applicability | CheckEngine | resolver, selection, coverage, reporter |
| regulatory limit | CheckEngine/catalog-backed canonical check authority | reporter/product report/legacy module |
| formula/comparison orchestration | CheckEngine | reporter, assessment |
| pure mathematical kernel | pure evaluator | reporter |
| check status/verdict | CheckEngine | reporter, assessment, product report helper |
| formal result construction | CheckEngine | reporter/product parallel DTO builder |
| expected-vs-observed reconciliation | Assessment | reporter |
| structural completeness | Assessment | reporter |
| product-level full TBDY gate | canonical product assessment | individual domain slice/reporter |
| formatting/localization | Reporter | CheckEngine SHOULD NOT own presentation formatting |

### Integration boundary

Any new production code that contains a regulatory threshold, PASS/FAIL/OK decision, runtime result-row governing choice, runtime case-name matching, or unit inference MUST identify its constitutional owner during review. If the owner is not the authorized layer above, the change MUST be rejected or redesigned.

---

## 6. Context grain model

### FROZEN CONSTITUTIONAL RULE

The canonical regulatory/project context model has these grains:

```text
MODEL
BUILDING
STRUCTURAL_SYSTEM
DIRECTION
STORY / LEVEL
COMPONENT
CHECK_EXECUTION
```

Context MUST be modeled at the grain at which it is true. Building/system/reference truth MUST NOT be copied into per-component factual truth merely for convenience. A giant undifferentiated `ModelContext` that mixes these grains is constitutionally prohibited.

ETABS session/table/result evidence grains MAY additionally exist as acquisition/evidence storage grains, but they MUST NOT replace the regulatory context grain model above.

### 6.1 MODEL

**Owner:** model/acquisition factual authority.

MODEL context contains model-wide facts such as:

- model identity/fingerprint,
- coordinate/source-system facts,
- factual analysis/session state,
- model-level source provenance.

MODEL MUST NOT become a container for every building, structural-system, direction, story, component, or check-specific regulatory dependency.

**Fail closed:** if the model identity/fingerprint needed to bind reviewed context to evidence cannot be established, dependent canonical execution MUST block.

### 6.2 BUILDING

**Owner:** reviewed building-level regulatory/project authority.

BUILDING context contains building-level reviewed regulatory/project truth. Examples MAY include reviewed classifications or project parameters that genuinely apply to the entire building.

BUILDING truth MUST NOT be inferred from one component, one report row, or one ETABS naming convention. It MUST NOT be duplicated into every component feature merely for convenience.

**Integration boundary:** typed downstream contexts MAY reference the reviewed building authority; component resolvers MUST NOT recreate it.

### 6.3 STRUCTURAL_SYSTEM

**Owner:** reviewed structural-system authority.

STRUCTURAL_SYSTEM context contains reviewed structural-system truth at the structural-zone/system grain where it is valid.

Where a rule is direction-dependent, structural-system authority MUST be keyed at least by:

```text
structural_zone × direction
```

There MUST NOT be a global `R`, `D`, structural-system, or equivalent fallback where directional authority is required.

**Fail closed:** if the applicable structural zone/system cannot be resolved for the requested direction, the dependent check is not runnable.

### 6.4 DIRECTION

**Owner:** reviewed direction-specific regulatory/system authority.

DIRECTION context contains truth that is specific to X/Y or another explicit analysis/regulatory direction, including the directional view of structural-system authority where applicable.

A direction-dependent rule MUST consume an explicit direction binding. Direction MUST NOT be guessed from case-name substrings or component orientation unless that mapping is itself an authoritative reviewed fact.

### 6.5 STORY / LEVEL

**Owner:** reviewed story/reference authority plus factual level evidence.

STORY / LEVEL context contains, where applicable:

- elevation,
- story height,
- reviewed `ReferenceRole` bindings,
- explicit level/story identity needed by checks.

Reference roles MUST be reviewed/frozen authority. A check MUST NOT choose a reference level by lexical story name, first/last row, or convenience ordering when the regulatory meaning requires an explicit binding.

### 6.6 COMPONENT

**Owner:** factual component resolver/evidence layer.

COMPONENT context contains factual component truth such as:

- geometry,
- material,
- topology,
- assignments,
- component/object identity,
- source evidence references.

COMPONENT MUST NOT own reviewed building/system/direction/reference truth merely because duplicating those values would simplify a DTO.

### 6.7 CHECK_EXECUTION

**Owner:** typed execution-context assembly consumed by `CheckEngine`.

CHECK_EXECUTION contains only the exact frozen dependencies required by one check instance, bound from the appropriate factual/result/context authorities.

It MAY include:

- check id,
- code/design basis,
- exact direction,
- exact structural-system/reference bindings,
- exact selection-policy identity,
- exact engineering quantity/evidence references,
- other mandatory policy/context explicitly required by that check.

It MUST NOT become a second giant model context or a location for hidden defaults.

**Fail closed:** any unresolved mandatory dependency makes the check not runnable.

### Acquisition/evidence storage grains

Session, table, raw-result bundle, parser, and provenance grains MAY be modeled separately for acquisition/storage. They are evidence organization, not substitutes for MODEL/BUILDING/STRUCTURAL_SYSTEM/DIRECTION/STORY/COMPONENT/CHECK_EXECUTION regulatory context.

---

## 7. Provenance and review model

### FROZEN CONSTITUTIONAL RULE

Every canonical factual feature and every derived `EngineeringQuantity` used by a check MUST be reviewable back to source evidence and reviewed authority.

At minimum provenance SHOULD support:

- source mode (`live`, `replay`, or other explicit source type),
- model/session identity,
- source table name,
- source field/column identity,
- source row or row-set identity,
- raw source value,
- source unit,
- normalized value and normalized unit,
- reviewed binding identity/version where result binding occurred,
- result-selection policy identity/version where selection occurred,
- selection trace identity,
- capture status for result evidence,
- reviewed context references,
- diagnostics that explain missing/ambiguous evidence.

Provenance MUST describe what happened; it MUST NOT be used as a hidden location for regulatory policy.

### Review invariant

A reviewer MUST be able to inspect a `CheckResult` and traverse backward to the factual evidence, derived quantity/selection trace, reviewed context, and policy that produced it without rerunning reporter calculations.

### Separation of identity and payload

For result evidence, identity MUST be represented separately from numeric payload so that two rows with equal values are not collapsed merely because their payloads match.

---

## 8. ETABS acquisition constitution

### FROZEN CONSTITUTIONAL RULE

ETABS acquisition owns connection, session identity, source/database/present unit evidence, table/result retrieval, parsing handoff, and any temporary ETABS display/read-state transaction required for retrieval.

It MUST NOT own TBDY applicability, code limits, engineering verdicts, or reporter presentation.

### 8.1 Session identity

Canonical live acquisition MUST establish enough identity to reject an ambiguous, stale, wrong, or unusable ETABS target. Model filename alone MAY be evidence but MUST NOT be assumed sufficient if multiple instances or stale COM objects can be confused.

Connection success MUST mean more than “a COM object exists.” The acquisition boundary SHOULD verify a coherent SapModel/database-table surface and record the verified identity.

### 8.2 Canonical unit acquisition rule

Canonical ETABS acquisition MUST NOT call:

```text
SetPresentUnits(...)
SetPresentUnits_2(...)
```

merely to normalize data.

The canonical strategy is:

```text
read source/present/database units
    -> preserve unit provenance
    -> convert in Python downstream using explicit unit contracts
```

Temporary transaction semantics do NOT make unit normalization through `SetPresentUnits` canonical.

A legacy explicitly mutating compatibility API MAY exist temporarily, but it MUST be clearly non-canonical, MUST NOT be the default acquisition path, and MUST NOT silently feed canonical engineering as if its mutation were source-unit provenance.

### 8.3 Read/display state

A fetcher MAY need to select a case or combination for display because ETABS can return headers/record counts without usable table data until display selection is set.

Where such state mutation is genuinely required for acquisition, it MUST be treated as an explicit bounded transaction under the ratified ETABS Safety implementation:

1. identify the current state where the API permits it,
2. record intended mutation,
3. apply only the minimum mutation required,
4. fetch,
5. restore prior state where restoration is supported/required,
6. record restoration success/failure,
7. fail closed if the acquired evidence cannot be trusted.

This display-state transaction permission MUST NOT be interpreted as permission to call `SetPresentUnits` for canonical normalization.

Hidden or unbounded ETABS state mutation is prohibited.

### 8.4 One live acquisition owner

There MUST be **ONE LIVE ETABS ACQUISITION OWNER AT A TIME** per live ETABS session within the enforced repository/process scope.

Canonical ETABS state mutation/acquisition through that boundary MUST be serialized. After acquisition, immutable evidence MAY be consumed in parallel.

The constitution does NOT claim cross-process or OS-global locking unless a concrete implementation proves and ratifies such a guarantee.

### 8.5 Acquisition output

Acquisition output MUST expose retrieval diagnostics sufficient to distinguish:

- call failure,
- empty table,
- header-only response,
- records-reported-but-data-empty response,
- successful parsed rows,
- `PARTIAL`, `SAMPLED`, `TRUNCATED`, or `UNKNOWN` capture where applicable,
- unsupported signature/API shape.

### CURRENT IMPLEMENTATION

`tbdy_engine/etabs/connection.py` attaches through helper/GetActiveObject fallbacks and validates a SapModel/table surface. It also calls `SetPresentUnits(6)` during connect and again in `get_sap()`. That behavior is **LEGACY DEBT** relative to the canonical unit-acquisition rule; restoration would not make it the canonical normalization strategy.

`tbdy_engine/providers/etabs_display_table_fetcher.py` probes multiple display-table COM signatures and records detailed fetch/parser diagnostics. It can call `SetLoadCombinationsSelectedForDisplay` or `SetLoadCasesSelectedForDisplay` before fetch. The audited baseline does not provide the ratified serialized acquisition owner plus snapshot/restore transaction contract around that mutation.

No separate `etabs_com_attach.py` exists at the audited baseline under the inspected repository paths. The attachment responsibility is currently represented by `tbdy_engine/etabs/connection.py`.

### PENDING IMPLEMENTATION RATIFICATION

The exact ETABS Safety Foundation class/module/API structure is not frozen. The semantic requirements in this section are frozen, including the no-`SetPresentUnits` canonical normalization rule and the one-live-acquisition-owner rule.

---

## 9. Raw result identity and capture

### FROZEN CONSTITUTIONAL RULE

Result evidence MUST distinguish row identity, row payload, and capture completeness.

### 9.1 Result row identity is not payload component

```text
RESULT ROW IDENTITY != PAYLOAD COMPONENT
```

There is no universal ETABS result-row identity. Identity is source-specific and MUST be defined from the source schema/grain required to distinguish candidate rows.

For a wide Pier Force-style source, identity may include, as applicable:

- `Story`,
- `Pier`,
- `OutputCase`,
- `CaseType`,
- `StepType`,
- `StepNumber`,
- `Location`.

Its payload may include:

- `P`,
- `V2`,
- `V3`,
- `T`,
- `M2`,
- `M3`.

`P`, `M3`, or another payload component MUST NOT automatically become row identity merely because a check requests that component.

A long-form ETABS source MAY legitimately include a component/quantity discriminator in identity when the source itself represents each component as a distinct row. The identity contract MUST follow the authoritative source shape rather than impose one universal key set.

Equal numeric payload does not imply equal identity.

### 9.2 RuntimeCaptureStatus

Canonical `RuntimeCaptureStatus` semantics are exactly:

- `FULL` — the required source population is proven complete.
- `PARTIAL` — usable evidence exists but the required population is incomplete.
- `SAMPLED` — acquisition intentionally contains a sampled subset rather than the required complete population.
- `TRUNCATED` — the source/acquisition is known to have been cut short.
- `UNKNOWN` — completeness cannot be established.

These are the canonical capture statuses. They MUST NOT be collapsed, renamed, or weakened in a way that erases any of the distinctions above.

### 9.3 Complete-population rule

For any selection, governing demand, or envelope that requires the complete source population:

```text
RuntimeCaptureStatus != FULL
    -> governing engineering demand unresolved
    -> formal execution BLOCKED
```

The visible maximum/minimum of a `PARTIAL`, `SAMPLED`, `TRUNCATED`, or `UNKNOWN` bundle MUST NOT be promoted to governing demand.

### CURRENT IMPLEMENTATION

`tbdy_engine/features/result_evidence.py` provides shared result-evidence bundle/capture foundations and is a valid foundation, but repository-wide adoption and the exact five-status contract are not yet complete across modal, drift, torsion, and future result consumers.

---

## 10. Result-selection constitution

### FROZEN CONSTITUTIONAL RULE

Result selection is a first-class boundary between raw result evidence and check execution. It produces selected/derived engineering evidence, not regulatory compliance.

### 10.1 Reviewed load-family / exact binding authority

Formal runtime result selection MUST consume an exact reviewed and frozen binding, not a runtime naming heuristic.

The allowed production pattern is:

```text
reviewed + versioned binding rule
    -> expand against the exact current ETABS case/combo inventory
    -> materialized exact binding manifest
    -> review/freeze
    -> ResultSelectionPolicy
```

Runtime heuristic authority is forbidden. Examples include:

- `"EQX" in case_name`,
- regex seismic-name matching,
- lexical preference,
- earthquake-looking names,
- first matching case.

Such heuristics MAY be used only for:

- discovery,
- suggestion,
- review assistance.

They MUST NOT become formal runtime authority even if a runtime policy flag would otherwise “authorize” the heuristic. Formal runtime selection consumes the exact frozen binding manifest.

### 10.2 ResultSelectionPolicy contract

A `ResultSelectionPolicy` MUST define, where relevant:

- policy id/version,
- requested engineering quantity,
- authoritative source,
- exact reviewed binding set,
- direction,
- analysis kind,
- `StepType`,
- `StepNumber`,
- sign semantics,
- Max/Min semantics,
- location/station semantics,
- envelope operator,
- tie semantics,
- completeness requirement.

There is NO default:

- `Max`,
- `Min`,
- `abs-max`,
- `Bottom`,
- `Top`,
- first row,
- lexical case,
- envelope operator,
- response-spectrum sign.

If any of those semantics matter to the requested quantity, they MUST be explicit in reviewed policy/binding authority.

### 10.3 Selection output and authority boundary

A `ResultSelectionPolicy` MAY derive an `EngineeringQuantity` and MUST emit a `SelectionTrace` sufficient to reconstruct that derivation.

It MUST NOT:

- apply final regulatory PASS/FAIL limits,
- issue final formal `OUT_OF_SCOPE`,
- create canonical `CheckResult`,
- use report layout needs to decide engineering selection,
- silently drop candidates without trace.

Regulatory applicability and final `OUT_OF_SCOPE` remain `CheckEngine` authority.

### Fail-closed behavior

If reviewed exact binding, requested selection semantics, or required capture completeness is unresolved, selection MUST return unresolved/blocked evidence. It MUST NOT choose a convenient case/row/operator.

---

## 11. SelectionTrace

### FROZEN CONSTITUTIONAL RULE

`SelectionTrace` is the deterministic audit artifact for result selection. It MUST be separate from the formal engineering verdict.

A conforming `SelectionTrace` MUST be capable of reconstructing, at minimum where relevant:

- policy ID/version,
- quantity ID,
- source bundle ID,
- model/source identity,
- capture status,
- requested component,
- requested story,
- requested direction,
- candidate count,
- eligible count,
- rejected rows/reason categories,
- selected exact case/combo,
- reviewed load family/binding identity,
- analysis kind,
- `StepType`,
- `StepNumber`,
- location/station,
- raw selected value,
- source unit,
- unit conversion,
- sign transformation,
- Max/Min interpretation,
- envelope operation,
- tie decision,
- final `EngineeringQuantity`,
- evidence refs.

The trace MAY contain additional candidate identities/diagnostics needed for review.

### Determinism invariant

```text
same immutable source bundle
+ same reviewed bindings
+ same request
+ same policy version
=> same SelectionTrace
```

A change in runtime iteration order, report ordering, import order, or lexical case ordering MUST NOT change the trace.

`SelectionTrace` MUST NOT contain a final regulatory PASS/FAIL/OUT_OF_SCOPE verdict. It MUST NOT become an alternate `CheckResult`.

### CURRENT IMPLEMENTATION

A shared, domain-neutral `SelectionTrace` with the complete semantics above is **NOT_IMPLEMENTED** on the audited baseline. Domain/product selection logic exists, but it is not yet the canonical traceable boundary required here.

---

## 12. FeatureSnapshot constitution

### FROZEN CONSTITUTIONAL RULE

`FeatureSnapshot` is the immutable factual boundary consumed by Coverage and check-input assembly.

It MAY contain:

- factual feature values,
- explicit units,
- entity identity,
- source/evidence references,
- factual diagnostics,
- selected raw factual row/component evidence where the selection does not transform the fact into a policy-derived governing demand.

It MUST NOT contain:

- regulatory PASS/FAIL/OK status,
- hidden code limits,
- check applicability decisions,
- report-specific formatting,
- inferred policy defaults that belong to execution context,
- policy-derived governing `EngineeringQuantity` disguised as a raw fact.

Feature resolvers MUST produce facts, not verdicts or governing-demand policy results.

### Integration boundary

Coverage MAY consume factual `FeatureSnapshot` dependencies together with separately derived `EngineeringQuantity`/selection evidence and reviewed typed context. A policy-derived result quantity does not need to be copied into `FeatureSnapshot` to cross the execution boundary.

CheckEngine MUST consume typed inputs built from the authorized dependency/readiness boundary rather than reaching backward into ETABS/provider code.

---

## 13. Coverage constitution

### FROZEN CONSTITUTIONAL RULE

Coverage is the canonical availability/readiness gate between authorized dependencies and formal check execution.

Canonical Coverage readiness statuses are exactly:

- `RUNNABLE`
- `PARTIAL`
- `BLOCKED`

Coverage owns readiness only.

Coverage owns questions such as:

- Is the required factual feature present?
- Is the required derived `EngineeringQuantity` resolved?
- Is source evidence usable?
- Is the unit explicit and acceptable?
- Is required result capture complete?
- Is mandatory reviewed context resolved?
- Is the typed check input constructible?

Coverage MUST NOT answer:

- Does the check apply under the code?
- What is the regulatory limit?
- Does the element pass?
- What ratio/status should be reported?
- Is the final formal result `OUT_OF_SCOPE`?

Those remain `CheckEngine` authority.

### Readiness semantics

- Missing authority or ambiguous semantic meaning -> `BLOCKED`.
- Missing mandatory context -> `BLOCKED`.
- Incomplete required result capture -> `BLOCKED` or `PARTIAL` readiness as defined by the check/dependency contract, but a check requiring a complete population MUST NOT execute as a complete-envelope check.
- `PARTIAL` MUST remain visibly incomplete and MUST NOT be treated as `RUNNABLE` by convenience.

### NO_DATA rule

`NO_DATA` is NOT a generic synonym for missing information.

A formal `CheckResult.NO_DATA` MAY be produced only when:

1. all required semantics, source meanings, units, reviewed bindings, and mandatory contexts are fully resolved; **and**
2. the authoritative factual row/data is genuinely absent.

Missing information MUST NOT imply `OUT_OF_SCOPE` or `NOT_APPLICABLE`. Final formal `OUT_OF_SCOPE` belongs to `CheckEngine`.

### CURRENT IMPLEMENTATION

CoverageBuilder and accepted wall/geometry orchestration establish the correct boundary for those domains. Repository-wide adoption is incomplete; therefore Coverage is `PARTIALLY_CONFORMING` at system scope even though the wall reference is conforming.

---

## 14. CheckInput / CheckExecutionContext

### FROZEN CONSTITUTIONAL RULE

Formal execution MUST accept a typed `CheckInput` plus explicit `CheckExecutionContext` or an equivalent typed boundary preserving the same semantics.

`CheckInput` is the sole formal execution-data boundary. It MUST carry or explicitly reference the normalized dependencies required by the check, which MAY include:

- factual values originating from `FeatureSnapshot`,
- derived `EngineeringQuantity` plus selection/evidence references,
- subject/entity identity,
- normalized unit-bearing values required by contract.

`CheckExecutionContext` carries the exact reviewed/shared policy/context dependencies required by one check, bound from the correct MODEL/BUILDING/STRUCTURAL_SYSTEM/DIRECTION/STORY-or-LEVEL/COMPONENT/CHECK_EXECUTION authorities.

### Prohibited behavior

Formal execution MUST NOT depend on:

- reporter globals,
- hidden module constants outside the canonical check authority,
- mutable ETABS state,
- environment-dependent defaults,
- implicit unit assumptions,
- runtime case-name guesses,
- a resolver deciding regulatory policy,
- a giant untyped `ModelContext` that obscures dependency grain.

### Readiness

If mandatory execution context or a required engineering quantity is unresolved, the check is not runnable. The system MUST represent that state explicitly and MUST NOT manufacture a result by choosing an arbitrary default.

### CURRENT IMPLEMENTATION

`GeometryCheckInput` and `CheckExecutionContext` are used by accepted geometry/wall execution paths. Pack C wall orchestration freezes execution-context readiness through Coverage before invoking `engine.run_input()`. Unresolved Ndm policy authority blocks execution rather than producing a guessed verdict.

### Evolution rule

The project SHOULD generalize the semantics of `CheckInput` across domains while retaining domain-typed inputs. It SHOULD NOT replace typed domain inputs with a universal unvalidated dictionary merely to reduce class count.

---

## 15. CheckEngine constitution

### FROZEN CONSTITUTIONAL RULE

`CheckEngine` is the sole production regulatory authority.

For each canonical check, the engine owns or orchestrates:

1. check-id validation/registration,
2. regulatory applicability,
3. binding to the authoritative rule/limit,
4. formula/comparison orchestration,
5. ratio semantics,
6. status/verdict semantics,
7. canonical `CheckResult` construction.

The engine MAY delegate mathematical kernels to pure evaluators and MAY consume catalog data, but delegation MUST NOT transfer regulatory ownership to reporters, feature resolvers, result selectors, assessment, or compatibility modules.

### One-engine rule

The repository MUST NOT create domain-specific mini-engines that independently produce formal regulatory results. Domain-specific evaluators/registrations MAY compose into the canonical engine.

### Fail-closed behavior

Unknown check id, duplicate check registration, unresolved mandatory context, invalid normalized input, unresolved required `EngineeringQuantity`, or missing authoritative rule MUST fail deterministically. The engine MUST NOT infer a rule from a nearby check or silently fall back to product-report constants.

### CURRENT IMPLEMENTATION

`tbdy_engine/checks/engine.py` (`MinimalCheckEngine`) is the accepted canonical engine for the migrated wall and geometry checks. It already owns canonical geometry comparison/status for registered beam/column geometry checks and the accepted wall execution path. System-wide conformance is partial because several product/report and legacy design paths bypass it.

The class name `MinimalCheckEngine` does not itself violate the constitution. Semantic centrality matters more than cosmetic renaming.

---

## 16. Pure evaluator rules

### FROZEN CONSTITUTIONAL RULE

A pure evaluator MUST be deterministic mathematics over explicit typed arguments.

A pure evaluator MAY:

- compute a mathematical value,
- compute intermediate scalars,
- return structured mathematical diagnostics.

A pure evaluator MUST NOT:

- connect to ETABS,
- fetch tables,
- choose result cases/rows,
- infer units,
- choose regulatory applicability,
- own product/report formatting,
- construct the canonical formal result,
- read hidden mutable global policy.

Where a mathematical formula itself includes code-defined parameters, the engine MUST bind those parameters explicitly before or while invoking the evaluator so the policy origin remains auditable.

### Review test

If changing a pure evaluator can change which source row is selected or which code rule applies without changing its explicit arguments, the evaluator is not pure enough.

---

## 17. Canonical CheckResult

### FROZEN CONSTITUTIONAL RULE

There MUST be exactly one formal production `CheckResult` DTO, and `CheckEngine` MUST construct the final formal `CheckResult`.

The canonical formal `CheckResult.status` set is exactly:

- `OK` — the applicable formal check was evaluated and satisfied its canonical rule.
- `FAIL` — the applicable formal check was evaluated and failed its canonical rule.
- `WARNING` — the formal check produced a canonical warning state explicitly defined by its check contract; it is not a substitute for unresolved input.
- `NO_DATA` — all semantics/context/source meanings are resolved, but the authoritative factual data is genuinely absent under the check contract.
- `BLOCKED` — formal evaluation cannot be completed because a mandatory dependency, authority, context, capture requirement, or trusted execution condition is unresolved.
- `OUT_OF_SCOPE` — `CheckEngine` determined from sufficient authoritative context that the formal check is regulatorily outside the assessed scope.

No additional final formal status MAY be introduced without constitutional amendment.

A lower-level resolver, selector, acquisition operation, or compatibility layer MAY report its own operation-specific unresolved/not-applicable diagnostic state, but it MUST NOT manufacture final formal `CheckResult.OUT_OF_SCOPE`.

The canonical result SHOULD carry enough information to review:

- check identity,
- subject/entity identity,
- final formal status,
- normalized value(s) and/or derived engineering quantity,
- authoritative limit/rule identity where applicable,
- comparison/ratio semantics where applicable,
- execution-context identity or summary,
- evidence/provenance/selection-trace references,
- diagnostics required for review.

A reporter-friendly dictionary MAY serialize a canonical `CheckResult`, but it MUST NOT become a second formal result authority.

### Compatibility rule

Legacy APIs that currently return `check_result.v1`-style dictionaries MUST eventually delegate from canonical `CheckResult` and MUST NOT independently derive status, limits, or applicability.

### CURRENT IMPLEMENTATION

`tbdy_engine/checks/result.py` provides the canonical formal DTO used by the accepted engine/wall path. `tbdy_engine/product_reports/check_results.py` remains a parallel legacy result builder and is constitutional debt.

---

## 18. Assessment constitution

### FROZEN CONSTITUTIONAL RULE

Assessment is reconciliation, not engineering.

Assessment owns:

- expected check inventory for the assessed scope,
- observed canonical result inventory,
- missing expected result detection,
- duplicate result detection,
- structural completeness,
- deterministic aggregation of already-canonical statuses where the assessment contract requires an aggregate.

Assessment MUST NOT:

- recompute a limit,
- rerun an engineering formula,
- change applicability,
- select ETABS result rows,
- infer units,
- turn a blocked result into pass/fail.

### Completeness rule

A materially missing or duplicate expected result MUST prevent an assessment from claiming structurally complete canonical coverage.

### Full TBDY product gate

Domain assessment completeness is not full-code completeness. Until every mandatory TBDY domain applicable to the assessed scope has authoritative dependencies, implemented canonical formal checks, complete Coverage, and canonical Assessment, the product MUST keep:

```text
full_tbdy_compliance_status = NOT_EVALUATED
```

No aggregation of successful partial domains MAY be labeled `FULL TBDY PASS`.

### CURRENT IMPLEMENTATION

`WallAssessment` is the accepted domain reference for expected-versus-observed reconciliation and is `CONFORMING` within the wall slice. A generic assessment abstraction MAY be introduced when a second domain proves identical semantics; premature universalization is not required.

---

## 19. Reporter constitution

### FROZEN CONSTITUTIONAL RULE

Reporter code is a serialization and display boundary only.

A reporter MAY own:

- ordering,
- grouping,
- labels,
- localization,
- formatting/rounding for display,
- human-readable provenance presentation,
- rendering of canonical statuses and diagnostics.

A reporter MUST NOT own:

- engineering thresholds,
- regulatory applicability,
- formula/comparison logic,
- engineering ratios,
- formal statuses,
- result-row selection,
- governing-envelope selection,
- source-unit inference,
- creation of a parallel formal result,
- promotion of partial-domain success to full TBDY compliance.

Display rounding MUST NOT alter the underlying canonical value or verdict.

### Fail-closed behavior

If the reporter receives an incomplete/malformed canonical artifact, it SHOULD render the incompleteness explicitly or refuse canonical rendering. It MUST NOT fill missing engineering fields with calculated guesses.

### CURRENT IMPLEMENTATION

`tools/render_product_report.py` violates this boundary in multiple domains and is `LEGACY_DEBT`: it owns geometry thresholds/status/ratios, a modal threshold/status path, reporter-only column checks, and magnitude-based length conversion.

---

## 20. Registration and composition

### FROZEN CONSTITUTIONAL RULE

Canonical check registration MUST be deterministic, additive, and globally uniqueness-checked.

The composition mechanism MUST ensure:

- one canonical check namespace,
- deterministic assembly independent of import order,
- hard failure on duplicate check id,
- domain-owned evaluator/definition contributions,
- no requirement for every domain worker to edit a giant shared registry for routine additions,
- one canonical engine execution surface.

Catalog composition SHOULD use additive overlays where that pattern already preserves deterministic authority.

### Parallel-worker rule

Central composition code, the canonical result DTO, shared Coverage/result-evidence contracts, and base catalog contracts SHOULD be architecture-owner controlled. Domain workers SHOULD contribute domain-local definitions/evaluators/overlays with minimal shared-hotspot edits.

### PENDING IMPLEMENTATION RATIFICATION

The semantic rules above are frozen. The exact B1 implementation shape — module names, registration map types, composer class/function names, and whether existing registry code is split — is **PENDING IMPLEMENTATION RATIFICATION**.

The constitution MUST NOT be used to pre-approve unmerged B1 code.

---

## 21. Units

### FROZEN CONSTITUTIONAL RULE

Units are explicit evidence, not a guess and not a reason to mutate ETABS into a preferred display unit system.

1. Acquisition MUST record source/present/database unit context using non-normalizing reads available to the authoritative source/API.
2. Canonical acquisition MUST NOT call `SetPresentUnits(...)` or `SetPresentUnits_2(...)` merely to normalize data.
3. Raw evidence SHOULD preserve raw value and source unit.
4. Conversion MUST use an explicit unit mapping/contract in Python downstream.
5. FeatureSnapshot MUST expose normalized unit with the normalized factual value where dimensional meaning matters.
6. CheckInput MUST receive normalized values whose units are known by contract.
7. Reporter MUST NOT infer or repair engineering units.
8. Missing or contradictory units MUST block canonical execution when the check depends on them.

### Prohibited heuristics

The following are prohibited as canonical engineering authority:

- “if absolute value <= 30, treat as metres; otherwise millimetres,”
- “if strength > 1000, divide by 1000; otherwise assume MPa,”
- guessing units from GUI strings without explicit acquisition evidence,
- choosing a conversion because the resulting value looks plausible,
- changing ETABS present units and treating the mutated state as the canonical normalization mechanism.

### CURRENT IMPLEMENTATION

`tbdy_engine/engine/unit_context.py` contains an immutable explicit `UnitContext` and a fail-closed `require_unit_context_for_engineering()` path, which are conforming foundations. It also contains optional compatibility heuristics/fallback discovery. Those heuristic paths MAY remain for compatibility/diagnostics but MUST NOT feed canonical engineering execution.

`tbdy_engine/etabs/connection.py` currently calls `SetPresentUnits(6)` and therefore does not conform to the canonical acquisition-unit rule.

`tools/render_product_report.py` and `tbdy_engine/product_reports/material_evidence.py` contain magnitude-based conversions that are legacy debt.

---

## 22. Fail-closed rules and prohibited heuristics

### FROZEN CONSTITUTIONAL RULE

Canonical execution MUST stop at the earliest boundary that can prove required information is unresolved.

The following conditions MUST NOT produce a confident engineering PASS/FAIL result:

- missing mandatory feature,
- unknown/ambiguous dimensional unit,
- unresolved reviewed building/system/direction/reference authority,
- unresolved execution policy/context,
- missing exact reviewed load/case/combo binding when result selection requires it,
- `PARTIAL`, `SAMPLED`, `TRUNCATED`, or `UNKNOWN` capture for a full-population governing/envelope selection,
- duplicate canonical check registration,
- unknown check id,
- failed ETABS state restoration where result trust depends on restoration semantics,
- ambiguous or stale ETABS session identity,
- conflicting source evidence without an explicit reviewed resolution policy.

### Prohibited heuristic authority

Canonical engineering MUST NOT use these as substitutes for missing authority:

- value magnitude,
- case-name/string substring,
- regex seismic-name matching,
- lexical preference,
- earthquake-looking names,
- first matching case,
- first/last row,
- “largest row seen” when the full universe is not captured,
- default Max/Min/abs-max/envelope/sign/location semantics,
- reporter defaults,
- silent unit defaults,
- silent code-edition defaults,
- mutable global ETABS present units as proof of source units,
- test fixture assumptions leaking into live execution.

Runtime case-name heuristics MAY exist only for discovery, suggestion, or review assistance. They MUST NOT be formal runtime selection authority.

Missing information MUST NOT be converted to `OUT_OF_SCOPE`, `NOT_APPLICABLE`, or PASS. Coverage blocks unresolved readiness; final regulatory `OUT_OF_SCOPE` is owned by `CheckEngine`.

---

## 23. Parallel-worker / ownership governance

### FROZEN CONSTITUTIONAL RULE

Parallel development MUST be organized around domain slices without duplicating authority.

### 23.1 Architecture-owner surfaces

Changes to these surfaces SHOULD be serialized or owned by an architecture/integration worker:

- `tbdy_engine/checks/engine.py`,
- canonical `CheckResult` model,
- shared `Coverage` contracts,
- shared result-evidence/capture contracts,
- central registration composer,
- base catalog schema/composition rules,
- shared execution-boundary semantics,
- ratified ETABS acquisition/session transaction boundary.

### 23.2 Domain-worker surfaces

A domain worker SHOULD primarily own:

- domain raw-evidence mapping,
- domain FeatureResolver for factual features,
- domain-specific factual feature definitions,
- domain `ResultSelectionPolicy` contribution where result selection is required,
- typed domain CheckInput adapter,
- pure evaluator,
- domain registration contribution,
- additive catalog overlay,
- domain tests/replay fixtures,
- compatibility delegation for that domain.

### 23.3 One-live-client / acquisition ownership

There MUST be **ONE LIVE ETABS ACQUISITION OWNER AT A TIME** per live ETABS session within the enforced repository/process scope.

Canonical ETABS acquisition and state mutation MUST be serialized through that owner. Workers MUST NOT concurrently mutate a shared live ETABS session through independent clients merely because their downstream domains are parallelizable.

After acquisition, immutable evidence bundles, factual snapshots, reviewed contexts, selection traces, and formal inputs MAY be consumed in parallel.

No worker or document MAY claim cross-process or OS-global locking unless the implementation actually enforces and proves that scope.

### 23.4 Hotspot avoidance

`tbdy_engine/checks/registry.py`, `tbdy_engine/checks/engine.py`, base catalogs, `tbdy_engine/product_reports/check_results.py`, `tools/render_product_report.py`, and the future canonical ETABS safety boundary are known integration hotspots. Multiple workers SHOULD NOT independently redesign them during domain migrations.

### 23.5 No speculative framework rule

A worker MUST NOT create a generic plugin framework, universal evidence bag, second engine, giant `ModelContext`, or alternate formal-result abstraction merely to avoid a merge conflict. Shared abstractions SHOULD be generalized only after real consumers prove the shared semantics.

---

## 24. Vertical-slice lifecycle

### FROZEN CONSTITUTIONAL RULE

Each domain migration SHOULD proceed as a vertical slice in this order:

1. inventory current checks/results and duplicate authorities,
2. identify exact source tables/result evidence and provenance,
3. establish factual raw/canonical evidence contract,
4. implement/confirm factual FeatureResolver where factual features are required,
5. produce factual `FeatureSnapshot` for factual dependencies only,
6. for result domains, establish source-specific result identity and exact `RuntimeCaptureStatus`, reviewed exact bindings, `ResultSelectionPolicy`, `EngineeringQuantity`, and deterministic `SelectionTrace`,
7. bind reviewed MODEL/BUILDING/STRUCTURAL_SYSTEM/DIRECTION/STORY-or-LEVEL/COMPONENT context dependencies at their proper grain,
8. establish Coverage/readiness,
9. build typed `CheckInput` + `CheckExecutionContext`,
10. register pure evaluator/check with canonical `CheckEngine`,
11. produce canonical `CheckResult`,
12. reconcile through Assessment,
13. convert reporter/product API to serialization/delegation only,
14. run boundary, replay, and live acceptance,
15. remove/deactivate duplicate authority only after parity/acceptance.

A migration MUST NOT force a policy-derived `EngineeringQuantity` into `FeatureSnapshot` merely to reuse a factual path.

A migration MUST NOT begin by deleting legacy behavior before the canonical path can prove equivalent or intentionally changed semantics.

### Required evidence for a completed slice

A completed slice SHOULD demonstrate:

- source evidence provenance,
- explicit units,
- correct context-grain binding,
- missing/invalid input behavior,
- exact-boundary comparisons where numeric limits exist,
- exact reviewed result binding and selection trace where applicable,
- duplicate registration failure,
- compatibility delegation,
- non-regression of previously canonical slices,
- reporter inability to change engineering status.

---

## 25. Legacy compatibility and migration

### FROZEN CONSTITUTIONAL RULE

Legacy compatibility is permitted as a temporary interface, not as a second authority.

A compatibility path MUST converge toward one of the canonical dependency lanes and then the canonical execution boundary:

```text
legacy/public API
    -> canonical factual evidence/features and/or canonical result evidence/selection
    -> reviewed typed context
    -> Coverage
    -> canonical CheckEngine
    -> canonical CheckResult
    -> compatibility serialization
```

It MUST NOT retain independent thresholds, applicability, formula, status, unit inference, or row-selection logic once the domain is migrated.

### Legacy batch labels

The following labels remain useful for debt mapping and compatibility cleanup:

- **B1 — Beam + Column Geometry**
- **B2 — Concrete Material Strength**
- **B3 — Modal Mass Participation**
- **B4 — Story Drift + Torsional A1**
- **B5 — Remaining Legacy Design/Result Authorities**

These labels are NOT, by themselves, the current execution schedule. The authoritative current acceleration roadmap is Section 28 and includes result-selection/context consumers interleaved with legacy canonicalization.

### Deletion rule

Duplicate authority MUST be deleted/deactivated last, after:

- canonical path exists,
- regression/boundary tests pass,
- replay/live acceptance appropriate to the domain passes,
- compatibility consumers delegate to the canonical path,
- intentionally retained/retired checks are explicitly resolved.

A giant legacy rewrite is prohibited as the default migration strategy.

---

## 26. Acceptance gates

### FROZEN CONSTITUTIONAL RULE

No vertical slice is complete merely because its new code exists. Acceptance MUST prove authority convergence.

### 26.1 Universal domain gate

A migrated domain MUST satisfy all applicable conditions:

- one authorized source-to-result canonical path,
- explicit provenance,
- explicit units,
- correct regulatory context-grain bindings,
- Coverage mandatory before formal execution,
- typed CheckInput/context boundary,
- no hidden mandatory context,
- CheckEngine sole regulatory verdict authority,
- one formal `CheckResult`,
- assessment reconciles rather than recomputes,
- reporter serializes only,
- fail-closed missing evidence/context behavior,
- deterministic registration with duplicate-id failure,
- replay and/or live acceptance appropriate to source type,
- legacy compatibility delegates only,
- previously canonical domains do not regress.

### 26.2 B1 Beam + Column Geometry acceptance gate

B1 MUST satisfy all twenty gates below before its implementation shape is considered ratified:

1. Exactly one execution path exists from raw section evidence -> normalized factual feature -> `FeatureSnapshot` -> Coverage -> typed `CheckInput` -> `CheckEngine` -> canonical `CheckResult`.
2. Coverage is mandatory.
3. No hidden execution context is required.
4. There is one numeric authority for 250 mm, 300 mm, 3.5, and any retained column limits.
5. Reporter-only column area/aspect criteria are explicitly promoted to canonical checks or explicitly retired; they are not silently lost.
6. No magnitude-based unit guessing remains in the canonical geometry path.
7. `CheckEngine` is sole verdict authority.
8. One formal result DTO is used.
9. Reporter behavior is serialization-only for migrated geometry checks.
10. Missing fact/unit/context fails closed.
11. Existing accepted canonical geometry check inventory remains represented unless an explicit retirement decision exists.
12. Boundary regression covers below/equal/above/missing/explicit-unit cases.
13. Live and/or accepted replay beam/column acceptance demonstrates the vertical slice.
14. Compatibility APIs preserve required external shape by delegation, not recomputation.
15. Wall canonical behavior does not regress.
16. Registration is additive and deterministic.
17. Duplicate check IDs fail deterministically.
18. Assessment completeness is structural; missing/duplicate expected results prevent complete status.
19. Tests fail if reporter code reintroduces threshold/status/unit inference for migrated checks.
20. Duplicate legacy authority is deleted/deactivated only after canonical acceptance and regression evidence.

### 26.3 Result-domain gate

Ndm, Vt/Eq7.14, modal, drift, torsion, and later governing/envelope result domains additionally MUST demonstrate:

- source-specific stable candidate identity distinct from payload,
- exact `RuntimeCaptureStatus` from `FULL/PARTIAL/SAMPLED/TRUNCATED/UNKNOWN`,
- `FULL` capture where full-population governing selection is required,
- reviewed + versioned exact binding manifest,
- explicit `ResultSelectionPolicy` including all relevant sign/step/location/envelope/tie semantics,
- deterministic `SelectionTrace`,
- explicit `EngineeringQuantity` output where a governing quantity is derived,
- no reporter/product selection authority,
- no runtime case-name heuristic used as authoritative metadata,
- regulatory applicability and final `OUT_OF_SCOPE` decided only by `CheckEngine`.

---

## 27. Current conformance & debt register

### CURRENT IMPLEMENTATION

This section records the audited state at exactly `46ed7f087290393786bd06feef3a7598a67805fd`. It is not a statement about unmerged B1 or ETABS Safety Foundation work.

### 27.1 Subsystem conformance classification

| Subsystem | Baseline classification | Audited current behavior | Constitutional target |
|---|---|---|---|
| Wall inventory | `CONFORMING` | Accepted wall check inventory/contract participates in the canonical wall path. | Preserve as inventory authority feeding canonical execution. |
| Wall Pack A | `CONFORMING` | Establishes accepted wall domain foundations/evidence/contracts without reporter verdict ownership. | Preserve domain-specific evidence semantics. |
| Wall Pack B | `CONFORMING` | Continues accepted wall canonicalization foundations. | Preserve wall-specific semantics; avoid unnecessary genericization. |
| Wall Pack C | `CONFORMING` | Canonical wall pipeline binds readiness/Coverage, typed input/context, engine execution, formal result, assessment; unresolved Ndm policy blocks. | Reference implementation for fail-closed execution. |
| `MinimalCheckEngine` | `PARTIALLY_CONFORMING` | Canonical authority for accepted wall and geometry checks; repo-wide bypasses still exist. | Sole regulatory production authority for all migrated domains. |
| `GeometryCheckInput` / `CheckExecutionContext` | `CONFORMING` | Accepted typed execution boundary used in wall/geometry paths. | Extend semantics with typed domain inputs, not universal dicts. |
| Coverage | `PARTIALLY_CONFORMING` | Correctly used by wall/geometry orchestration; not yet universal across material/result domains. | Mandatory `RUNNABLE/PARTIAL/BLOCKED` readiness boundary for every canonical check. |
| Canonical `CheckResult` | `CONFORMING` | `tbdy_engine/checks/result.py` is used by accepted engine path. | Remain sole formal DTO with exact canonical status set. |
| `WallAssessment` | `CONFORMING` | Reconciles accepted wall expected/observed results rather than becoming a wall formula engine. | Reuse semantics only when second domain proves common abstraction. |
| `product_reports/check_results.py` | `LEGACY_DEBT` | Builds parallel formal-looking `check_result.v1` dictionaries and owns material/modal/drift/A1 status/limit/selection behavior. | Compatibility serializer over canonical `CheckResult` only. |
| `tools/render_product_report.py` | `LEGACY_DEBT` | Owns geometry/modal thresholds, ratios/statuses, reporter-only column checks, magnitude-based length conversion. | Serialization/display only. |
| `engine/unit_context.py` | `PARTIALLY_CONFORMING` | Has immutable explicit `UnitContext` and fail-closed engineering requirement; also compatibility heuristic fallback paths. | Explicit acquisition unit context; heuristics excluded from canonical engineering. |
| `etabs/connection.py` | `PARTIALLY_CONFORMING` | Attaches to running ETABS with multiple COM fallbacks, validates SapModel/tables, but calls `SetPresentUnits(6)` and lacks ratified serialized acquisition/session safety contract. | Read unit provenance without canonical normalization mutation; safe explicit session identity. |
| `etabs_com_attach.py` | `NOT_IMPLEMENTED` | No separate file with this exact responsibility/name was found on audited baseline; attach behavior resides in `tbdy_engine/etabs/connection.py`. | Exact attach API shape pending ETABS Safety ratification. |
| Display-table fetcher | `PARTIALLY_CONFORMING` | Shared fetcher probes COM signatures and records rich diagnostics; may mutate display case/combination selection without baseline transaction restore contract. | Serialized acquisition owner + observable bounded display-state transaction. |
| Result-evidence capture | `PARTIALLY_CONFORMING` | `features/result_evidence.py` provides identity/capture foundations, not yet adopted consistently by modal/drift/A1. | Shared source-specific identity + exact `FULL/PARTIAL/SAMPLED/TRUNCATED/UNKNOWN` contract. |
| Shared `SelectionTrace` | `NOT_IMPLEMENTED` | No complete shared canonical trace boundary verified at baseline. | Required deterministic trace for migrated result-selection domains. |
| Beam geometry | `PARTIALLY_CONFORMING` | Canonical engine/input/Coverage pieces exist, but reporter duplicates limits/status/unit behavior. | B1 single canonical vertical slice. |
| Column geometry | `PARTIALLY_CONFORMING` | Canonical engine/input/Coverage pieces exist; reporter also owns area/aspect checks not present in engine inventory. | B1 reconcile/promote/retire inventory, then single authority. |
| Concrete material strength | `LEGACY_DEBT` | Evidence module is mostly factual, but unit normalization uses magnitude heuristic; product result builder owns minimum fck/status. | B2 explicit-unit factual feature -> Coverage -> engine. |
| Modal mass participation | `LEGACY_DEBT` | Reporter/product path owns threshold/status/selected-row behavior; no complete canonical result-selection trace path. | Later result wave: exact binding -> policy -> EngineeringQuantity/trace -> engine. |
| Story drift | `LEGACY_DEBT` | Product result path owns frozen threshold/status and case-selection heuristics. | Later result wave: exact reviewed binding/selection -> engine. |
| Torsional A1 | `LEGACY_DEBT` | Product path owns threshold/status and permits case-name fallback for generic/missing case metadata. | Later result wave: exact reviewed binding/selection -> engine. |
| Beam legacy design | `LEGACY_DEBT` | `design/beams/*` contains independent engineering calculation paths outside canonical engine. | Family-by-family canonical migration. |
| Column legacy design | `LEGACY_DEBT` | `design/columns/*` contains independent engineering calculation paths outside canonical engine. | Family-by-family canonical migration. |
| Registration exact implementation | `PENDING_IMPLEMENTATION` | Existing registry/engine composition works for accepted checks but is a shared hotspot and not the ratified B1 end state. | Deterministic additive composition; exact API pending B1 ratification. |
| ETABS safety transaction API | `PENDING_IMPLEMENTATION` | Current connection/fetching behavior lacks ratified one-live-owner session/state transaction interface. | Frozen safety semantics; exact API pending ETABS Safety ratification. |

### 27.2 Material debt register

| Path | Current behavior | Violated constitutional rule | Target authority | Planned migration batch/wave | Severity |
|---|---|---|---|---|---|
| `tools/render_product_report.py` | Defines geometry thresholds including beam width/depth/ratio and column limits; computes ratios/status; performs magnitude-based `_length_to_mm`; owns modal threshold/status behavior. | Reporter MUST be serialization-only; units MUST be explicit; CheckEngine sole verdict authority. | FeatureSnapshot/Coverage/CheckEngine/canonical `CheckResult`; reporter delegates. | B1 + later modal wave | **CRITICAL** |
| `tbdy_engine/product_reports/check_results.py` | Builds parallel `check_result.v1`; owns `MIN_FCK_MPA`, modal aggregation, `MAX_STORY_DRIFT_RATIO`, `MAX_TORSION_A1_COEFFICIENT`, selection/status behavior. | One formal result DTO; CheckEngine sole regulatory authority; selection separate from compliance. | Canonical result-selection boundary + CheckEngine + canonical `CheckResult`. | B2 + result-selection waves | **CRITICAL** |
| `tbdy_engine/product_reports/material_evidence.py` | Mostly factual evidence/provenance, but `_fck_to_mpa` divides values >1000 and otherwise assumes MPa. | No magnitude-based unit inference. | Explicit source `UnitContext` + factual material resolver. | B2 | **HIGH** |
| `tbdy_engine/engine/unit_context.py` | Provides explicit unit context and fail-closed requirement but retains heuristic fallback/discovery compatibility paths. | Heuristic authority MUST NOT enter canonical engineering. | Explicit ETABS acquisition unit context; heuristic APIs compatibility/diagnostic only. | ETABS Safety + B1/B2 | **HIGH** |
| `tbdy_engine/etabs/connection.py` | Attaches to active ETABS, validates tables, calls `SetPresentUnits(6)` during connect/get_sap. | Canonical acquisition MUST NOT use `SetPresentUnits`/`SetPresentUnits_2` merely to normalize data; source unit provenance must be read/preserved. | ETABS acquisition/session boundary with Python downstream conversion. | ETABS Safety Foundation | **HIGH** |
| `tbdy_engine/providers/etabs_display_table_fetcher.py` | Robust COM signature probing/diagnostics; may call display-selection mutators before result fetch; baseline does not establish restoration transaction or one-live-owner serialization. | No hidden/unbounded ETABS state mutation; one live acquisition owner. | ETABS acquisition read/display transaction. | ETABS Safety Foundation | **HIGH** |
| `tbdy_engine/checks/engine.py` + `tools/render_product_report.py` | Beam/column geometry authority is split: engine has canonical geometry checks while reporter repeats numeric policy/status. | One authority per decision. | Canonical CheckEngine/catalog path. | B1 | **HIGH** |
| `tools/render_product_report.py` | Contains reporter-only column minimum-area and aspect-ratio criteria not represented in accepted engine inventory. | Check inventory and regulatory authority MUST be explicit/canonical. | Explicit promote-to-canonical or retire decision, then CheckEngine. | B1 | **HIGH** |
| `tbdy_engine/product_reports/check_results.py` + report path | Modal selected-row/threshold/status flow remains outside canonical result evidence/selection/engine architecture. | Raw result identity + exact reviewed binding + SelectionTrace + CheckEngine authority. | ResultRowEvidenceBundle -> reviewed binding -> ResultSelectionPolicy -> EngineeringQuantity/SelectionTrace -> CheckEngine. | later modal wave | **HIGH** |
| `tbdy_engine/product_reports/check_results.py` | Drift case selector uses metadata/name patterns and owns product threshold/status. | Runtime name heuristics MUST NOT be formal authority; regulatory status belongs to engine. | Exact reviewed binding -> ResultSelectionPolicy -> SelectionTrace -> CheckEngine. | Story Drift + Torsional A1 wave | **CRITICAL** |
| `tbdy_engine/product_reports/check_results.py` | Torsion A1 selector permits name fallback when metadata is generic/missing and owns threshold/status. | Runtime name fallback MUST NOT be canonical authority; final status belongs to engine. | Exact reviewed binding -> ResultSelectionPolicy -> SelectionTrace -> CheckEngine. | Story Drift + Torsional A1 wave | **CRITICAL** |
| `tbdy_engine/design/beams/*` | Independent legacy beam engineering calculations exist outside canonical execution boundary. | One regulatory authority / one formal result path. | Domain vertical slices through canonical CheckEngine. | remaining legacy cleanup | **HIGH** |
| `tbdy_engine/design/columns/*` | Independent legacy column engineering calculations exist outside canonical execution boundary. | One regulatory authority / one formal result path. | Domain vertical slices through canonical CheckEngine. | remaining legacy cleanup | **HIGH** |

### 27.3 Current authority map by audited domain

| Domain | Facts / result evidence | Coverage/input | Formula/limit/status | Formal result | Reporter | State |
|---|---|---|---|---|---|---|
| Wall | canonical factual/evidence path | canonical | CheckEngine | canonical `CheckResult` | downstream display | **canonical reference** |
| Beam geometry | factual features exist | canonical pieces exist | engine + duplicate reporter | canonical + report duplicate behavior | calculates | **split authority** |
| Column geometry | factual features exist | canonical pieces exist | engine + reporter-only criteria | canonical + report duplicate behavior | calculates | **split inventory/authority** |
| Material | evidence mostly factual but unit heuristic | canonical boundary incomplete | product builder | product parallel dict | downstream | **legacy product authority** |
| Modal | result evidence foundation incomplete in product path | canonical boundary incomplete | reporter/product | product parallel dict | calculates/selects | **legacy result authority** |
| Drift | product result selection | canonical boundary incomplete | product builder | product parallel dict | downstream | **legacy result authority** |
| Torsion A1 | product result selection | canonical boundary incomplete | product builder | product parallel dict | downstream | **legacy result authority** |

### 27.4 Debt interpretation rule

The presence of legacy debt does not invalidate the accepted wall architecture. It means new work MUST migrate toward the constitutional boundaries rather than copying product/report authority patterns.

No test-only threshold constant is classified as duplicate production authority merely because its numeric value matches production policy.

---

## 28. Current acceleration roadmap

### FROZEN CONSTITUTIONAL RULE

The current project roadmap is dependency-driven. Legacy batch names remain useful for debt accounting, but the actual execution order is the following.

### DONE

- Wall Inventory
- Wall Pack A
- Wall Pack B
- Wall Pack C

### CURRENT PARALLEL SPRINT

- B1 Beam + Column Canonicalization
- ETABS Safety Foundation
- Architecture Constitution

The exact B1 registration/composition implementation and exact ETABS Safety API remain pending implementation ratification; their frozen semantics are defined by this constitution.

### NEXT PARALLEL WAVE

- B2 Concrete Material
- `ResultSelectionPolicy` + **Ndm first real consumer**

Ndm MUST be the first `ResultSelectionPolicy` implementation. The project MUST NOT prebuild Vt, drift, torsion, modal, and every possible context/result abstraction before Ndm proves the selection/binding/trace model with a real engineering consumer.

### THEN

- Vt / Eq7.14 as the second result/context consumer

Vt / Eq7.14 SHOULD reuse only the semantics actually proven by Ndm. New shared abstractions MUST be justified by the second consumer rather than by framework preference.

### THEN PARALLEL

- Modal Mass
- next Wall vertical slice

### THEN

- Story Drift + Torsional A1

### THEN

- remaining legacy design/result authority cleanup

### THEN

- broader FULL TBDY expansion

### Roadmap-change rule

The roadmap MAY change only in response to real:

- engineering dependency,
- regulatory discovery,
- architecture regression,
- ETABS/source constraint.

A new framework preference, naming preference, or desire to generalize earlier is not sufficient reason to reorder the dependency sequence.

### Acceleration invariant

Architecture speed is measured by reduction of duplicate authority and successful reuse by real consumers. Ndm proves the first result-selection abstraction; Vt/Eq7.14 is the next validation point.

---

## 29. Pending implementation ratifications

### PENDING IMPLEMENTATION RATIFICATION — B1 registration/composition

Frozen semantics:

- one canonical check namespace,
- additive domain contributions,
- deterministic composition,
- hard duplicate-id failure,
- one canonical engine execution surface,
- compatibility/report code cannot register alternate verdict authorities.

Not yet ratified:

- exact module names,
- exact registry/composer class names,
- exact mapping/registry data structure,
- exact split of the current large registry,
- exact catalog composer function/API.

The B1 branch MUST be reviewed against these semantics after merge-ready implementation exists. Its unmerged shape is not constitutional evidence.

### PENDING IMPLEMENTATION RATIFICATION — ETABS Safety Foundation

Frozen semantics:

- explicit session/model identity,
- explicit source/present/database unit provenance,
- canonical normalization MUST NOT call `SetPresentUnits(...)` or `SetPresentUnits_2(...)`,
- one live ETABS acquisition owner at a time per live session within enforced repository/process scope,
- canonical acquisition/state mutation serialized through that owner,
- bounded display/read-state mutation only where genuinely required,
- transaction-style snapshot/mutate/fetch/restore evidence where temporary display/read state changes are required,
- failure/restore diagnostics,
- fail-closed ambiguous or untrusted session state,
- live versus replay provenance,
- immutable acquired evidence MAY be consumed in parallel.

Not yet ratified:

- exact attach/session class names,
- exact transaction context-manager/API shape,
- exact one-live-owner enforcement mechanism,
- exact snapshot object schema,
- exact restore mechanism for every ETABS API variant,
- whether attachment and display-state transactions reside in one module or multiple modules.

The constitution does NOT pre-ratify cross-process or OS-global locking.

### Rule

Pending ratification is not permission to violate frozen semantics. It means workers MAY choose an implementation shape, but supervisor review MUST ratify that shape before it is treated as the canonical pattern for later workers.

---

## 30. Constitutional amendment process

### FROZEN CONSTITUTIONAL RULE

A MUST/MUST NOT rule in this document may be changed only by an explicit constitutional amendment.

A valid amendment MUST:

1. name the exact rule being changed,
2. explain the architectural contradiction or new evidence that requires change,
3. identify affected authority boundaries,
4. identify migration impact on existing canonical domains,
5. update acceptance gates if required,
6. state whether legacy behavior becomes accepted, deprecated, or prohibited,
7. receive explicit supervisor/architecture review before workers treat it as authority.

A feature branch MUST NOT silently amend the constitution by implementation precedent.

### Conflict protocol

If a worker discovers two frozen rules that cannot both be satisfied for a real domain, the worker MUST:

- stop at the conflicting boundary,
- preserve existing accepted architecture,
- document the exact conflict with concrete evidence,
- request an amendment/decision.

The mere fact that implementation is incomplete, inconvenient, or requires migration is not an architecture contradiction.

### Audit baseline rule

Future conformance audits MUST identify the exact commit audited. They MUST NOT classify unmerged conceptual work as current implementation.

---

## Appendix A — Constitutional invariants

The following condensed list is normative and uses stable semantic IDs for implementation reviews.

- **ARCH-WORKER** — All implementation workers MUST conform to this constitution. Conflicting requests MUST stop and surface the conflict; workers MUST NOT silently create parallel architecture.
- **ARCH-AUTH** — There MUST be one authority per engineering decision. `CheckEngine` MUST be sole regulatory verdict authority; pure evaluators are math only; Assessment reconciles only; Reporter serializes/displays only.
- **ARCH-CTX** — Regulatory/project context grains are MODEL, BUILDING, STRUCTURAL_SYSTEM, DIRECTION, STORY/LEVEL, COMPONENT, CHECK_EXECUTION. Where a rule is direction-dependent, structural-system authority MUST be keyed at least by `structural_zone × direction`. Global R/D/system fallback is prohibited where directional authority is required. Building/system/reference truth MUST NOT be copied into per-component factual truth merely for convenience. A giant `ModelContext` is prohibited.
- **ARCH-ETABS** — Canonical acquisition MUST NOT call `SetPresentUnits(...)` or `SetPresentUnits_2(...)` merely to normalize data. It MUST read/preserve source/present/database unit provenance and convert in Python downstream. There MUST be one live ETABS acquisition owner at a time per live session within enforced repository/process scope; canonical acquisition/state mutation is serialized through it. Immutable evidence MAY be consumed in parallel.
- **ARCH-UNITS** — Source units are explicit evidence. Magnitude-based or plausibility-based unit inference MUST NOT enter canonical engineering execution.
- **ARCH-FEAT** — Raw evidence/canonical tables and `FeatureSnapshot` contain facts/evidence only. A policy-derived governing `EngineeringQuantity` MUST NOT be disguised as a factual FeatureSnapshot value.
- **ARCH-CAP** — Canonical `RuntimeCaptureStatus` is exactly `FULL`, `PARTIAL`, `SAMPLED`, `TRUNCATED`, `UNKNOWN`. Any complete-population selection requires `FULL`; otherwise governing demand is unresolved and formal execution is blocked.
- **ARCH-ID** — Result-row identity is source-specific and MUST be distinct from payload components. There is no universal ETABS result identity.
- **ARCH-BIND** — Formal runtime result selection consumes a reviewed, versioned, materialized exact binding manifest. Runtime case-name/regex/lexical/first-match heuristics MAY support discovery/review only and MUST NOT be formal authority.
- **ARCH-SEL** — `ResultSelectionPolicy` has no default Max/Min/abs-max/Top/Bottom/first-row/lexical-case/envelope/sign semantics. Relevant semantics MUST be explicit. Selection MAY derive `EngineeringQuantity` but MUST NOT issue final PASS/FAIL/OUT_OF_SCOPE. Same immutable bundle + same reviewed bindings + same request + same policy version MUST produce the same `SelectionTrace`.
- **ARCH-COV** — Coverage readiness statuses are exactly `RUNNABLE`, `PARTIAL`, `BLOCKED`. Coverage owns readiness only. Missing authority or ambiguous meaning is `BLOCKED`; missing mandatory context is `BLOCKED`. Missing information MUST NOT imply OUT_OF_SCOPE/NOT_APPLICABLE.
- **ARCH-EXEC** — Typed `CheckInput` + explicit `CheckExecutionContext` is the formal execution boundary. Mandatory execution dependencies MUST NOT be hidden in globals, reporters, defaults, or a giant model context.
- **ARCH-RES** — The canonical formal `CheckResult.status` set is exactly `OK`, `FAIL`, `WARNING`, `NO_DATA`, `BLOCKED`, `OUT_OF_SCOPE`. `CheckEngine` constructs final `CheckResult`. Final regulatory `OUT_OF_SCOPE` belongs only to `CheckEngine`.
- **ARCH-NODATA** — `NO_DATA` is not generic missing information. It is valid only when semantics/source/context are resolved and authoritative factual data is genuinely absent.
- **ARCH-ASSESS** — Assessment MUST reconcile expected versus observed canonical results and MUST NOT recompute engineering formulas. Missing/duplicate expected results prevent structurally complete assessment.
- **ARCH-REPORT** — Reporter MUST NOT own thresholds, ratios, applicability, result selection, unit inference, formal status, or full-TBDY promotion.
- **ARCH-REG** — Registration MUST be deterministic and additive; duplicate check IDs MUST fail hard. Exact B1 implementation shape remains pending ratification.
- **ARCH-COMPAT** — Compatibility APIs MUST delegate after migration and MUST NOT preserve duplicate verdict/selection/unit authority. Legacy authority is removed only after canonical acceptance/parity.
- **ARCH-GLOBAL** — Product target is FULL TBDY ENGINE, not screening-only. Until every mandatory applicable TBDY domain has authoritative dependencies, implemented formal checks, complete Coverage, and canonical Assessment, `full_tbdy_compliance_status = NOT_EVALUATED`. Partial slice success MUST NOT become FULL TBDY PASS.
- **ARCH-ROADMAP** — Ndm is the first `ResultSelectionPolicy` implementation; Vt/Eq7.14 is the second result/context consumer. Abstractions MUST be proven by these real consumers before broader result-domain generalization.
- **ARCH-RATIFY** — B1 exact registration/composition shape and ETABS Safety exact session/transaction API shape remain pending implementation ratification; their semantics are frozen. Unmerged sprint work MUST NOT be treated as accepted baseline evidence.
- **ARCH-AMEND** — A feature branch MUST NOT silently amend this constitution by precedent. Architecture incompleteness is not itself a contradiction. A real conflict between frozen rules requires the Section 30 amendment/conflict process.

---

## Appendix B — Authority examples

These examples are normative interpretations of the authority rules.

### B.1 Beam width

**Allowed:**

```text
ETABS section evidence (explicit unit)
 -> beam width factual feature
 -> FeatureSnapshot
 -> Coverage
 -> GeometryCheckInput + CheckExecutionContext
 -> CheckEngine binds authoritative minimum width
 -> canonical CheckResult
 -> reporter renders value/limit/status
```

**Prohibited:** reporter sees width, converts it by magnitude, compares to `250`, and emits its own PASS/FAIL.

Owner of width fact: FeatureResolver.  
Owner of minimum-width regulatory decision: CheckEngine.  
Owner of display: Reporter.

### B.2 Column area/aspect criteria

If a current reporter contains a column area/aspect criterion that the canonical engine inventory does not contain, the migration MUST make an explicit inventory decision.

**Allowed:** promote the criterion into a reviewed canonical check, or explicitly retire it with acceptance evidence.

**Prohibited:** keep it as a hidden reporter check or silently delete it because the engine does not currently know it.

### B.3 Concrete `fck`

**Allowed:** acquisition records source strength unit -> resolver converts by explicit mapping in Python -> snapshot stores normalized MPa -> Coverage verifies readiness -> engine binds minimum-strength rule.

**Prohibited:** “value > 1000 means kN/m², divide by 1000; otherwise assume MPa.”

### B.4 Ndm governing demand — first ResultSelectionPolicy consumer

**Allowed:**

```text
Raw Result Evidence with source-specific identity and FULL capture
 -> reviewed/versioned load-family binding expanded against exact current ETABS inventory
 -> materialized exact binding manifest reviewed/frozen
 -> ResultSelectionPolicy with explicit direction/step/location/sign/envelope/tie semantics
 -> EngineeringQuantity(Ndm) + deterministic SelectionTrace
 -> Coverage
 -> typed CheckInput + CheckExecutionContext
 -> CheckEngine
```

**Prohibited:** identify “seismic” cases at runtime by `EQX` substring/regex/lexical preference and choose a visible maximum.

### B.5 Modal mass participation

**Allowed:** acquire required modal rows with source-specific identities -> mark capture `FULL` where complete-population selection requires it -> consume reviewed exact binding/policy -> derive the required `EngineeringQuantity` and `SelectionTrace` -> engine decides applicable regulatory threshold/status.

**Prohibited:** reporter selects a visible mode, applies `0.95`, and calls the report compliant.

### B.6 Story drift

**Allowed:** result evidence records source-specific identities -> reviewed exact seismic binding is materialized/frozen -> explicit `ResultSelectionPolicy` derives intended demand and trace -> engine decides applicability and drift limit.

**Prohibited:** product/runtime code treats any case name containing `drift`, `seismic`, `EQX`, or similar text as authoritative, then applies a hardcoded drift limit.

### B.7 Torsional A1

**Allowed:** exact reviewed case/result binding plus explicit selection policy produce a traceable `EngineeringQuantity` -> CheckEngine decides the regulatory comparison.

**Prohibited:** generic/missing case metadata is repaired through a runtime name fallback and directly converted into PASS/FAIL by a product-result builder.

### B.8 Partial/sampled/truncated/unknown result capture

Suppose ten candidate rows are required to establish a maximum but only six are captured.

**Allowed:** classify the source accurately as `PARTIAL`, `SAMPLED`, `TRUNCATED`, or `UNKNOWN` according to acquisition facts; selection says governing value unresolved; Coverage blocks the check requiring the full population.

**Prohibited:** choose the maximum of the six visible rows and label it governing.

### B.9 ETABS unit acquisition

**Allowed:** canonical acquisition reads source/present/database unit provenance without normalizing ETABS through `SetPresentUnits`; downstream Python performs explicit conversion.

**Prohibited:** call `SetPresentUnits(6)` merely so all fetched values “look normalized,” even if code intends to restore units later.

### B.10 ETABS display selection mutation

**Allowed:** the serialized canonical acquisition owner records previous display state where supported, selects the required exact reviewed case/combination for acquisition, fetches, restores previous state where required/supported, records transaction evidence, and exposes source/capture diagnostics.

**Prohibited:** a reporter, resolver, or parallel worker changes display selection on the shared live session outside the canonical acquisition owner.

### B.11 UnitContext fallback

**Allowed:** a legacy UI diagnostic uses a heuristic to suggest likely units and labels the result non-authoritative.

**Prohibited:** the same heuristic output enters a canonical `CheckInput` without explicit source-unit evidence.

### B.12 Coverage versus OUT_OF_SCOPE

**Allowed:** mandatory structural-system direction authority is missing; Coverage returns `BLOCKED`; no formal OUT_OF_SCOPE result is invented.

**Allowed:** all dependencies are resolved and CheckEngine determines from the canonical rule that the check is outside assessed regulatory scope; CheckEngine emits `CheckResult.OUT_OF_SCOPE`.

**Prohibited:** selector/resolver/coverage equates “could not resolve applicability” with OUT_OF_SCOPE.

### B.13 NO_DATA

**Allowed:** exact source meaning, unit, reviewed binding, context, and applicability dependencies are resolved; the authoritative factual row is genuinely absent; CheckEngine emits `NO_DATA` according to the check contract.

**Prohibited:** missing case semantics or unknown units are labeled `NO_DATA` to avoid a blocked result.

### B.14 Assessment

**Allowed:** expected checks are `{A, B, C}` and observed canonical results are `{A, B}`; Assessment marks the set incomplete because `C` is missing.

**Prohibited:** Assessment calculates `C` itself or treats missing `C` as PASS.

### B.15 Reporter

**Allowed:** reporter formats `0.007812` as `0.0078` for display while preserving the canonical underlying result/status.

**Prohibited:** reporter rounds the source value first and then re-evaluates a threshold, causing status to change.

### B.16 Compatibility API

**Allowed:** legacy caller receives the historical JSON shape, but every value/limit/status is serialized from the canonical `CheckResult` and provenance is retained where compatible.

**Prohibited:** the compatibility serializer keeps its old threshold constants and recomputes status “for parity.”

### B.17 Registration

**Allowed:** beam and column domains contribute additive definitions to a deterministic composer; duplicate `check_id` aborts composition.

**Prohibited:** import order decides which duplicate check implementation wins.

### B.18 Parallel worker conflict

**Allowed:** domain workers operate in parallel on immutable acquired evidence while an architecture owner controls the shared composer seam and a single canonical live ETABS acquisition owner serializes live-session access/mutation.

**Prohibited:** each worker creates a private registry/engine or independently mutates the same live ETABS session because shared ownership is inconvenient.

### B.19 Direction-dependent structural-system authority

**Allowed:** reviewed structural-system authority is resolved by `structural_zone × direction`, and the X-direction check consumes the X binding while the Y-direction check consumes the Y binding.

**Prohibited:** one global R/D/system value is copied onto every component and used for both directions when the rule is direction-dependent.

### B.20 New domain

A new domain MUST first answer these questions before formal evaluation code is accepted:

1. What is the authoritative source evidence?
2. What is its source-specific identity and unit contract?
3. Which regulatory context grains are required: MODEL, BUILDING, STRUCTURAL_SYSTEM, DIRECTION, STORY/LEVEL, COMPONENT, CHECK_EXECUTION?
4. What factual dependencies belong in `FeatureSnapshot`?
5. Does the domain require result selection or a derived governing quantity?
6. If yes, what is the exact five-state capture status, reviewed binding authority, explicit `ResultSelectionPolicy`, resulting `EngineeringQuantity`, and deterministic `SelectionTrace`?
7. What makes Coverage `RUNNABLE`, `PARTIAL`, or `BLOCKED`?
8. What mandatory `CheckExecutionContext` dependencies exist?
9. What check id is registered with CheckEngine?
10. What pure evaluator, if any, performs math?
11. How is the canonical `CheckResult` assessed and reported without recomputation?
12. Does this slice change only domain compliance, or is full TBDY compliance still `NOT_EVALUATED`?

If those questions cannot be answered, the domain is not ready to claim canonical engineering execution.
