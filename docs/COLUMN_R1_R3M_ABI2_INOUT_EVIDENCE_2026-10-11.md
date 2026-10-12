# COLUMN-R1 R3M ABI-2 — observed INOUT contract

## Accepted observation and authority boundary

Base HEAD `bbfd5b675f06eda92a5710818d52e86cd5d2fc1b`, TREE
`f15b7cd4c282f5149de468e3a3960c8e51648988`, existing R3M branch.

Supervisor accepts the original ABI-1 metadata experiment:
`column-r1-r3m-abi1-metadata_20261011_192728_592_84caa9aefe2040b6b483138bd84ffc09.json`.
Owner `POINTER(cFrameObj)`, path `__com_interface__`, IID
`{F87E3A66-8381-4202-897F-46683A8477D4}`; ONE matching `_ComMemberSpec` on
`_methods_`; flags `NumberNames=3`, `MyName=3`, `pRetVal=10`;
ABI-1 failed closed at INOUT rejection, native getter NOT invoked and source SHA
unchanged. Historical pointer discovery is resolved for this observed owner.

These facts are supervisor-accepted native metadata observations. Original JSON
and sidecar were not materialized here; their independent whole-byte SHA is NOT
AVAILABLE. Full native type reprs were not included in the supervisor excerpt.
Do not manufacture them or claim independent receipt verification. The new probe
REQUIRES that original receipt and sidecar, hashes them, validates exact ABI-1
HEAD/TREE/source/PID/identity/flags and compares the live declaration's names,
flags, type metadata, return metadata and declaring IID before any target call.
The offline contract is qualified; live type/receipt binding is a mandatory gate.

## Native directions versus Python call contract

| Parameter | Numeric flags | COM direction | Python input handling | Returned position |
| --- | --- | --- | --- | --- |
| NumberNames | 3 = IN + OUT | INOUT, signed Int32 by reference | Named INOUT may be omitted by verified comtypes wrapper | 0 |
| MyName | 3 = IN + OUT | INOUT, SAFEARRAY(BSTR) by reference | Named INOUT may be omitted by verified comtypes wrapper | 1 |
| pRetVal | 10 = OUT + RETVAL | Pure OUT + RETVAL, signed Int32 by reference | Generated output container | 2 |

INOUT appears in BOTH native input and output sequences. RETVAL is separately
classified; it does not mean that Python drops other outputs. Numeric flags,
parameter names, native type declarations, restype, original default metadata
and resolved/declaring IID remain in the receipt. Native HRESULT transport is
separate from the final ETABS integer pRetVal output. No native return code is
invented; zero is required only when the actual raw response arrives.

Primary dependency source (accepted version 1.4.17):
https://github.com/enthought/comtypes/blob/1.4.17/comtypes/_memberspec.py
and
https://github.com/enthought/comtypes/blob/1.4.17/comtypes/safearray.py.
Published wheel SHA256
`4e0a221dde2c589b82977bed802efd71cd5eb67a380347b732e02735e597f586`;
unchanged `_memberspec.py` bytes SHA256
`bc85a42d1daf6d84b2697c7ab0f56f70689db4e97122e06bee40af15e583ada2`.
Official tag source independently fetched and matched after newline normalization.
Fresh reads of the operator's ABI-1 Python/PowerShell copies match audited artifacts.

`ComMemberGenerator._fix_args` detects direction `IN | OUT` and selects
`_fix_inout_args`. Its actual `call_with_inout` iterates declaration order: for a
named omitted INOUT it takes the declared pointer's `_type_`, constructs the empty
pointee and passes it by keyword. After the generated backend returns, it replaces
each INOUT output position using `__ctypes_from_outparam__`. With two INOUTs and
one RETVAL there are THREE Python outputs, in declaration order. This conclusion
comes from executing the original dependency functions offline with synthetic
ctypes containers, not from the method name or speculative overloads.

