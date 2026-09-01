# Prior Engineering Asset Reuse Guide — G0-R1 Supervisor Patch P4

**Status:** `READY_FOR_SUPERVISOR_REVIEW`
**Original frozen base:** `6273c19030ab6ecb7ad2637e3bfc74f88b1da086`
**Original frozen base tree:** `8f6ef822b5ab26d22c859438689e7bb9aea9439a`
**P3 parent:** `66ca38152ebed5ac9c358b4a94d5201e5156c91a`
**P1 semantic source:** `ed307e5084ad85bf837efcf24724bcacee1b25d9`
**Accepted P3 head:** `12fffcc11fda57dab17a80eb3a6b186a16b5c904`
**Post-main-move reconciliation base:** `224f44621b88ded2900be3a2f2c560b6c59df905`
**Post-main-move reconciliation tree:** `63353f9922df0e02017b6bbd67efc374afedc244`
**Branch:** `research/g0-r1-prior-engineering-asset-reuse-index`

This guide accompanies `PRIOR_ENGINEERING_ASSET_REUSE_INDEX.yaml`. The index is research/routing/debt metadata only:

```text
production_import_allowed = false
engineering_authority = none
```

P4 preserves the full accepted P3/P1 semantic payload and reconciles only the knowledge-spine state that changed because R-LINEAGE-1, R-LIFE-1, and R-CI-1 have since merged into current `main`. It also removes the known opening-metadata trailing whitespace. P4 does not implement CI-D1/D2/D3/D4, production behavior, ETABS execution, or engineering authority.

## Post-main-move reconciliation

Historical research provenance remains anchored to the original frozen base:

```text
ORIGINAL_FROZEN_RESEARCH_BASE
6273c19030ab6ecb7ad2637e3bfc74f88b1da086

POST_MERGE_REVALIDATION_BASE
224f44621b88ded2900be3a2f2c560b6c59df905
```

These identities are intentionally different. P4 does not rewrite `base_sha`, `base_tree`, P3 ancestry, or the P1 semantic source to make history look current.

Exact current-main movement from the original frozen base is six added research/governance artifacts and no modifications to the original 48 CURRENT path/blob pairs. Therefore:

```text
ORIGINAL_CURRENT_ASSETS_CHECKED = 48
ORIGINAL_CURRENT_ASSET_MISSING_COUNT = 0
ORIGINAL_CURRENT_ASSET_BLOB_MISMATCH_COUNT = 0
NEW_MERGED_RESEARCH_ASSET_COUNT = 6
POST_RECONCILIATION_CURRENT_ASSET_COUNT = 54
```

The six reconciled CURRENT knowledge-spine assets are:

```text
R-LINEAGE-1
  docs/architecture/RESULT_FRESHNESS_AND_CAUSAL_PROOF_RESEARCH.md
  docs/architecture/RESULT_QUALIFICATION_EVIDENCE_MATRIX.yaml

R-LIFE-1
  docs/architecture/ETABS_EXECUTION_LIFECYCLE_CENSUS.md
  docs/architecture/ETABS_EXECUTION_LIFECYCLE_MATRIX.yaml

R-CI-1
  docs/audit/CURRENT_CI_BASELINE_GOVERNANCE.md
  docs/audit/CURRENT_CI_DEBT_REGISTRY.yaml
```

Their presence as CURRENT reuse-spine knowledge does not promote them to production engineering authority, runtime authority, a positive lineage issuer, or a production dependency.

## P1 corrections preserved

P4 preserves the P1 34-check matrix, 32-feature resolution index, historical W2/W3/W6/W7 classifications, current catalog archaeology, context-object evidence, stable IDs, detailed rejection and gap registries, product-capability reuse routing, the beam shear catalog gap, T1 negative knowledge, and check-ID/product-capability separation.

Two original current path/blob pairs remain corrected:

```text
tbdy_engine/features/etabs_analysis_lineage.py
-> tbdy_engine/integration/etabs_analysis_lineage.py
blob d78f08ef106123fd23aff41df3e1e2291d508bf4

tbdy_engine/features/live_etabs_acquisition_context.py
-> tbdy_engine/integration/live_etabs_acquisition_context.py
blob 6adbebe79ea61d01d82c38d8dd513b8efb143204
```

The pair audit validates the exact pair, not path and blob independently:

```text
tree[path].type == blob
AND
tree[path].sha == recorded blob
```

Original frozen-base result remains historical truth:

