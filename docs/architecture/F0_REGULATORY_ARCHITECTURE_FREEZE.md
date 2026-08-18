# F0 Regulatory Architecture Freeze

**Status:** NORMATIVE ARCHITECTURE FREEZE  
**Scope:** Full cast-in-place reinforced-concrete TBDY regulatory engine — type system and execution semantics only  
**Repository:** `feridunfc/TBDY`  
**Frozen repository baseline:** `9dcea08dd17c4e48adbfe6c2a1d8858df85e2814`  
**Architecture phase:** F0  

This specification freezes the production architecture that later implementation workers MUST obey. It does not implement any engineering rule, code equation, system table, capacity formula, material limit, ETABS acquisition, or schema migration.

Normative terms **MUST**, **MUST NOT**, **SHALL**, **SHALL NOT**, **MAY**, and **SHOULD** are used deliberately.

---

## 0. Authority order and purpose

Architecture decisions SHALL be interpreted in this order:

1. current repository reality and accepted contracts at the frozen baseline;
2. this F0 freeze specification;
3. the full-engine algorithm blueprint where it does not conflict with this freeze;
4. earlier architecture criticism/refinement material where it does not conflict with this freeze.

Where an earlier blueprint or existing implementation disagrees with this document, this F0 freeze governs future migration. Existing production behavior is not silently changed by this document; migration occurs only through the phased parity sequence in Section 22.

F0 freezes:

- regulatory identity and type contracts;
- authority boundaries;
- source-population boundaries;
- compile lifecycle;
- execute lifecycle;
- dependency validation;
- closure semantics;
- analysis-basis mismatch semantics;
- deterministic execution requirements;
- provenance requirements;
- migration boundaries;
- implementation acceptance criteria for later F0 work.

F0 SHALL NOT implement engineering equations or numerical regulatory thresholds.

---

## 1. Constitutional statements

The following statements are normative and SHALL be mechanically enforceable by the future F0 kernel:

> **ETABS produces evidence, not regulatory truth.**

> **Regulatory derivations produce engineering quantities or regulatory states, not PASS/FAIL verdicts.**

> **Formal checks consume declared facts, selected source quantities, reviewed contexts and regulatory quantities; they do not rediscover them.**

> **Compilation determines the complete regulatory program; execution is not allowed to discover scope.**

> **A changed regulatory analysis basis requires reanalysis, not post-hoc reinterpretation of stale analysis results.**

> **Reporter is serialization/projection only.**

Consequences:

- no regulatory node may query ETABS;
- no reporter may derive or repair engineering truth;
- no evaluator may obtain undeclared model state through a global context;
- no runtime component may add rules, dependencies, applicability branches, or expected closure records;
- no source-selection layer may hide a regulatory governing operation inside factual result processing.

---

## 2. Canonical pipeline

The conceptual production pipeline is frozen as follows:

```text
EVIDENCE
    |
    +--> FACTS / TOPOLOGY
    |
    +--> RAW RESULT EVIDENCE
              |
              v
         SOURCE POPULATION
              |
              +--> SourcePopulation
              |
              +--> SelectedSourceQuantity
                   only where selection is non-regulatory

REVIEWED DECLARATIONS
        |
ANALYSIS SYSTEM ASSUMPTIONS
        |
ANALYSIS EVIDENCE
        |
SYSTEM QUALIFICATION
        |
ANALYSIS-BASIS COMPATIBILITY
        |
        +--> MATCH
        |      |
        |      v
        |   RESOLVED REGULATORY POLICY
        |
        +--> MISMATCH
               |
               v
         REANALYSIS_REQUIRED
               |
         affected downstream STOP

                      |
                      v
                    COMPILE
                      |
           immutable closure inventory
           typed dependency graph
           producer validation
           semantic validation
           cycle validation
                      |
                      v
              TBDYExecutionPlan
                      |
                      v
                    EXECUTE
                 /           \
                v             v
 RegulatoryDerivationSpec   CheckSpec
           |                    |
           v                    v
 RegulatoryQuantity         CheckResult
                 \            /
                  \          /
                   reconciliation
                        |
                        v
                   Full Assessment
```

These layers MUST NOT be collapsed. In particular, source-population formation, regulatory derivation, formal verdict creation, closure reconciliation, and reporting are separate authorities.

---

## 3. Authority boundaries

| Layer | Owns | Explicitly does not own |
|---|---|---|
| Acquisition / evidence | session/source identity, raw facts/results, units, capture completeness, provenance | regulatory applicability, derivation, limits, verdicts |
| Factual model / topology | normalized factual identity and topology | regulatory system declaration, governing operations, verdicts |
| FeatureSnapshot / factual facts | factual values with evidence | formulas, ratios, applicability, PASS/FAIL |
| SourcePopulation | exact bounded source population and factual source semantics | regulatory governing selection, amplification, code equations, capacity comparison |
| SelectedSourceQuantity | only non-regulatory scalar/source selection | regulatory governing operations or verdicts |
| Reviewed declarations | reviewed regulatory declarations at their true grain | ETABS result fabrication, formal verdicts |
| Analysis assumptions/evidence | what analysis population was actually produced under | post-hoc regulatory reinterpretation |
| System qualification | qualification facts/states derived from declared context and analysis evidence | stale-result repair |
| Analysis-basis compatibility | MATCH / mismatch state and affected scope | formal CheckResult status |
| RegulatoryCompiler | complete immutable program, closure inventory, typed DAG, static validation | runtime engineering execution |
| ReadinessEngine | whether declared dependencies are executable | engineering comparison/verdict |
| RegulatoryEngine | execution of already-compiled derivations/checks | discovery of new scope/dependencies |
| AssessmentEngine | closure reconciliation and full-assessment completeness | re-evaluation of formulas or source selection |
| Reporter | serialization/projection of canonical truth | derivation, selection, comparison, status repair |

No layer MAY silently inherit authority from another layer.

---

## 4. F0 core contract families

F0 has exactly these core contract families:

1. `RuleId`
2. `RuleInstanceId`
3. `Grain`
4. `SemanticType`
5. `PhysicalDimension` + `Unit`
6. `DependencyKey` + `DependencySpec`
7. `ApplicabilityState`
8. `AvailabilityState`
9. `RegulatoryQuantity`
10. `RegulatoryDerivationSpec` + `CheckSpec`
11. `CompiledClosureRecord` + `RuleClosureOutcome`
12. `TBDYExecutionPlan`

`RegulatoryRegistry`, `RegulatoryCompiler`, `RegulatoryStore`, `ReadinessEngine`, `RegulatoryEngine`, and `AssessmentEngine` are services. They are not regulatory truth DTOs.

F0 MUST NOT introduce Chapter-specific domain contracts merely to anticipate later phases.

### 4.1 RuleId

**Purpose.** Stable identity of one registered regulatory rule definition.

