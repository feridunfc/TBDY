# F0.9 Source-Bound Regulatory Algorithm Foundation

**Status:** BOUNDED F0 AUTHORITY EXTENSION  
**Repository:** `feridunfc/TBDY`  
**Frozen base:** `1395261d800a0636851dd65fcbe1b883bafa7cbc`  
**Scope:** source/review/implementation authority provenance only

## 1. Constitutional boundary

F0.9 extends the existing frozen F0 architecture. It does **not** create a second regulatory engine, a second compiler, a generic knowledge-graph runtime, a formula DSL, YAML equation execution, runtime rule discovery, or a generic consequence/remediation executor.

The existing F0 typed DAG remains the execution authority:

```text
evidence
→ typed dependencies
→ RegulatoryDerivationSpec / CheckSpec
→ RegulatoryCompiler
→ immutable TBDYExecutionPlan
→ RegulatoryEngine
→ canonical CheckResult / RegulatoryQuantity / closure
→ Assessment
```

F0.9 adds no TBDY, TS500, TS498, TS708, or other engineering equation, threshold, table value, design formula, system-resolution rule, strong-column rule, remediation rule, or reanalysis execution loop.

ProtaStructure is **not regulatory authority**. Future Prota observations may be used only as commercial-software behavioral evidence where primary regulatory text does not answer software-behavior questions such as governing selection, post-analysis qualification, directional propagation, capacity-demand selection, system fallback, or analysis-basis invalidation.

## 2. Reproduced gap

Before F0.9, a rule could carry `code_refs` and numerical regulatory constants while the compiler had no mechanical proof of the complete authority chain:

```text
source document
→ exact source anchor
→ reviewed regulatory claim
→ approved evaluator implementation
→ current implementation fingerprint
```

A `code_ref` is trace/display metadata. It is not executable regulatory authority by itself.

## 3. Executable authority condition

Executable regulatory authority requires all of the following:

```text
Source Anchor
+
Reviewed Regulatory Claim
+
Approved Implementation Binding
+
Fresh Implementation Fingerprint
=
Executable Regulatory Authority
```

Any missing, stale, ambiguous, rejected, superseded, or draft authority state fails closed when strict source authority is enabled.

## 4. Bounded authority contracts

`tbdy_engine.regulatory.authority` defines immutable contracts for:

- `RegulatorySourceDocument`
- `SourceAnchor`
- `RegulatoryClaim`
- `AuthorityReviewStatus`
- `AuthorityReviewRecord`
- `ApprovedImplementationBinding`
- `RegulatoryAuthorityCatalog`
- `ValidatedRuleAuthority`

The catalog is a deterministic immutable composition root. Duplicate identities and broken source/anchor/claim/review/binding references are rejected during composition.

`RegulatorySourceDocument` stores identity/version metadata and a source fingerprint. It does not store copyrighted full standard text.

`SourceAnchor` stores an exact locator such as a clause, table, equation, section, or annex reference. It does not interpret equation text.

`RegulatoryClaim.normalized_statement` is a reviewed proposition/summary. It is not executable code and must not evolve into a formula scripting language.

## 5. Review semantics

Review status is bounded to:

```text
DRAFT
APPROVED
SUPERSEDED
REJECTED
```

Only referenced `APPROVED` review records can support production authority. A binding must reference reviewed claims, and each bound claim must have a referenced approved review.

## 6. Implementation fingerprint

The implementation fingerprint deliberately does **not** use repository HEAD SHA.

Fingerprint identity includes:

```text
rule_id
rule_version
evaluator_binding_id
explicit reviewed implementation module names
SHA-256 of each reviewed Python source module
```

The evaluator's own module must be explicitly included in the reviewed module set. Helper modules are included only when review metadata explicitly names them.

There is no magical call-graph discovery. If implementation ownership is uncertain, authority validation fails closed rather than guessing transitive dependencies.

Consequences:

- changing a reviewed implementation module changes the fingerprint;
- changing an unrelated file or unrelated module does not change the fingerprint;
- a stale approved fingerprint blocks compilation before execution.

## 7. Compiler integration

F0.9 extends the single existing `RegulatoryCompiler`; it does not introduce `AuthorizedRegulatoryCompiler` or any parallel execution path.

`RegulatoryCompileInputs` accepts optional `regulatory_authority_catalog`.

### Legacy migration mode

```text
regulatory_authority_catalog is None
→ accepted legacy VS-0/1/2/3 compilation behavior remains active
```

No source-authority diagnostic is added to the legacy path.

### Strict source-authority mode

```text
regulatory_authority_catalog is supplied
→ every rule in the targeted registry must pass authority validation
→ one failure blocks the whole compile
→ no TBDYExecutionPlan is emitted
```

Strict validation checks rule identity, claim/review/source-chain integrity, evaluator binding identity, rule version, explicit evaluator-module review membership, and implementation fingerprint freshness.

## 8. Plan provenance and identity

When strict source authority is active, `TBDYExecutionPlan` carries immutable references for:

- `regulatory_authority_catalog_version`
- compiled rule-instance → implementation-binding refs
- compiled rule-instance → approved implementation fingerprint refs

The plan does not duplicate source documents, claims, or review objects inside every closure.

Strict plan identity includes authority catalog version, validated binding refs, and approved implementation fingerprints. Therefore a reviewed authority change changes plan identity even when evidence, context, and regulatory rules are otherwise unchanged.

With no catalog, the legacy F0.1 plan-identity payload remains unchanged.

## 9. Central regression proof

The central F0.9 proof is:

```text
CheckSpec(code_refs=("TBDY-2018-X.Y.Z", ...))
+
no approved source-authority binding
+
strict catalog-enabled compilation

→ COMPILE FAILS
```

`code_refs` cannot authorize an evaluator.

## 10. Future rule-authoring pattern

All new regulatory domain work after F0.9 should follow:

```text
SOURCE DOCUMENT
    ↓
ANCHOR
    ↓
CLAIM + REVIEW
    ↓
typed dependencies
    ↓
typed evaluator
    ↓
approved implementation binding
    ↓
existing CheckSpec / RegulatoryDerivationSpec
    ↓
existing RegulatoryCompiler
```

No new runtime rule representation is introduced.

## 11. Future system/consequence work

System lifecycle, consequence propagation, invalidation, remediation, and reanalysis behavior are intentionally outside F0.9. The next production slice should prove real domain behavior using existing F0 primitives such as `RegulatoryDerivationSpec`, `DependencySpec`, `RegulatoryQuantity`, `AnalysisBasisStatus`, `RuleScopeTarget`, and `CheckSpec`.

Expected future lifecycle:

```text
DECLARED
→ PRE-ELIGIBLE
→ PROVISIONAL ANALYSIS POLICY
→ ANALYZED
→ POST-QUALIFIED
→ RESOLVED
```

If resolved analysis basis differs from the basis under which the evidence was produced:

```text
REANALYSIS_REQUIRED
```

That behavior must be demonstrated by real domain rules rather than by pre-building a generic consequence DSL.

## 12. Scope exclusions

F0.9 intentionally does not implement:

- new engineering checks;
- new ETABS acquisition behavior;
- system resolver;
- analysis equations;
- strong-column semantics;
- generic graph framework;
- remediation engine;
- reanalysis execution loop;
- bulk migration of the 147-rule research inventory;
- authoritative real TBDY claims without a separate reviewed source package.

The purpose of F0.9 is narrower: make future executable regulatory algorithms mechanically source-bound before they enter production authority.
