# Typed ETABS Gateway

Phase-1 contract foundation is active.

## Current implementation

- immutable typed gateway contracts,
- typed deterministic gateway errors,
- pure model-context normalization,
- pure diagnostic event construction,
- offline contract and boundary tests.

## Current runtime status

- COM implementation: none,
- STA worker implementation: none,
- ETABS runtime wiring: none,
- model write operations: forbidden,
- generic code execution: forbidden,
- engineering verdict generation: forbidden.

The production gateway must remain read-only by default, isolate all future
COM activity on a dedicated STA worker, preserve ETABS version and unit
provenance, and never import or activate code from `vendor/etabs-mcp`.
