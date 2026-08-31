# Prior Engineering Asset Reuse Guide — G0-R1

**Status:** `READY_FOR_SUPERVISOR_REVIEW`  
**Base:** `6273c19030ab6ecb7ad2637e3bfc74f88b1da086`  
**Base tree:** `8f6ef822b5ab26d22c859438689e7bb9aea9439a`  
**Branch:** `research/g0-r1-prior-engineering-asset-reuse-index`

This guide explains how to consume `PRIOR_ENGINEERING_ASSET_REUSE_INDEX.yaml`. It is a research/reuse artifact only.

```text
production_import_allowed = false
engineering_authority = none
```

Nothing in this guide or the YAML creates a new engineering authority, changes a current catalog, or permits historical worker code to enter production by import.

## 1. Post-T1 base refresh rule

The final index is based on the exact post-T1 `main` above. Prior archaeology was not discarded, but old current-asset conclusions were not silently carried forward.

For a previously researched current asset:

```text
OLD FINDING
  -> current path exists?
  -> old blob == current blob?
       YES: classification may be retained
       NO / old blob unavailable: reread + reclassify on current base
```

The prior per-path old blob ledger was not preserved for the seven previously classified current files listed in the YAML. Those seven were therefore **reclassified on the current base**, not claimed as blob-identical salvage. Historical W2/W3/W6/W7 findings remain historical test-vector/dependency/lineage knowledge and are explicitly marked historical.

## 2. T1 is now current architecture

The current boundary is:

```text
packages/etabs_gateway
=
SOLE production COM / STA / session / attach owner
```

The current gateway connection implementation and T1 isolation tests establish the reusable offline/mock mechanics:

```text
EXPLICIT CUSTOM/FAKE COM DEPENDENCY
  -> CLOSED DEPENDENCY UNIVERSE
  -> REAL/default COM FALLBACK FORBIDDEN
```

Use these stable IDs in future prompts:

- `REUSE-OAPI-T1-GATEWAY-OWNERSHIP`
- `REUSE-OAPI-T1-FAKE-RUNTIME-ISOLATION`
- `REUSE-OAPI-T1-PID-ISOLATION`
- `REUSE-OAPI-T1-CLOSED-DEPENDENCY-UNIVERSE`

And these rejection IDs:

- `REJECT-LEGACY-FALLBACK-ATTACH`
- `REJECT-T1-CUSTOM-COMTYPES-DEFAULT-WIN32`
- `REJECT-T1-CUSTOM-RUNTIME-DEFAULT-COMTYPES`
- `REJECT-T1-RAW-COM-ESCAPE`

T1 test mechanics are architecture/test knowledge only. They are not engineering authority.

## 3. Current check census

The YAML serializes every current check as a concrete record:

| Family | Count |
|---|---:|
| Beam | 9 |
| Column | 5 |
| Wall | 16 |
| Story / Global | 4 |
| **Total** | **34** |

The census is the union of the current base check catalog, the column-geometry overlay, and Wall Packs A/B/C. Every record carries required features, factual-source assets, combo and section-state status, shared/reviewed contexts, lineage requirements, result-selection requirement, reuse assets, mechanics oracle, current owner, blockers, future sprint, and forbidden shortcuts. Where current contracts do not resolve a field, the YAML says `UNKNOWN` rather than inventing an answer.

The YAML also indexes all 32 unique required feature IDs used by those 34 checks. It intentionally serializes **no raw table keys** in per-check reuse records; raw source-table authority remains behind `REUSE-CONTRACT-TABLE-REGISTRY` and `REUSE-CONTRACT-ETABS-FEATURE-SOURCE`.

## 4. Check IDs are not product capabilities

The following labels are tracked separately and are **not fabricated as current `check_catalog` IDs**:

- `FND-COL-1`
- `FND-COL-2`
- `P8A`
- `P8A-B`
- `FND-COL-4`
- `P8B`
- `FINAL COLUMN SHEAR`
- `COLUMN-R1`

Each capability points only to stable `REUSE-*` assets in the YAML.

## 5. Historical context concepts vs current objects

| Concept | Current classification |
|---|---|
| `StructuralSystemContext` | `CURRENT_OBJECT_PARTIAL` |
| `ReferenceLevelContext` | `CURRENT_OBJECT_PARTIAL` |
| `GroundMotionContext` | `CURRENT_OBJECT_PARTIAL` |
| `BuildingUseContext` | `CURRENT_OBJECT_PARTIAL` |
| `DuctilityContext` | `CURRENT_OBJECT_PARTIAL` |
| `ReviewedLoadFamilyBinding` | `CURRENT_OBJECT_PARTIAL` |
| `ResultSelectionPolicy` | `CURRENT_OBJECT_PARTIAL` |
| `SelectionTrace` | `CURRENT_OBJECT_EXISTS` |
| `CheckExecutionContext` | `CURRENT_OBJECT_EXISTS` |
| `MaterializedCheckDependencies` | `HISTORICAL_DESIGN_ONLY` |