**Owns.** Definition identity only.

**Does not own.** Scope instance, direction, story, component, candidate row, execution outcome, or result status.

**Minimum field.** A deterministic canonical identifier.

**Lifecycle.** Declared before registry composition; immutable thereafter.

**Mutability.** Immutable.

**Validation.** Nonblank, canonicalized by construction, globally unique in one registry version. Duplicate `RuleId` is fatal at composition.

**Producers / consumers.** Produced by rule-definition code; consumed by registry, compiler, plan, closure records, traces, and assessment.

### 4.2 RuleInstanceId

**Purpose.** Identity of one compiled verification instance at the regulatory verification grain.

**Owns.** Exact compiled rule-instance identity.

**Does not own.** Envelope candidate identity unless the code explicitly defines that candidate as a separate formal verification grain.

**Minimum fields/contributors.** `RuleId`, grain, scope identity, direction where applicable, and deterministic versioned identity policy.

**Lifecycle.** Created only during compilation from the immutable registry plus immutable scope/context inputs.

**Mutability.** Immutable.

**Validation.** Deterministic, unique within a plan, reproducible from the same compile inputs.

**Producers / consumers.** Produced by `RegulatoryCompiler`; consumed by plan nodes, closure records, quantities, results, traces, and assessment.

Formal instance example shape:

```text
component:B23:zone-1:X:RULE_ALPHA
```

Candidate identities such as positive/negative, top/bottom, maximum/minimum, station, step, or eccentricity belong in `derivation_trace` / `governing_trace` unless a rule explicitly establishes them as formal verification grain.

### 4.3 Grain

**Purpose.** First-class type describing the scope resolution level of a fact, dependency, rule instance, or output.

**Initial bounded vocabulary.** At minimum:

```text
MODEL
STRUCTURAL_ZONE
DIRECTION
STORY
COMPONENT
COMPONENT_DIRECTION
COMPONENT_END
COMPONENT_END_DIRECTION
MATERIAL_DEFINITION
```

The vocabulary MAY be extended deliberately in later phases, but runtime free-form grains are forbidden.

**Owns.** Structural scope resolution type.

**Does not own.** Semantic engineering meaning or units.

**Lifecycle.** Registry/type-system definition before composition.

**Mutability.** Immutable enum/value contract.

**Validation.** Compatibility MUST be explicit. There is no implicit story-to-component, component-to-joint, or X-to-Y coercion.

**Producers / consumers.** Declared by facts, dependency specs, rule specs, compiled instances, and quantities; checked by compiler.

F0 MUST NOT create a generic grain DSL.

### 4.4 SemanticType

**Purpose.** Declares engineering/domain meaning independently from physical dimension and unit.

**Owns.** Semantic identity such as a named factual, source, or regulatory concept.

**Does not own.** Physical dimension, unit conversion, scope grain, or verdict.

**Minimum field.** A registered bounded semantic identifier.

**Lifecycle.** Declared in versioned semantic contracts before composition.

**Mutability.** Immutable.

**Validation.** Dependency source and consumer expectations MUST be semantically compatible before runtime.

**Producers / consumers.** Declared by sources/outputs and `DependencySpec`; validated by compiler.

### 4.5 PhysicalDimension and Unit

**Purpose.** Prevent semantic or dimensional wiring errors and permit only reviewed unit conversions.

**Initial physical dimensions.** At minimum:

```text
FORCE
MOMENT
STRESS
AREA
LENGTH
DIMENSIONLESS
BOOLEAN_STATE
ENUM_STATE
```

No arbitrary free-text physical dimension may be created at runtime.

**Owns.** Dimensional class and explicit unit metadata.

**Does not own.** Semantic identity or regulatory meaning.

**Lifecycle.** Dimension vocabulary and conversion registry exist before compile; concrete unit value accompanies source/output.

**Mutability.** Immutable contracts and immutable unit metadata.

**Validation.** Compiler SHALL validate semantic compatibility, physical-dimension compatibility, and unit convertibility as three separate checks.

Examples:

```text
MOMENT(kN*m) -> MOMENT(N*mm)    may be convertible
MOMENT(kN*m) -> FORCE(kN)       always incompatible
```

A string resemblance is never evidence of dimensional compatibility.

### 4.6 DependencyKey and DependencySpec

**Purpose.** Typed declaration of every input a regulatory node may consume.

Production dependencies MUST NOT be untyped `tuple[str]` wiring.

**Minimum conceptual fields.**

```text
key
source_kind
semantic_type
physical_dimension
grain
scope_policy
direction_policy
required_availability
population_completeness_requirement
unit_requirement_or_conversion_policy
```

**Required source kinds.**

```text
FACT
SOURCE_POPULATION
SELECTED_SOURCE_QUANTITY
REGULATORY_QUANTITY
CONTEXT
```

**Owns.** Dependency contract, not dependency value.

**Does not own.** Runtime data retrieval outside the compiled binding, evaluator logic, or result status.

**Lifecycle.** Declared on a rule spec before composition; resolved and bound during compile.

**Mutability.** Immutable.

**Validation.** Every dependency resolves to exactly one declared producer or exactly one declared external source. Its semantic type, dimension, grain, scope, direction, unit policy, availability requirement, and population requirement are compile-validated.

**Producers / consumers.** Produced by rule definitions; consumed by compiler, readiness, and execution-envelope materialization.

No evaluator may access a dependency it did not declare. A global `ModelContext` escape hatch is prohibited.

### 4.7 ApplicabilityState

**Purpose.** Represent rule applicability without confusing missing knowledge with proven exclusion.

Frozen states:

```text
APPLIES
PROVEN_NOT_APPLICABLE
UNRESOLVED
INVALID_CONTEXT
```

**Owns.** Applicability state for the compiled rule instance.

**Does not own.** Dependency availability or formal `CheckStatus`.

**Lifecycle.** Materialized into compile-time closure inventory from declared applicability contracts and compile inputs.

**Mutability.** Immutable inside `CompiledClosureRecord`.

**Validation.** `UNRESOLVED` MUST remain represented; missing information MUST NOT become `PROVEN_NOT_APPLICABLE`; `INVALID_CONTEXT` MUST NOT be treated as non-applicability.

**Producers / consumers.** Produced by compile-time applicability resolution; consumed by readiness, execution scheduling, closure reconciliation, and assessment.

Runtime may not invent, remove, or widen applicability.

### 4.8 AvailabilityState

**Purpose.** Represent whether a factual, selected, contextual, or regulatory dependency can be consumed.

Frozen minimum states:

```text
RESOLVED
BLOCKED
NO_DATA
NOT_APPLICABLE
```

**Owns.** Dependency/output availability only.

**Does not own.** Formal regulatory verdict.

**Lifecycle.** Comes from factual/source readiness or regulatory derivation execution.

