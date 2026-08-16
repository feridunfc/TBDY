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

This document is the normative architecture constitution for TBDY Engine. It governs the boundaries by which ETABS evidence becomes factual features, check execution, formal results, assessment, and reporting.

The constitution governs, at minimum:

1. ETABS session acquisition and display-table acquisition.
2. Raw factual evidence and canonical tables.
3. Raw result evidence and result-row identity.
4. Feature resolution and `FeatureSnapshot`.
5. Result selection and `SelectionTrace`.
6. Coverage/readiness.
7. Typed `CheckInput` and `CheckExecutionContext`.
8. `CheckEngine` and pure evaluators.
9. Canonical `CheckResult`.
10. Assessment/reconciliation.
11. Reporter behavior.
12. Registration and composition.
13. Units and provenance.
14. Compatibility and migration of legacy authorities.
15. Parallel-worker ownership and integration rules.

The audited baseline is exactly `46ed7f087290393786bd06feef3a7598a67805fd`. Unmerged work from B1 Beam + Column Canonicalization and ETABS Safety Foundation is not accepted implementation evidence for this document.

The semantics of registration/composition and ETABS session safety are frozen here. Their exact implementation shapes are **PENDING IMPLEMENTATION RATIFICATION**.

### CURRENT IMPLEMENTATION

The accepted wall path is the strongest current reference implementation. Beam/column geometry has part of the same canonical execution machinery. Material and result-based domains still contain product/report-owned authority. ETABS acquisition has usable connection/fetch foundations but does not yet satisfy the complete safety transaction constitution.

### Integration boundary

Changes cross the constitutional boundary when they introduce or change any owner of:

- raw evidence,
- feature facts,
- candidate result selection,
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

TBDY Engine MUST produce engineering conclusions that are deterministic, auditable, reproducible, fail-closed, and attributable to explicit source evidence and explicit policy/context.

The product objective is not merely to produce a report that looks correct. The product MUST be able to answer, for every formal check result:

- What source evidence was used?
- What units did the source evidence use?
- Which factual features were resolved?
- What candidate result rows existed?
- If rows were selected, why were they included or excluded?
- Was the required evidence capture complete?
- Which execution context/policy was required?
- Which check owned applicability?
- Which rule/limit/formula produced the comparison?
- Which canonical result object recorded the conclusion?
- Whether all expected checks were present exactly once?
- Whether the reporter merely serialized the already-decided result?

A product output that cannot answer those questions MUST NOT be treated as complete canonical engineering evidence.

### Decision ownership

- Acquisition owns retrieval fidelity.
- Feature resolution owns factual interpretation only.
- Result selection owns deterministic candidate selection only.
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
3. **One execution boundary.** Formal engineering execution MUST cross through typed `CheckInput` plus explicit `CheckExecutionContext`.
4. **One regulatory authority.** `CheckEngine` MUST be the sole production authority for check applicability, limits, comparison/formula orchestration, ratio semantics, status, and formal `CheckResult` creation.
5. **One formal result DTO.** There MUST be one canonical `CheckResult` type. Parallel “formal” dictionaries or DTOs MUST NOT become independent authorities.
6. **Fail closed.** Missing mandatory fact, unit, context, identity, or complete result capture MUST produce a blocked/not-runnable state, not a guessed pass/fail.
7. **Provenance is data.** Source identity and transformation evidence MUST travel with the facts/results they support.
8. **Selection is not compliance.** Result-row selection MUST NOT decide PASS/FAIL.
9. **Coverage is not compliance.** Coverage/readiness MUST NOT decide engineering status.
10. **Assessment is not engineering.** Assessment MUST reconcile expected versus observed formal results and MUST NOT recompute check formulas.
11. **Reporting is not engineering.** Reporter code MUST NOT own thresholds, ratios, regulatory row selection, unit inference, or statuses.
12. **No hidden state.** ETABS state mutations MUST be explicit, bounded, observable, and restored where temporary mutation is required.
13. **No heuristic authority.** Name, magnitude, default-unit, or similar heuristics MUST NOT become authoritative input to canonical engineering execution.
14. **Delete duplicate authority last.** Migration MUST first establish canonical equivalence and acceptance, then remove legacy decision code.
15. **Generalize semantics, not data bags.** Shared contracts SHOULD encode shared invariants while domain facts and policies remain typed and domain-specific.

### Fail-closed default

Where this constitution does not explicitly grant decision authority, a layer MUST NOT invent it. If canonical execution cannot determine the required input or policy through an authorized source, it MUST block.

---

## 4. Canonical end-to-end architecture

### FROZEN CONSTITUTIONAL RULE

TBDY Engine has two canonical evidence lanes that converge before execution.

### 4.1 Factual-table lane

```text
ETABS acquisition
    -> Raw Evidence / CanonicalTable
    -> FeatureResolver
    -> FeatureSnapshot
    -> Coverage
    -> typed CheckInput + CheckExecutionContext
    -> CheckEngine
    -> canonical CheckResult
    -> Assessment
    -> Reporter
```

This lane is appropriate for geometry, material facts, assignments, metadata, and other facts that do not require choosing a governing row from an ETABS result candidate universe.

### 4.2 Result-evidence lane

```text
ETABS acquisition
    -> Raw Result Evidence
       (stable identity + payload + capture status)
    -> Result Selection + SelectionTrace
    -> resolved result features / FeatureSnapshot
    -> Coverage
    -> typed CheckInput + CheckExecutionContext
    -> CheckEngine
    -> canonical CheckResult
    -> Assessment
    -> Reporter
```

This lane is required for modal participation, story drift, torsional A1, and any domain where a formal check depends on selecting rows, modes, cases, combinations, stories, directions, stations, steps, or an envelope from a candidate result set.

### 4.3 Boundary ownership

