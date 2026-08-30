# ETABS-OAPI-LAYER-1 — Phase-0 Exact-Census Amendments

Frozen base: `74d5b6083afed75e44b832336c31755aee482daa`

Supervisor dispositions:

- `OPTION B ACCEPTED` — attach implementation census correction.
- `EXACT_CENSUS_CONFLICT ACCEPTED` — provider-ownership accounting/classification correction.

These amendments correct exact-base accounting errors only. They do not change the frozen architecture, write boundary, or semantic ownership and do not broaden the sprint.

## Amendment A — attach metric

```text
ATTACH_IMPLEMENTATION_COUNT_BEFORE = 3
ATTACH_IMPLEMENTATION_COUNT_TARGET = 1
```

The three exact-base attach implementations are:

1. `tbdy_engine/features/etabs_com_attach.py` — PID-aware `Helper.GetObjectProcess` plus bounded compatibility fallback.
2. `tbdy_engine/etabs/connection.py` — legacy independent comtypes attach implementation.
3. `packages/etabs_gateway/src/etabs_gateway/connection.py` — existing STA-owned/private-COM `GetActiveObject` implementation.

The gateway implementation is the target owner with incomplete attach mechanics. It is not a legacy implementation to replace.

## Amendment B — provider-local CSI ABI-owner metric

Definition used by the supervisor disposition:

```text
PROVIDER_LOCAL_ABI_OWNER
=
a provider-layer production module that directly invokes
a CSI/OAPI method and owns interpretation/validation of that
method's raw positional/tuple ABI
```

A provider does not qualify merely because it consumes a factual DTO, mentions an OAPI method in source refs/docstrings, or performs semantic promotion using already-decoded evidence.

Bounded exact-frozen-base verification of the affected/remaining owner list:

| FILE | SYMBOL | DIRECT CSI OBJECT | DIRECT CSI METHOD | RAW RETURN DECODED HERE? | QUALIFIES AS PROVIDER_LOCAL_ABI_OWNER? |
| --- | --- | --- | --- | --- | --- |
| `tbdy_engine/providers/etabs_display_table_fetcher.py` | `fetch_display_table` | `DatabaseTables` | `GetTableForDisplayArray` | YES — signature probing, raw/mutated-argument normalization and parser/capture interpretation are owned by this provider boundary | YES |
| `tbdy_engine/providers/etabs_column_endpoint_restraint_provider.py` | `capture_etabs_point_restraint` / `_decode_get_restraint` | `PointObj` | `GetRestraint` | YES | YES |
| `tbdy_engine/providers/etabs_column_rebar_intent_provider.py` | `capture_etabs_column_rebar_intent` / `_api_sequence` | `PropFrame` | `GetRebarColumn` | YES | YES |
| `tbdy_engine/providers/etabs_combo_definition_provider.py` | `_get_combo_type`, `_get_case_list` | `RespCombo` | `GetTypeCombo`, `GetCaseList` | YES | YES |
| `tbdy_engine/providers/etabs_concrete_column_design_result_provider.py` | `capture_concrete_column_design_results` / `decode_summary_results_column` | `SapModel.DesignConcrete` | `GetSummaryResultsColumn` | YES — exact 14-member live-observed Python COM contract | YES |
| `tbdy_engine/providers/etabs_load_pattern_catalog_provider.py` | `capture_etabs_load_pattern_catalog` | `LoadPatterns` | `GetNameList` | YES — count/name-array/return-code validation | YES |
| `tbdy_engine/providers/etabs_static_linear_case_provider.py` | `capture_etabs_load_pattern_type`, `capture_etabs_static_linear_case` | `LoadPatterns`, `LoadCases.StaticLinear` | `GetLoadType`, `GetLoads` | YES | YES |
| `tbdy_engine/providers/etabs_ts500_stability_action_provider.py` | `promote_etabs_static_cases_to_ts500_stability_actions` | NONE | NONE | NO — consumes `EtabsStaticLinearCaseEvidence` | NO |
| `tbdy_engine/providers/etabs_concrete_design_section_provider.py` | `capture_concrete_column_design_sections` | `DesignConcrete` | `GetDesignSection` | NO — raw two-slot ABI is decoded by `tbdy_engine.features.column_concrete_design_evidence.decode_get_design_section` | NO under the strict provider-local-owner definition |
| `tbdy_engine/providers/etabs_concrete_design_combo_selection_probe.py` | `acquire_actual_concrete_design_combo_selection` | NONE directly | NONE directly | NO — delegates to shared display-table fetcher | NO |
| `tbdy_engine/providers/etabs_auto_seismic_direction_provider.py` | `capture_etabs_auto_seismic_direction_evidence` | NONE directly | NONE directly | NO — delegates to shared display-table fetcher | NO |