**Mutability.** Immutable on the value/result carrying it.

**Validation.** A dependency may execute only if its `DependencySpec.required_availability` is satisfied. Availability and `CheckStatus` are distinct types.

**Producers / consumers.** Produced by facts, selected quantities, contexts, derivations, readiness; consumed by compiler/readiness/engine/assessment.

### 4.9 RegulatoryQuantity

**Purpose.** Immutable output of a `RegulatoryDerivationSpec` when a code rule truly derives a new quantity or regulatory state.

**Minimum conceptual fields.**

```text
quantity_key
producer_instance_id
semantic_type
physical_dimension
grain
scope_ref
direction
value
unit
availability
code_refs
rule_version
dependency_refs
evidence_refs
provenance
derivation_trace
governing_trace
```

**Owns.** The derived value/state and its exact derivation provenance.

**Does not own.** PASS/FAIL verdict or reporter formatting.

**Lifecycle.** Produced only by execution of its compiled derivation instance.

**Mutability.** Immutable.

**Validation.** Output MUST satisfy the derivation output contract: semantic type, dimension, grain, scope, direction, unit, and availability. Dependency/evidence refs MUST resolve to the materialized execution inputs.

**Producers / consumers.** Produced by `RegulatoryDerivationSpec`; consumed by other derivations, `CheckSpec`, traces, and assessment.

A `RegulatoryQuantity` MUST NOT be created merely to wrap every factual input. A canonical factual material strength, for example, may remain a `FACT` dependency when no intermediate regulatory derivation exists.

### 4.10 RegulatoryDerivationSpec

**Purpose.** Executable definition of one regulatory derivation.

`RegulatoryDerivationSpec` is the definition; `RegulatoryQuantity` is its immutable execution result. F0 SHALL NOT introduce a third ambiguous "RegulatoryDerivation object".

**Minimum conceptual fields.**

```text
rule_id
code_refs
rule_version
output_contract
typed_dependency_specs
applicability_contract
typed_evaluator_binding
```

**Owns.** Regulatory derivation authority for its single declared output authority.

**Does not own.** Formal verdict, ETABS access, source acquisition, undeclared dependency access, or report projection.

**Lifecycle.** Registered before composition; instantiated at compile; executed only through the plan.

**Mutability.** Immutable spec.

**Validation.** Typed dependencies and output contract are statically validated; duplicate authority production is rejected; evaluator binding must match its typed input/view contract.

**Producers / consumers.** Produced by regulatory rule-definition modules; consumed by registry/compiler/engine.

Future complex equations and branches live in typed Python evaluators. F0 forbids formula DSLs, YAML equation execution, and generic operator programming.

### 4.11 CheckSpec

**Purpose.** Formal executable regulatory rule definition whose output is one canonical `CheckResult`.

**Minimum conceptual fields.**

```text
rule_id
code_refs
rule_version
formal_result_contract
typed_dependency_specs
applicability_contract
typed_evaluator_binding
```

**Owns.** Formal regulatory decision authority for its declared rule.

**Does not own.** ETABS access, source discovery, undeclared result selection, duplicate upstream derivation, or reporting.

**Allowed dependency kinds.**

```text
FACT
SOURCE_POPULATION
SELECTED_SOURCE_QUANTITY
REGULATORY_QUANTITY
CONTEXT
```

A check does not have to consume a `RegulatoryQuantity` when no intermediate regulatory derivation is needed.

**Lifecycle.** Registered before composition; expanded into compiled instances; executed only through the plan.

**Mutability.** Immutable spec.

**Validation.** Same typed dependency rules as derivations. Its evaluator MUST return the canonical formal result contract and MUST NOT re-derive an upstream authority already produced elsewhere.

**Producers / consumers.** Produced by formal rule-definition modules; consumed by registry/compiler/engine; output consumed by store/assessment/reporter.

A single upstream regulatory state MAY feed both a derivation and a formal check. Creating two independent derivations of the same engineering authority is forbidden.

### 4.12 CompiledClosureRecord and RuleClosureOutcome

#### CompiledClosureRecord

**Purpose.** Immutable compile-time expected-inventory record.

**Minimum concepts.**

```text
instance_id
rule_id
grain
scope_ref
mandatory
applicability
declared_dependency_refs
code_refs
rule_version
```

**Owns.** What the frozen program expects for that rule instance.

**Does not own.** Runtime result, mutable execution state, or late-discovered applicability.

**Lifecycle.** Created during compile before execution.

**Mutability.** Immutable and embedded in `TBDYExecutionPlan`.

**Validation.** Unique `RuleInstanceId`; every dependency binding valid; applicability retained even if unresolved.

#### RuleClosureOutcome

**Purpose.** Separate immutable runtime/reconciliation record describing what happened to one compiled closure candidate.

**Minimum concepts.**

```text
compiled_record_ref
execution_status
formal_result_ref
regulatory_quantity_refs
diagnostic_refs
```

**Owns.** Runtime closure outcome only.

**Does not own.** Mutation of the compiled plan or formula re-evaluation.

**Lifecycle.** Created by execute/reconcile from a pre-existing compiled record.

**Mutability.** Immutable.

**Producers / consumers.** Produced by engine/store/reconciliation; consumed by `AssessmentEngine` and reporter projection.

The plan MUST never be mutated to "fill in" runtime fields.

### 4.13 TBDYExecutionPlan

**Purpose.** Complete immutable regulatory program for one frozen set of compile inputs.

**Minimum conceptual contents.**

```text
registry_version
plan_identity
compiled_rule_instances
compiled_dependency_bindings
typed_DAG
compiled_closure_inventory
deterministic_execution_order
analysis_basis_compatibility_refs
compile_diagnostics
```

**Owns.** Program closure and execution order.

**Does not own.** Runtime source acquisition, mutable store state, result fabrication, or late scope discovery.

**Lifecycle.** Created only after all static validation succeeds.

**Mutability.** Immutable.

**Validation.** All producer, semantic, dimension, grain, scope, direction, unit, population, and cycle checks MUST succeed. A plan does not exist on compile failure.

**Producers / consumers.** Produced by `RegulatoryCompiler`; consumed by `RegulatoryEngine`, `RegulatoryStore`, and `AssessmentEngine`.

---

## 5. SourcePopulation and SelectedSourceQuantity boundary

These are distinct factual/result-side contracts and MUST remain outside regulatory decision authority.

### 5.1 SourcePopulation

**Purpose.** Preserve the exact source population required by downstream execution without prematurely collapsing it to a scalar.

**Minimum conceptual fields.**

```text
population_key
grain
source_rows_or_evidence_handles
source_identities
factual_filters
reviewed_exact_source_bindings
source_semantics
capture_status
provenance
```

It MAY apply factual filters such as exact object/story/location/step/source identity and exact reviewed case binding. It MAY preserve the complete candidate population.

