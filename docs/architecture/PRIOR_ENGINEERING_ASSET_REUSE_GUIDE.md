# Prior Engineering Asset Reuse Guide — G0-R1 Supervisor Patch P3

**Status:** `READY_FOR_SUPERVISOR_REVIEW`  
**Frozen base:** `6273c19030ab6ecb7ad2637e3bfc74f88b1da086`  
**Frozen base tree:** `8f6ef822b5ab26d22c859438689e7bb9aea9439a`  
**P3 parent:** `66ca38152ebed5ac9c358b4a94d5201e5156c91a`  
**P1 semantic source:** `ed307e5084ad85bf837efcf24724bcacee1b25d9`  
**Branch:** `research/g0-r1-prior-engineering-asset-reuse-index`

This guide accompanies `PRIOR_ENGINEERING_ASSET_REUSE_INDEX.yaml`. The index is research/routing/debt metadata only:

```text
production_import_allowed = false
engineering_authority = none
```

P3 restores the full P1 semantic payload. The only intentional P2-derived change retained is removal of volatile unmerged parallel-research branch/SHA identities in favor of a stable supervisor-reconciliation policy.

## P1 corrections preserved

P3 preserves the P1 34-check matrix, 32-feature resolution index, historical W2/W3/W6/W7 classifications, current catalog archaeology, context-object evidence, stable IDs, detailed rejection and gap registries, product-capability reuse routing, the beam shear catalog gap, T1 negative knowledge, and check-ID/product-capability separation.

Two current path/blob pairs remain corrected:

```text
tbdy_engine/features/etabs_analysis_lineage.py
-> tbdy_engine/integration/etabs_analysis_lineage.py
blob d78f08ef106123fd23aff41df3e1e2291d508bf4

tbdy_engine/features/live_etabs_acquisition_context.py
-> tbdy_engine/integration/live_etabs_acquisition_context.py
blob 6adbebe79ea61d01d82c38d8dd513b8efb143204
```

The final pair audit validates the exact pair, not path and blob independently:

```text
tree[path].type == blob
AND
tree[path].sha == recorded blob
```

Expected frozen-base result:

```text
CURRENT_ASSET_COUNT = 48
CURRENT_PATH_BLOB_PAIRS_CHECKED = 48
MISSING_CURRENT_PATHS = 0
CURRENT_BLOB_MISMATCHES = 0
```

## B1 causal-lineage semantics

`REUSE-LINEAGE-ETABS-ANALYSIS` is the current B1 causal-lineage asset and covers:

- `AnalysisStateIdentity`
- `AnalysisResultIdentity`
- `AnalysisLineageQualification`

The reusable rule is:

```text
IDENTITY OBJECT != QUALIFIED LINEAGE
```

A naked identity object is not trusted engineering input. Current public production cannot positively qualify pre-existing ETABS results because the read-only surface cannot prove which execution generated them. `EvidenceEpoch`, `model_fingerprint`, component match, or a row's existence cannot substitute for causal lineage.

`TrustedLiveAcquisitionContext` and `SourceModelIdentity` remain factual provenance. Source-model reference identity is not physical-file identity, current in-memory state, analysis state, analysis result lineage, or design lineage.

## Roadmap reuse sets

P1 removed the erroneous Wall-Pack-by-letter mapping; P3 preserves those corrected roadmap meanings and their asset lists plus semantic-review rationales.

| Reuse set | Roadmap meaning | Semantic review |
|---|---|---|
| `B2_REUSE_SET` | `DESIGN-LINEAGE-1` | `VERIFIED` |
| `B4A_REUSE_SET` | `DERIVED-STATE-1` | `VERIFIED` |
| `B4B_REUSE_SET` | `ANALYSIS-STATE-MUTATION-1` | `VERIFIED` |
| `B5_REUSE_SET` | `ANALYSIS-EXEC-1` | `VERIFIED` |
| `C0_REUSE_SET` | `FND2-LIVE-MATERIALIZATION-1` | `VERIFIED` |
| `B6_REUSE_SET` | `DESIGN-EXEC-1` | `VERIFIED` |
| `C1_REUSE_SET` | `COLUMN-LIVE-CUTOVER-1` | `VERIFIED` |
| `P8B_REUSE_SET` | `COLUMN-CANDIDATE-ADEQUACY-SELECTION-INTEGRATION` | `VERIFIED` |

