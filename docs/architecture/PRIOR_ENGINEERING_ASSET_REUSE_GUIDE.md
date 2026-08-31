# Prior Engineering Asset Reuse Guide — G0-R1 Supervisor Patch P1

**Status:** `READY_FOR_SUPERVISOR_REVIEW`  
**Frozen base:** `6273c19030ab6ecb7ad2637e3bfc74f88b1da086`  
**Frozen base tree:** `8f6ef822b5ab26d22c859438689e7bb9aea9439a`  
**P1 parent:** `d21232faffe1c32879684e358e487748090e1ecd`  
**Branch:** `research/g0-r1-prior-engineering-asset-reuse-index`

This guide accompanies `PRIOR_ENGINEERING_ASSET_REUSE_INDEX.yaml`. The index is research/routing/debt metadata only:

```text
production_import_allowed = false
engineering_authority = none
```

## P1 corrections

P1 preserves the 34-check census, historical W2/W3/W6/W7 classifications, current catalog archaeology, context archaeology, stable IDs, the beam shear catalog gap, T1 negative knowledge, and check-ID/product-capability separation.

Two current path/blob pairs were corrected:

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

Result recorded in the YAML:

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

P1 removes the erroneous Wall-Pack-by-letter mapping and records roadmap meaning explicitly.

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

`BEAM_REUSE_SET`, `WALL_REUSE_SET`, `GLOBAL_REUSE_SET`, and `REPORTING_REUSE_SET` also carry explicit semantic review records.

### B2 — design lineage

B2 now centers B1 causal lineage, W6 factual design-result ABI/population negative knowledge, W7 exact component/combo/basis join knowledge, `design_combo_matrix`, table-registry design-result sources, load-combo vocabulary only, current P8A exact combo/basis projection, current factual P8A provider/population, and trusted live-acquisition provenance.

It explicitly rejects:

```text
component match -> design lineage
EvidenceEpoch -> design lineage
model fingerprint -> design lineage
ETABS row exists -> DesignResultIdentity
```

### B4A — derived/scratch state lifecycle

B4A centers `SourceModelIdentity`, trusted acquisition provenance, B1 identity boundaries, T1 session/transport ownership, closed fake/custom dependency universes, verified session/model-path facts, and the retired legacy raw-COM facade as a negative pattern.

Source mutation and raw `SapModel` export are forbidden. `R-LIFE-1` is recorded only as unmerged parallel research, never CURRENT.

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

No partial-success salvage. `R-LINEAGE-1` remains unmerged research.

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

Every CURRENT asset now carries:

```text
reuse_disposition
semantic_role
authority_ceiling
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

## Parallel research

The frozen base does not contain these research branches:

- `R-LIFE-1` — candidate `84159cae238c489473ba5781ce03459a8fb1ab4b`
- `R-LINEAGE-1` — candidate `9e491faf823aaa844188f806be1cd5efa0ce297c`
- `R-CI-1` — candidate `32f51695543291e8954fc3e07e01499df3109795`

They are encoded as `UNMERGED_RESEARCH / PARALLEL_RESEARCH_CANDIDATE`, never as CURRENT assets.

```text
UNMERGED RESEARCH != CURRENT ASSET
```

G0-R1 remains valid if any of those branches are later rejected.

## Check/capability separation

The current census remains:

```text
BEAM         = 9
COLUMN       = 5
WALL         = 16
STORY_GLOBAL = 4
TOTAL        = 34
```

The YAML serializes all 34 checks individually and retains 32 unique required feature IDs.

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

## Catalog contradiction

P1 preserves without repairing:

```text
GAP-CATALOG-BEAM-SHEAR-ASW-TOP-AS
classification = POTENTIAL_CATALOG_SEMANTIC_CONTRADICTION

beam_shear_asw_ge_asw_min
-> beam_As_top_governing_required_mm2
```

A future beam regulatory owner must verify the intended rule and semantics before changing the catalog.

## Validation

The YAML records:

```text
all CURRENT (path, blob) pairs exact-tree verified = PASS
all REUSE-* IDs unique = PASS
all GAP-* IDs unique = PASS
all REJECT-* IDs unique = PASS
all 34 check IDs resolve = PASS
all 32 required feature IDs resolve = PASS
all reuse-set references resolve = PASS
all reuse-set semantic reviews = PASS
all CURRENT assets have reuse_disposition = PASS
all CURRENT assets have semantic_role = PASS
all CURRENT assets have authority_ceiling = PASS
historical assets clearly historical = PASS
unmerged research never CURRENT = PASS
production_import_allowed = false
index engineering_authority = none
```

No exact repository checkout is available in the local container, so repository-shell validations are not fabricated:

```text
LOCAL_CHECKOUT_AVAILABLE = NO
python -m compileall = NOT RUN LOCALLY
git diff --check = NOT RUN LOCALLY
```

The generated YAML itself is locally parsed and cross-reference validated before commit.

Before candidate freeze, `main` must again resolve to `6273c19030ab6ecb7ad2637e3bfc74f88b1da086`. If it has moved, stop as `BASE_MOVED`.

## Allowed status

```text
READY_FOR_SUPERVISOR_REVIEW
```

This guide does not declare the candidate canonical, merge-ready, or ready for merge.