It MUST NOT perform code-defined governing minimum/maximum selection, amplification, capacity comparison, regulatory signed selection, or any code equation.

Capture completeness is factual evidence, not a regulatory verdict.

If a downstream dependency requires a complete population, `SourcePopulation` itself SHALL be passed to the regulatory node.

### 5.2 SelectedSourceQuantity

**Purpose.** Represent a source-level scalar selection only when the selection is genuinely non-regulatory.

**Minimum conceptual fields.**

```text
quantity_key
semantic_type
physical_dimension
grain
scope_ref
direction
value
unit
availability
source_population_ref
selection_policy_version
selection_trace
provenance
```

It MUST NOT become a second regulatory engine. If the act of choosing the governing candidate is defined by a regulatory rule, selection belongs in `RegulatoryDerivationSpec`, not here.

A future migration MUST classify each existing result-selection path explicitly rather than assuming every existing selection is non-regulatory.

---

## 6. Analysis system authority and REANALYSIS_REQUIRED

The future system authority MUST NOT be represented as one mixed object that combines reviewed declaration, analysis assumptions, qualification, and resolved policy.

Frozen lifecycle:

```text
ReviewedDirectionalSystemDeclaration
        |
AnalysisSystemAssumption
        |
Analysis Evidence
        |
DirectionalSystemQualification
        |
compare assumed vs qualified
        |
        +--> MATCH
        |      |
        |      v
        | ResolvedDirectionalSystemPolicy
        |
        +--> MISMATCH
               |
               v
         REANALYSIS_REQUIRED
```

### 6.1 ReviewedDirectionalSystemDeclaration

The reviewed declaration is authoritative regulatory input at its true zone/direction grain. Automatically inferred candidate systems MAY exist as diagnostics/support evidence, but inferred candidates are not production declaration authority.

### 6.2 AnalysisSystemAssumption

Records the basis under which the existing analysis result population was actually produced, including exact analysis-case binding references and other basis values required by later system qualification. It is factual/analysis provenance, not a formal check result.

### 6.3 DirectionalSystemQualification

Represents post-analysis qualification facts/states at the required directional/zone grain. F0 freezes its place in the lifecycle but implements none of its engineering operators.

### 6.4 ResolvedDirectionalSystemPolicy

May exist only when declaration, qualification, and analysis-basis compatibility are resolved as `MATCH`. Downstream regulatory dependencies SHALL consume this resolved policy rather than independently reconstructing system authority.

### 6.5 AnalysisBasisStatus

Analysis-basis compatibility is a separate state machine from `CheckStatus`. At minimum it SHALL support:

```text
MATCH
REANALYSIS_REQUIRED
UNRESOLVED
INVALID
```

`REANALYSIS_REQUIRED` means the existing analysis result population may have been captured correctly, but it is incompatible with the now-qualified regulatory analysis basis. The affected result population MUST NOT be post-hoc reinterpreted or scaled into validity. Affected downstream regulatory nodes MUST NOT execute.

`REANALYSIS_REQUIRED` is not added to canonical `CheckStatus`. It arises before formal check execution and prevents full closure for affected mandatory scope.

F0 implements no structural-system table values, system equations, or analysis-basis repair logic.

---

## 7. Registry composition

`RegulatoryRegistry` is an immutable composition root.

It SHALL:

- accept typed `RegulatoryDerivationSpec` and `CheckSpec` definitions;
- reject duplicate `RuleId` values;
- reject duplicate declared output authority;
- expose deterministic registry identity/version metadata;
- become immutable after composition;
- contain only typed evaluator bindings and contract metadata.

It SHALL NOT:

- discover plugins at runtime;
- inject regulatory rules dynamically after composition;
- execute rules;
- host a formula DSL;
- interpret YAML equations;
- provide a generic operator scripting environment.

Unknown producer references are fatal during compile.

---

## 8. Compile lifecycle and static validation

Compilation determines the complete regulatory program. Execution is not allowed to discover scope.

The compiler SHALL:

1. freeze the registry version and compile inputs;
2. establish the compile scope and deterministic scope identities;
3. expand rule definitions into deterministic `RuleInstanceId` values at regulatory verification grain;
4. resolve applicability into `ApplicabilityState` for every compiled candidate, retaining `UNRESOLVED` candidates;
5. create the immutable `CompiledClosureRecord` inventory before runtime;
6. bind every `DependencySpec` to exactly one producer or external source;
7. build the typed dependency DAG;
8. perform static validation in the frozen order below;
9. establish deterministic topological execution order;
10. emit an immutable `TBDYExecutionPlan` only if all compile checks pass.

### 8.1 Frozen dependency validation order

The static validation order is normative:

```text
1. producer or external source exists?
2. exactly one producer/source?
3. semantic type compatible?
4. physical dimension compatible?
5. grain compatible?
6. scope compatible?
7. direction compatible?
8. unit convertible under the declared policy?
9. population completeness requirement satisfiable?
10. graph cycle-free?
```

Any failure is a **compile failure**. It MUST NOT be deferred to evaluator runtime.

### 8.2 Population completeness

A dependency requiring `FULL` source population may be satisfied only by a factually complete capture. `PARTIAL`, `SAMPLED`, truncated, ambiguous, or otherwise incomplete capture MUST NOT satisfy that dependency.

Readiness/compiler logic MUST NOT convert incomplete capture into a governing regulatory quantity.

### 8.3 No runtime scope discovery

Runtime MUST NOT add:

- rule instances;
- dependencies;
- applicability branches;
- expected closure records;
- new producers;
- alternative scope identities.

If the plan cannot be fully compiled, execution does not begin for that program.

### 8.4 Compile pseudocode

```python
def compile(registry, compile_inputs):
    frozen_registry = require_immutable_registry(registry)
    scope = resolve_compile_scope(compile_inputs)

    instances = deterministically_expand_instances(
        frozen_registry,
        scope,
        compile_inputs,
    )

    closure = build_compiled_closure_inventory(instances)
    bindings = bind_declared_dependencies(instances, compile_inputs)
    graph = build_typed_dependency_graph(instances, bindings)

    validate_producer_existence(bindings)
    validate_single_producer(bindings)
    validate_semantic_types(bindings)
    validate_physical_dimensions(bindings)
    validate_grains(bindings)
    validate_scopes(bindings)
    validate_directions(bindings)
    validate_unit_convertibility(bindings)
    validate_population_requirements(bindings)
    validate_acyclic(graph)

    return immutable_execution_plan(
        registry=frozen_registry,
        instances=instances,
        bindings=bindings,
        graph=graph,
        closure=closure,
        execution_order=deterministic_topological_order(graph),
    )
```

This pseudocode defines orchestration semantics only; it contains no regulatory formula.

---

## 9. Execution input boundary