| Boundary | Owner | MUST NOT own | Fail-closed trigger |
|---|---|---|---|
| ETABS -> raw evidence | acquisition/provider | code limits, verdicts | session/source ambiguity, failed fetch |
| raw evidence -> feature | resolver | applicability, pass/fail | missing/ambiguous factual mapping or unit |
| raw result -> selected evidence | selection policy | regulatory limit/status | incomplete required capture, unresolved policy |
| feature -> runnable check | Coverage + input adapter | engineering verdict | missing feature/context/readiness |
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
| source unit identity | acquisition/evidence | reporter, evaluator |
| explicit unit conversion | authorized factual normalization using explicit unit metadata | magnitude/name heuristic |
| result-row identity | raw result evidence layer | reporter |
| capture completeness | result acquisition/evidence | result selector, reporter MUST consume but not invent |
| result candidate selection | explicit result-selection policy | reporter, product check builder, pure evaluator |
| selection audit trail | `SelectionTrace` | `CheckResult` status logic |
| feature availability | Coverage | CheckEngine status logic |
| execution context readiness | Coverage + `CheckExecutionContext` validation | hidden globals/defaults |
| regulatory applicability | CheckEngine | resolver, selection, coverage, reporter |
| regulatory limit | CheckEngine/catalog-backed canonical check authority | reporter/product report/legacy module |
| formula/comparison orchestration | CheckEngine | reporter, assessment |
| pure mathematical kernel | pure evaluator | reporter |
| check status/verdict | CheckEngine | reporter, assessment, product report helper |
| formal result construction | CheckEngine | reporter/product parallel DTO builder |
| expected-vs-observed reconciliation | Assessment | reporter |
| structural completeness | Assessment | reporter |
| formatting/localization | Reporter | CheckEngine SHOULD NOT own presentation formatting |

### Integration boundary

Any new production code that contains a regulatory threshold, PASS/FAIL/OK decision, result-row governing choice, or unit inference MUST identify its constitutional owner during review. If the owner is not the authorized layer above, the change MUST be rejected or redesigned.

---

## 6. Context grain model

### FROZEN CONSTITUTIONAL RULE

Context MUST be modeled at the grain at which it is true. Context MUST NOT be smuggled across grains through globals, implicit defaults, mutable singleton state, or reporter-side guesses.

Five context grains are recognized.

### 6.1 Session/acquisition grain

Examples:

- ETABS process/instance identity,
- model filename/model identity,
- ETABS version,
- source mode: live vs replay,
- explicit present/source units,
- acquisition timestamp or run identity,
- display-state transaction state.

Owner: ETABS acquisition.

### 6.2 Evidence/table grain

Examples:

- table name,
- field keys,
- source table version/shape,
- fetch diagnostics,
- raw row identity,
- capture status,
- parser/probe signature.

Owner: provider/evidence layer.

### 6.3 Entity/feature grain

Examples:

- frame/column/wall/story identity,
- section assignment,
- resolved width/depth,
- material name,
- `fck`,
- selected result feature.

Owner: FeatureResolver / result-resolution layer.

### 6.4 Check-execution grain

Examples:

- check id,
- code edition/design basis,
- mandatory policy selections,
- applicable direction/case family,
- context needed to decide regulatory applicability,
- canonical catalog/limit identity.

Owner: `CheckExecutionContext` consumed by `CheckEngine`.

### 6.5 Result/assessment/report grain

Examples:

- formal `CheckResult` identity,
- expected check inventory,
- missing/duplicate reconciliation,
- report ordering/localization.

Owners: `CheckResult`, Assessment, Reporter respectively.

### Fail-closed behavior

If a required context value exists only at a broader or narrower grain and cannot be unambiguously bound to the check instance, canonical execution MUST block instead of applying it globally.

---

## 7. Provenance and review model

### FROZEN CONSTITUTIONAL RULE

Every canonical factual feature and selected result feature used by a check MUST be reviewable back to source evidence.

At minimum provenance SHOULD support:

- source mode (`live`, `replay`, or other explicit source type),
- model/session identity,
- source table name,
- source field/column identity,
- source row or row-set identity,
- raw source value,
- source unit,
- normalized value and normalized unit,
- resolver/selection policy identity,
- selection trace identity where selection occurred,
- capture status for result evidence,
- diagnostics that explain missing/ambiguous evidence.

Provenance MUST describe what happened; it MUST NOT be used as a hidden location for regulatory policy.

### Review invariant

A reviewer MUST be able to inspect a `CheckResult` and traverse backward to the evidence and policy/context that produced it without rerunning reporter calculations.

### Separation of identity and payload

For result evidence, identity MUST be represented separately from numeric payload so that two rows with equal values are not collapsed merely because their payloads match.

---

## 8. ETABS acquisition constitution

### FROZEN CONSTITUTIONAL RULE

ETABS acquisition owns connection, session identity, explicit unit context, table/result retrieval, parsing handoff, and any temporary ETABS display/read-state transaction required for retrieval.

It MUST NOT own TBDY applicability, code limits, engineering verdicts, or reporter presentation.

### 8.1 Session identity

Canonical live acquisition MUST establish enough identity to reject an ambiguous, stale, wrong, or unusable ETABS target. Model filename alone MAY be evidence but MUST NOT be assumed sufficient if multiple instances or stale COM objects can be confused.

Connection success MUST mean more than “a COM object exists.” The acquisition boundary SHOULD verify a coherent SapModel/database-table surface and record the verified identity.

### 8.2 Unit context

Source units MUST be explicit acquisition evidence. Setting ETABS present units MAY be part of an explicit transaction, but canonical engineering MUST NOT infer source units solely from value magnitudes.

If acquisition changes present units, it MUST record the change and MUST restore prior state when the change is temporary under the ratified safety transaction design.

### 8.3 Read/display state

A fetcher MAY need to select a case or combination for display because ETABS can return headers/record counts without usable table data until display selection is set.

Such mutation MUST be treated as a transaction:

