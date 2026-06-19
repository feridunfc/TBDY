# C13.4-P9 Offline Product Acceptance Gate

## 1. Sprint purpose

C13.4-P9 adds one deterministic offline acceptance gate for the C13.4 geometry product line. The gate runs the accepted offline verification chain from a single command and writes a structured acceptance report.

The gate runs:

1. Python compileall;
2. Contract Constitution validator;
3. legacy boundary audit;
4. pytest suites C13.4-P1 through C13.4-P8;
5. P8 golden regression CLI;
6. deterministic acceptance report JSON.

## 2. Why this sprint is offline

P9 must run without ETABS. It does not call ETABS, Excel production input, Streamlit, live providers, FeatureResolver, P3 adapter, MinimalCheckEngine, CheckEngine, P4 runner API, P5 renderer API, P6 product smoke API, P7 validator API, or P8 golden regression API directly.

The only execution mechanism is shell-level subprocess commands.

## 3. Why this gate uses shell-level commands

P9 models what a user or CI runner does. It must verify the product from the outside instead of bypassing CLI boundaries or importing internal APIs.

This is intentional:

- it catches broken scripts;
- it binds pytest to the active Python interpreter with `python -m pytest`;
- it validates the real acceptance path;
- it avoids adding another internal product engine.

## 4. Exact command plan

The command plan is fixed and ordered:

```bash
python -m compileall -q tbdy_engine tools tests
python tbdy_engine/tools/validate_contract_constitution.py
python tools/audit_legacy_boundary.py
python -m pytest -q tests/c13_4_p1
python -m pytest -q tests/c13_4_p2
python -m pytest -q tests/c13_4_p3
python -m pytest -q tests/c13_4_p4
python -m pytest -q tests/c13_4_p5
python -m pytest -q tests/c13_4_p6
python -m pytest -q tests/c13_4_p7
python -m pytest -q tests/c13_4_p8
python tools/run_geometry_golden_regression.py --feature-snapshot tests/fixtures/c13_4_p4/geometry_feature_snapshots.json --golden tests/fixtures/c13_4_p8/golden_geometry_product_fingerprint.json --out <output_dir>/golden_regression
```

The implementation uses `sys.executable` by default, or the caller-provided `python_executable`.

## 5. Report JSON contract

P9 writes:

```text
<output_dir>/offline_product_acceptance_report.json
```

Required groups:

- `status`
- `scope`
- `output_dir`
- `command_count`
- `failed_command_count`
- `commands`
- `guardrails`

Each command result includes:

- `name`
- `command`
- `returncode`
- `status`
- `stdout_tail`
- `stderr_tail`

`status` is `OK` only when `failed_command_count == 0`.

## 6. stop_on_failure behavior

Default behavior:

```text
stop_on_failure = false
```

The gate runs all 12 commands and reports every command status.

When `--stop-on-failure` is used, the gate stops immediately after the first failed command. In that case, `command_count` is the number of attempted commands and can be less than 12.

## 7. stdout/stderr tail policy

P9 does not store full stdout or stderr. For each command it stores:

- last 40 non-empty stdout lines;
- last 40 non-empty stderr lines.

This keeps the report bounded and deterministic enough for CI artifacts while preserving useful failure context.

## 8. Determinism policy

The report JSON is deterministic:

- fixed command order;
- fixed command names;
- no timestamps;
- no durations;
- no random IDs;
- bounded stdout/stderr tails;
- JSON uses `indent=2`, `sort_keys=True`, `ensure_ascii=False`, and final newline.

The report may include the selected Python executable and output path because this is an execution report, not a golden fingerprint.

## 9. Legacy boundary statement

The P9 module is:

```text
tbdy_engine/product/offline_acceptance.py
```

It must not import:

- `tbdy_engine.design`
- `tbdy_engine.adapters.check_adapter`
- `tbdy_engine.engine.topology`
- `tbdy_engine.runtime`
- `tbdy_engine.runner_v2`
- `tbdy_engine.archx`

It must also not import:

- `MinimalCheckEngine`
- `build_geometry_check_inputs_from_feature_snapshot`
- `run_geometry_vertical_slice_from_file`
- `render_geometry_markdown_report_from_artifact_dir`
- `run_geometry_product_smoke`
- `validate_geometry_product_bundle`
- `run_geometry_golden_regression`

P9 invokes P8 through the CLI script path only:

```text
tools/run_geometry_golden_regression.py
```

The existing legacy boundary audit scans:

```text
tbdy_engine/product/*.py
```

## 10. Explicitly excluded engineering scope

P9 excludes:

- ETABS live fetching;
- Excel production input;
- Streamlit UI;
- FeatureResolver execution;
- direct P3 adapter execution;
- direct MinimalCheckEngine execution;
- direct CheckEngine execution;
- direct P4 runner execution;
- direct P5 report renderer execution;
- new engineering checks;
- beam flexure;
- beam shear;
- rebar adequacy;
- capacity design;
- governing combo selection;
- force envelope selection;
- SCWB;
- column PMM;
- drift compliance;
- modal mass checks;
- column area checks;
- column aspect ratio checks;
- final building compliance verdict.

## 11. Acceptance outputs

Required commands:

```bash
python -m compileall -q tbdy_engine tools tests
python tbdy_engine/tools/validate_contract_constitution.py
python tools/audit_legacy_boundary.py
pytest -q tests/c13_4_p1
pytest -q tests/c13_4_p2
pytest -q tests/c13_4_p3
pytest -q tests/c13_4_p4
pytest -q tests/c13_4_p5
pytest -q tests/c13_4_p6
pytest -q tests/c13_4_p7
pytest -q tests/c13_4_p8
pytest -q tests/c13_4_p9
python tools/run_offline_product_acceptance.py --out local_out/c13_4_p9_offline_acceptance
```

Connector implementation note: this patch was authored through the GitHub connector. Local acceptance commands were not executed in this session, so no PASS is claimed here.

Current recorded status:

| Command | Status |
| --- | --- |
| `python -m compileall -q tbdy_engine tools tests` | NOT_RUN_IN_CONNECTOR_SESSION |
| `python tbdy_engine/tools/validate_contract_constitution.py` | NOT_RUN_IN_CONNECTOR_SESSION |
| `python tools/audit_legacy_boundary.py` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p1` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p2` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p3` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p4` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p5` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p6` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p7` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p8` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p9` | NOT_RUN_IN_CONNECTOR_SESSION |
| P9 offline acceptance CLI | NOT_RUN_IN_CONNECTOR_SESSION |
