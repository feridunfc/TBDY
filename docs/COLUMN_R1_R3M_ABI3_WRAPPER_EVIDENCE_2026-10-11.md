# R3M ABI-3 — remaining wrapper code/closure inspection package

The accepted native declaration observation remains CLOSED. The eight target
getters were not invoked. This new external artifact prepares inspection of the
existing generated Python wrappers through the unchanged verified STA gateway.
Its offline qualification does not qualify native results or authorize a getter.

Base HEAD: `86778e456db15dfe42e9bc1635a4a3372cd58fa3`.
Base TREE: `6ad2377496f8bae5669ca2b660d673da13d57848`.
Branch: `worker/column-r1-r3m-source-drift-reconciliation`.
Derived validation receipt: `COLUMN_R1_R3M_ABI3_WRAPPER_OFFLINE_RECEIPT_2026-10-11.json`.

## Original evidence reused

The original ABI-2 GetNameList JSON and sidecar, and ABI-3 eight-declaration JSON
and sidecar, remain unchanged outside Git. Whole-file and sidecar hashes are
mandatory inputs; all eight original raw metadata hashes are recomputed.
Neither original response is copied or regenerated in this package.

- ABI-2 JSON SHA256: `bf720aba0fd474313cecb2cd8f9e4ae650f4fe624e5dd69f882495ceea6dca21`.
- ABI-3 JSON SHA256: `11355e6860ba435e1275a7251efb0a5701268e4293c98c58a9231b2194f5b5be`.
- ABI-3 metadata capture HEAD/TREE: `c66bb0e6ce574ff3f667e324660d26c8e0cb055e` /
  `794dac8a5cf3a408cf9609ba7523d122254f38b5`.
- External Python SHA256: `89a5a53e05f48e5dc3b04cf614ec63e09174f6841b5c924400237e6ee0db3b21`.

## Dependency and actual wrapper contract

The accepted installed comtypes 1.4.16 `_memberspec.py` bytes have SHA256
`bc85a42d1daf6d84b2697c7ab0f56f70689db4e97122e06bee40af15e583ada2`.
The locally audited distribution copy has exactly these same bytes. This does
not change the accepted installed version to the local copy's distribution label.
The original receipt observed Python 3.14.0 and comtypes 1.4.16; the proposed
operator probe requires those exact versions and unoptimized execution.

`ComMemberGenerator` creates a ctypes native function with declaration argtypes,
HRESULT, parameter flags and generated interface identity, then `_fix_inout_args`
wraps INOUT parameters. Pointer classes inherit the interface; the interface
installs generated functions as built-in `instancemethod` descriptors.
The new probe inspects those existing descriptors without calling the target.
It permits only an exact Python function or built-in instancemethod descriptor,
rejects instance overrides and requires one static MRO match before binding.

The pinned dependency source is compiled for comparison, never executed by the
operator probe. Existing factory/helper bytecode must match that source on the
running interpreter, including constants, names, variables, closure structure,
flags and exception table. The accepted AST check retains explicit empty fields
on Python 3.14. The target function must use the exact existing nested
`call_with_inout` code, exact argtypes/paramflags closure, exact global helpers and
native ctypes backend prototype. Built-in Python binding must return this same
function bound to this same verified owner. Neither wrapper nor backend is called.

Only code/closure/prototype/binding are inspected. Backend vtable index and native
method IID are NOT_OBSERVED_NOT_PROBED. No backend casting, QueryInterface,
alternative attachment, speculative introspection or target invocation is used.
Successful inspection still leaves native return codes and response validation
NOT_OBSERVED and all eight native factual/result contracts unqualified.

## Named argument plan and limits

| Method | Pure-IN named argument plan | INOUT handling |
| --- | --- | --- |
| FrameObj.GetSection | Name | PropName, SAuto omitted only after wrapper qualification |
| PropFrame.GetSectProps | Name | All twelve scalar outputs omitted conditionally |
| FrameObj.GetPoints | Name | Point1, Point2 omitted conditionally |
| PointObj.GetLabelFromName | Name | Label, Story omitted conditionally |
| PointObj.GetCoordCartesian | Name, CSys | X, Y, Z omitted conditionally; observed CSys flag17/default Global |
| PointObj.GetElm | Name | Elm omitted conditionally; scalar BSTR is not a physical/panel-zone proof |
| PointElm.GetTransformationMatrix | Name | Value omitted conditionally; array size/order/direction not proven |
| Results.JointDispl | Name, ItemTypeElm | Twelve INOUT outputs omitted conditionally; no result rows acquired |

No argument plan is executed. In particular, `GetCoordCartesian(name, "Global")`
is not substituted for the named plan: INOUT X/Y/Z occupy input positions.
Offline tests replay the accepted dependency on synthetic owners/declarations and
ctypes callbacks that are never called. They are explicitly synthetic evidence,
not observations of actual Windows native backends.

## Proposed operator scope

Exactly one 30-second existing verified STA callback inspects eight wrappers in
accepted order, comparing each native metadata hash to its original observation.
Any mismatch preserves the first failure and stops; no later target, overload,
retry or fallback is attempted. The target getters, GetNameList, full fact census,
172-point matrix scan, modal capture and P2 result acquisition remain unexecuted.

The separately pinned external PowerShell wrapper requires an exact clean final
HEAD/TREE, exact artifact/dependency/original evidence hashes, existing PID2072
and its accepted start identity, and the exact candidate SHA. It checks the same
files and process again afterwards. The Python probe checks source SHA and exact
session/path/units/lock identity against the accepted original before and after.
New JSON and sidecar are exclusively created and made immutable outside Git.
Selection is NOT_READ in this scope; no independent selection comparison claimed.
No Results.Setup or DatabaseTables access, setters, analysis/design/save/unit or
model mutation is permitted. No worker ETABS execution or automatic live retry.

Operator prerequisites: both original JSON/sidecar pairs unchanged in `C:\tmp`,
new external Python/PowerShell files there, reviewed checkout in
`C:\Users\FCY\PycharmProjects\tbdy_engine_r3m_probe`, and the existing accepted
Python environment. A different source/process/session/runtime fails closed.
The old metadata artifact remains pinned to its original capture and is not rerun.

## Offline validation and continuing gates

Focused 39 PASS; integrated 1988 PASS = all 1949 accepted identities preserved +39.
All accepted test files and 45 protected surfaces remain byte-identical. Fresh
exact-baseline architecture comparison retains 31 PASS and six real FAIL with
identical full violation sets, zero new/expanded violations and no allowlist changes.
Compile/import/diff checks PASS; PowerShell runtime NOT_EXECUTED.

These counts are backed by the immutable derived receipt, not a live native call.
FC09 production gate UNCHANGED; current source CANDIDATE_ONLY. Engineering fact
equivalence, panel-zone mapping, matrix direction and global displacement remain
NOT_PROVEN. M6_B OPEN; R2_RERUN_READY NO.

NEXT EXACT CAUSAL EDGE: review final pinned getter-free wrapper inspection artifact
and obtain separate bounded operator authorization; review the original wrapper
receipt before proposing any native factual getter or scan.