1. identify the current state where the API permits it,
2. record intended mutation,
3. apply only the minimum mutation required,
4. fetch,
5. restore prior state,
6. record restoration success/failure,
7. fail closed if the state cannot be trusted for a canonical result.

Hidden or unbounded ETABS state mutation is prohibited.

### 8.4 Acquisition output

Acquisition output MUST expose retrieval diagnostics sufficient to distinguish:

- call failure,
- empty table,
- header-only response,
- records-reported-but-data-empty response,
- successful parsed rows,
- partial capture,
- unsupported signature/API shape.

### CURRENT IMPLEMENTATION

`tbdy_engine/etabs/connection.py` attaches through helper/GetActiveObject fallbacks and validates a SapModel/table surface. It also calls `SetPresentUnits(6)` during connect and again in `get_sap()`. That is usable acquisition functionality but does not yet implement the full explicit state-transaction constitution.

`tbdy_engine/providers/etabs_display_table_fetcher.py` probes multiple display-table COM signatures and records detailed fetch/parser diagnostics. It can call `SetLoadCombinationsSelectedForDisplay` or `SetLoadCasesSelectedForDisplay` before fetch. The audited baseline does not provide the ratified snapshot/restore transaction contract around that mutation.

No separate `etabs_com_attach.py` exists at the audited baseline under the inspected repository paths. The attachment responsibility is currently represented by `tbdy_engine/etabs/connection.py`.

### PENDING IMPLEMENTATION RATIFICATION

The exact ETABS Safety Foundation class/module/API structure is not frozen. The semantic requirements in this section are frozen.

---

## 9. Raw result identity and capture

### FROZEN CONSTITUTIONAL RULE

Result evidence MUST distinguish row identity, row payload, and capture completeness.

A result row identity SHOULD use all source keys required to distinguish candidates at source grain, for example as applicable:

- model/run identity,
- table identity,
- case/combination identity and type,
- story,
- object/element,
- direction/component,
- mode,
- step/step type,
- station/location,
- source row index or equivalent stable discriminator.

Equal numeric payload does not imply equal identity.

### Capture status

Result acquisition MUST expose a capture status equivalent to at least:

- `FULL` — the complete candidate universe required by the intended selection is known to have been captured;
- `PARTIAL` — useful rows exist but completeness is not guaranteed;
- `NONE`/failed — no usable candidate universe exists.

Exact enum names MAY differ, but semantics MUST be explicit.

### Derived-envelope rule

Any governing/envelope calculation that requires comparison across the candidate universe MUST require `FULL` capture. If capture is `PARTIAL`, selection MUST NOT pretend the visible maximum/minimum is governing. The path MUST block or remain explicitly unresolved.

### CURRENT IMPLEMENTATION

`tbdy_engine/features/result_evidence.py` provides shared result-evidence bundle/capture semantics and is a valid foundation. Adoption is incomplete across modal, drift, and torsion product/report paths.

---

## 10. Result-selection constitution

### FROZEN CONSTITUTIONAL RULE

Result selection is a first-class boundary between raw result evidence and check execution.

A result-selection component MUST:

- consume raw result evidence with stable identity,
- consume an explicit deterministic selection policy,
- verify required capture completeness,
- emit selected evidence or resolved result features,
- emit a `SelectionTrace`,
- preserve unresolved reasons.

It MUST NOT:

- apply regulatory PASS/FAIL limits,
- create canonical `CheckResult`,
- convert missing authoritative metadata into a confident policy decision through case-name heuristics,
- use report layout needs to decide engineering selection,
- silently drop candidates without trace.

### Applicability boundary

Selection determines which factual result evidence is presented to execution under an explicit selection policy. Regulatory applicability remains owned by `CheckEngine`.

For example, “this row belongs to an explicitly selected seismic result family” may be a selection fact; “TBDY check X applies and passes” is an engine decision.

### Fail-closed behavior

If required policy metadata is absent, contradictory, or capture is insufficient for the requested governing selection, selection MUST return unresolved/blocked evidence. It MUST NOT choose by filename, case-name substring, first row, last row, or largest visible value unless that behavior is an explicitly authorized and reviewable policy with adequate evidence.

---

## 11. SelectionTrace

### FROZEN CONSTITUTIONAL RULE

`SelectionTrace` is the audit artifact for result selection. It MUST be separate from the formal engineering verdict.

A conforming trace SHOULD contain:

- trace identity,
- selection policy id/version,
- source result-evidence bundle identity,
- source capture status,
- candidate row identities,
- candidate inclusion/exclusion decisions,
- reasons for each exclusion where material,
- tie-breaking/governing rule identity,
- selected row identities,
- unresolved reason(s), if any,
- diagnostics needed for review.

`SelectionTrace` MUST NOT contain a regulatory limit or final compliance status except as inert source metadata already present in evidence. It MUST NOT become an alternate `CheckResult`.

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
- selected result features and their trace/evidence references.

It MUST NOT contain:

- regulatory PASS/FAIL/OK status,
- hidden code limits,
- check applicability decisions,
- report-specific formatting,
- inferred policy defaults that belong to execution context.

Feature resolvers MUST produce facts, not verdicts.

### Integration boundary

Coverage MUST consume the snapshot rather than re-fetching ETABS or recalculating source facts. CheckEngine MUST consume typed inputs built from the snapshot/readiness boundary rather than reaching backward into ETABS/provider code.

---

## 13. Coverage constitution

### FROZEN CONSTITUTIONAL RULE

Coverage is the canonical availability/readiness gate between facts and formal check execution.

Coverage owns questions such as:

- Is the required feature present?
- Is source evidence usable?
- Is the unit explicit and acceptable?
- Is required result capture complete?
- Is mandatory execution context resolved?
- Is the typed check input constructible?

Coverage MUST NOT answer:

- Does the check apply under the code?
- What is the regulatory limit?
- Does the element pass?
- What ratio/status should be reported?

