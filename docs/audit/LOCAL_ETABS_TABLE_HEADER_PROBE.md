# Local ETABS Table Header Probe

This probe is **manual/local only**. It is not run in CI and does not require ETABS in the worker/test environment.

The worker environment cannot validate live ETABS behavior. Run this on a Windows machine where ETABS is already open with the target model loaded, then share the JSON outputs for the next audit sprint.

## Safety boundaries

The probe:

- attaches only to an already-open ETABS instance;
- never starts ETABS;
- never creates or modifies a model;
- never runs design;
- never executes checks;
- never emits `CheckResult`;
- never emits `OK` / `FAIL` statuses;
- never computes engineering ratios;
- dumps only headers, call metadata, and at most a small sample row set.

## Command

```bash
python tools/probe_etabs_table_headers.py --out local_out/etabs_table_probe
```

Optional arguments:

```bash
python tools/probe_etabs_table_headers.py --out local_out/etabs_table_probe --tables story,beam,global --max-rows 3 --raw-debug
```

`--tables` accepts groups (`story`, `beam`, `column`, `wall`, `global`) or exact ETABS display table names. By default it probes the whitelisted structural tables needed for contract-fit auditing.

## Outputs

The probe writes:

```text
local_out/etabs_table_probe/table_headers_report.json
local_out/etabs_table_probe/raw_table_call_debug.json
local_out/etabs_table_probe/column_alias_fit_report.json
local_out/etabs_table_probe/feature_column_fit_report.json
local_out/etabs_table_probe/identity_column_fit_report.json
local_out/etabs_table_probe/combo_column_probe_report.json
```

### `table_headers_report.json`

Per requested table:

- `actual_table_name`
- `canonical_table_key`
- `fetch_status`: `FETCHED`, `EMPTY`, `FAILED`, or `NOT_AVAILABLE`
- `field_keys` / `headers`
- `column_count`
- `row_count_reported`
- `sample_row_count`
- `sample_rows_limited`
- `diagnostics`

### `raw_table_call_debug.json`

Per table:

- `api_method`: `GetTableForDisplayArray`
- `return_code`
- `return_shape_metadata`
- `number_fields`
- `number_records`
- `field_keys_type`
- `table_data_type`
- `table_data_length`
- `parse_strategy_used`
- `parse_error`, if any

### Fit reports

`column_alias_fit_report.json`, `feature_column_fit_report.json`, `identity_column_fit_report.json`, and `combo_column_probe_report.json` are audit diagnostics built from the fetched headers/sample rows plus the current contracts. They do not execute checks.

## Known ETABS API limitation

`GetTableForDisplayArray` signatures differ between ETABS/comtypes versions. If the local API wrapper cannot fetch headers or sample rows for a table, the probe writes a diagnostic and continues to the next table. In that case table-name fit may be proven, but column/header fit remains partial until a successful local probe output is provided.
