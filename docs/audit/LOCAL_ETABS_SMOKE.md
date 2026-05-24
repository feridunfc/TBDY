# Local ETABS Smoke Gate

## Purpose

- Optional local release gate for Windows machines with ETABS installed and a model open.
- Not part of default CI or default pytest.
- Converts the manually verified local ETABS smoke into an opt-in pytest marker workflow.

## How to run

```powershell
$env:PYTHONPATH = (Get-Location).Path
pytest -q tests -m etabs_smoke
```

The default test suite remains independent from ETABS:

```powershell
$env:PYTHONPATH = (Get-Location).Path
pytest -q tests
```

## Known validated environment

- ETABS 23.2.0
- Model: `C:\tmp\B-BLOK_Revised.EDB`
- Available tables: 194

## Manual smoke result summary

- Story Definitions: PASS, shape (4, 8)
- Concrete Column Design Summary - TS 500-2000(R2018): PASS, shape (1090, 19)
- Concrete Beam Design Summary - TS 500-2000(R2018): PASS, shape (19073, 23)
- Concrete Column PMM Envelope - TS 500-2000(R2018): PASS, shape (520, 11)
- Concrete Joint Design Summary - TS 500-2000(R2018): PASS, shape (260, 15)

## Known optional empty tables

- Concrete Column Shear Envelope - TS 500-2000(R2018)
- Concrete Beam Flexure Envelope - TS 500-2000(R2018)
- Concrete Beam Shear Envelope - TS 500-2000(R2018)
- Concrete Joint Envelope - TS 500-2000(R2018)

## Rules

- ETABS must be open.
- A model must be loaded.
- Tests are read-only.
- Tests do not run analysis/design.
- Tests may skip if ETABS is unavailable.
- Empty optional envelope tables are not a failure.

## Test selection behavior

The ETABS smoke tests are marked with `pytest.mark.etabs_smoke`.

- `pytest -q tests` does not require ETABS.
- `pytest -q tests -m etabs_smoke` runs the local ETABS smoke gate.
- If ETABS is unavailable during the smoke run, the tests skip with the connection message.