Those remain `CheckEngine` authority.

### Fail-closed behavior

A check that lacks a mandatory feature, explicit unit, required selection resolution, or mandatory execution context MUST be unavailable/not-ready/blocked before formal evaluation. Missing evidence MUST NOT be converted to zero, a benign default, PASS, or “not applicable” unless the canonical engine explicitly decides regulatory non-applicability from sufficient context.

### CURRENT IMPLEMENTATION

CoverageBuilder and accepted wall/geometry orchestration establish the correct boundary for those domains. Repository-wide adoption is incomplete; therefore Coverage is `PARTIALLY_CONFORMING` at system scope even though the wall reference is conforming.

---

## 14. CheckInput / CheckExecutionContext

### FROZEN CONSTITUTIONAL RULE

Formal execution MUST accept a typed `CheckInput` plus explicit `CheckExecutionContext` or an equivalent typed boundary preserving the same semantics.

`CheckInput` is the sole formal execution-data boundary. It MUST carry normalized factual inputs required by the check and references necessary for auditability.

`CheckExecutionContext` carries mandatory policy/context that is not itself a source fact, for example code/design basis or execution policy choices.

### Prohibited behavior

Formal execution MUST NOT depend on:

- reporter globals,
- hidden module constants outside the canonical check authority,
- mutable ETABS state,
- environment-dependent defaults,
- implicit unit assumptions,
- case-name guesses,
- a resolver deciding regulatory policy.

### Readiness

If mandatory execution context is unresolved, the check is not runnable. The system MUST represent that state explicitly and MUST NOT manufacture a result by choosing an arbitrary default.

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

The engine MAY delegate mathematical kernels to pure evaluators and MAY consume catalog data, but delegation MUST NOT transfer regulatory ownership to reporters, feature resolvers, assessment, or compatibility modules.

### One-engine rule

The repository MUST NOT create domain-specific mini-engines that independently produce formal regulatory results. Domain-specific evaluators/registrations MAY compose into the canonical engine.

### Fail-closed behavior

Unknown check id, duplicate check registration, unresolved mandatory context, invalid normalized input, or missing authoritative rule MUST fail deterministically. The engine MUST NOT infer a rule from a nearby check or silently fall back to product-report constants.

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

There MUST be exactly one formal production `CheckResult` DTO.

The canonical result MUST be produced by `CheckEngine` and SHOULD carry enough information to review:

- check identity,
- subject/entity identity,
- applicable/not-applicable/blocked/evaluated semantics as defined by the result contract,
- normalized value(s),
- authoritative limit/rule identity where applicable,
- comparison/ratio semantics where applicable,
- final status,
- execution-context identity or summary,
- evidence/provenance references,
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
- creation of a parallel formal result.

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

Units are explicit evidence, not a guess.

1. Acquisition MUST record source unit context.
2. Raw evidence SHOULD preserve raw value and source unit.
3. Conversion MUST use an explicit unit mapping/contract.
4. FeatureSnapshot MUST expose normalized unit with the normalized value where dimensional meaning matters.
5. CheckInput MUST receive normalized values whose units are known by contract.
6. Reporter MUST NOT infer or repair engineering units.
7. Missing or contradictory units MUST block canonical execution when the check depends on them.

### Prohibited heuristics

The following are prohibited as canonical engineering authority:

- “if absolute value <= 30, treat as metres; otherwise millimetres,”
- “if strength > 1000, divide by 1000; otherwise assume MPa,”
- guessing units from GUI strings without explicit acquisition evidence,
- choosing a conversion because the resulting value looks plausible.

### CURRENT IMPLEMENTATION

`tbdy_engine/engine/unit_context.py` contains an immutable explicit `UnitContext` and a fail-closed `require_unit_context_for_engineering()` path, which are conforming foundations. It also contains optional compatibility heuristics/fallback discovery. Those heuristic paths MAY remain for compatibility/diagnostics but MUST NOT feed canonical engineering execution.

`tools/render_product_report.py` and `tbdy_engine/product_reports/material_evidence.py` contain magnitude-based conversions that are legacy debt.

---

## 22. Fail-closed rules and prohibited heuristics

### FROZEN CONSTITUTIONAL RULE

Canonical execution MUST stop at the earliest boundary that can prove required information is unresolved.

The following conditions MUST NOT produce a confident engineering PASS/FAIL result:

- missing mandatory feature,
- unknown/ambiguous dimensional unit,
- unresolved execution policy/context,
- missing authoritative result-case metadata when the selection policy requires it,
- `PARTIAL` capture for a full-universe governing/envelope selection,
- duplicate canonical check registration,
- unknown check id,
- failed ETABS state restoration where result trust depends on restoration semantics,
- ambiguous or stale ETABS session identity,
- conflicting source evidence without an explicit resolution policy.

### Prohibited heuristic authority

Canonical engineering MUST NOT use these as substitutes for missing authority:

- value magnitude,
- string/name substring,
- first/last row,
- first successful case unless policy explicitly defines it,
- “largest row seen” when the full universe is not captured,
- reporter defaults,
- silent unit defaults,
- silent code-edition defaults,
- mutable global ETABS present units as proof of source units,
- test fixture assumptions leaking into live execution.

Heuristics MAY exist for diagnostics, user assistance, legacy compatibility, or discovery only if their non-authoritative status is explicit and they cannot silently enter canonical execution.

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
- shared execution-boundary semantics.

### 23.2 Domain-worker surfaces

A domain worker SHOULD primarily own:

- domain raw-evidence mapping,
- domain FeatureResolver,
- domain-specific factual feature definitions,
- typed domain CheckInput adapter,
- pure evaluator,
- domain registration contribution,
- additive catalog overlay,
- domain tests/replay fixtures,
- compatibility delegation for that domain.

### 23.3 Hotspot avoidance