`BEAM_REUSE_SET`, `WALL_REUSE_SET`, `GLOBAL_REUSE_SET`, and `REPORTING_REUSE_SET` also retain explicit semantic review records and rationale.

### B2 — design lineage

B2 centers B1 causal lineage, W6 factual design-result ABI/population negative knowledge, W7 exact component/combo/basis join knowledge, `design_combo_matrix`, table-registry design-result sources, load-combo vocabulary only, current P8A exact combo/basis projection, current factual P8A provider/population, and trusted live-acquisition provenance.

It explicitly rejects:

```text
component match -> design lineage
EvidenceEpoch -> design lineage
model fingerprint -> design lineage
ETABS row exists -> DesignResultIdentity
```

### B4A — derived/scratch state lifecycle

B4A centers `SourceModelIdentity`, trusted acquisition provenance, B1 identity boundaries, T1 session/transport ownership, closed fake/custom dependency universes, verified session/model-path facts, and the retired legacy raw-COM facade as a negative pattern.

Source mutation and raw `SapModel` export are forbidden. Unmerged parallel lifecycle research is deliberately absent from CURRENT assets.

### B4B — analysis-state mutation

B4B centers `section_state_policy`, current state transaction mechanics, B1 `AnalysisStateIdentity`, and T1 bounded transport.

Required future chain:

```text
typed mutation
-> SET
-> ret
-> READBACK
-> equality/tolerance
-> mutation manifest
-> AnalysisStateIdentity
```

The current state-transaction asset is a mechanics oracle, not the future mutation authority.

### B5 — controlled analysis execution

B5 centers B1 lineage, trusted live acquisition, T1 transport/session isolation, verified session facts, factual analysis-case readiness, analysis-basis invariants and W7 exact-binding knowledge.

Permanent rule:

```text
partial/failed execution
-> NO qualified AnalysisResultIdentity
```

No partial-success salvage. Unmerged parallel lineage research is not CURRENT.

### C0 — FND2 live materialization

The target dependency chain is:

```text
TrustedLiveAcquisitionContext
+
QUALIFIED AnalysisResultIdentity
+
canonical factual providers
+
reviewed typed regulatory inputs
+
frozen engineering policy
->
canonical RegulatoryCompileInputs
->
existing FND-COL-2
```

No current generic `RegulatoryCompileInputs` object was found on the frozen base, so `GAP-REGULATORY-COMPILE-INPUTS` records new required work. C0 rejects giant `ModelContext`, FeatureSnapshot as regulatory context, and caller-supplied compile-input authority.

### B6 — controlled design execution

B6 centers B1 parent lineage, W6 factual ABI knowledge, W7 exact joins, current P8A design-result provider/population, exact combo eligibility, row-wise ETABS-required-rebar promotion, `design_combo_matrix`, actual selected-design-combo factual acquisition, and T1 isolation.

Permanent rules:

```text
W6 factual result proof != positive design execution qualification
W7 exact join != positive design execution qualification
B6 owns StartDesign
B6 != second RunAnalysis owner
```

`GAP-DESIGN-EXECUTION-QUALIFICATION` records the missing causal controlled-design qualification rather than pretending it already exists.

## Asset classification fields

Every CURRENT asset retains:

```text
category
temporal_status
path
blob
reuse_disposition
semantic_role
authority_ceiling
reuse_scope
production_import_allowed
engineering_authority
```

These ceilings are asset-specific. Examples:

```text
table_registry
-> RAW_ETABS_FACT

feature_catalog
-> FACTUAL_NORMALIZATION_ONLY

check_catalog
-> CURRENT_CHECK_REQUIREMENT_DECLARATION_ONLY

design_combo_matrix
-> REQUIREMENT_DECLARATION_ONLY

load_combo_policy
-> DIAGNOSTIC_CLASSIFICATION_ONLY

W2
-> TEST_ORACLE_ONLY_MECHANICS_ONLY

W6
-> CONTRACT_CANDIDATE_FACTUAL_ABI_ONLY

W7
-> EXACT_BINDING_KNOWLEDGE_NOT_EXECUTION_QUALIFICATION

B1 analysis lineage
-> CURRENT_CANONICAL_LINEAGE_AUTHORITY
```