```text
CURRENT_ASSET_COUNT_AT_ORIGINAL_BASE = 48
CURRENT_PATH_BLOB_PAIRS_CHECKED_AT_ORIGINAL_BASE = 48
MISSING_CURRENT_PATHS = 0
CURRENT_BLOB_MISMATCHES = 0
```

After current-main reconciliation the CURRENT asset registry contains 54 records: the same 48 original records plus the six merged research/governance knowledge records.

## B1 causal-lineage semantics

`REUSE-LINEAGE-ETABS-ANALYSIS` remains the current B1 causal-lineage contract asset and covers:

- `AnalysisStateIdentity`
- `AnalysisResultIdentity`
- `AnalysisLineageQualification`

The reusable rule is:

```text
IDENTITY OBJECT != QUALIFIED LINEAGE
```

A naked identity object is not trusted engineering input. Current public production cannot positively qualify pre-existing ETABS results because the read-only surface cannot prove which execution generated them. `EvidenceEpoch`, `model_fingerprint`, component match, or a row's existence cannot substitute for causal lineage.

Merged R-LINEAGE-1 adds CURRENT architecture-research knowledge that tightens this ceiling without becoming a positive issuer:

```text
pre-existing results != qualified result lineage
partial/failed execution -> no qualified AnalysisResultIdentity
whole predeclared scope must succeed
B5 owns RunAnalysis semantically
B6 owns StartDesign semantically
```

`TrustedLiveAcquisitionContext` and `SourceModelIdentity` remain factual provenance. Source-model reference identity is not physical-file identity, current in-memory state, analysis state, analysis result lineage, or design lineage.

## Roadmap reuse sets

P1 removed the erroneous Wall-Pack-by-letter mapping; P4 preserves those corrected roadmap meanings and their asset lists plus semantic-review rationales, then adds only the merged research knowledge now relevant to those routes.

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

`BEAM_REUSE_SET`, `WALL_REUSE_SET`, `GLOBAL_REUSE_SET`, and `REPORTING_REUSE_SET` also retain explicit semantic review records and rationale. R-CI knowledge is routed only through `GLOBAL_REUSE_SET` as CI-governance knowledge; it is not engineering calculation authority.

### B2 — design lineage

B2 centers B1 causal lineage, W6 factual design-result ABI/population negative knowledge, W7 exact component/combo/basis join knowledge, `design_combo_matrix`, table-registry design-result sources, load-combo vocabulary only, current P8A exact combo/basis projection, current factual P8A provider/population, trusted live-acquisition provenance, and merged R-LINEAGE causal-result research.

It explicitly rejects:

```text
component match -> design lineage
EvidenceEpoch -> design lineage
model fingerprint -> design lineage
ETABS row exists -> DesignResultIdentity
```

Merged R-LINEAGE knowledge is architecture research only. It does not grant positive qualification authority to this index or to any caller.

### B4A — derived/scratch state lifecycle

B4A centers `SourceModelIdentity`, trusted acquisition provenance, B1 identity boundaries, T1 session/transport ownership, closed fake/custom dependency universes, verified session/model-path facts, the retired legacy raw-COM facade as a negative pattern, and merged R-LIFE lifecycle ownership knowledge.

Source mutation and raw `SapModel` export are forbidden. R-LIFE establishes that gateway owns transport / COM / STA / session, not analysis/design execution authority, and that scratch lifecycle requires causal ownership. Exact future module placement remains unresolved.

### B4B — analysis-state mutation

B4B centers `section_state_policy`, current state transaction mechanics, B1 `AnalysisStateIdentity`, T1 bounded transport, and merged R-LIFE lifecycle knowledge.

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

The current state-transaction asset is a mechanics oracle, not the future mutation authority. R-LIFE does not select the future implementation module.

### B5 — controlled analysis execution

B5 centers B1 lineage, trusted live acquisition, T1 transport/session isolation, verified session facts, factual analysis-case readiness, analysis-basis invariants, W7 exact-binding knowledge, merged R-LINEAGE causal qualification research, and merged R-LIFE execution-ownership research.

Permanent rules:

```text
B5 owns RunAnalysis semantically
partial/failed execution
-> NO qualified AnalysisResultIdentity
whole predeclared execution scope must succeed
```

No partial-success salvage. Gateway remains transport-only; OAPI remains factual ABI-only.

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

No current generic `RegulatoryCompileInputs` object was found on the original frozen base, so `GAP-REGULATORY-COMPILE-INPUTS` records new required work. C0 rejects giant `ModelContext`, FeatureSnapshot as regulatory context, and caller-supplied compile-input authority. Merged R-LINEAGE knowledge is routed here only to preserve the causal qualification ceiling.

