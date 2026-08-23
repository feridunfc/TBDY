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
Exact Source Chain
+
Exact Reviewed Regulatory Claim Snapshot
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

## 5. Review semantics and freshness

Review status is bounded to:

```text
DRAFT
APPROVED
SUPERSEDED
REJECTED
```

Only referenced `APPROVED` review records can support production authority. A binding must reference reviewed claims, and each bound claim must have a referenced approved review.

A review is not bound only to `claim_id`. `AuthorityReviewRecord.reviewed_claim_fingerprint` captures the exact claim/source-chain snapshot that was reviewed. The deterministic `regulatory_claim_fingerprint(...)` includes, at minimum:

```text
RegulatoryClaim
- claim_id
- claim_version
- normalized_statement
- anchor_refs

Each resolved SourceAnchor
- anchor_id
- source_id
- locator

Each resolved RegulatorySourceDocument
- source_id
- edition
- source_fingerprint
```

The current implementation also includes deterministic source metadata (`title`, `issuer`, `jurisdiction`). It includes no repository HEAD SHA and no copyrighted source text.

During strict authority validation the current claim and its complete resolved source chain are fingerprinted again. The current fingerprint must exactly equal `reviewed_claim_fingerprint`. A mismatch raises:

```text
STALE_REGULATORY_CLAIM_REVIEW
```

and compilation fails before execution. Therefore changing `claim_version`, `normalized_statement`, an anchor locator, source edition, or source fingerprint invalidates the old review even when `claim_id` is unchanged. A new matching `APPROVED` review is required before strict compilation can succeed.

`reviewed_claim_fingerprint` participates in deterministic `RegulatoryAuthorityCatalog` identity. Identical source/claim/review state therefore produces the same catalog version; a re-review or changed reviewed authority produces a different catalog version.

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

Strict validation checks rule identity, exact claim-review/source-chain freshness, review approval status, evaluator binding identity, rule version, explicit evaluator-module review membership, and implementation fingerprint freshness.

## 8. Plan provenance and identity

When strict source authority is active, `TBDYExecutionPlan` carries immutable references for:

- `regulatory_authority_catalog_version`
- compiled rule-instance → implementation-binding refs
- compiled rule-instance → approved implementation fingerprint refs

The plan does not duplicate source documents, claims, or review objects inside every closure.

Strict plan identity includes authority catalog version, validated binding refs, and approved implementation fingerprints. Therefore a successfully re-reviewed authority change changes plan identity even when evidence, context, and regulatory rules are otherwise unchanged. A stale claim review does not reach plan creation at all.

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

The review-freshness proof is:

```text
same claim_id
+
changed reviewed claim/source-chain content
+
old APPROVED review fingerprint

→ STALE_REGULATORY_CLAIM_REVIEW
→ COMPILE FAILS
```

## 10. Future rule-authoring pattern

All new regulatory domain work after F0.9 should follow:

```text
SOURCE DOCUMENT
    ↓
ANCHOR
    ↓
CLAIM
    ↓
EXACT CLAIM/SOURCE FINGERPRINT + APPROVED REVIEW
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

The purpose of F0.9 is narrower: make future executable regulatory algorithms mechanically source-bound and review-fresh before they enter production authority.
