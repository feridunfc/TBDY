# R3M ABI-3 remaining getter metadata package

ABI-3 offline preparation is CLOSED. All eight remaining live getter contracts
are BLOCKED_UNQUALIFIED. ABI-1/ABI-2 and the one successful ABI-2 GetNameList
operator observation remain CLOSED; no accepted experiment was rerun.

Base HEAD `19a18ab497f8d15589f101df0bb41340504e1698`, TREE
`03e715e333114223c7af644889555f1f96bf1830`, clean continuation branch. Remote
identity and ancestry were verified before editing. No production code, gateway
owner, mechanics, selection transaction, architecture guard or allowlist changed.
Only focused offline tests, derived evidence and documentation are tracked.

## Evidence layers and exact inventory

CSI's official ETABS 2016 documentation supplies the parameter sequence and
managed ref types below. It is SOURCE_BACKED_OFFLINE; it does not supply observed
ETABS 23.2 COM numeric flags, generated ctypes, declaring IIDs or runtime wrapper
closures. Those remain NOT_YET_OBSERVED. Names do not establish native directions.
The accepted FrameObj owner IID is `{F87E3A66-8381-4202-897F-46683A8477D4}`; that
observation does not qualify GetSection or GetPoints on this interface.

| Owner / getter | Documented input and ordered byref outputs | Qualification |
| --- | --- | --- |
| FrameObj.GetSection / cFrameObj | Name; PropName, SAuto; Int32 return | SOURCE_BACKED_OFFLINE; native BLOCKED |
| PropFrame.GetSectProps / cPropFrame | Name; Area, As2, As3, Torsion, I22, I33, S22, S33, Z22, Z33, R22, R33; Int32 return | SOURCE_BACKED_OFFLINE; native BLOCKED |
| FrameObj.GetPoints / cFrameObj | Name; Point1, Point2; Int32 return | SOURCE_BACKED_OFFLINE; native BLOCKED |
| PointObj.GetLabelFromName / cPointObj | Name; Label, Story; Int32 return | SOURCE_BACKED_OFFLINE; native BLOCKED |
| PointObj.GetCoordCartesian / cPointObj | Name; X, Y, Z; late CSys="Global"; Int32 return | SOURCE_BACKED_OFFLINE; native BLOCKED |
| PointObj.GetElm / cPointObj | Name; scalar string Elm; Int32 return | SOURCE_BACKED_OFFLINE; native and physical association BLOCKED |
| PointElm.GetTransformationMatrix / cPointElm | Name; Double[] Value; Int32 return | SOURCE_BACKED_OFFLINE; native layout/direction BLOCKED |
| Results.JointDispl / cAnalysisResults | Name, ItemTypeElm; NumberResults, Obj, Elm, LoadCase, StepType, StepNum, U1, U2, U3, R1, R2, R3; Int32 return | SOURCE_BACKED_OFFLINE; metadata-only, NO capture |

Each exact official CSI page is pinned in the derived receipt's inventory. Native
COM output spelling, flags, types and ordering must agree with a single generated
_method_ declaration before a later getter can be proposed. Missing, duplicate,
inherited-conflicting, dispatch-only and malformed declarations are preserved and
blocked. `_disp_methods_` is observed but never treated as a convenient alternative.
No native metadata is synthesized from this table or documentation examples.

## Actual dependency and INOUT call binding

The accepted installed comtypes 1.4.16 `_memberspec.py` bytes have SHA256
`bc85a42d1daf6d84b2697c7ab0f56f70689db4e97122e06bee40af15e583ada2`.
The offline dependency copy has these exact bytes. The accepted ABI-2 direction
classifier, identity guard, immutable writer and gateway exception preservation
are reused without AST changes. ABI-2 Python 3.14 serialization is not reopened.

IN=1, OUT=2, INOUT=3 and OUT|RETVAL=10 are distinct; original numeric flags,
optional/default metadata and ctypes are retained. INOUT belongs to both native
input and output lists. The actual dependency factory prepares omitted named
INOUT pointer containers and replaces corresponding returned output positions.
HRESULT is transport metadata; it is not inserted into the Python returned tuple.
The ETABS Int32 return code must be the final OUT|RETVAL output and zero.

The historical external `GetCoordCartesian(name, "Global")` is unqualified. If
X/Y/Z are INOUT before CSys, that positional string binds to X. An offline replay
of the accepted dependency implementation demonstrates rejection before its
synthetic backend is invoked. The explicit named plan `Name=..., CSys="Global"`
works for that synthetic exact declaration with X/Y/Z omitted by name. This is
an offline hypothesis for the remaining actual wrapper, not live qualification.
The existing production wrapper already supplies X/Y/Z seeds before CSys and is
unchanged. No remaining bound getter callable is fetched in this metadata scope;
its runtime code/closure identity remains a separate future qualification gate.

