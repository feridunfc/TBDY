# C13.5-P3 ETABS 23 COM Attach Compatibility Boundary

## 1. Sprint purpose

C13.5-P3 isolates the live ETABS COM attach boundary from geometry FeatureSnapshot probing. The goal is not to expand extraction or checking logic; the goal is to make ETABS 23 attachment explicit, bounded, import-safe, and diagnosable.

## 2. Original failure

The observed Windows ETABS 23 smoke failed before FeatureSnapshot generation:

```text
(-2147467262, 'No such interface supported', None, None)
```

No `feature_snapshot.json` was produced. This sprint treats that as a COM attach/interface failure, not as a geometry or engineering failure.

## 3. Local environment reported for the failure

```yaml
python:
  version: 3.12.10
  bitness: 64-bit
  executable: .venv/Scripts/python.exe

com_libraries:
  comtypes: OK
  win32com: OK

etabs_process:
  process_name: ETABS
  version: ETABS 23
  path: C:\Program Files\Computers and Structures\ETABS 23\ETABS.exe
```

## 4. Attach strategy list

The attach boundary is implemented in:

```text
tbdy_engine/features/etabs_com_attach.py
```

It uses a bounded ordered strategy list:

```yaml
strategies:
  - comtypes_get_active_object_etabs_api_object
  - comtypes_create_helper_get_object
  - win32com_get_active_object_etabs_api_object
```

Candidate ProgIDs are also explicit and bounded:

```yaml
candidate_prog_ids:
  - CSI.ETABS.API.ETABSObject
  - CSI.ETABS.API.ETABSObject.1
  - ETABSv1.Helper
```

The attach module does not import `comtypes` or `win32com` at module import time. Optional COM imports occur only inside the live attach function.

## 5. Failure diagnostic contract

If no strategy succeeds, the live CLI writes only these files:

```text
<out>/
  live_geometry_probe_summary.json
  live_geometry_probe_diagnostics.json
  live_geometry_probe_manifest.json
```

It must not write `feature_snapshot.json` on attach failure. If a stale `feature_snapshot.json` exists in the output directory, the failure writer removes it.

The failure summary has this contract:

```json
{
  "status": "FAIL",
  "scope": "LIVE_ETABS_GEOMETRY_FEATURE_SNAPSHOT_PROBE",
  "failure_stage": "COM_ATTACH",
  "feature_snapshot_written": false,
  "diagnostic_count": 1
}
```

The diagnostics JSON contains one top-level diagnostic with a deterministic `attempts` list. Each attempt records:

```yaml
fields:
  - strategy
  - prog_id
  - status
  - message
  - exception_type
  - hresult
```

Raw COM objects are not serialized.

## 6. Success boundary contract

An attach strategy is successful only when:

```yaml
minimum_success_contract:
  - etabs_object is not None
  - sap_model is accessible
```

The attach layer does not fetch model tables, run checks, select load combinations, or compute engineering results. It only returns the attached object boundary to the existing live geometry provider.

## 7. Why this is read-only

The live geometry probe only reads candidate geometry display tables after a successful attach. It does not mutate ETABS, does not run analysis, does not run the check engine, and does not create `CheckResult` objects.

## 8. Why CI does not require ETABS

All C13.5-P3 tests use fake COM clients, fake errors, and source-contract assertions. ETABS, comtypes, and pywin32 are optional live boundary dependencies and are not required for offline acceptance.

## 9. Optional live smoke command

Manual only on Windows with ETABS 23 open:

```powershell
python tools/probe_live_etabs_geometry_snapshot.py --live-etabs --out local_out/c13_5_p3_live_geometry_probe
```

If attach succeeds and `feature_snapshot.json` is produced, the downstream optional product smoke may be run manually:

```powershell
python tools/run_geometry_product_smoke.py --feature-snapshot local_out/c13_5_p3_live_geometry_probe/feature_snapshot.json --out local_out/c13_5_p3_live_geometry_product_smoke
```

Do not claim live smoke PASS unless both commands actually pass on the local Windows ETABS environment.

## 10. Explicitly excluded engineering scope

C13.5-P3 does not add or modify:

```text
engineering checks
check engine behavior
geometry check semantics
force extraction
load combination extraction
rebar extraction
capacity design
PMM
SCWB
drift
modal mass
Excel production input
Streamlit UI
section-name parsing
unit conversion
guessing geometry
CheckResult generation from live probe
CheckEngine execution from live probe
broad ETABS table scanning
```

## 11. Acceptance results

Connector implementation session status:

```yaml
implemented:
  - ETABS COM attach compatibility layer
  - structured attach attempts
  - graceful attach-failure JSON outputs
  - live CLI attach-failure handling
  - C13.5-P3 fake COM tests
  - offline acceptance command count update to 15

not_run_in_connector_session:
  - python -m compileall -q tbdy_engine tools tests
  - python tbdy_engine/tools/validate_contract_constitution.py
  - python tools/audit_legacy_boundary.py
  - pytest -q tests/c13_4_p1
  - pytest -q tests/c13_4_p2
  - pytest -q tests/c13_4_p3
  - pytest -q tests/c13_4_p4
  - pytest -q tests/c13_4_p5
  - pytest -q tests/c13_4_p6
  - pytest -q tests/c13_4_p7
  - pytest -q tests/c13_4_p8
  - pytest -q tests/c13_4_p9
  - pytest -q tests/c13_4_p10
  - pytest -q tests/c13_5_p1
  - pytest -q tests/c13_5_p2
  - pytest -q tests/c13_5_p3
  - python tools/run_offline_product_acceptance.py --out local_out/c13_5_p3_offline_acceptance
```
