# Typed ETABS Gateway

Phase-1.6 deterministic offline fixture/replay support is active.

## Current implementation

- immutable typed gateway contracts,
- dedicated STA worker and lazy COM apartment lifecycle,
- read-only running-instance attachment,
- application/model/unit context extraction,
- deterministic session orchestration,
- strict canonical JSON fixture schema,
- SHA-256 fixture integrity verification,
- immutable offline replay provider,
- deterministic UTF-8 serialization,
- strict unknown-key, enum, type, and UTC validation,
- offline replay and tamper-detection tests.

## Runtime boundaries

The replay provider never loads COM, attaches to ETABS, reads tables, runs
analysis or design, mutates a model, or exposes raw platform references.
It reconstructs only `ETABSGatewayContext` contracts from validated fixtures.

A fixture is signed over its canonical JSON payload using SHA-256. Unknown
fields are rejected rather than ignored. Timestamps must be explicit UTC
values using the `Z` suffix. Human-readable unit names are not guessed.

Live ETABS behavior remains unverified in this phase. Fixture/replay is for
offline tests, deterministic regression reproduction, and contract validation;
it is not production evidence that a live model satisfies TBDY.