Important distinctions:

- Current `CheckExecutionContext` is an exact frozen carrier.
- Current `SelectionTrace` exists in the Ndm slice.
- Current `ReviewedNdmLoadBinding` and `ReviewedNdmPolicy` are target-scoped implementations, not proof that the historical generic shared abstractions are complete.
- `WallRegulatoryReferenceFacts` is a real typed current reference context for the Wall Pack C domain, but it is not a generic `ReferenceLevelContext`.
- `design_basis.yaml` contains partial seismic/building-use fields while `design_basis_reviewed=false`; those values are not silently promoted to executable regulatory truth.
- The historical `MaterializedCheckDependencies` design remains useful architecture research, but no exact current object was found.

Exact current path/blob evidence and historical report names are in the YAML.

## 6. Catalog contradiction: record, do not repair

Stable debt ID:

```text
GAP-CATALOG-BEAM-SHEAR-ASW-TOP-AS
```

Classification:

```text
POTENTIAL_CATALOG_SEMANTIC_CONTRADICTION
```

Observed current dependency:

```text
beam_shear_asw_ge_asw_min
  -> beam_As_top_governing_required_mm2
```

The dependency is suspicious because an `Asw >= Asw,min` shear-reinforcement check points to a feature named as governing **top longitudinal reinforcement area**. That may be a placeholder, a naming problem, or a binding problem. G0-R1 makes no engineering correction. A future beam regulatory owner must reconcile the intended rule, formula, feature semantics, source history, and consumer before changing the catalog.

## 7. How to cite reuse assets in future implementation prompts

Future prompts should cite stable IDs, not copy a free-text archaeology paragraph.

Examples:

```text
Reuse C0_REUSE_SET.
Preserve REUSE-OAPI-T1-CLOSED-DEPENDENCY-UNIVERSE.
Enforce REJECT-T1-CUSTOM-RUNTIME-DEFAULT-COMTYPES.
Do not import historical assets into production.
```

or:

```text
For wall execution, use WALL_REUSE_SET.
Treat REUSE-CONTEXT-WALL-REFERENCE-FACTS as factual context only.
Do not violate REJECT-FEATURE-REGULATORY-SEMANTIC-LEAK.
```

Required high-value sets present in the YAML:

```text
B2_REUSE_SET
B4A_REUSE_SET
B4B_REUSE_SET
B5_REUSE_SET
C0_REUSE_SET
B6_REUSE_SET
C1_REUSE_SET
P8B_REUSE_SET

BEAM_REUSE_SET
WALL_REUSE_SET
GLOBAL_REUSE_SET
REPORTING_REUSE_SET
```

Every set member resolves to a stable `REUSE-*` asset ID.

## 8. Historical assets: what “reuse” means

Historical W2/W3/W6/W7 material may be reused only in the classification recorded by the YAML:

- test vectors;
- dependency/source archaeology;
- negative-contract mechanics;
- lineage/binding invariants.

Historical worker code, fixtures, or prose do **not** become production truth or engineering authority merely because they are useful.

In particular:

```text
TEST VECTOR != ENGINEERING AUTHORITY
DEPENDENCY DISCOVERY != ENGINEERING AUTHORITY
ETABS DESIGN RESULT != FINAL TBDY VERDICT
```

## 9. Validation status

Connector verification established the exact current base/tree and current path/blob census. The generated YAML was parsed locally and its internal stable-ID, check-count, feature-reference, capability-reference, and reuse-set integrity checks passed.

There was no exact repository checkout in the local container, and outbound GitHub DNS was unavailable there. Therefore these are deliberately not fabricated:

```text
LOCAL_CHECKOUT_AVAILABLE = NO
python -m compileall = NOT RUN LOCALLY
git diff --check = NOT RUN LOCALLY
git fetch origin = NOT RUN LOCALLY
git rev-parse origin/main = NOT RUN LOCALLY
```

Before candidate freeze, `main` must again resolve to `6273c19030ab6ecb7ad2637e3bfc74f88b1da086`. If it has moved, the candidate must stop as `BASE_MOVED`.

## 10. Non-authority declaration

This sprint changes documentation only. The index is a routing/reuse/debt map for future workers.

It is **not**:

- a new check catalog;
- a new feature catalog;
- a regulatory source;
- an ETABS acquisition implementation;
- a selection authority;
- a final engineering verdict engine;
- a declaration that any historical branch is production-ready.

The only allowed final review state for G0-R1 is:

```text
READY_FOR_SUPERVISOR_REVIEW
```
