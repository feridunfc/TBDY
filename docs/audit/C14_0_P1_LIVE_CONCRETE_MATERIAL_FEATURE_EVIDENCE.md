# C14.0-P1 Live Concrete Material Feature Evidence

Status: IMPLEMENTED_ON_BRANCH_NOT_LOCALLY_VERIFIED

Branch:

```text
sprint/c14-0-p1-live-concrete-material-feature-evidence
```

## Scope

C14.0-P1 adds a separate read-only material-enriched FeatureSnapshot probe. It does not modify the existing C13.5-P7 command or product bundle.

Production entry points:

```text
tbdy_engine/features/live_etabs_concrete_material_probe.py
tools/probe_live_etabs_concrete_material_features.py
```

Required command:

```powershell
python tools/probe_live_etabs_concrete_material_features.py `
  --live-etabs `
  --out local_out/c14_0_p1_live_concrete_material_features `
  --max-rows 20
```

Without `--live-etabs`, the CLI exits nonzero before creating the output directory or attempting ETABS attach.

## Locked production source chain

```text
Frame Assignments - Summary
→ explicit beam/column classification by UniqueName

Frame Assignments - Section Properties
  UniqueName
  SectProp

Frame Section Property Definitions - Concrete Rectangular
  Name
  Material
  t2
  t3

Material Properties - Concrete Data
  Material
  Fc
  SFc
```

The existing live ETABS table fetcher/parser, component-type source, assignment/property geometry resolver, and runtime unit reader are reused.

Material resolution uses only:

```text
section row Material == material definition Material
```

The comparison is raw Python equality. There is no trimming fallback, case folding, alias mapping, fuzzy matching, material-name parsing, or concrete-class inference.

`Fc` is the only concrete-strength source. `SFc` is retained only as raw material-table evidence and is never used to resolve `concrete_fck_mpa`.

## Unit contract

Only the proven runtime source pair is supported:

```yaml
source_force_unit: kN
source_length_unit: m
source_stress_unit: kN/m²
target_strength_unit: MPa
normalization_factor_to_mpa: 0.001
```

The normalization is explicit:

```text
Fc [kN/m²] × 0.001 = concrete_fck_mpa [MPa]
```

Any other runtime force/length pair produces `MATERIAL_STRESS_UNIT_UNSUPPORTED`. Missing runtime evidence produces `MATERIAL_UNIT_EVIDENCE_MISSING`.

## Numeric parsing

The parser accepts only finite native numeric values or plain numeric strings matching a strict signed decimal literal. It rejects suffixed values, material names, booleans, NaN, and Infinity.

No unit suffix is removed and no material name is parsed.

## Feature evidence

A resolved `concrete_fck_mpa` preserves:

- complete assignment source row;
- complete rectangular section source row;
- exact raw material name and Python type;
- complete concrete material definition source row;
- exact raw `Fc` value and Python type;
- parsed numeric value;
- present and database ETABS unit API payloads;
- source force, length, and stress units;
- normalization factor and basis;
- normalized MPa value and unit.

Material-enriched snapshots also retain the existing resolved beam/column width and depth features produced from the reused geometry mapping.

## Outputs

```text
<out>/
  feature_snapshot.json
  concrete_material_probe_summary.json
  concrete_material_probe_diagnostics.json
  concrete_material_probe_manifest.json
```

The probe owns only these four files. Unrelated files and existing P7 output directories/files under the same root are preserved.

## Status semantics

- `OK`: every selected accepted candidate emitted a resolved material-enriched snapshot and no diagnostics were produced.
- `PARTIAL`: at least one material-enriched snapshot was emitted and diagnostics remain visible.
- `FAIL`: no usable material-enriched snapshot was emitted.

These statuses describe source evidence, not engineering compliance.

## Direct API boundary

Production code does not call frame-material or concrete-material property APIs. Production evidence is table-based only. The manifest records:

```yaml
direct_material_api_used: false
checks_executed: false
existing_p7_pipeline_modified: false
```

## Guardrails

C14.0-P1 does not add or modify:

- engineering checks or thresholds;
- check catalog entries;
- feature catalog aliases;
- axial capacity, PMM, shear, confinement, reinforcement, or SCWB;
- material-name strength inference;
- `SFc` strength fallback;
- direct material API production calls;
- ETABS table discovery, registry scanning, or source hunting;
- fuzzy joins;
- `SetPresentUnits`;
- Excel production input;
- Streamlit;
- the existing P7 production command or product output.

## Verification ownership

Local compile, pytest, offline acceptance, and live ETABS execution were not run in the implementation environment. The user owns verification using the sprint acceptance commands.