Therefore the corrected scalar is:

```text
PROVIDER_LOCAL_ABI_OWNER_COUNT_BEFORE = 7
```

This value is an exact bounded correction, not arithmetic preservation of the revoked value `8`.

### TS500 semantic ownership invariant

Exact frozen-base and current-candidate inspection preserve:

```text
etabs_static_linear_case_provider
= factual CSI acquisition / raw ABI owner before migration

etabs_ts500_stability_action_provider
= semantic promotion owner
```

The following policy remains outside `tbdy_engine.etabs.oapi`:

```text
ETABS_PATTERN_TYPE_TO_TS500_ACTION
```

Target flow remains:

```text
CSI ETABS
   ↓
oapi.load_definitions
   ↓
typed factual static-linear/load-pattern evidence
   ↓
etabs_ts500_stability_action_provider
   ↓
reviewed TS500 semantic promotion
   ↓
stability engineering consumers
```

## Other accepted Phase-0 metrics

```text
DIRECT_RAW_OAPI_PRODUCTION_CALLSITE_COUNT = 29
DATABASETABLES_RAW_ACCESS_COUNT           = 9 files
RESULTS_SETUP_RAW_ACCESS_COUNT            = 1
RunAnalysis production callsites          = 0
StartDesign production callsites          = 0
production SetPresentUnits callers        = 0
```

These values are not changed by the two accounting amendments above.

## Governance after the accounting corrections

A proven clerical census error may be recorded as `CENSUS_AMENDMENT` and implementation may continue when all of the following remain unchanged:

```text
architecture direction
write boundary
semantic owner
required subsystem/layers
```

A material contradiction still stops as `ARCHITECTURE_CONFLICT`, including a different canonical owner, new semantic authority, required write outside the approved boundary, missing required layer, contradictory raw-capability architecture, mutation requirement, or new identity/provenance architecture.

## Frozen target ownership

```text
PRODUCT / APPLICATION / DOMAINS
              |
              v
      SEMANTIC PROVIDERS
              |
              v
      tbdy_engine.etabs.oapi
              |
              v
      tbdy_engine.etabs.safety
              |
              v
      packages/etabs_gateway
              |
              v
          CSI ETABS
```

Final attach ownership:

```text
packages/etabs_gateway
= SOLE production COM / STA / session / attach owner
```

Migration target:

- migrate the proven PID-aware mechanics from `features/etabs_com_attach.py` into the existing gateway owner;
- preserve the gateway's `DedicatedSTAWorker`, private `_application`, private `_model_api`, owning-thread access, and owning-thread detach/release;
- make `features/etabs_com_attach.py` compatibility-only if legacy callers still require its public DTO/functions;
- remove independent production attach mechanics from `tbdy_engine/etabs/connection.py` after negative-reachability proof;
- never expose raw `SapModel` publicly from the gateway;
- allow low-level bounded execution only to `tbdy_engine.etabs.safety` and `tbdy_engine.etabs.oapi`;
- migrate raw factual CSI invocation/ABI downward without moving semantic TS500 policy into OAPI.

## Validation state

This amendment does not claim local pytest, compile, broad-suite, delta, hygiene, or live ETABS execution. Those gates remain mandatory before supervisor PR authorization. In an environment without a complete exact checkout, implementation may reach only `READY_FOR_OFFLINE_VALIDATION`.
