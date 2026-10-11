# COLUMN-R1 R3M ABI-1 — native metadata discovery

## Accepted input and narrow root-cause boundary

Base HEAD `5ae4f19851dff795a2eb2e2951b8588bad2fd026`, TREE
`99999e74f29a9e41dd68378a1fa386a4e44178f9`, branch
`worker/column-r1-r3m-source-drift-reconciliation`.

Supervisor accepts original diagnostic receipt
`column-r1-r3m-diag1_20261011_174304_642_83137830ee06411e914fdd0224a521a3.json`:
operation `r3m_candidate_fact_reconciliation`; first expected getter
`FrameObj.GetNameList`; census entered; ABI check entered and failed;
getter NOT invoked; native return NOT observed; zero facts and matrices;
`ValueError: generated native ABI unavailable: GetNameList`.

These are supervisor-accepted observations. The exact original JSON and sidecar
were not materialized here; whole-file SHA and independent raw-byte verification
are NOT AVAILABLE. No original native receipt is reconstructed or copied into Git.
This failure is the external Python resolver before native invocation. It is not
an ETABS analysis or model failure. The exact live owner representation and its
GetNameList declaration remain PENDING METADATA RECEIPT.

## Source-backed audit

DIAG-1 `generated_abi()` selects `getattr(type(owner), "_type_", type(owner))`
and reads only that object's `_methods_`. It then insists on one exact name,
parameter flags, exact input/output names and IID. The accepted artifact SHA is
`8a55a6d3792066f5acfd68b4c7226c3482b846586f4d4f8d832058a8bdc63df5`.

Official comtypes interface documentation:
https://comtypes.readthedocs.io/en/stable/com_interfaces.html
(`_methods_` lists only an interface's own slots; superclass slots are inherited;
COMMETHOD specifies directions and names; output parameters form Python results).
Source reference:
https://github.com/enthought/comtypes/blob/1.4.17/comtypes/_post_coinit/unknwn.py
and
https://github.com/enthought/comtypes/blob/1.4.17/comtypes/_memberspec.py.

Locally audited published comtypes 1.4.17 wheel SHA256:
`4e0a221dde2c589b82977bed802efd71cd5eb67a380347b732e02735e597f586`.
Its unchanged `unknwn.py` SHA256:
`ae4be60c5539b48acd084eedc659162d470e6d674650994b456f9e80668640ac`;
`_memberspec.py` SHA256:
`bc85a42d1daf6d84b2697c7ab0f56f70689db4e97122e06bee40af15e583ada2`.
This establishes the dependency's representation contract, not the installed
operator version or live ETABS declaration.

`unknwn.py` pointer construction uses bases `(interface, POINTER(base_interface))`
(or the IUnknown pointer base), writes `__com_interface__ = interface`, and uses
`_compointer_base(c_void_p)`. Consequently a valid pointer can inherit the ctypes
scalar `_type_ == "P"`; that value is not the generated interface class. The old
resolver searches the scalar's nonexistent `_methods_`. This defect is reproduced
with actual offline ctypes c_void_p subclasses and comtypes-style interface mixins.

`_ComMemberSpec` has restype/name/argtypes/paramflags/idlflags/doc.
`_DispMemberSpec` has what/name/idlflags/restype/argspec; it does not expose the same
paramflags contract. No guessed dispatch conversion is added.

Repository audit: `tbdy_engine/etabs/oapi/object_model.py::_read_name_list`
uses the already-owned container, calls GetNameList() through the existing
verified-session OAPI path, and validates count/names/zero status and duplicate
identities. It does not rediscover the owner interface via `_type_`. This explains
why working repository wrappers do not justify removing the external ABI guard.
No repository OAPI wrapper, gateway or ownership rule changes.

| Representation | Old resolver | ABI-1 resolver |
| --- | --- | --- |
| Explicit ctypes interface `_type_` with direct COMMETHOD | Supported | Supported, exact flags/order required |
| Direct interface class with own methods/IID | Supported offline | Supported offline, exact flags/order required |
| comtypes pointer with `__com_interface__`, scalar `_type_` | Missed | Explicit interface link inspected |
| Derived interface with its own `_methods_`, target on base | Missed when hidden by child list | Declared MRO tables inspected once |
| Dispatch-only argspec or mixed duplicate target | Unqualified | Recorded, remains BLOCKED |
| Missing/conflicting interface or duplicate target declaration | BLOCKED | BLOCKED |

## Bounded correction and metadata-only live design

New external artifact: `column_r1_r3m_abi1_metadata_probe.py`, SHA256
`e2b94d5a4b557ae9bdfdcd9db83e42ba60821ebdef7f72e1743ad185048c5e0d`.
It is outside Git. Only offline regressions and this source-bound derived evidence
are committed. The accepted DIAG-1/candidate/FC09 artifacts remain byte-identical.

