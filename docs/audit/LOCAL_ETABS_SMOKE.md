# Local ETABS Smoke Audit

This smoke script is **manual/local only**. CI does not run ETABS and the worker environment cannot validate live ETABS behavior.

The script is opt-in and only attaches to an already-open ETABS model. It never starts a model, never modifies the model, never runs design, never executes checks, never emits OK/FAIL, and never emits CheckResult objects.

Run locally on a Windows machine with ETABS open:

```bash
python tools/smoke_etabs_live_provider.py --out local_out/etabs_smoke
```

Expected outputs:

```text
local_out/etabs_smoke/etabs_table_inventory.json
local_out/etabs_smoke/table_registry_match_summary.json
local_out/etabs_smoke/missing_expected_tables.json
```

Exit behavior:

- exits `0` when ETABS attach succeeds and inventory files are written, even if some expected tables are missing;
- exits `0` with clear diagnostic JSON when ETABS/comtypes is unavailable or no open model can be attached;
- exits nonzero only for unexpected script/runtime errors.

Paste the three JSON outputs back into the audit workflow for contract-fit review.

## C5.3 Deep-Fit Outputs

C5.3 extends the manual smoke to write contract-fit diagnostics in addition to the basic table inventory. These files are audit-only and do not execute checks, compute ratios, emit OK/FAIL, or produce CheckResult payloads.

Expected local outputs:

- `etabs_table_inventory.json`
- `table_registry_match_summary.json`
- `missing_expected_tables.json`
- `table_contract_fit_report.json`
- `feature_source_fit_report.json`
- `combo_family_fit_report.json`
- `element_identity_fit_report.json`
- `missing_required_sources.json`

The smoke remains manual/local only. CI does not run ETABS. If ETABS or COM attachment is unavailable, the script writes diagnostic JSON and exits gracefully.

## C5.4 Header/Sample Audit Extension

C5.4 adds a header/sample audit step for matched canonical tables. The script still remains manual/local only and never modifies the ETABS model, never starts a design run, never executes checks, and never emits CheckResult or OK/FAIL status values.

When the local CSI API exposes `DatabaseTables.GetTableForDisplayArray`, the smoke attempts to read the table headers and a small redacted row sample for each available ETABS table. These rows are used only to prove table-header, feature-source, identity-column, and combo-family fit. If the local ETABS API wrapper cannot return headers/rows without the display-table call, the script writes an explicit limitation diagnostic and leaves column-fit reports partial.

Additional output:

```text
local_out/etabs_smoke/table_headers_report.json
```

The deep-fit reports are then updated from the fetched headers/sample rows:

- `table_contract_fit_report.json` includes `matched_columns` and `missing_columns`.
- `feature_source_fit_report.json` includes `matched_column` where field aliases match.
- `element_identity_fit_report.json` includes `available_identity_columns` and identity mappings.
- `combo_family_fit_report.json` is populated by scanning combo/output-case/design-combo columns in the redacted sample rows.

Optional row sample limit:

```bash
python tools/smoke_etabs_live_provider.py --out local_out/etabs_smoke --sample-rows 3
```

If ETABS tables include design status text such as OK/FAIL, the sample writer redacts those literal values before writing JSON so the smoke remains an audit/data-fit artifact, not a check result artifact.
