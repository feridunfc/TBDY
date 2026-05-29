# BEAM_RUNTIME_SMOKE

## Purpose

This document defines the real ETABS smoke entrypoint for the reduced beam runtime path.

This is smoke preparation, not live validation. `REAL_ETABS_VALIDATION` is not proven in CI because CI does not connect to ETABS, does not use COM automation, and does not require Windows, SAP2000, or ETABS installation.

## Prerequisites

- Windows machine with ETABS installed.
- ETABS is open with the target model loaded.
- Python process and ETABS run with compatible privileges.
- `comtypes`, `pandas`, and `openpyxl` are installed in the runtime environment.
- ETABS database tables for concrete beam design summary, flexure envelope, and shear envelope are available in the open model.

## Existing ETABS entrypoints

Connection entrypoints:

```python
from tbdy_engine.etabs.connection import check_etabs_connection, get_sap
```

Table reader entrypoint:

```python
from tbdy_engine.etabs.table_reader import get_table_df
```

Synchronous table access entrypoint:

```python
from tbdy_engine.etabs.table_access import read_etabs_table_on_demand
```

Beam normalizer entrypoints:

```python
from tbdy_engine.etabs.normalizers.beam_design import (
    normalize_beam_design_summary,
    normalize_beam_flexure_envelope,
    normalize_beam_shear_envelope,
    build_beam_context_from_tables,
)
```

Runner entrypoint:

```python
from tbdy_engine.runner_v2 import run_engine_v2
```

## Exact callable sequence for real smoke

No new runner or CLI is introduced. The real smoke should use the existing callables:

```python
from tbdy_engine.etabs.table_access import read_etabs_table_on_demand
from tbdy_engine.etabs.normalizers.beam_design import build_beam_context_from_tables
from tbdy_engine.runner_v2 import run_engine_v2

BEAM_DESIGN_SUMMARY_TABLE = "Concrete Beam Design Summary - TS 500-2000(R2018)"
BEAM_FLEXURE_TABLE = "Concrete Beam Flexure Envelope - TS 500-2000(R2018)"
BEAM_SHEAR_TABLE = "Concrete Beam Shear Envelope - TS 500-2000(R2018)"

design_summary = read_etabs_table_on_demand(BEAM_DESIGN_SUMMARY_TABLE)
flexure = read_etabs_table_on_demand(BEAM_FLEXURE_TABLE)
shear = read_etabs_table_on_demand(BEAM_SHEAR_TABLE)

assert design_summary.has_data
assert flexure.has_data
assert shear.has_data

context = build_beam_context_from_tables(
    {
        "beam_design_summary": design_summary.df,
        "beam_design_summary_source_table": BEAM_DESIGN_SUMMARY_TABLE,
        "beam_flexure_envelope": flexure.df,
        "beam_flexure_envelope_source_table": BEAM_FLEXURE_TABLE,
        "beam_shear_envelope": shear.df,
        "beam_shear_envelope_source_table": BEAM_SHEAR_TABLE,
    }
)

result = run_engine_v2(context, report_dir="reports_out")
```

## Required ETABS state / model assumptions

- The ETABS model is open and unlocked enough for database table reads.
- Present units can be set to kN-m-C by the existing connection layer.
- The model exposes the beam design tables listed above.
- Concrete beam design has been run in ETABS so summary, flexure, and shear envelope tables have rows.
- The beam table rows include enough labels/story data for the normalizer to build `design_metadata.beam_design_summary_rows`.

## Required context shape

`build_beam_context_from_tables(...)` must produce a context with `design_metadata` shaped for `BeamDesignModule.run()`:

```text
design_metadata.beam_design_summary_rows
design_metadata.beam_flexure_grouped
design_metadata.beam_shear_grouped
```

The active beam module consumes that context and emits:

```text
tuple[BeamEvaluationPackage, ...]
```

## Expected runtime path

```text
ETABS
→ table access / table reader
→ beam normalizer
→ context design_metadata
→ BeamDesignModule.run()
→ BeamEvaluationPackage
→ CheckAdapter
→ CheckResult[]
→ ReportingFacade
→ engine_report.json
→ engine_report.xlsx
```

## Expected artifacts

The smoke passes only if these report artifacts are written in the selected report directory:

```text
engine_report.json
engine_report.xlsx
```

## Pass criteria

- ETABS connection succeeds.
- Required beam tables are available and non-empty.
- `build_beam_context_from_tables(...)` produces beam `design_metadata`.
- `run_engine_v2(context, report_dir=...)` returns status `OK` or an explicitly understood partial status with report artifacts present.
- `engine_report.json` exists and contains only `summary` and `checks`.
- JSON checks are canonical `CheckResult` rows.
- `engine_report.xlsx` exists when `openpyxl` is available.
- Excel workbook contains only `Summary` and `Checks` sheets.

## Fail criteria

- ETABS is unavailable or no model is open.
- Required beam tables are unavailable or empty.
- Normalizer cannot produce `design_metadata.beam_design_summary_rows`.
- `run_engine_v2(...)` does not write `engine_report.json`.
- `openpyxl` is available but `engine_report.xlsx` is not written.
- JSON contains runtime/report metadata such as `runtime_bridge`, `report_contract`, `evaluation_errors`, `execution_order`, `cache_stats`, `coverage`, or `distributions`.
- Excel contains `Eval_Skipped`, `Eval_Errors`, or `Report_Contract` sheets.

## Known unproven items

- `REAL_ETABS_VALIDATION` is not proven in CI.
- COM automation is not executed in tests.
- The exact ETABS table names may need confirmation against the installed ETABS version and code/design table naming.
- Live model row content and unit conventions are not validated by this document alone.
- `BEAM_RUNTIME_CLOSURE` is not claimed until live ETABS smoke produces `engine_report.json` and `engine_report.xlsx` from a real model.