The compiler SHALL materialize only declared dependencies for a node.

A regulatory evaluator receives conceptually:

```text
RuleExecutionEnvelope
+
typed domain input/view
```

`RuleExecutionEnvelope` carries execution identity/provenance common to regulatory nodes. The typed domain input/view carries only dependencies declared by that node.

A production evaluator MUST NOT receive:

- all model facts;
- all contexts;
- all selected quantities;
- all regulatory quantities;
- an unrestricted global model object;
- a generic `Mapping[str, Any]` as an authority escape hatch.

F0 does not need to create Chapter-specific evaluator input DTOs. Later phases SHALL create narrow typed views as rules are migrated.

Undeclared dependency access SHALL be structurally impossible, not merely discouraged by convention.

---

## 10. Execute lifecycle

Execution SHALL operate only on an immutable `TBDYExecutionPlan` and immutable inputs.

For each node in deterministic topological order:

1. resolve only its compiled dependency bindings;
2. materialize the node's `RuleExecutionEnvelope` and typed input/view;
3. evaluate readiness against declared availability/population requirements;
4. if not executable, record a fail-closed closure outcome and diagnostics without fabricating a formal verdict;
5. if it is a derivation node, execute its typed evaluator and store one validated immutable `RegulatoryQuantity`;
6. if it is a formal check node, execute its typed evaluator and store one canonical immutable `CheckResult`;
7. never mutate the execution plan;
8. never discover additional scope.

### 10.1 Execute pseudocode

```python
def execute(plan, immutable_inputs):
    store = RegulatoryStore(plan_ref=plan.plan_identity)

    for instance in plan.deterministic_execution_order:
        compiled = plan.instance(instance)

        if analysis_basis_blocks(compiled, immutable_inputs):
            store.record_nonexecution(compiled, reason="analysis_basis")
            continue

        dependencies = materialize_declared_dependencies(
            compiled,
            plan,
            immutable_inputs,
            store,
        )

        readiness = ReadinessEngine.assess(compiled, dependencies)
        if not readiness.executable:
            store.record_nonexecution(compiled, readiness.diagnostics)
            continue

        envelope, typed_input = build_declared_execution_view(
            compiled,
            dependencies,
        )

        if compiled.is_derivation:
            output = RegulatoryEngine.execute_derivation(
                compiled, envelope, typed_input
            )
            store.record_regulatory_quantity(validate_output(output))
        else:
            result = RegulatoryEngine.execute_check(
                compiled, envelope, typed_input
            )
            store.record_check_result(validate_canonical_result(result))

    return immutable_store_snapshot(store)
```

No evaluator may fetch ETABS data or consult an undeclared producer while executing.

---

## 11. Closure and full-assessment semantics

Full PASS is not "no FAIL found".

For every mandatory `CompiledClosureRecord`, reconciliation must prove either:

- applicability is `PROVEN_NOT_APPLICABLE`; or
- the required formal execution completed exactly once with a canonical result.

The following prevent full PASS for affected mandatory scope:

- `UNRESOLVED` applicability;
- `INVALID_CONTEXT` applicability;
- missing expected formal result;
- duplicate formal result;
- `BLOCKED` formal result/outcome;
- `NO_DATA` formal result/outcome;
- unsupported mandatory domain;
- incomplete analysis basis;
- `REANALYSIS_REQUIRED`;
- inconsistent plan/result identity.

A duplicate formal instance is an invalid assessment condition, not a second vote.

Three status layers MUST remain distinct:

1. formal `CheckResult.status` — outcome of one formal check;
2. `RuleClosureOutcome` — execution/reconciliation status of one compiled closure candidate;
3. product-level full-assessment status — whether the complete mandatory regulatory program can close.

### 11.1 Reconcile pseudocode

```python
def reconcile(plan, store_snapshot, analysis_basis_state):
    outcomes = []

    for compiled in plan.compiled_closure_inventory:
        if compiled.applicability == PROVEN_NOT_APPLICABLE:
            outcomes.append(outcome_proven_not_applicable(compiled))
            continue

        if analysis_basis_state.blocks(compiled.scope_ref):
            outcomes.append(outcome_not_executed(compiled, "analysis_basis"))
            continue

        observed = store_snapshot.formal_results_for(compiled.instance_id)

        if len(observed) == 0:
            outcomes.append(outcome_missing(compiled))
        elif len(observed) > 1:
            outcomes.append(outcome_duplicate(compiled, observed))
        else:
            outcomes.append(outcome_from_result(compiled, observed[0]))

    return AssessmentEngine.close(
        plan=plan,
        closure_outcomes=tuple(outcomes),
        analysis_basis_state=analysis_basis_state,
    )
```

`AssessmentEngine` MUST reconcile structure only. It MUST NOT recompute an engineering formula, source selection, applicability derivation, or formal verdict.

---

## 12. Canonical CheckResult remains unchanged by F0 freeze

The current canonical `CheckStatus` vocabulary remains:

```text
OK
FAIL
WARNING
NO_DATA
BLOCKED
OUT_OF_SCOPE
```

F0 makes no schema migration to `CheckResult`.

`REANALYSIS_REQUIRED` is not a `CheckStatus`. It belongs to analysis-basis compatibility. Product-level full-assessment state is also separate from `CheckResult`.

Until a complete expected-inventory closure implementation exists and all mandatory applicable domains are implemented, product reporting SHALL retain:

```text
full_tbdy_compliance_status = NOT_EVALUATED
```

A successful partial/domain slice SHALL NOT be promoted to full-code PASS.

---

## 13. Services

### 13.1 RegulatoryRegistry

**Responsibility.** Immutable composition of rule definitions and declared producers.

**Inputs.** Typed `RegulatoryDerivationSpec` and `CheckSpec` definitions plus versioned semantic contracts.

**Outputs.** Immutable registry with deterministic identity/version and producer index.

**Forbidden.** Runtime plugin discovery, dynamic rule injection, duplicate rule/output authority, evaluator execution, formula DSL.

### 13.2 RegulatoryCompiler

**Responsibility.** Convert immutable registry + compile inputs into complete immutable `TBDYExecutionPlan`.

**Inputs.** Registry, factual/topology scope, reviewed contexts/declarations, analysis-basis compatibility, source/quantity contracts available for binding.

**Outputs.** Compiled rule instances, immutable closure inventory, typed dependency bindings, typed DAG, deterministic order, compile diagnostics.

**Forbidden.** Regulatory evaluator execution, late runtime scope, unresolved static mismatch deferral.

### 13.3 RegulatoryStore

**Responsibility.** Record immutable execution outputs and runtime closure evidence keyed by compiled identity.

**Inputs.** Validated `RegulatoryQuantity`, canonical `CheckResult`, diagnostics, outcome references.

**Outputs.** Immutable store snapshot for downstream execution/reconciliation.

