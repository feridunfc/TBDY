# C13.5-P4 Live ETABS Geometry Table Discovery

## 1. Sprint purpose

C13.5-P4 adds a read-only discovery sidecar for live ETABS database tables. The purpose is to inventory visible tables, rank geometry-relevant candidates, fetch a bounded number of candidate schemas, and explain why live geometry snapshots may contain no rows.

## 2. Current live smoke state

The reported C13.5-P3 manual live smoke state is:

```text
python tools/probe_live_etabs_geometry_snapshot.py --live-etabs --out local_out/c13_5_p3_live_geometry_probe

Live geometry probe: OK
FeatureSnapshot: local_out\c13_5_p3_live_geometry_probe\feature_snapshot.json
Snapshots: 0
Diagnostics count: 0
```

Interpretation:

```yaml
ETABS_attach: works
SapModel_boundary: works
FeatureSnapshot_written: true
Snapshots: 0
Diagnostics: 0
next_blocker: live_ETABS_geometry_table_discovery_or_mapping
```

## 3. Why this sprint is table discovery only

This sprint does not modify geometry checks, the check engine, FeatureSnapshot semantics, or product smoke. It only answers what ETABS database tables are visible and whether candidate tables expose explicit width/depth columns.

## 4. Discovery artifacts

The new CLI is:

```powershell
python tools/probe_live_etabs_geometry_tables.py --live-etabs --out local_out/c13_5_p4_live_table_discovery
```

Required outputs:

```text
live_geometry_table_discovery_summary.json
live_geometry_table_inventory.json
live_geometry_table_candidates.json
live_geometry_table_rejections.json
live_geometry_table_discovery_diagnostics.json
live_geometry_table_discovery_manifest.json
```

Optional output, only when explicit width/depth columns are proven:

```text
accepted_geometry_table_mapping.json
```

## 5. Candidate scoring policy

Candidate table discovery uses a bounded keyword list:

```yaml
geometry_table_keywords:
  - frame
  - section
  - property
  - assignment
  - assign
  - column
  - beam
  - dimension
  - object
```

Candidate scores are deterministic. Keyword matches provide the base score. Fetched candidate schemas can add score for explicit width/depth columns and useful identity columns.

Only a bounded number of candidates are fetched. Candidates beyond the cap are recorded with `SKIPPED_BY_CAP`.

## 6. Accepted mapping policy

No accepted mapping is written unless a fetched candidate exposes explicit width/depth source columns. Tables that only expose section/property names remain candidates, but they are not accepted mappings.

If no accepted mapping exists, diagnostics include:

```text
NO_ACCEPTED_GEOMETRY_TABLE_MAPPING
```

This explains why the C13.5-P3 FeatureSnapshot probe can attach successfully but still produce zero snapshots.

## 7. Why section-name parsing is forbidden

Section labels such as `B40x70` or `C40x50` may look like dimensions, but accepting them would introduce derived geometry and parsing assumptions. C13.5-P4 only inventories and maps explicit table columns.

## 8. Why unit conversion is forbidden

The discovery sidecar inventories names and columns. It does not normalize or convert dimensional values. Any later value extraction must preserve observed units and produce diagnostics when unit evidence is missing.

## 9. Why no checks or product smoke run here

The sidecar is separate from:

```text
FeatureSnapshot → CheckInput Adapter → Check Engine → CheckResult → Product Artifacts
```

It does not emit CheckResult, does not call CheckEngine, and does not trigger product smoke.

## 10. Offline acceptance results

Connector implementation session status:

```yaml
implemented:
  - live ETABS geometry table discovery module
  - discovery CLI
  - fake ETABS table inventory fixture
  - discovery contract tests
  - discovery negative scope tests
  - P9 offline acceptance update to include tests/c13_5_p4
  - command count update to 16

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
  - pytest -q tests/c13_5_p4
  - python tools/run_offline_product_acceptance.py --out local_out/c13_5_p4_offline_acceptance
```

Expected local acceptance after validation:

```text
Offline product acceptance: OK
Commands: 16
Failed: 0
```

## 11. Optional live table discovery smoke command

Manual only, not CI:

```powershell
python tools/probe_live_etabs_geometry_tables.py --live-etabs --out local_out/c13_5_p4_live_table_discovery
```

Do not claim live discovery PASS unless this command is actually run and artifacts are inspected.

## 12. Next sprint expectation

The next sprint can use the discovery artifacts to decide whether the blocker is table name matching, column mapping, row extraction, missing explicit dimensions, or missing unit evidence. It must still avoid section-name parsing and geometry guessing.
