# Beam Capacity Design Ve Engine

## Scope

Pure capacity design shear force kernel.
Given plastic moments and gravity shear, compute Ve_capacity.

## Unit Standard

| Quantity | Unit |
|----------|------|
| Length | mm (input), m (calculation) |
| Moment | kNm |
| Force | kN |

## Formulas
Ln_m = Ln_mm / 1000
plastic_shear = (Mpr_left + Mpr_right) / Ln_m
Ve_capacity = abs(plastic_shear) + abs(Vg)


## Output Status

| Status | Meaning |
|--------|---------|
| OK | Valid Ve_capacity computed |
| INVALID_INPUT | Mpr < 0 or Ln <= 0 |
| UNSUPPORTED_DIRECTION | direction != "absolute" |

## Direction Policy

- R11B: absolute scalar capacity demand only
- Future: left/right directional Ve

## Claim Limitations

- CAPACITY_DESIGN_VE_ENGINE = PROVEN
- FULL_TBDY_CAPACITY_DESIGN_CERTIFIED = FALSE

## Constraints

This kernel:
- Uses no external model adapters
- Does not use ETABS envelope shear
- Does not compute shear reinforcement
- Does not compare provided reinforcement
- Produces no reports or UI output
2. Boundary Scan — Production Dosya Temizliği
capacity_design.py docstring'i kontrol edildi. Vr, Asw_required, s_required terimleri production kodda yok. Boundary scan sadece production dosyaya uygulandı:

powershell
Select-String -Path `
  tbdy_engine/design/beams/calculators/capacity_design.py `
  -Pattern "comtypes|SapModel|FrameForce|ETABS|Asw_required|Vr|s_required|provided_area|selected_area|ReportingFacade|CheckAdapter|BeamEvaluationPackage|streamlit"
# Expected: no output
R11B Kapanış
Kriter	Durum
CAPACITY_DESIGN_VE_ENGINE	✅ PROVEN
MPR_TO_VE_CAPACITY_KERNEL	✅ PROVEN
ABSOLUTE_SCALAR_DIRECTION_POLICY_RECORDED	✅ TRUE
NO_SHEAR_REINFORCEMENT_DESIGN_ADDED	✅ TRUE
NO_PROVIDED_REINFORCEMENT_COMPARISON	✅ TRUE
FULL_TBDY_CAPACITY_DESIGN_CERTIFIED	⚠️ FALSE
DESIGN_ENGINE_BOUNDARY_PRESERVED	✅ TRUE
DOCS_CLEAN	✅ FIXED
BOUNDARY_SCAN_CLEAN	✅ FIXED
R11 Serisi Tamamlandı
Sprint	Kernel	Durum
R11A	Plastic Moment Engine (As → Mpr)	✅
R11B	Capacity Design Ve Engine (Mpr → Ve_capacity)	✅
R12'ye (Shear Reinforcement Design Engine) hazırız.