### B6 — controlled design execution

B6 centers B1 parent lineage, W6 factual ABI knowledge, W7 exact joins, current P8A design-result provider/population, exact combo eligibility, row-wise ETABS-required-rebar promotion, `design_combo_matrix`, actual selected-design-combo factual acquisition, T1 isolation, merged R-LINEAGE causal-result research, and merged R-LIFE execution-ownership research.

Permanent rules:

```text
W6 factual result proof != positive design execution qualification
W7 exact join != positive design execution qualification
B6 owns StartDesign
B6 MUST NOT RunAnalysis
```

`GAP-DESIGN-EXECUTION-QUALIFICATION` records the missing causal controlled-design qualification rather than pretending it already exists.

### C1 — column live cutover

C1 retains the accepted column authority and P8A/FND-COL-4 composition and now also routes merged R-LINEAGE and R-LIFE knowledge so live cutover cannot bypass causal result qualification or execution ownership boundaries.

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

B1 analysis lineage contracts
-> CURRENT_CANONICAL_LINEAGE_AUTHORITY

R-LINEAGE-1 research artifacts
-> MERGED_ARCHITECTURE_RESEARCH_KNOWLEDGE_ONLY

R-LIFE-1 research artifacts
-> MERGED_ARCHITECTURE_RESEARCH_KNOWLEDGE_ONLY

R-CI-1 governance artifacts
-> CURRENT_MERGED_CI_CLASSIFICATION_GOVERNANCE_ONLY
```

The index itself still has `engineering_authority = none`; an indexed current asset's authority ceiling is a description of that asset, not authority granted by G0-R1.

## Parallel research policy

The stable policy remains:

```text
unmerged_research_is_current_asset: false
unmerged_research_may_supply_current_authority: false
reconciliation_owner: SUPERVISOR
```

The current distinction is:

```text
UNMERGED RESEARCH
-> external evidence only

MERGED RESEARCH
-> may become CURRENT reuse-spine knowledge after supervisor reconciliation

MERGED RESEARCH
!= production engineering authority
```

R-LINEAGE-1, R-LIFE-1, and R-CI-1 are now merged and have been explicitly reconciled by P4. This does not change the rule for future unmerged parallel research and does not freeze moving branch identities into the stable reuse spine.

## CI-governance knowledge

R-CI-1 is CURRENT merged governance knowledge only. Its reusable rules are:

```text
RED != CURRENT_SPRINT_REGRESSION
CI-DEBT-001..006 = FAILURE_SIGNATURE
CI-DEBT-007..008 = WORKFLOW_GOVERNANCE
```

An actual failed test may be classified inherited only when its failed node plus normalized exception/signature exactly matches a `FAILURE_SIGNATURE` debt. `WORKFLOW_GOVERNANCE` debt may classify stale/wrong gate policy but may never whitelist arbitrary runtime/test failures.

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

P4 retains P1/P3 evidence-bearing classifications for:

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

The detailed P1/P3 `reject_registry` remains with both `pattern` and `reason` for every stable rejection ID. Stable negative knowledge includes T1 fallback isolation, name-heuristic rejection, factual/regulatory lane separation, design-result/verdict separation, exact combo/basis requirements, causal lineage requirements, context boundaries, controlled execution ownership and source-model immutability.

The detailed gap records are also preserved. In particular P4 preserves without repairing:

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

Committed-byte validation must parse the exact P4 YAML blob with `yaml.safe_load` and validate the parsed object, including:

```text
CHECK_RECORD_COUNT = 34
UNIQUE_REQUIRED_FEATURES = 32
ORIGINAL_CURRENT_ASSETS_CHECKED = 48
NEW_MERGED_RESEARCH_ASSET_COUNT = 6
POST_RECONCILIATION_CURRENT_ASSET_COUNT = 54
```

It must also validate stable-ID integrity, reuse-set reference/semantic integrity, asset classification fields, rejection detail, gap detail, product-capability reuse routing, context evidence, exact current-main paths/blobs, and the research/governance authority ceilings.

Repository-level CI validation is not fabricated by this guide; PR CI is classified from the actual PR runs after the P4 candidate is pushed.

## Allowed status

Only after the required committed-byte, pair, current-main, integrity, hygiene, mergeability, and CI-classification gates pass may the supervisor handoff state be:

```text
READY_FOR_SUPERVISOR_MERGE_REVIEW
```

This guide does not declare the candidate canonical and does not merge PR #175.
