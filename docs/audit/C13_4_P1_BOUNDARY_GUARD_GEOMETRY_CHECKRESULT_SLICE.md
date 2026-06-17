# C13.4-P1 Boundary Guard + Canonical Geometry CheckResult Slice

## Sprint goal

C13.4-P1 introduces the first tiny constitution-safe canonical `CheckResult` slice. The slice is geometry-only and intentionally narrow.

The preserved architecture is:

```text
ETABS / Provider
-> FeatureSnapshot
-> CheckInput / coverage readiness
-> CheckEngine
-> Canonical CheckResult
-> Report artifact
```

This sprint does not broaden the engineering engine.

## Architecture boundaries

Feature layer remains observed evidence only. `FeatureSnapshot` does not contain check results, final decisions, utilization ratios, capacity ratios, flexure results, shear results, or detailing decisions.

`MinimalCheckEngine` consumes only:

- `FeatureSnapshot`
- `CoverageRow`
- catalog/check definition data
- canonical `CheckResult`

`MinimalCheckEngine` does not import ETABS providers, ETABS table fetchers, feature resolver internals, Excel readers, legacy beam/design modules, old runtime, runner_v2, archx, or old check adapters.

## Legacy beam policy

Legacy beam/design/runtime code may remain in the repository as reference-only code.

It must not be imported or executed by the new pipeline.

The legacy beam engine is reference-only.

## Allowed checks

C13.4-P1 allows only these catalog ids:

- `column_geometry_min_dimension`
- `beam_geometry_min_width`
- `beam_geometry_min_depth`
- `beam_depth_width_ratio`

The engine uses catalog ids only. The old `column_min_dimension` id is not used.

## Geometry behavior

Implemented behavior:

- `column_geometry_min_dimension`: evaluates `min(column_width_mm, column_depth_mm)` against `300 mm`.
- `beam_geometry_min_width`: evaluates `beam_width_mm` against `250 mm`.
- `beam_geometry_min_depth`: evaluates `beam_depth_mm` against `300 mm`.
- `beam_depth_width_ratio`: evaluates `beam_depth_mm / beam_width_mm` against maximum `3.5`.

Missing feature data returns `NO_DATA`. A zero beam width for depth/width ratio also returns `NO_DATA`.

## Forbidden checks

C13.4-P1 intentionally excludes:

- beam flexure
- beam shear
- rebar adequacy
- capacity design
- force envelope selection
- governing load combo selection
- SCWB
- column PMM
- story drift compliance
- final building compliance verdict

This is not full TBDY compliance. This is a geometry-only canonical `CheckResult` slice.

Beam flexure, shear, rebar adequacy, force envelope, capacity design, SCWB, and PMM are intentionally excluded.

## Status semantics

Status semantics are explicit:

- `OK`: check executed and requirement satisfied.
- `FAIL`: check executed and requirement not satisfied.
- `WARNING`: check executed with partial/screening/uncertain data.
- `NO_DATA`: required feature is missing or unresolved.
- `BLOCKED`: check is not allowed to execute because required policy/contract is not ready.
- `OUT_OF_SCOPE`: element/source exists but this product slice intentionally does not evaluate it.

`NO_DATA`, `BLOCKED`, and `OUT_OF_SCOPE` force `EvaluationLevel.NO_DATA`.

## Files touched

- `tbdy_engine/checks/result.py`
- `tbdy_engine/checks/engine.py`
- `tools/audit_legacy_boundary.py`
- `tests/c13_4_p1/test_legacy_boundary_guard.py`
- `tests/c13_4_p1/test_canonical_check_result_statuses.py`
- `tests/c13_4_p1/test_engine_catalog_check_id_alignment.py`
- `tests/c13_4_p1/test_geometry_checkresult_slice.py`
- `tests/c13_4_p1/test_missing_blocked_out_of_scope_semantics.py`
- `docs/audit/C13_4_P1_BOUNDARY_GUARD_GEOMETRY_CHECKRESULT_SLICE.md`

## Test commands

```bash
python -m compileall -q tbdy_engine tools tests
python tbdy_engine/tools/validate_contract_constitution.py
python tools/audit_legacy_boundary.py
pytest -q tests/c13_4_p1
```

## Acceptance results

Acceptance must be produced from a local run. The implementation provides the commands and audit output path, but this document does not claim local command success until those commands are run.

Boundary audit output path:

```text
local_out/c13_4_p1_boundary_guard/legacy_boundary_audit_report.json
```

## Known limitations

- No beam flexure.
- No beam shear.
- No rebar adequacy.
- No capacity design.
- No force envelope or governing combo selection.
- No PMM.
- No SCWB.
- No story drift compliance.
- No final building compliance verdict.
- No Streamlit UI.
- No Excel production path.

## Next sprint recommendation

Next sprint should not jump to full design. The next safe step is a small CheckInput contract layer or a second small geometry slice with explicit coverage/readiness promotion rules, still without legacy beam/design execution.