Resolver chooses the existing class's explicit __com_interface__ link; accepts a
class-valued _type_ only when consistent; otherwise permits the direct class
representation with IID. It uses class dictionaries rather than descriptor access.
It bounds MRO to 16 and each declaration list to 4096. Every matching method across
own MRO tables and both metadata styles is recorded; exactly ONE target declaration
must exist. Dispatch-only metadata remains unqualified. No QueryInterface, casts,
alternate attachment, overload search, or native invocation follows a failure.

Required GetNameList input sequence remains empty; exact ordered outputs remain
`NumberNames, MyName, pRetVal`. The original accepted ABI names are reused, not
invented. Retain native numeric flags, reject malformed/duplicate names, incompatible
directions, unsupported bits, property declarations, missing type metadata or
argument-type/flag count mismatch. Preserve resolved and declaring IID. A metadata
PASS is explicitly labelled `PASS_METADATA_ONLY_LIVE_GETTER_NOT_VALIDATED`.

The **only prepared live callback** obtains the already-owned `model.FrameObj`
and inspects Python owner class, class-level `_type_`, `__com_interface__`, interface
MRO/IID, `_methods_`/`_disp_methods_` availability and exact GetNameList declarations
with their original flags/type metadata. It never obtains or calls the GetNameList
callable. It retains partial metadata and original gateway exception metadata on
failure and immediately stops that operation. No fact census, matrix scan, selection
snapshot, Results or DatabaseTables access is present in this artifact.

Existing gateway identity getters before/after and the owned FrameObj property
access are necessary integrity reads; “getter-free metadata” means no target
native fact/result getter invocation in the inspection callback. No raw SapModel
escape, owner rebinding or gateway modification is introduced.

## Operator package — prepared, not authorized or executed

Use the reviewed Windows Python/comtypes environment. Existing PID 2072 must still
be ETABS, source exactly `C:\tmp\B-BLOK_Revised.EDB`, current candidate SHA exactly
`61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621`.
Historical FC09 is a separate identity and its production gate remains unchanged.
No historical byte restoration is required. No current whole-model equivalence
claim follows from this inspection.

Use clean exact ABI-1 checkout at
`C:\Users\FCY\PycharmProjects\tbdy_engine_r3m_probe`; external Python and PowerShell
files go in `C:\tmp`, not Git. The accompanying PowerShell artifact pins the final
pushed HEAD/TREE and Python SHA after commit. Both PowerShell and Python independently
check candidate source SHA before/after. Python verifies exact session, loaded path,
lock and accepted present/database unit identities before/after. PID fallback is
false. The one STA metadata callback has 30-second timeout. Failure stops without
retry. Immutable unique JSON and SHA sidecar are written outside Git.

Separately reviewable command, **not executed and not automatic authorization**:

```powershell
& 'C:\tmp\column_r1_r3m_abi1_operator.ps1' `
  -CandidateSha256 '61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621'
```

No GUI precision input is needed: no displacement/result acquisition is present.
Original source authority, selection policy/transaction, native results, column
mechanics, matrix hypotheses, physical comparisons and P2 contract are unchanged.
No RunAnalysis, StartDesign, Save, SetPresentUnits or model mutation. No worker
ETABS execution. Metadata receipt review precedes any separately authorized getter
or 172-point scan continuation.

## Offline validation and exit

38 focused offline regressions cover concrete pointer/direct/explicit/inherited
representations; old miss reproduction; missing, malformed and ambiguous metadata;
dispatch-only refusal; exact names/flags/order; argument metadata count/property
rejection; native descriptor non-access; partial metadata preservation; unchanged
source authority; immutable error receipts and source/session drift rejection.
All original accepted test files and protected guard surfaces remain unchanged.
Integrated result is 1796 PASS / 0 FAIL / 0 ERROR / 0 SKIP: all 1758 accepted
identities preserved plus 38 new. Both exact architecture baselines report 31 PASS
and 6 real unchanged FAIL (five canonical, one supplemental), zero new or expanded
violations; all 45 protected hashes are unchanged. Compile/import and diff check
PASS. PowerShell is statically reviewed; no Windows runtime was used.
Full integrated PASS identities and exact negative guard comparison are recorded
in `COLUMN_R1_R3M_ABI1_OFFLINE_RECEIPT_2026-10-11.json`.

`LIVE_VALIDATION = PENDING`; `172_MATRIX_SCAN = NOT_PROVEN`;
`GLOBAL_DELTA = NOT_PROVEN`; `M6_B = OPEN`; `R2_RERUN_READY = NO`.
Next exact causal edge: supervisor-authorized **metadata-only** original receipt
and sidecar proving the live owner link, IID and one exact GetNameList declaration;
then review whether this correction applies before any native getter is authorized.