## Response and engineering boundaries

The offline-only response validator is unreachable from the metadata execution
path. GetSectProps retains all twelve property names and I22/I33 order without
axis interchange. GetPoints retains I/J endpoint identity without assuming lower
or upper story. GetElm rejects multiple mappings without selecting one; a scalar
response alone cannot establish one-to-one/panel-zone analysis-joint identity.

A future matrix must contain nine finite values, be proper orthogonal and have
return zero. Orthogonality and determinant checks are invariant under transpose;
these checks do not prove row/column layout, local/global direction, or displacement
applicability. No matrix is repaired, assumed identity or used to calculate global
results. Both synthetic identity and nonidentity matrices remain unqualified.

JointDispl's ordered parallel arrays must match NumberResults and preserve every
Obj/Elm/case/step/sign row. No duplicate row is selected, no mode is invented and
no case-selection change is prepared. Source docs do not establish accepted modal
grain or panel-zone applicability. No result getter is invoked by ABI-3.

## Prepared external metadata-only experiment

External Python: `column_r1_r3m_abi3_metadata_probe.py`. External PowerShell:
`column_r1_r3m_abi3_operator.ps1`. Neither is committed to Git. A separately pinned
PowerShell wrapper binds the final committed HEAD/TREE and Python hash; its own
SHA is included in the delivery. These are proposed artifacts, NOT an execution
receipt and NOT permission to run.

Exactly one existing verified PID2072 attachment, with fallback disabled, owns
one 30-second STA metadata callback. Only existing FrameObj, PropFrame, PointObj,
PointElm and Results owners are obtained. Python owner class, `_type_`,
`__com_interface__`, bounded MRO, interface/declaring IID, `_methods_` and
`_disp_methods_`, exact matching declarations, paramflags, argtypes, HRESULT,
idlflags and argspec are recorded without target method access or invocation.
Each method has its own raw metadata and canonical SHA256. Missing/ambiguous or
incompatible metadata fails closed; no overload, QueryInterface, casts, alternate
attachment, dispatch probing, getter fallback or automatic retry is used.

The original accepted ABI-2 JSON and original sidecar are required unmodified
outside Git. Whole-byte hashes, receipt capture HEAD/TREE, raw response hash,
source/session/selection checks and the accepted count of 998 are independently
checked without copying raw native evidence into Git. Missing/modified originals
block attachment. They are not regenerated from the derived index.

Exact current candidate SHA:
`61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621`.
Historical FC09 SHA:
`FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F`.
These identities remain separate. No current-candidate fact becomes FC09 authority.

Before/after checks include file SHA, loaded `C:\tmp\B-BLOK_Revised.EDB`, PID,
ETABS23.2/API2.014, exact accepted session, model lock, present/database units and
unchanged Git/artifact/original evidence. Accepted Python3.14.0/comtypes1.4.16 and
dependency bytes are required. The wrapper independently hashes files and checks
PID2072's name/start time before/after. Fresh operator confirmation of that PID and
loaded model is a prerequisite. Selection is NOT READ in this metadata scope;
no Results.Setup or DatabaseTables selection access/mutation occurs. Permitted
verified-session identity getters provide integrity observations only.

Every success/failure produces a uniquely reserved outside-Git JSON and SHA
sidecar with readonly attributes. Gateway code/operation/details and original
exception cause/context survive outer wrapping. Source/session/unit/lock drift
blocks the observation and remains recorded. File destinations are never overwritten.

## Validation and next gate

The derived offline receipt records focused/integrated identities, exact-baseline
negative architecture comparison, protected surface hashes, compile/import and
diff checks. Six real architecture failures remain FAIL; they are not waived or
converted to PASS. No guard/allowlist change or expanded violation is accepted.

ABI3_LIVE_METADATA = PENDING_SUPERVISOR_AUTHORIZATION. After review the supervisor
may separately authorize exactly one getter-free operator metadata observation.
Then inspect the original declarations and separately qualify each actual bound
wrapper before proposing native fact getters. Full fact census, 172-point matrix
scan, JointDispl capture and P2 remain NOT_AUTHORIZED. Worker ETABS execution NO.
FC09_PRODUCTION_GATE UNCHANGED; CURRENT_SOURCE CANDIDATE_ONLY; GLOBAL_DELTA
NOT_PROVEN; M6_B OPEN; R2_RERUN_READY NO.