**Forbidden.** Recomputing outputs, mutating plan/specs, resolving missing dependencies heuristically, creating duplicate authority.

### 13.4 ReadinessEngine

**Responsibility.** Determine whether a compiled node's already-bound declared dependencies satisfy execution requirements.

**Inputs.** Compiled node contract and materialized declared dependencies.

**Outputs.** Executable/non-executable readiness state with diagnostics.

**Forbidden.** PASS/FAIL decisions, regulatory formula execution, ETABS queries, undeclared dependency access, scope creation.

### 13.5 RegulatoryEngine

**Responsibility.** Execute compiled typed derivation and formal-check evaluators.

**Inputs.** Compiled node, `RuleExecutionEnvelope`, typed declared input/view.

**Outputs.** Validated immutable `RegulatoryQuantity` or canonical immutable `CheckResult`.

**Forbidden.** Runtime registration, scope discovery, ETABS queries, undeclared dependency lookup, reporter behavior.

### 13.6 AssessmentEngine

**Responsibility.** Reconcile compiled mandatory closure inventory against execution outcomes and analysis-basis state.

**Inputs.** Immutable plan, immutable store snapshot, closure outcomes, analysis-basis compatibility.

**Outputs.** Full-assessment structural status and diagnostics.

**Forbidden.** Engineering formula evaluation, source selection, limit ownership, unit inference, result repair.

---

## 14. Determinism

The following identity is normative:

```text
same immutable registry version
+ same immutable execution plan
+ same immutable evidence/context inputs
=> same RegulatoryQuantities
+ same CheckResults
+ same traces
+ same closure outcomes
```

Determinism requirements:

- registry composition order MUST have a canonical deterministic representation;
- rule expansion order MUST be deterministic;
- `RuleInstanceId` values MUST be deterministic;
- dependency binding MUST be deterministic;
- graph topological order MUST use a deterministic tie-break rule;
- source population identity/order used in traces MUST be deterministic or explicitly canonicalized;
- execution output ordering MUST be deterministic;
- provenance/traces MUST not depend on hash-map iteration order, process address, wall-clock time, or environment-dependent traversal;
- the reporter MUST preserve canonical order rather than introduce engineering significance through presentation sorting.

Package-level deterministic serialization patterns may be reused, but serialization determinism does not substitute for regulatory execution determinism.

---

## 15. Provenance

Every final formal result SHALL be traceable backwards through declared references. Where a layer is not applicable, the trace may skip it, but no consumed authority may be anonymous.

Conceptual chain:

```text
CheckResult
  -> CheckSpec + rule version
  -> declared dependency refs
  -> RegulatoryQuantity where consumed
  -> RegulatoryDerivationSpec + rule version
  -> SelectedSourceQuantity or SourcePopulation where consumed
  -> exact source evidence / factual facts
  -> reviewed declaration/context where consumed
  -> analysis assumption / qualification where relevant
```

Minimum provenance rules:

- exact source identity and unit authority SHALL be retained;
- source-population completeness SHALL be traceable;
- reviewed semantic/binding contract version SHALL be traceable;
- every regulatory derivation SHALL retain dependency and evidence refs;
- governing/candidate traces SHALL remain inside the authority that performed the regulatory operation;
- every formal result SHALL reference its compiled rule identity/version;
- references/handles SHOULD be used instead of duplicating giant raw payloads through every layer;
- reporter SHALL serialize existing provenance and MUST NOT regenerate it.

---

## 16. Neutral toy DAG

The following is deliberately non-regulatory. It demonstrates type/compile/execution semantics only.

```text
FACT_A
  semantic_type = TOY_INPUT_A
  physical_dimension = DIMENSIONLESS
  grain = COMPONENT
  unit = ratio
        |
        v
DERIVATION_X
  consumes FACT_A
  produces TOY_DERIVED_STATE
        |
        v
CHECK_Y
  consumes TOY_DERIVED_STATE
  produces canonical CheckResult
```

Conceptual specs:

```python
DERIVATION_X = RegulatoryDerivationSpec(
    rule_id="TOY_DERIVATION_X",
    dependencies=(typed_dependency_on_FACT_A,),
    output_contract=typed_toy_output_contract,
    evaluator=typed_toy_derivation,
)

CHECK_Y = CheckSpec(
    rule_id="TOY_CHECK_Y",
    dependencies=(typed_dependency_on_DERIVATION_X,),
    evaluator=typed_toy_check,
)
```

The example intentionally omits derivation arithmetic and check criteria. F0 freezes wiring and authority, not domain mathematics.

---

## 17. F0 hard invariants

The following invariants are constitutional and SHALL be enforced by later implementation/tests:

1. Every dependency has exactly one declared producer or one declared external source.
2. No regulatory node may query ETABS.
3. No regulatory node may infer case/combo semantics from names, regex, prefixes, or suffixes.
4. No evaluator may access an undeclared dependency.
5. Wrong semantic type, physical dimension, grain, scope, direction, or non-convertible unit is a compile failure.
6. A FULL-population dependency cannot be satisfied by incomplete capture.
7. `RegulatoryQuantity` is immutable.
8. Formal `RuleInstance` grain is regulatory verification grain; candidate-envelope identities remain in traces unless the code explicitly defines separate formal verification grain.
9. Applicability `UNRESOLVED` remains in compile-time closure inventory.
10. Every mandatory closure candidate must terminate as either `PROVEN_NOT_APPLICABLE` or complete formal evaluation before full PASS.
11. `REANALYSIS_REQUIRED` invalidates downstream use of affected analysis results.
12. Reporter cannot derive, select, compare, modify, reinterpret, or override engineering truth.
13. Registry is immutable after composition.
14. Dependency graph must be acyclic before execution.
15. Same immutable plan plus same immutable inputs produces identical outputs and traces.
16. Runtime may not add `RuleInstance`s, dependencies, applicability branches, or expected closure records.
17. A derivation and formal check may consume the same upstream regulatory state, but duplicate independent derivation of that same authority is forbidden.

---

## 18. Current repository seams at the frozen baseline

F0 names existing production seams so later migration workers operate on real repository surfaces rather than hypothetical architecture.

### 18.1 PRESERVE