Required factory AST SHA256 (without source locations):
`5c4668efa8f7b15c312153d246bebbb29c8ccbbfc671515ec18bac12aa8f9e01`.
Before target invocation the installed wrapper factory must match this source,
the bound Python function's code must be the exact factory's nested
`call_with_inout`, and its closure's argtypes/paramflags must match the ONE generated
declaration. No wrapper replacement, own COM cast, QueryInterface or second attachment.
The installed version is recorded; an unqualified implementation fails closed.

The reviewed effective call is **one bound GetNameList() with no supplied positional
or keyword arguments**, justified only by this exact wrapper/closure/type contract.
The two COM INOUT values are still supplied by the verified wrapper. Native types
are checked structurally: signed 32-bit pointer for NumberNames and pRetVal;
exact generated pointer-by-reference to SAFEARRAY(BSTR) for MyName; HRESULT restype.
Their complete live metadata must also match the accepted original receipt.

Supervisor supplied the ETABSv1 cFrameObj.GetNameList reference text during ABI-2:
namespace ETABSv1; assembly ETABSv1.dll; version 1.0.0.0 (2.3.0.0); exact C#
signature `int GetNameList(ref int NumberNames, ref string[] MyName)`. NumberNames
is System.Int32; MyName is a zero-based one-dimensional System.String[] whose
length and contents are set inside ETABS; Int32 zero indicates success. This is
a USER_PROVIDED_CSI_ETABSv1_REFERENCE_EXCERPT, with no original URL or byte hash
supplied. It strengthens the type policy without pretending the .NET reference
is the installed comtypes declaration. Assembly text is not silently equated to
the program/API version. The source's model-creation/analysis example is NOT an
operator authorization and is not implemented.

CSI's historical typed reference additionally corroborates the ref Int32/ref string-array
shape and zero-success integer; it is not substituted for the ETABS 23.2 native
metadata:
https://docs.csiamerica.com/help-files/etabs-api-2016/html/d0cc0291-3352-b32b-79a0-8815c631a3d8.htm.
Existing repository `object_model.py::_read_name_list` calls the already-owned
container and decodes `[count, names, status]`; its contract is unchanged. Offline
actual-wrapper output is accepted by that repository decoder. The external strict
`decode_names` remains AST-identical to the accepted artifact: exact integer zero,
nonnegative integer count, exact array length, strings and unique identities.
The one-call probe additionally bounds the count to 20,000.

## Other planned getters — audited, not invoked

| Planned getter | Prior explicit inputs | INOUT concern / disposition |
| --- | --- | --- |
| FrameObj.GetSection | Name | Output slots may be INOUT; original directions/types must be inspected before continuation |
| PropFrame.GetSectProps | Name | Scalar output slots may be INOUT; preserve exact twelve-output order and status; no invocation |
| FrameObj.GetPoints | Name | Two endpoint output slots may be INOUT; no mapping/compare changes |
| PointObj.GetLabelFromName | Name | Label/Story may be INOUT; no native declaration acquired here |
| PointObj.GetCoordCartesian | Name, CSys | A late CSys positional value can bind to X INOUT instead; original `(Name, "Global")` is NOT qualified without declaration-aware Python call review |
| PointObj.GetElm | Name | Associated-element output may be INOUT; no one-to-one assumption or invocation |
| PointElm.GetTransformationMatrix | Name | Value array may be INOUT; matrix scan remains NOT_EXECUTED |
| Results.JointDispl | Name, ItemTypeElm | Result arrays may be INOUT; no result call or modal/table capture |

No actual declarations for these additional getters are claimed. A focused
synthetic late-input regression executes the original wrapper: a second positional
`"Global"` cannot skip X/Y/Z INOUT; explicit Name/CSys keywords can be represented
in that synthetic contract. This is an audit finding, not an engineering or future
getter patch. Existing census, matrix, physical binding and selection policy remain
unchanged and blocked from live continuation by this package.

## Separately reviewable one-getter operator design

