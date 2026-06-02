# Beam Shear Reinforcement Design Engine

## Scope

Pure shear reinforcement spacing requirement kernel.
Given design shear force, compute required stirrup spacing.

## Unit Standard

| Quantity | Unit |
|----------|------|
| Length | mm |
| Force | kN, N |
| Stress | MPa |
| Area | mm² |

## Formulas
Vc = vc_factor * fctd * bw * d
Vs_required = max(V_design - Vc, 0)
bar_area = π * diameter² / 4
Asw_per_stirrup = legs * bar_area
s = Asw * fywd * d * cot_theta / Vs_required
s_limited = min(s, s_max)


## Policy Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| vc_factor | 0.65 | Concrete shear contribution factor |
| cot_theta | 1.0 | Truss model strut angle |
| s_max_mm | 200.0 | Maximum stirrup spacing |

## Output Status

| Status | Meaning | s_limited |
|--------|---------|-----------|
| SHEAR_REINFORCEMENT_REQUIRED | V_design > Vc | min(s_required, s_max) |
| MIN_SHEAR_REINFORCEMENT_GOVERNS | V_design <= Vc | s_max |
| INVALID_INPUT | Invalid geometry/material | — |

## Claim Limitations

- SHEAR_REINFORCEMENT_DESIGN_ENGINE = PROVEN
- FULL_TBDY_SHEAR_DESIGN_CERTIFIED = FALSE
- Policy parameters pending code-article benchmark

## Constraints

This kernel:
- Uses no external model adapters
- Does not compute Ve_capacity or Mpr
- Does not compare provided stirrup spacing
- Produces no reports or UI output
2. Boundary Scan — Production Dosya Temizliği
shear_reinforcement_design.py docstring'i kontrol edildi. Mpr, Ve_capacity, provided_area, selected_area terimleri production kodda yok.

powershell
Select-String -Path `
  tbdy_engine/design/beams/calculators/shear_reinforcement_design.py `
  -Pattern "comtypes|SapModel|FrameForce|ETABS|provided_area|selected_area|Mpr|Ve_capacity|ReportingFacade|CheckAdapter|BeamEvaluationPackage|streamlit"
# Expected: no output
R12 Kapanış
Kriter	Durum
SHEAR_REINFORCEMENT_DESIGN_ENGINE	✅ PROVEN
V_TO_STIRRUP_SPACING_KERNEL	✅ PROVEN
CONCRETE_SHEAR_CONTRIBUTION_POLICY_RECORDED	✅ TRUE
NO_PROVIDED_STIRRUP_COMPARISON	✅ TRUE
NO_ETABS_DEPENDENCY	✅ TRUE
FULL_TBDY_SHEAR_DESIGN_CERTIFIED	⚠️ FALSE
DESIGN_ENGINE_BOUNDARY_PRESERVED	✅ TRUE
DOCS_CLEAN	✅ FIXED
BOUNDARY_SCAN_CLEAN	✅ FIXED
R10-R12 Serisi Tamamlandı — Özet
Sprint	Kernel	Durum
R10A	Demand Processor (FrameForce → BeamDemandSet)	✅
R10B	Pure Md→As Flexure Kernel	✅
R10B2	Flexure Benchmark Suite	✅
R10C	Flexure Limits Engine (rho_min/rho_max)	✅
R10D	Beam Region Flexure Mapping	✅
R11A	Plastic Moment Engine (As → Mpr)	✅
R11B	Capacity Design Ve Engine (Mpr → Ve_capacity)	✅
R12	Shear Reinforcement Design Engine (V → s_required)	✅
R13'e (Verification Layer Split) hazırız.