| Current surface | Preserved architectural value |
|---|---|
| `tbdy_engine/etabs/safety.py` | ETABS Safety boundary and bounded acquisition ownership |
| `tbdy_engine/features/snapshot.py` | `FeatureSnapshot` factual-only/read-only contract |
| `tbdy_engine/features/value.py` | factual `FeatureValue` without formal decision semantics |
| `tbdy_engine/features/evidence.py` | explicit traceability evidence contract |
| `tbdy_engine/coverage/models.py` | Coverage/readiness-only philosophy and fail-closed evidence requirements |
| `tbdy_engine/checks/result.py` | canonical immutable `CheckResult` and existing six-status vocabulary |
| `tbdy_engine/features/used_rc_material_population.py` | factual used-RC material population, explicit-unit canonical facts, reconciliation and source binding |
| `tbdy_engine/checks/ndm_selection.py` | exact reviewed binding, complete-population/provenance discipline, explicit availability pattern |
| `tbdy_engine/features/wall_inventory.py` | authoritative factual wall population identity |
| current wall applicability knowledge | domain knowledge to migrate without duplicate authority |
| product/report truth notices | `full_tbdy_compliance_status = NOT_EVALUATED` until complete closure exists |
| `tbdy_engine/product_reports/report_package.py` | deterministic package serialization pattern; not engineering authority |

Preserve means preserve the architectural property. It does not mean every current class name or internal implementation is permanently frozen.

### 18.2 MIGRATE / GENERALIZE

| Current surface | F0 migration seam |
|---|---|
| `tbdy_engine/checks/input_adapter.py::GeometryCheckInput` | geometry-specific carrier becomes a parity source for future rule-specific typed execution views; no giant generic model context |
| geometry adapter allowlists / unit maps | migrate into typed rule/dependency contracts without changing accepted behavior until parity |
| `tbdy_engine/checks/engine.py::MinimalCheckEngine` | existing canonical execution authority used as parity reference until production cutover |
| hardcoded member/wall dispatch in `MinimalCheckEngine` | migrate to registry + compiler + typed DAG dispatch after parity |
| existing canonical member/wall formal checks | parity-migrate to `CheckSpec` and, where truly needed, `RegulatoryDerivationSpec` |
| `tbdy_engine/product_reports/combined_verdict.py` | current product-scope aggregation becomes a migration seam toward compile-time closure + `AssessmentEngine` |
| `tbdy_engine/product_reports/c13_1_report.py` | current product assembly/report packaging becomes projection of canonical assessment after cutover |
| existing report formal-artifact wiring | migrate only after canonical result parity is demonstrated |

### 18.3 RETIRE AS PRODUCTION AUTHORITY AFTER PARITY CUTOVER

The following SHALL remain untouched by this documentation task but SHALL NOT remain final production authority after F0.5 production cutover:

- hardcoded `_ALLOWED_CHECKS` production authority;
- member-versus-wall `if` dispatch as regulatory composition authority;
- product-owned regulatory thresholds;
- reporter-side PASS/FAIL creation;
- universal fixed capacity-factor semantics;
- runtime case/combo-name inference used as regulatory authority;
- duplicated regulatory equations/derivations across product and canonical paths.

Concrete current examples include legacy material verdict generation and name-pattern fallback logic in `tbdy_engine/product_reports/check_results.py`. Their existence is migration debt; this F0 task does not modify or delete them.

---

## 19. M1 position after F0 freeze

`CONCRETE_MATERIAL_MIN_STRENGTH` SHALL NOT be added as a new rule to the legacy hardcoded `MinimalCheckEngine` architecture.

It is repositioned to **F0.3**, the first genuinely new DAG-native formal rule after F0.2 proves one existing formal check can execute with exact canonical parity on the new kernel.

Its purpose is to prove that the new architecture can deliver a real new regulatory check before full legacy migration. A full canonical B1/Wall migration is NOT a prerequisite for this new material rule.

During transition, accepted legacy checks MAY continue on the accepted legacy path while `CONCRETE_MATERIAL_MIN_STRENGTH` runs exclusively on the DAG path, provided the same formal regulatory authority is never active in both paths.

Its future input MAY remain the factual canonical material-strength value supplied by the accepted used-material population. A pointless `RegulatoryQuantity` wrapper MUST NOT be invented merely because the DAG exists.

Material applicability shall distinguish:

- exact used material facts and exact assignments as factual evidence;
- the ETABS material-type-to-concrete meaning as a versioned/reviewed API semantic contract;
- formal rule applicability/verdict as `CheckSpec` authority.

The versioned API semantic binding does not imply human review of every individual material object.

This F0 freeze contains no material minimum-strength threshold implementation.

---

## 20. Explicit F0 non-scope

F0 SHALL NOT implement:

- structural-system table values;
- response-modification or overstrength-factor values;
- building-height-system eligibility calculations;
- seismic design-class calculations;
- structural-system qualification equations;
- Chapter-4 demand equations;
- any Ndm engineering change;
- beam shear rules;
- column shear rules;
- strong-column/weak-beam formulas;
- joint formulas;
- wall shear formulas;
- concrete minimum-strength numerical threshold;
- TS500 capacity formulas;
- reinforcement design;
- automatic design iteration;
- ETABS mutation;
- new ETABS acquisition;
- reporter migration implementation;
- `MinimalCheckEngine` deletion;
- schema migration;
- generic regulation/formula/operator DSL.

F0 is type-system and execution-semantics freeze only.

---

## 21. F0 implementation acceptance criteria for later phases

No tests are implemented by this documentation task. Future F0.0/F0.1 implementation SHALL include tests proving at minimum:

**A. Duplicate producer.** Two producers for one dependency authority cause compile failure.

**B. Missing producer.** A dependency with no declared producer/external source causes compile failure.

**C. Semantic mismatch.** Incompatible `SemanticType` wiring causes compile failure.

**D. Dimension mismatch.** Incompatible `PhysicalDimension` wiring causes compile failure.

**E. Grain mismatch.** An undeclared/incompatible grain connection causes compile failure.

**F. Direction mismatch.** A dependency violating direction policy causes compile failure.

**G. Incompatible unit.** A non-convertible unit connection causes compile failure.

**H. Cycle.** A dependency cycle prevents plan creation.

**I. Undeclared dependency access impossible.** Evaluator construction/execution cannot obtain a dependency absent from its compiled declaration.

**J. Incomplete population.** A `FULL` population dependency rejects partial, sampled, truncated, or ambiguous capture.

**K. Unresolved applicability survives closure inventory.** `UNRESOLVED` remains represented in `CompiledClosureRecord` and cannot be silently dropped.

**L. Runtime cannot add expected rule.** Execution cannot add rule instances, dependencies, applicability branches, or closure records.

**M. Deterministic plan ordering.** Equivalent immutable compile inputs produce exactly the same deterministic node ordering.

**N. Deterministic rule-instance IDs.** Equivalent compile inputs produce identical `RuleInstanceId` values.

**O. Deterministic outputs/traces.** Equivalent immutable plan and inputs produce identical quantities, results, traces, and closure outcomes.

**P. Derivation output immutable.** `RegulatoryQuantity` cannot be mutated after construction.

**Q. Shared upstream state.** One upstream regulatory state can feed both a derivation and a formal check through declared dependencies.

**R. Duplicate authority derivation rejected.** Registry/composition rejects two independent producers claiming the same frozen regulatory authority.

