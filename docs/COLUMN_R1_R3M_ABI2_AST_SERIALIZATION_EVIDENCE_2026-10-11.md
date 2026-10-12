# COLUMN-R1 R3M ABI-2 — Python AST serialization reconciliation

Base HEAD: `a1ec16ec41c332316e2a14f6ac01ad770246a208`.
Base TREE: `998df11699c63c3173796354eaa672554370ca30`.
This closes an external verifier defect; engineering and production gateway code are unchanged.

## Original evidence and authority

Operator-supplied static dependency diagnostic:
`column-r1-r3m-abi2-runtime-diag_20261011_195807_387_0c53b4c6c52d4bdcbfa6f6347faf1746.json`.
Independent whole JSON SHA256: `c4661b69bdaf3133404d44d104917a288f3912f4e362e3dbd0943570b01a5800`.
The supplied SHA sidecar matches exactly, including original filename. Original bytes remain outside Git.

The diagnostic contains the original failed ABI-2 receipt as embedded data, reports
its original JSON SHA256 as `1c4a7bc7a0178139f9b06f5672c5fd09c41b54c3c734e23c0ccf02d31783f1f4`,
and records matching source SHA before/after, session/units/lock and selection.
That original receipt's byte serialization was not separately supplied here; its
reported hash is not presented as a fresh whole-byte verification.
Original FrameObj.GetNameList attempts: **0**. Native return: NOT_OBSERVED.
Native ABI declaration qualified before failure; generated Python wrapper verification failed.
This is an external verifier failure before the native target, not a model/analysis failure.

## Exact root cause

Operator Python: **3.14.0**, executable
`C:\Users\FCY\PyCharmMiscProject\etabs_tbdy\.venv\Scripts\python.exe`.
Distribution metadata reports comtypes **1.4.16**. Its `_memberspec.py` original
byte SHA256 is `bc85a42d1daf6d84b2697c7ab0f56f70689db4e97122e06bee40af15e583ada2`,
identical to the accepted dependency source. The complete observed `_fix_inout_args`
function text is identical to the offline-qualified text.
The distribution version difference did not cause this observed rejection.

The verifier used `ast.dump(..., include_attributes=False)` with default options.
Python 3.12 includes optional empty list fields; Python 3.14 defaults to omitting them.
Consequently identical function source produced different serialization hashes:

| Serialization | SHA256 |
| --- | --- |
| Accepted complete AST | `5c4668efa8f7b15c312153d246bebbb29c8ccbbfc671515ec18bac12aa8f9e01` |
| Observed Python 3.14 default | `26a38b48f60e24f1d367c827d4effc41b7f149f97a056ee29a9837aceda15502` |

Official Python contract: https://docs.python.org/3.14/library/ast.html#ast.dump .
Official CPython formatter: https://raw.githubusercontent.com/python/cpython/v3.14.0/Lib/ast.py .
The original formatter source is bound by SHA256 in the derived receipt.

## Bounded correction and regression

Only external `qualify_python_wrapper` changes: when `ast.dump` exposes `show_empty`,
pass `show_empty=True`; preserve the legacy call for older interpreters. The
previous exact accepted AST hash remains mandatory. Receipt metadata identifies
the complete empty-field serialization policy. No additional implementation
hash, version allowlist, AST node removal or native call fallback is introduced.

Exact native `[3,3,10]` flags, names, type ordering, HRESULT/SAFEARRAY/Int32 types,
IID, original ABI-1 metadata, wrapper code identity and closure matching remain
unchanged. All other external function ASTs and old artifact bytes are unchanged.

Fourteen new offline regressions replay the unchanged official Python 3.14
`dump` function over offline AST nodes, reproduce the observed original dump
byte-for-byte, and restore the accepted hash with `show_empty=True`. They verify
the legacy formatter, actual comtypes wrapper with synthetic backend, and rejection
of changed direction/pointee/output/return semantics and incorrect code/closure.
This formatter replay is not execution of a full Python 3.14 runtime or live COM.

Integrated validation: **1856 PASS**, all **1842** accepted identities preserved,
**14 new PASS**, no failures/errors/skips. Compile/import/diff checks PASS.
Fresh exact-base and candidate architecture diagnostics match: 31 PASS and
**6 real pre-existing FAIL**, no new/expanded violations; all 45 protected
surface hashes remain unchanged. See the derived JSON receipt for exact identities.

## Separately pinned external operator package

Corrected Python artifact (not tracked in Git):
`column_r1_r3m_abi2_astfix_getnamelist_probe.py`.
SHA256: `1738ac0ce9cc97825035311a2c694bea7e503ce207a09e27dd78830c7a4f2753`.
The delivered PowerShell pins the new committed HEAD/TREE, this script hash,
the observed operator Python, full candidate SHA and existing ETABS PID **2072**.
It requires the original ABI-1 JSON and sidecar, and creates a new unique receipt.
It never retries automatically.

One reviewed `FrameObj.GetNameList` target read remains the maximum scope. Existing
getter-only source/session/unit/lock/selection guards remain in force. No full
factual census, matrix scan, global modal capture, setters, RunAnalysis, StartDesign,
Save, unit changes or alternate attachment are included. The worker executed no ETABS.

Current candidate source remains:
`61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621`.
Historical production source remains separately:
`FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F`.
FC09 production gate unchanged; authority not rebound.

NEXT EXACT CAUSAL EDGE: operator review of a new, individually invoked, bounded
one-GetNameList receipt. Native wrapper/call validation is still pending that receipt.
No automatic live retry or 172-point matrix scan is authorized by the diagnostic.
GLOBAL_DELTA = NOT_PROVEN; M6_B = OPEN; R2_RERUN_READY = NO.
