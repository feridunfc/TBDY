# ETABS-OAPI-LAYER-1 — Phase-0 Exact-Census Amendment

Frozen base: `74d5b6083afed75e44b832336c31755aee482daa`

Supervisor disposition: `OPTION B ACCEPTED`

This amendment corrects one accounting error in the previously accepted exact-base census. It does not change the frozen architecture or broaden the sprint.

## Corrected attach metric

```text
ATTACH_IMPLEMENTATION_COUNT_BEFORE = 3
ATTACH_IMPLEMENTATION_COUNT_TARGET = 1
```

The three exact-base attach implementations are:

1. `tbdy_engine/features/etabs_com_attach.py` — PID-aware `Helper.GetObjectProcess` plus bounded compatibility fallback.
2. `tbdy_engine/etabs/connection.py` — legacy independent comtypes attach implementation.
3. `packages/etabs_gateway/src/etabs_gateway/connection.py` — existing STA-owned/private-COM `GetActiveObject` implementation.

The gateway implementation is the target owner with incomplete attach mechanics. It is not a legacy implementation to replace.

## Other accepted Phase-0 metrics remain frozen

```text
DIRECT_RAW_OAPI_PRODUCTION_CALLSITE_COUNT = 29
DATABASETABLES_RAW_ACCESS_COUNT           = 9 files
RESULTS_SETUP_RAW_ACCESS_COUNT            = 1
PROVIDER_LOCAL_ABI_OWNER_COUNT            = 8
RunAnalysis production callsites          = 0
StartDesign production callsites          = 0
production SetPresentUnits callers        = 0
```

No other count is changed by this amendment. A material contradiction discovered later must stop as `EXACT_CENSUS_CONFLICT` rather than being silently reconciled.

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
- allow low-level bounded execution only to `tbdy_engine.etabs.safety` and `tbdy_engine.etabs.oapi`.

## Validation state

This amendment itself does not claim local pytest, compile, broad-suite, delta, hygiene, or live ETABS execution. Those gates remain mandatory before supervisor PR authorization.
