# Prior Engineering Asset Reuse Guide — G0-R1 Supervisor Patch P2

**Status:** `READY_FOR_SUPERVISOR_REVIEW`  
**Frozen base:** `6273c19030ab6ecb7ad2637e3bfc74f88b1da086`  
**Frozen base tree:** `8f6ef822b5ab26d22c859438689e7bb9aea9439a`  
**P2 parent:** `ed307e5084ad85bf837efcf24724bcacee1b25d9`

This guide accompanies `PRIOR_ENGINEERING_ASSET_REUSE_INDEX.yaml`. The index is a research-only reuse/debt artifact. It has `engineering_authority = none` and `production_import_allowed = false`; it does not create production, regulatory, analysis, design, or selection authority.

## Parallel research policy

Unmerged parallel research is intentionally **not CURRENT, not canonical, and not a stable G0 asset**. The index therefore publishes no live research branch names, candidate SHAs, patch SHAs, or moving-head ledger. Parallel research candidates are reconciled externally by the supervisor at review time and may not supply CURRENT authority merely by being present on a remote branch.

## Frozen/current asset rule

Every CURRENT entry is identified by an exact frozen-base `(path, blob)` pair. Reuse validation means both conditions hold against the frozen base tree:

```text
tree[path].type == blob
AND
tree[path].sha == recorded blob
```

P2 preserves 48 CURRENT asset entries. Each CURRENT entry carries its `reuse_disposition`, `semantic_role`, and `authority_ceiling`. Historical evidence remains explicitly HISTORICAL and may be extracted as research/oracle knowledge only within its stated ceiling.

## Authority boundaries

`packages/etabs_gateway` remains the sole production COM / STA / session / attach owner. Explicit custom/fake COM dependencies close the dependency universe; implicit real/default COM fallback is forbidden. Raw COM capability must not escape through legacy or product layers.

`SourceModelIdentity`, model fingerprints, and `EvidenceEpoch` are factual provenance concepts. They are not causal analysis/design execution proof. `AnalysisStateIdentity` and `AnalysisResultIdentity` are identity objects; identity alone is not a qualified lineage. Current public production cannot positively qualify pre-existing ETABS results without a controlled causal execution proof.

Component readiness or MATCH must never be broadcast to unproven design combinations. P8A reuse requires exact `(design_combo_type, combo_name)` identity, definition fingerprint, component demand evidence, and combo-grain analysis-basis binding. Factual ETABS design rows are not engine-selected/final reinforcement verdicts.

## Roadmap reuse-set meanings

The stable roadmap meanings are:

```text
B2  = DESIGN-LINEAGE-1
B4A = DERIVED-STATE-1
B4B = ANALYSIS-STATE-MUTATION-1
B5  = ANALYSIS-EXEC-1
C0  = FND2-LIVE-MATERIALIZATION-1
B6  = DESIGN-EXEC-1
C1  = COLUMN-LIVE-CUTOVER-1
P8B = COLUMN-CANDIDATE-ADEQUACY-SELECTION-INTEGRATION
```

B4B reuses factual snapshot/set/readback/restore mechanics only; future mutation authority must preserve typed mutation, SET return code, READBACK equality/tolerance, mutation manifest, and `AnalysisStateIdentity`. B5 owns controlled `RunAnalysis` qualification. B6 owns controlled `StartDesign` qualification and must not become a second `RunAnalysis` owner. C0 must canonically materialize trusted facts, qualified analysis lineage, reviewed typed context, and frozen policy; caller-supplied compile authority and a giant shared `ModelContext` are rejected.

## Catalog and check boundaries

The current check census remains 34: 9 beam, 5 column, 16 wall, and 4 story/global checks. Product capability labels such as FND-COL-1, FND-COL-2, P8A, P8B, FINAL COLUMN SHEAR, and COLUMN-R1 are not silently treated as catalog check IDs.

`GAP-CATALOG-BEAM-SHEAR-ASW-TOP-AS` remains recorded as a potential catalog semantic contradiction. P2 does not modify or repair the catalog.

## Historical evidence

W2 column goldens remain a test/mechanics oracle only. W3 beam/foundation material remains historical dependency-discovery knowledge. W6 P8A live evidence remains factual ABI/population and negative-contract knowledge only. W7 remains exact component/combo/definition/basis binding knowledge only. None of those historical evidence sets is positive analysis or design execution qualification.

## Review use

Before reusing an asset, verify its exact frozen-base path/blob pair, temporal status, reuse disposition, semantic role, and authority ceiling. Apply reject/gap records before promoting any finding into implementation planning. Reporting/package assets consume established engineering results and provenance; they create no engineering authority.
