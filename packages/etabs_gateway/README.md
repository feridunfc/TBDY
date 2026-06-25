# Typed ETABS Gateway

Phase-1.1 dedicated worker infrastructure is active.

## Current implementation

- immutable typed gateway contracts,
- typed deterministic gateway errors,
- pure model-context normalization,
- pure diagnostic event construction,
- a single-thread task worker,
- injectable apartment initializer and finalizer callbacks,
- deterministic startup, timeout, failure, and shutdown behavior,
- offline contract and architecture boundary tests.

## Current runtime status

- platform COM binding: none,
- ETABS attachment: none,
- ETABS runtime wiring: none,
- model write operations: forbidden,
- generic code execution: forbidden,
- engineering verdict generation: forbidden.

The worker owns exactly one thread and serializes all submitted operations on
that thread. A running-task timeout poisons the worker so execution cannot
silently continue as if the operation had completed successfully.

The production gateway must remain read-only by default, preserve ETABS version
and unit provenance, and never import or activate code from
`vendor/etabs-mcp`.