`tbdy_engine/checks/registry.py`, `tbdy_engine/checks/engine.py`, base catalogs, `tbdy_engine/product_reports/check_results.py`, and `tools/render_product_report.py` are known integration hotspots. Multiple workers SHOULD NOT independently redesign them during domain migrations.

### 23.4 No speculative framework rule

A worker MUST NOT create a generic plugin framework, universal evidence bag, second engine, or alternate formal-result abstraction merely to avoid a merge conflict. Shared abstractions SHOULD be generalized only after at least two real domains prove the shared semantics.

---

## 24. Vertical-slice lifecycle

### FROZEN CONSTITUTIONAL RULE

Each domain migration SHOULD proceed as a vertical slice in this order:

1. inventory current checks/results and duplicate authorities,
2. identify exact source tables/result evidence and provenance,
3. establish factual raw/canonical evidence contract,
4. implement/confirm factual FeatureResolver,
5. produce `FeatureSnapshot`,
6. for result domains, establish stable result identity, capture status, selection policy, and `SelectionTrace`,
7. establish Coverage/readiness,
8. build typed `CheckInput` + `CheckExecutionContext`,
9. register pure evaluator/check with canonical `CheckEngine`,
10. produce canonical `CheckResult`,
11. reconcile through Assessment,
12. convert reporter/product API to serialization/delegation only,
13. run boundary, replay, and live acceptance,
14. remove/deactivate duplicate authority only after parity/acceptance.

A migration MUST NOT begin by deleting legacy behavior before the canonical path can prove equivalent or intentionally changed semantics.

### Required evidence for a completed slice

A completed slice SHOULD demonstrate:

- source evidence provenance,
- explicit units,
- missing/invalid input behavior,
- exact-boundary comparisons where numeric limits exist,
- duplicate registration failure,
- compatibility delegation,
- non-regression of previously canonical slices,
- reporter inability to change engineering status.

---

## 25. Legacy compatibility and migration

### FROZEN CONSTITUTIONAL RULE

Legacy compatibility is permitted as a temporary interface, not as a second authority.

A compatibility path MUST converge toward:

```text
legacy/public API
    -> canonical acquisition/features/selection
    -> Coverage
    -> canonical CheckEngine
    -> canonical CheckResult
    -> compatibility serialization
```

It MUST NOT retain independent thresholds, applicability, formula, status, or row-selection logic once the domain is migrated.

### Migration sequence

The currently approved migration order is:

1. **Batch 1 — Beam + Column Geometry**
2. **Batch 2 — Concrete Material Strength**
3. **Batch 3 — Modal Mass Participation**
4. **Batch 4 — Story Drift + Torsional A1**
5. **Batch 5 — Remaining Legacy Design/Result Authorities**

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

- one source-to-result canonical path,
- explicit provenance,
- explicit units,
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

1. Exactly one execution path exists from raw section evidence -> normalized feature -> `FeatureSnapshot` -> Coverage -> typed `CheckInput` -> `CheckEngine` -> canonical `CheckResult`.
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

Modal, drift, torsion, and later envelope/governing result domains additionally MUST demonstrate:

- stable candidate identity,
- explicit capture status,
- `FULL` capture where full-universe governing selection is required,
- explicit selection policy,
- `SelectionTrace`,
- no reporter/product selection authority,
- no case-name fallback used as authoritative metadata,
- regulatory applicability still decided by `CheckEngine`.

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
| Coverage | `PARTIALLY_CONFORMING` | Correctly used by wall/geometry orchestration; not yet universal across material/result domains. | Mandatory readiness boundary for every canonical check. |
| Canonical `CheckResult` | `CONFORMING` | `tbdy_engine/checks/result.py` is used by accepted engine path. | Remain sole formal DTO. |
| `WallAssessment` | `CONFORMING` | Reconciles accepted wall expected/observed results rather than becoming a wall formula engine. | Reuse semantics only when second domain proves common abstraction. |
| `product_reports/check_results.py` | `LEGACY_DEBT` | Builds parallel formal-looking `check_result.v1` dictionaries and owns material/modal/drift/A1 status/limit/selection behavior. | Compatibility serializer over canonical `CheckResult` only. |
| `tools/render_product_report.py` | `LEGACY_DEBT` | Owns geometry/modal thresholds, ratios/statuses, reporter-only column checks, magnitude-based length conversion. | Serialization/display only. |
| `engine/unit_context.py` | `PARTIALLY_CONFORMING` | Has immutable explicit `UnitContext` and fail-closed engineering requirement; also compatibility heuristic fallback paths. | Explicit acquisition unit context; heuristics excluded from canonical engineering. |
| `etabs/connection.py` | `PARTIALLY_CONFORMING` | Attaches to running ETABS with multiple COM fallbacks, validates SapModel/tables, but changes present units and lacks ratified session transaction contract. | Safe explicit session identity + state transaction semantics. |
| `etabs_com_attach.py` | `NOT_IMPLEMENTED` | No separate file with this exact responsibility/name was found on audited baseline; attach behavior resides in `tbdy_engine/etabs/connection.py`. | Exact attach API shape pending ETABS Safety ratification. |
| Display-table fetcher | `PARTIALLY_CONFORMING` | Shared fetcher probes COM signatures and records rich diagnostics; may mutate display case/combination selection without baseline transaction restore contract. | Read-safe transactional acquisition with observable snapshot/restore. |
| Result-evidence capture | `PARTIALLY_CONFORMING` | `features/result_evidence.py` provides identity/capture foundations, not yet adopted consistently by modal/drift/A1. | Shared stable identity + explicit FULL/PARTIAL semantics for all result domains. |
| Shared `SelectionTrace` | `NOT_IMPLEMENTED` | No complete shared canonical trace boundary verified at baseline. | Required for migrated result-selection domains. |
| Beam geometry | `PARTIALLY_CONFORMING` | Canonical engine/input/Coverage pieces exist, but reporter duplicates limits/status/unit behavior. | B1 single canonical vertical slice. |
| Column geometry | `PARTIALLY_CONFORMING` | Canonical engine/input/Coverage pieces exist; reporter also owns area/aspect checks not present in engine inventory. | B1 reconcile/promote/retire inventory, then single authority. |
| Concrete material strength | `LEGACY_DEBT` | Evidence module is mostly factual, but unit normalization uses magnitude heuristic; product result builder owns minimum fck/status. | B2 explicit-unit factual feature -> Coverage -> engine. |
| Modal mass participation | `LEGACY_DEBT` | Reporter/product path owns threshold/status/selected-row behavior; no complete canonical result-selection trace path. | B3 full result evidence -> selection trace -> engine. |
| Story drift | `LEGACY_DEBT` | Product result path owns frozen threshold/status and case-selection heuristics. | B4 explicit selection/context -> engine. |
| Torsional A1 | `LEGACY_DEBT` | Product path owns threshold/status and permits case-name fallback for generic/missing case metadata. | B4 explicit authoritative selection/context -> engine. |
| Beam legacy design | `LEGACY_DEBT` | `design/beams/*` contains independent engineering calculation paths outside canonical engine. | B5 family-by-family canonical migration. |
| Column legacy design | `LEGACY_DEBT` | `design/columns/*` contains independent engineering calculation paths outside canonical engine. | B5 family-by-family canonical migration. |
| Registration exact implementation | `PENDING_IMPLEMENTATION` | Existing registry/engine composition works for accepted checks but is a shared hotspot and not the ratified B1 end state. | Deterministic additive composition; exact API pending B1 ratification. |
| ETABS safety transaction API | `PENDING_IMPLEMENTATION` | Current connection/fetching behavior lacks ratified end-to-end state/session transaction interface. | Frozen safety semantics; exact API pending ETABS Safety ratification. |

