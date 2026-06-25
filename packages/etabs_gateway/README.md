# Typed ETABS Gateway

Phase-1.2 Windows COM apartment binding is active.

## Current implementation

- immutable typed gateway contracts,
- typed deterministic gateway errors,
- pure model-context normalization,
- pure diagnostic event construction,
- a single-thread task worker,
- deterministic worker startup, timeout, failure, and shutdown behavior,
- lazy Windows COM apartment initialization,
- same-thread COM finalization enforcement,
- offline fake-runtime lifecycle and boundary tests.

## Current runtime status

- Windows COM apartment lifecycle: implemented,
- eager platform dependency import: forbidden,
- ETABS attachment: none,
- ETABS application or `SapModel` acquisition: none,
- ETABS runtime wiring: none,
- model write operations: forbidden,
- generic code execution: forbidden,
- engineering verdict generation: forbidden.

`WindowsCOMApartment` loads `pythoncom` only when initialization is requested.
It calls `CoInitializeEx(COINIT_APARTMENTTHREADED)` and requires
`CoUninitialize()` to execute on the same owner thread. It is designed to be
injected into `DedicatedSTAWorker`; it does not attach to ETABS.

The production gateway must remain read-only by default, preserve ETABS version
and unit provenance, and never import or activate code from
`vendor/etabs-mcp`.
