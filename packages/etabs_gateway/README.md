# Typed ETABS Gateway

Phase-1.4 read-only application/model/unit context extraction is active.

## Current implementation

- immutable typed gateway contracts,
- dedicated single-thread worker infrastructure,
- lazy Windows COM apartment lifecycle binding,
- lazy read-only attachment to a running ETABS application,
- private application and model API reference ownership,
- ETABS version read,
- model filename read,
- model lock-state read,
- present-unit code read,
- immutable gateway/application/model/unit context,
- typed per-operation read failures,
- offline fake-runtime lifecycle and boundary tests.

## Current runtime status

- Windows COM apartment lifecycle: implemented,
- running ETABS attachment: implemented, not live-verified in this phase,
- application/model/unit context reads: implemented, not live-verified,
- exact process identity: not implemented,
- table or result extraction: none,
- model write operations: forbidden,
- generic code execution: forbidden,
- FeatureSnapshot and CheckEngine integration: none,
- engineering verdict generation: forbidden.

`ReadOnlyETABSConnection.read_context()` executes all metadata reads through
`DedicatedSTAWorker`. Parsing and typed error mapping live in
`context_reader.py`; raw COM references remain private to the connection.

When `GetModelFilename(True)` returns an empty value, the gateway emits an
explicit no-open-model context and does not attempt lock-state or unit reads.
No human-readable unit-name mapping is guessed in this phase; the authoritative
raw present-unit code is preserved.

The production gateway must remain read-only by default and must never import
or activate code from `vendor/etabs-mcp`.