The index itself still has `engineering_authority = none`; an indexed current asset's authority ceiling is a description of that asset, not authority granted by G0-R1.

## Parallel research policy

Unmerged parallel research is intentionally **not CURRENT, not canonical, and not a stable G0 asset**. This guide and the YAML therefore publish no live research branch names, candidate SHAs, patch SHAs, or moving-head ledger.

```text
UNMERGED RESEARCH != CURRENT ASSET
UNMERGED RESEARCH != CURRENT AUTHORITY
```

Parallel research candidates are reconciled externally by the supervisor at review time. The stable G0-R1 index does not freeze moving research identities.

## Check/capability separation

The current census remains:

```text
BEAM         = 9
COLUMN       = 5
WALL         = 16
STORY_GLOBAL = 4
TOTAL        = 34
```

The YAML serializes all 34 checks individually and retains 32 unique required feature IDs. Each check record retains combo, section-state, context, lineage, result-selection, reuse, oracle, owner, blocker, future-sprint and forbidden-shortcut information, with unresolved values remaining `UNKNOWN`.

These product/roadmap capabilities remain separate and are not fabricated as catalog check IDs:

```text
FND-COL-1
FND-COL-2
P8A
P8A-B
FND-COL-4
P8B
FINAL COLUMN SHEAR
COLUMN-R1
```

Each capability retains its P1 `current_reuse_assets` and `blockers_or_notes` routing.

## Context object evidence

P3 retains P1 evidence-bearing classifications for:

```text
StructuralSystemContext
ReferenceLevelContext
GroundMotionContext
BuildingUseContext
DuctilityContext
ReviewedLoadFamilyBinding
ResultSelectionPolicy
SelectionTrace
CheckExecutionContext
MaterializedCheckDependencies
```

The YAML records classification together with current evidence/scope and historical source/scope where applicable; it does not reduce those concepts to bare enum labels.

## Negative knowledge and gaps

The detailed P1 `reject_registry` is restored with both `pattern` and `reason` for every stable rejection ID. Stable negative knowledge includes T1 fallback isolation, name-heuristic rejection, factual/regulatory lane separation, design-result/verdict separation, exact combo/basis requirements, causal lineage requirements, context boundaries, controlled execution ownership and source-model immutability.

The detailed P1 gap records are also restored. In particular P3 preserves without repairing:

```text
GAP-CATALOG-BEAM-SHEAR-ASW-TOP-AS
classification = POTENTIAL_CATALOG_SEMANTIC_CONTRADICTION

beam_shear_asw_ge_asw_min
-> beam_As_top_governing_required_mm2
```

A future beam regulatory owner must verify the intended rule and semantics before changing the catalog.

Also retained with explanatory meaning are:

```text
GAP-GENERIC-RESULT-SELECTION-POLICY
GAP-MATERIALIZED-CHECK-DEPENDENCIES
GAP-REGULATORY-COMPILE-INPUTS
GAP-DESIGN-EXECUTION-QUALIFICATION
```

## Historical evidence

W2 column goldens remain a test/mechanics oracle only. W3 beam/foundation material remains historical dependency-discovery knowledge. W6 P8A live evidence remains factual ABI/population and negative-contract knowledge only. W7 remains exact component/combo/definition/basis binding knowledge only. None of those historical evidence sets is positive analysis or design execution qualification.

## Validation contract

Committed-byte validation must parse the exact P3 YAML blob with `yaml.safe_load` and validate the parsed object, including:

```text
CHECK_RECORD_COUNT = 34
UNIQUE_REQUIRED_FEATURES = 32
CURRENT_ASSET_COUNT = 48
PARALLEL_RESEARCH_DYNAMIC_REFS = 0
```

It must also validate stable-ID integrity, reuse-set reference/semantic integrity, asset classification fields, rejection detail, gap detail, product-capability reuse routing and context evidence.

No exact repository checkout is assumed in the local container, so repository-shell validations are not fabricated. Frozen-base path/blob evidence and final main ref are connector-verified.

## Allowed status

Only after the required committed-byte, pair and final-base gates pass:

```text
READY_FOR_SUPERVISOR_REVIEW
```

This guide does not declare the candidate canonical, merge-ready, or ready for merge.