### 27.2 Material debt register

| Path | Current behavior | Violated constitutional rule | Target authority | Planned migration batch | Severity |
|---|---|---|---|---|---|
| `tools/render_product_report.py` | Defines geometry thresholds including beam width/depth/ratio and column limits; computes ratios/status; performs magnitude-based `_length_to_mm`; owns modal threshold/status behavior. | Reporter MUST be serialization-only; units MUST be explicit; CheckEngine sole verdict authority. | FeatureSnapshot/Coverage/CheckEngine/canonical `CheckResult`; reporter delegates. | B1 + B3 | **CRITICAL** |
| `tbdy_engine/product_reports/check_results.py` | Builds parallel `check_result.v1`; owns `MIN_FCK_MPA`, modal aggregation, `MAX_STORY_DRIFT_RATIO`, `MAX_TORSION_A1_COEFFICIENT`, selection/status behavior. | One formal result DTO; CheckEngine sole regulatory authority; selection separate from compliance. | Canonical result-selection boundary + CheckEngine + canonical `CheckResult`. | B2 + B3 + B4 | **CRITICAL** |
| `tbdy_engine/product_reports/material_evidence.py` | Mostly factual evidence/provenance, but `_fck_to_mpa` divides values >1000 and otherwise assumes MPa. | No magnitude-based unit inference. | Explicit source `UnitContext` + factual material resolver. | B2 | **HIGH** |
| `tbdy_engine/engine/unit_context.py` | Provides explicit unit context and fail-closed requirement but retains heuristic fallback/discovery compatibility paths. | Heuristic authority MUST NOT enter canonical engineering. | Explicit ETABS acquisition unit context; heuristic APIs compatibility/diagnostic only. | ETABS Safety + B1/B2 | **HIGH** |
| `tbdy_engine/etabs/connection.py` | Attaches to active ETABS, validates tables, calls `SetPresentUnits(6)` during connect/get_sap without a ratified snapshot/restore transaction abstraction. | ETABS mutation MUST be explicit/bounded/restored when temporary; source units are evidence. | ETABS acquisition/session transaction boundary. | ETABS Safety Foundation | **HIGH** |
| `tbdy_engine/providers/etabs_display_table_fetcher.py` | Robust COM signature probing/diagnostics; may call display-selection mutators before result fetch; baseline does not establish restoration transaction. | No hidden/unbounded ETABS state mutation. | ETABS acquisition read/display transaction. | ETABS Safety Foundation | **HIGH** |
| `tbdy_engine/checks/engine.py` + `tools/render_product_report.py` | Beam/column geometry authority is split: engine has canonical geometry checks while reporter repeats numeric policy/status. | One authority per decision. | Canonical CheckEngine/catalog path. | B1 | **HIGH** |
| `tools/render_product_report.py` | Contains reporter-only column minimum-area and aspect-ratio criteria not represented in accepted engine inventory. | Check inventory and regulatory authority MUST be explicit/canonical. | Explicit promote-to-canonical or retire decision, then CheckEngine. | B1 | **HIGH** |
| `tbdy_engine/product_reports/check_results.py` + report path | Modal selected-row/threshold/status flow remains outside canonical result evidence/selection/engine architecture. | Raw result identity + SelectionTrace + CheckEngine authority. | ResultRowEvidenceBundle -> SelectionTrace -> typed input -> CheckEngine. | B3 | **HIGH** |
| `tbdy_engine/product_reports/check_results.py` | Drift case selector uses metadata/name patterns and owns product threshold/status. | Selection MUST be explicit/traceable; regulatory status belongs to engine; no heuristic substitution for missing authority. | Result selection + SelectionTrace + CheckEngine. | B4 | **CRITICAL** |
| `tbdy_engine/product_reports/check_results.py` | Torsion A1 selector permits name fallback when metadata is generic/missing and owns threshold/status. | Same as drift; case-name fallback MUST NOT be canonical authority. | Result selection + SelectionTrace + CheckEngine. | B4 | **CRITICAL** |
| `tbdy_engine/design/beams/*` | Independent legacy beam engineering calculations exist outside canonical execution boundary. | One regulatory authority / one formal result path. | Domain vertical slices through canonical CheckEngine. | B5 | **HIGH** |
| `tbdy_engine/design/columns/*` | Independent legacy column engineering calculations exist outside canonical execution boundary. | One regulatory authority / one formal result path. | Domain vertical slices through canonical CheckEngine. | B5 | **HIGH** |

