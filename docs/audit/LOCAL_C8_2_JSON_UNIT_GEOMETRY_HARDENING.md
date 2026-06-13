# C8.2 JSON / Unit Context / Geometry Diagnostics Hardening

C8.2 is a narrow patch on C8.1.1. It does not execute CheckEngine, does not emit CheckResult, does not emit OK/FAIL verdicts, and does not mutate ETABS units.

## Changes

- `Path` JSON serialization now uses `Path.as_posix()`.
- Live ETABS `GetPresentUnits` / `GetPresentUnits_2` raw outputs are decoded before unit context can be marked `RESOLVED`.
- Observed raw tuple `[4, 6, 2, 0]` decodes as `force_unit=kN`, `length_unit=m`, `temperature_unit=C`, `return_code=0`.
- Raw table diagnostics are preserved for geometry source tables:
  - table name
  - return code
  - number fields
  - number records
  - fields
  - table data length
  - expected flat length
  - parser status
- Geometry remains conservative: width/depth/length resolve only from real rows or verified provider fixture rows, never from section-name parsing.

## Still forbidden

- CheckEngine execution
- CheckResult output
- OK/FAIL verdicts
- rebar/flexure/shear unlock
- legacy imports
- ETABS unit mutation
