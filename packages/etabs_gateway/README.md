# Typed ETABS Gateway

Phase-1.3 read-only running-instance attachment is active.

## Current implementation

- immutable typed gateway contracts,
- typed deterministic gateway errors,
- dedicated single-thread worker infrastructure,
- lazy Windows COM apartment lifecycle binding,
- lazy `win32com.client` active-object discovery,
- read-only attachment to an already-running ETABS application,
- private application and model API reference ownership,
- immutable attachment results with no raw COM object exposure,
- deterministic same-thread detachment,
- offline fake-runtime lifecycle and boundary tests.

## Current runtime status

- Windows COM apartment lifecycle: implemented,
- running ETABS active-object discovery: implemented,
- ETABS application attachment: implemented, not live-verified in this phase,
- model API acquisition: implemented, not live-verified in this phase,
- ETABS version/model/unit reads: none,
- table or result extraction: none,
- model write operations: forbidden,
- generic code execution: forbidden,
- engineering verdict generation: forbidden.

`ReadOnlyETABSConnection` loads `win32com.client` only during attachment.
`GetActiveObject` and model API acquisition execute exclusively through
`DedicatedSTAWorker`. Raw application and model API references remain private;
the public result is the immutable `ETABSAttachment` contract.

Process-ID-specific selection is explicitly rejected because the active-object
boundary cannot yet prove exact process identity.

The production gateway must remain read-only by default and must never import
or activate code from `vendor/etabs-mcp`.
