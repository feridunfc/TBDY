# C13.4-P5 Geometry Markdown Report Contract

## 1. Sprint purpose

C13.4-P5 adds a deterministic Markdown report generated from C13.4-P4 JSON artifacts. The report is human-readable and report-only. It does not execute checks, read ETABS, read Excel, or introduce engineering calculations.

The executable chain remains:

```text
FeatureSnapshot-like JSON
→ P3 geometry adapter
→ MinimalCheckEngine
→ CheckResult
→ P4 JSON artifacts
→ P5 Markdown report
```

## 2. Report boundary

The report module is:

```text
tbdy_engine/reports/geometry_markdown_report.py
```

The CLI wrapper is:

```text
tools/render_geometry_report.py
```

The report reads only P4 artifact files and writes only `geometry_report.md`.

## 3. Input artifact contract

The renderer requires exactly these input files in the artifact directory:

```text
check_results.json
adapter_diagnostics.json
run_summary.json
run_manifest.json
```

All four files are mandatory. If any file is missing, the module raises a clear exception and the CLI returns nonzero.

The renderer does not accept:

- Excel files;
- ETABS live sources;
- table registry fetches;
- live provider output;
- hidden network data.

## 4. Output report contract

The output file is:

```text
geometry_report.md
```

It starts with:

```markdown
# TBDY Geometry Vertical Slice Report — C13.4-P5
```

The file ends with a newline and is written using UTF-8 encoding.

## 5. Section/table contract

The report contains exactly nine sections in this order:

1. Executive Summary
   - Table name: `executive_summary`
2. Geometry Check Summary
   - Table name: `geometry_check_summary`
3. Adapter Diagnostics
   - Table name: `adapter_diagnostics`
4. Beam Geometry Detail
   - Table name: `beam_geometry_detail`
5. Column Geometry Detail
   - Table name: `column_geometry_detail`
6. Evidence Trace Detail
   - Table name: `evidence_trace_detail`
7. Artifact Manifest
   - Table name: `artifact_manifest`
8. Guardrails
   - Table name: `guardrails`
9. Boundary Notes
   - Table name: `boundary_notes`

Each section uses deterministic Markdown pipe tables with fixed column order.

## 6. Determinism policy

The renderer is deterministic:

- required artifacts are read from fixed file names;
- section order is fixed;
- table column order is fixed;
- executive summary row order is fixed;
- grouped check rows are sorted by `check_id`;
- beam and column details are sorted by component and check id;
- evidence rows are sorted by component, check id, and evidence index;
- Markdown tables escape pipe characters and replace newlines inside cells;
- lists and tuples are joined by `, `;
- dictionary cells are JSON-encoded with `sort_keys=True`;
- no new numeric rounding is introduced.

## 7. Missing artifact behavior

Missing artifacts are hard input errors for the report layer.

The module raises `FileNotFoundError` with the missing artifact path. The CLI prints a short error and exits nonzero. Partial reports are not emitted for missing required artifacts.

## 8. Adapter diagnostics behavior

Adapter diagnostics are read from `adapter_diagnostics.json` and rendered in the Adapter Diagnostics table.

If diagnostics are empty, the report emits a deterministic `NONE` row:

```text
check_id: -
component_id: -
component_type: -
status: NONE
reason: No adapter diagnostics
```

If an adapter diagnostic contains `OK` or `FAIL`, the report raises `ValueError`. Engineering decision statuses belong only to `CheckResult` payloads, not adapter diagnostics.

## 9. Evidence traceability policy

Evidence is flattened from `CheckResult.evidence` into the Evidence Trace Detail table. The report preserves these serialized fields:

- `evidence_status`
- `source_table`
- `actual_table_name`
- `source_column`
- `raw_value`
- `normalized_value`
- `unit`
- `resolver`

The report does not recompute evidence and does not replace it with summaries.

## 10. Guardrails

The report includes static guardrails that declare the P5 boundary:

| guardrail | value |
| --- | --- |
| json_artifact_input_used | True |
| etabs_live_fetching_used | False |
| excel_production_path_used | False |
| streamlit_ui_used | False |
| legacy_runtime_used | False |
| rebar_flexure_shear_capacity_unlocked | False |
| modal_mass_unlocked | False |
| report_only_no_check_execution | True |
| no_new_engineering_logic | True |

These rows are report contract guardrails. They are not an ETABS or runtime detection mechanism.

## 11. Explicitly excluded C13.1 sections

P5 intentionally does not include these C13.1-style sections:

- `modal_mass_full_table`
- `modal_mass_final_verdict`
- live ETABS beam section aggregation tables
- live ETABS unsupported beam section tables
- live ETABS column section aggregation tables
- live ETABS unsupported column section tables
- `column_geometry_min_area`
- `column_geometry_aspect_ratio`

P5 reports only what exists in P4 artifacts.

## 12. Legacy boundary statement

The report module must not import:

- `tbdy_engine.design`
- `tbdy_engine.adapters.check_adapter`
- `tbdy_engine.engine.topology`
- `tbdy_engine.runtime`
- `tbdy_engine.runner_v2`
- `tbdy_engine.archx`

The legacy boundary audit now scans:

```text
tbdy_engine/reports/*.py
```

P5 tests also inspect `tools/render_geometry_report.py` for forbidden legacy imports.

## 13. Acceptance outputs

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
python tools/run_geometry_vertical_slice.py --feature-snapshot tests/fixtures/c13_4_p4/geometry_feature_snapshots.json --out local_out/c13_4_p5_source_artifacts
python tools/render_geometry_report.py --artifact-dir local_out/c13_4_p5_source_artifacts --out local_out/c13_4_p5_geometry_report/geometry_report.md
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
| P4 runner smoke command | NOT_RUN_IN_CONNECTOR_SESSION |
| P5 report CLI smoke command | NOT_RUN_IN_CONNECTOR_SESSION |