### 27.3 Current authority map by audited domain

| Domain | Facts | Coverage/input | Formula/limit/status | Formal result | Reporter | State |
|---|---|---|---|---|---|---|
| Wall | canonical factual/evidence path | canonical | CheckEngine | canonical `CheckResult` | downstream display | **canonical reference** |
| Beam geometry | factual features exist | canonical pieces exist | engine + duplicate reporter | canonical + report duplicate behavior | calculates | **split authority** |
| Column geometry | factual features exist | canonical pieces exist | engine + reporter-only criteria | canonical + report duplicate behavior | calculates | **split inventory/authority** |
| Material | evidence mostly factual but unit heuristic | canonical boundary incomplete | product builder | product parallel dict | downstream | **legacy product authority** |
| Modal | result evidence foundation incomplete in product path | canonical boundary incomplete | reporter/product | product parallel dict | calculates/selects | **legacy result authority** |
| Drift | product result selection | canonical boundary incomplete | product builder | product parallel dict | downstream | **legacy result authority** |
| Torsion A1 | product result selection | canonical boundary incomplete | product builder | product parallel dict | downstream | **legacy result authority** |

### 27.4 Debt interpretation rule

The presence of legacy debt does not invalidate the accepted wall architecture. It means new work MUST migrate toward the wall-established boundaries rather than copying product/report authority patterns.

No test-only threshold constant is classified as duplicate production authority merely because its numeric value matches production policy.

---

## 28. Current acceleration roadmap

### FROZEN CONSTITUTIONAL RULE

The fastest safe route is authority convergence, not framework replacement.

### Batch 1 — Beam + Column Geometry

Goal: make geometry the second broadly canonical domain and prove additive composition.

Required moves:

- retain raw/factual geometry resolution,
- require explicit units,
- preserve Coverage and typed geometry input,
- keep `CheckEngine` as sole geometry verdict authority,
- move reporter to serialization-only,
- resolve column minimum-area/aspect inventory explicitly: promote or retire,
- establish additive deterministic registration with duplicate-id failure,
- pass the twenty-item B1 gate in Section 26.

This batch SHOULD NOT introduce a new generic framework.

### Batch 2 — Concrete Material Strength

Goal: convert material from factual evidence + product verdict into a canonical vertical slice.

Required moves:

- expose explicit source unit metadata,
- remove magnitude-based `fck` normalization from canonical path,
- resolve canonical `concrete_fck_mpa` or equivalent typed factual feature,
- pass through FeatureSnapshot/Coverage/typed input/context,
- make CheckEngine own minimum strength/applicability/status,
- make product result/report paths delegate.

### Batch 3 — Modal Mass Participation

Goal: prove the result-evidence selection architecture.

Required moves:

- capture all relevant modal candidates with stable identity,
- require `FULL` capture for governing/final-mode policy where complete universe is required,
- represent applicable directions/case identity/type and governing policy explicitly,
- emit `SelectionTrace`,
- make CheckEngine own 0.95 or other authoritative limit/comparison/status,
- remove reporter/product threshold/status/selection authority.

### Batch 4 — Story Drift + Torsional A1

Goal: reuse the result-selection constitution for two more real domains.

Required moves:

- share stable result identity/capture semantics,
- establish explicit seismic case classification/policy context,
- emit traces for row/case selection,
- make CheckEngine own regulatory applicability/limits/status,
- remove case-name fallback as canonical authority,
- remove product thresholds/verdict recomputation.

### Batch 5 — Remaining legacy design/result authorities

Goal: migrate independent design families without a giant rewrite.

Required moves:

- inventory real production callers,
- choose small check/result families,
- construct canonical vertical slices,
- preserve compatibility by delegation,
- delete duplicate design authority only after accepted replacement.

### Acceleration rule

Parallelization SHOULD increase only after the shared registration seam and result-evidence semantics have been proven by real vertical slices. Architecture speed is measured by reduction of duplicate authority, not by number of new abstraction files.

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
- explicit source unit context,
- bounded ETABS state mutation,
- transaction-style snapshot/mutate/fetch/restore evidence where temporary display/read state changes are required,
- failure/restore diagnostics,
- fail-closed ambiguous or untrusted session state,
- live versus replay provenance.

Not yet ratified:

- exact attach/session class names,
- exact transaction context-manager/API shape,
- exact snapshot object schema,
- exact restore mechanism for every ETABS API variant,
- whether attachment and display-state transactions reside in one module or multiple modules.

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

The following condensed list is normative and is intended for implementation reviews.

