# C13.2-P0 Probe Acceptance Patch

This patch hardens `tools/probe_live_contract_sources.py` before any C13.2 contract/schema expansion.

## Acceptance fixes included

1. `tools/probe_live_contract_sources.py` starts directly with `#!/usr/bin/env python`.
2. Canonical path is kept: `tools/probe_live_contract_sources.py`.
3. Offline tests live under `tests/c13_2_p0/test_c13_2_p0_live_contract_source_probe.py`.
4. Tests import with `from tools import probe_live_contract_sources as probe`.
5. Probe profile validation happens before ETABS connection. Invalid profile references return exit code `2`, write `connection_report.json`, and do not connect ETABS.
6. Missing profile families are now defined: `concrete_material_properties`, `rebar_material_properties`, and `wall_section_properties`.
7. Expected header validation is alias-aware for `DesignSect/Design Section`, `AnalysisSect/Analysis Section`, `Type/Design Type`, `t2/Width`, `t3/Depth`, `OutputCase/Output Case`, `MaxDrift/Max Drift`, and `AvgDrift/Avg Drift`.
8. `probe_summary.json` includes expanded acceptance fields and always reports `safe_to_implement_checks_now: false`.
9. Default `--probe-profile current_product` fetches only:
   - `Frame Assignments - Summary`
   - `Frame Section Property Definitions - Concrete Rectangular`
   - `Modal Participating Mass Ratios`
10. No catalogs, schemas, FeatureResolver, CheckEngine, or product checks are edited.

## First live command

```powershell
python tools/probe_live_contract_sources.py `
  --out local_out/c13_2_p0_current_product_probe `
  --live-etabs `
  --probe-profile current_product `
  --preferred-output-case Crack_SeisY_UpSoil `
  --max-sample-rows 20
```

The first live command must fetch exactly the three current-product exact tables listed above. If it fetches more, reject the patch.