External Python `column_r1_r3m_abi2_getnamelist_probe.py`, SHA256
`3c2ec29d660e6c354ebd7ae534370b24e5c941c35a887821ea5128d8f7e826a3`.
External PowerShell pins the final pushed HEAD/TREE and this Python hash after commit.
Neither artifact is tracked in Git.

Use reviewed Windows Python/comtypes environment and clean exact final ABI-2
checkout at `C:\Users\FCY\PycharmProjects\tbdy_engine_r3m_probe`. Existing PID 2072
must still be ETABS, loaded path `C:\tmp\B-BLOK_Revised.EDB`, exact candidate SHA
`61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621`.
Historical FC09 SHA remains separate, unchanged and required by its production
route. No source-authority rebind or historical byte restoration is introduced.

Place the original accepted ABI-1 JSON and its `.sha256` sidecar in `C:\tmp`.
Keep them unchanged. No template, reconstructed receipt or fabricated metadata may
be substituted. The probe recomputes both hashes before/after. Incompatible or
missing inputs stop BEFORE gateway/target execution.

The existing gateway owns the exact PID attachment with fallback false. Fresh
session/path/units/lock identities are checked before/after and against session
identity. Both PowerShell and Python independently check source SHA before/after.
Selection identity uses accepted snapshot getters before/after: LoadCases/RespCombo
name catalogs and Results.Setup selected flags only. Those integrity reads are
separate from the single BUSINESS FrameObj.GetNameList read; setters/restoration
are forbidden. No selected-case requirement is invented for a frame-name census.
All gateway callbacks have 30-second bounds. Exactly one target invocation attempt
is permitted; metadata/callable failure prevents it, target failure ends it. No
retry or overload fallback. Failed raw responses and gateway metadata remain in
exclusive immutable outside-Git JSON/sidecar; drift invalidates the result.

Prepared command, **NOT executed and awaiting separate live authorization**:

```powershell
& 'C:\tmp\column_r1_r3m_abi2_operator.ps1' `
  -CandidateSha256 '61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621'
```

Worker ETABS execution NO. No full fact census, engineering comparison, 172-point
scan, native displacement or P2 capture. No RunAnalysis/StartDesign/Save/SaveAs,
SetPresentUnits, Results.Setup setters, DatabaseTables selection mutation, model
mutation, alternative attachment or production gateway architecture change.

## Validation and exit

46 new offline regressions cover observed [3,3,10], exact pointer hierarchy/IID,
actual accepted dependency wrapper construction/conversion, raw/native versus
Python argument sequences, unchanged repository decoder, invalid flags/types/order,
ambiguous declarations, installed-wrapper/closure rejection, mandatory original
receipt binding, one-call budget, failed native status and immutable outer gateway
errors, source/session/selection drift and late pure-IN positional binding risk.

Integrated result: 1842 PASS / 0 FAIL / 0 ERROR / 0 SKIP; 1796 accepted identities
preserved plus 46 new. Both exact architecture baselines: 31 PASS / 6 real unchanged
FAIL (five canonical, one supplemental), zero new or expanded violations; all 45
protected hashes unchanged. Compile/import/diff check PASS. PowerShell statically
reviewed only; no Windows/native runtime used by worker.
Full PASS identities, original file hashes, negative architecture comparison and
compile/import/diff results are in `COLUMN_R1_R3M_ABI2_OFFLINE_RECEIPT_2026-10-11.json`.
`LIVE_GETNAMELIST = NOT_EXECUTED`; `MATRIX_SCAN = NOT_EXECUTED`;
`FC09_PRODUCTION_GATE = UNCHANGED`; `CURRENT_SOURCE = CANDIDATE_ONLY`;
`GLOBAL_DELTA = NOT_PROVEN`; `M6_B = OPEN`; `R2_RERUN_READY = NO`.

Next exact causal edge: separately authorize ONE bounded getter-only operator
operation with mandatory original ABI-1 receipt/type/IID binding and verified
installed Python wrapper. Review its original immutable receipt before any fact
census or 172-matrix scan authorization.