1. All implementation workers MUST conform to this constitution.
2. Conflicting requests MUST stop and surface the conflict; workers MUST NOT silently create parallel architecture.
3. ETABS acquisition MUST own source/session acquisition and MUST NOT own regulatory verdicts.
4. ETABS state mutation MUST be explicit, bounded, and restorable where temporary mutation is required.
5. Source units MUST be explicit evidence.
6. Magnitude-based unit inference MUST NOT enter canonical engineering execution.
7. Raw evidence/canonical tables MUST contain facts, not PASS/FAIL policy.
8. FeatureResolver MUST resolve facts and explicit units only.
9. FeatureSnapshot MUST contain facts/evidence only, not regulatory verdicts.
10. Raw result identity MUST be distinct from numeric payload.
11. Result capture completeness MUST be explicit.
12. Derived governing/envelope selection requiring the full universe MUST require `FULL` capture.
13. Result selection MUST use explicit deterministic policy.
14. Result selection MUST emit `SelectionTrace`.
15. Result selection MUST NOT own regulatory PASS/FAIL.
16. Case-name fallback MUST NOT replace missing authoritative metadata in canonical selection.
17. Coverage MUST own availability/readiness only.
18. Missing required fact/unit/context MUST fail closed.
19. Typed `CheckInput` + explicit `CheckExecutionContext` MUST be the formal execution boundary.
20. Mandatory execution policy MUST NOT be hidden in globals/reporters/defaults.
21. `CheckEngine` MUST be sole regulatory authority.
22. Pure evaluators MUST be deterministic math only.
23. There MUST be one canonical formal `CheckResult` DTO.
24. Product/report dictionaries MUST NOT become a parallel formal result authority.
25. Assessment MUST reconcile expected versus observed results and MUST NOT recompute engineering formulas.
26. Missing/duplicate expected formal results MUST prevent structurally complete assessment.
27. Reporter MUST serialize/display only.
28. Reporter MUST NOT own thresholds, ratios, applicability, result selection, unit inference, or formal status.
29. Registration MUST be deterministic and duplicate check ids MUST fail.
30. Registration SHOULD be additive to support safe parallel domain work.
31. Shared abstractions SHOULD generalize proven semantics, not create universal untyped data bags.
32. Compatibility APIs MUST delegate after migration and MUST NOT preserve duplicate verdict authority.
33. Legacy authority MUST be removed only after canonical acceptance/parity is demonstrated.
34. The accepted wall path is a reference implementation, not permission to make every wall class generic.
35. B1 exact registration/composition shape is pending ratification; semantics are frozen.
36. ETABS Safety exact session/transaction API shape is pending ratification; semantics are frozen.
37. Unmerged sprint work MUST NOT be used as accepted baseline evidence.
38. A feature branch MUST NOT silently amend this constitution by precedent.
39. Architecture incompleteness is not itself an architecture contradiction.
40. When authority is unclear, canonical execution MUST block rather than guess.

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

**Allowed:** acquisition records source strength unit -> resolver converts by explicit mapping -> snapshot stores normalized MPa -> Coverage verifies readiness -> engine binds minimum-strength rule.

**Prohibited:** “value > 1000 means kN/m², divide by 1000; otherwise assume MPa.”

### B.4 Modal mass participation

**Allowed:** acquire complete modal rows with case/direction/mode identities -> mark capture `FULL` -> explicit policy selects governing/final mode and emits `SelectionTrace` -> engine decides applicable regulatory threshold/status.

**Prohibited:** reporter selects a visible mode, applies `0.95`, and calls the report compliant.

### B.5 Story drift

**Allowed:** result evidence records authoritative case metadata and row identities -> explicit selection policy selects intended seismic candidates -> trace records inclusions/exclusions -> engine decides applicability and drift limit.

**Prohibited:** product code treats any case name containing `drift`, `seismic`, or similar text as authoritative when required metadata is unresolved, then applies a hardcoded drift limit.

### B.6 Torsional A1

**Allowed:** explicit case/result metadata plus selection policy produce traceable selected A1 evidence -> CheckEngine decides the regulatory comparison.

**Prohibited:** generic/missing case metadata is repaired through a name fallback and directly converted into PASS/FAIL by a product-result builder.

### B.7 Partial result capture

Suppose ten candidate rows are required to establish a maximum but only six are captured.

**Allowed:** capture status `PARTIAL`; selection says governing value unresolved; Coverage blocks the check requiring the full envelope.

**Prohibited:** choose the maximum of the six visible rows and label it governing.

### B.8 ETABS display selection mutation

**Allowed:** acquisition transaction records previous display state, selects the required case/combination, fetches, restores previous state, records restoration evidence, and exposes source/capture diagnostics.

**Prohibited:** a reporter or resolver changes display selection and leaves ETABS in a different state without restoration evidence.

### B.9 UnitContext fallback

**Allowed:** a legacy UI diagnostic uses a heuristic to suggest likely units and labels the result non-authoritative.

**Prohibited:** the same heuristic output enters a canonical `CheckInput` without explicit source-unit evidence.

### B.10 Assessment

**Allowed:** expected checks are `{A, B, C}` and observed canonical results are `{A, B}`; Assessment marks the set incomplete because `C` is missing.

**Prohibited:** Assessment calculates `C` itself or treats missing `C` as PASS.

### B.11 Reporter

**Allowed:** reporter formats `0.007812` as `0.0078` for display while preserving the canonical underlying result/status.

**Prohibited:** reporter rounds the source value first and then re-evaluates a threshold, causing status to change.

### B.12 Compatibility API

**Allowed:** legacy caller receives the historical JSON shape, but every value/limit/status is serialized from the canonical `CheckResult` and provenance is retained where compatible.

**Prohibited:** the compatibility serializer keeps its old threshold constants and recomputes status “for parity.”

### B.13 Registration

**Allowed:** beam and column domains contribute additive definitions to a deterministic composer; duplicate `check_id` aborts composition.

**Prohibited:** import order decides which duplicate check implementation wins.

### B.14 Parallel worker conflict

**Allowed:** a domain worker adds a domain evaluator/overlay while an architecture owner controls the shared composer seam.

**Prohibited:** each worker creates a private registry/engine because editing the shared registry is inconvenient.

### B.15 New domain

A new domain MUST first answer these questions before formal evaluation code is accepted:

1. What is the source evidence?
2. What is its identity and unit contract?
3. Does it require result selection?
4. If yes, what proves capture completeness and what is the explicit selection policy?
5. What factual features enter FeatureSnapshot?
6. What makes Coverage ready?
7. What mandatory `CheckExecutionContext` exists?
8. What check id is registered with CheckEngine?
9. What pure evaluator, if any, performs math?
10. How is the canonical `CheckResult` assessed and reported without recomputation?

If those questions cannot be answered, the domain is not ready to claim canonical engineering execution.