**S. REANALYSIS_REQUIRED downstream stop.** Affected compiled nodes do not execute and affected mandatory scope cannot close.

**T. Canonical parity.** One existing formal check migrated through the DAG produces exact canonical `CheckResult` parity with the accepted pre-cutover path for the frozen test fixture/input.

Acceptance tests SHALL verify contracts and architecture, not smuggle new Chapter-specific engineering authority into F0.

---

## 22. Frozen migration sequence

The implementation roadmap is frozen as follows:

### F0.0 — Semantic Contracts

Implement the bounded core type contracts, semantic/dimension/unit vocabulary foundation, typed dependencies, applicability/availability separation, and immutable registry composition.

### F0.1 — Pure DAG Kernel

Implement compiler, plan, typed dependency binding, static validation, deterministic ordering, store, readiness, execution boundary, closure records/outcomes, and assessment skeleton without adding new engineering rules.

### F0.2 — One Existing Formal Check Parity Migration

Migrate one already-accepted formal check to prove exact canonical `CheckResult` parity and exercise the new kernel end-to-end.

### F0.3 — First New DAG-native Formal Rule

Introduce `CONCRETE_MATERIAL_MIN_STRENGTH` as the first genuinely new formal rule implemented natively on the DAG architecture.

Its purpose is to prove that the new architecture can deliver a real new regulatory check before full legacy migration. A full canonical B1/Wall migration is NOT a prerequisite for this phase.

During transition, accepted legacy checks MAY continue on the accepted legacy path while this new material rule runs exclusively on the DAG path, provided the same formal regulatory authority is never active in both paths.

### F0.4 — Existing Canonical B1 / Wall Parity Migration

Migrate accepted canonical member/wall formal checks and their existing authoritative domain knowledge without changing engineering behavior.

### F0.5 — Production Cutover of Migrated Legacy Composition/Dispatch Authority

Only after the relevant legacy authorities have proven parity may their hardcoded `MinimalCheckEngine` composition/dispatch authority be retired from production. Legacy paths SHALL remain for authorities not yet migrated; no formal regulatory authority may be simultaneously active on both legacy and DAG paths.

### F1.0 — Reviewed Directional System Declaration

Introduce the reviewed declaration contract at zone/direction grain.

### F1.1 — Analysis System Assumption

Capture the basis under which analysis results were produced.

### F1.2 — Post-analysis System Qualification

Introduce post-analysis system qualification states/evidence.

### F1.3 — Resolved Directional Policy or REANALYSIS_REQUIRED

Resolve compatible downstream system policy or stop affected stale analysis use.

### F2 — Analysis Contracts + Exact Bindings

Expand analysis semantics and exact reviewed bindings without name inference authority.

### F3 — Frozen RC Capacity Primitives

Introduce reviewed/frozen capacity primitives required by later Chapter-specific verification.

### F4 — High-ductility Beam vertical slice

Implement the first high-ductility beam regulatory program on the frozen DAG.

### F5 — SCWB + Column

Implement shared upstream state and column program without duplicate derivation authority.

### F6 — Joint

Implement joint program.

### F7 — Wall completion

Complete wall program on the common architecture.

### F8 — Limited ductility

Implement applicable limited-ductility programs.

### F9 — Slab/Diaphragm + Foundation Transfer

Complete remaining cast-in-place RC transfer domains.

### F10 — Full Expected-inventory Assessment Closure

Only after complete mandatory expected inventory can be compiled and reconciled may the product-level full assessment become capable of full PASS/FAIL closure.

None of these phases are implemented by this F0 documentation task.

---

## 23. Migration rules

1. Preserve current production behavior until an explicit parity migration proves replacement equivalence.
2. Do not add new engineering authority to legacy paths merely to ease migration.
3. Migrate one authority at a time; do not run two independent production authorities indefinitely.
4. Delete duplicate authority only after parity acceptance and production cutover.
5. Existing tests for accepted behavior remain regression evidence; F0 kernel tests add architecture guarantees rather than silently rewriting expected engineering behavior.
6. Existing ETABS Safety and factual acquisition boundaries remain outside regulatory nodes.
7. Existing Coverage and FeatureSnapshot truth boundaries remain conceptually preserved.
8. Current product/report paths remain `NOT_EVALUATED` for full compliance until true closure exists.
9. Runtime case-name heuristics, reporter verdicts, and product thresholds are migration debt, not templates for new DAG-native rules.
10. No migration worker may bypass compile-time closure by emitting formal results directly to make reports look complete.

---

## 24. Implementation-ready ownership summary

| Contract | Construction | Immutable? | Primary producer | Primary consumers |
|---|---|---:|---|---|
| `RuleId` | rule definition | yes | rule modules | registry/compiler/plan |
| `RuleInstanceId` | compile | yes | compiler | plan/store/assessment |
| `Grain` | semantic contract | yes | type system | compiler/all typed contracts |
| `SemanticType` | semantic contract | yes | type system | dependency/output contracts |
| `PhysicalDimension` + `Unit` | semantic/unit contract | yes | type/unit system | compiler/evidence/outputs |
| `DependencyKey` + `DependencySpec` | rule definition | yes | rule modules | compiler/readiness |
| `ApplicabilityState` | compile | yes | applicability resolution | closure/readiness/assessment |
| `AvailabilityState` | fact/source/runtime result | yes | evidence/selection/derivation | readiness/engine |
| `RegulatoryQuantity` | execute | yes | derivation evaluator | store/downstream nodes |
| `RegulatoryDerivationSpec` | registry composition | yes | rule modules | compiler/engine |
| `CheckSpec` | registry composition | yes | rule modules | compiler/engine |
| `CompiledClosureRecord` | compile | yes | compiler | plan/reconcile |
| `RuleClosureOutcome` | execute/reconcile | yes | store/assessment | assessment/reporter |
| `TBDYExecutionPlan` | compile | yes | compiler | engine/store/assessment |
| `SourcePopulation` | factual/result boundary | yes | acquisition/factual source service | compiler/readiness/regulatory nodes |
| `SelectedSourceQuantity` | non-regulatory source selection | yes | source-selection service | compiler/readiness/regulatory nodes |

---

## 25. Final F0 freeze statement

F0 freezes the regulatory program as a **compiled, typed, immutable, deterministic dependency graph with compile-time closure inventory**. ETABS evidence and reviewed context enter through declared source contracts. Regulatory derivations may create immutable engineering quantities/states. Formal checks create canonical `CheckResult`. Assessment reconciles the complete precompiled mandatory inventory. Reporter projects the already-decided truth.

No runtime actor may discover new regulatory scope, no reporter may repair engineering truth, and no stale analysis result population may be reinterpreted after an analysis-basis mismatch.

This architecture is the mandatory foundation for all later full cast-in-place RC regulatory work.
