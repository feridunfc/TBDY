# Typed ETABS Gateway

Reserved for the future production ETABS gateway.

Phase-0 intentionally contains no Python implementation.

The future gateway must:

- expose explicit typed read methods,
- isolate COM/STA lifecycle,
- preserve ETABS version and unit provenance,
- represent ambiguity and failures deterministically,
- default to read-only operation,
- reject generic code execution,
- never emit an engineering verdict.

Do not import or activate code from `vendor/etabs-mcp`.