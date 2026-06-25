# Typed ETABS Gateway

Phase-1.5 deterministic gateway-session orchestration is active.

## Current implementation

- immutable typed gateway contracts,
- dedicated single-thread worker infrastructure,
- lazy Windows COM apartment lifecycle binding,
- lazy read-only attachment to a running ETABS application,
- read-only application/model/unit context extraction,
- one deterministic session owner for apartment, worker, and connection,
- startup rollback after attach or context-read failure,
- idempotent shutdown and typed close failures,
- immutable health and diagnostic snapshots,
- offline fake-runtime lifecycle and failure-path tests.

## Current runtime status

- Windows COM apartment lifecycle: implemented,
- running ETABS attachment: implemented, not live-verified,
- application/model/unit context reads: implemented, not live-verified,
- gateway session lifecycle: implemented and offline-verified,
- exact process identity: not implemented,
- table or result extraction: none,
- model write operations: forbidden,
- generic code execution: forbidden,
- FeatureSnapshot and CheckEngine integration: none,
- engineering verdict generation: forbidden.

`ETABSGatewaySession` is the sole lifecycle owner for
`WindowsCOMApartment`, `DedicatedSTAWorker`, and
`ReadOnlyETABSConnection`. Construction remains offline-safe and does not
load platform modules. `start()` performs attach plus initial context read;
any failure triggers best-effort component cleanup before the typed error is
re-raised.

The session never exposes raw COM references. Public state is limited to
immutable context, health, and diagnostic contracts.

The production gateway must remain read-only by default and must never import
or activate code from `vendor/etabs-mcp`.
