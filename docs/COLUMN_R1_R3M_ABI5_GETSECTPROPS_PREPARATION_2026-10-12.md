# R3M ABI-5 — one GetSectProps offline proposal

Base `75868c7a62580271017647a281133f41b499faa4`, tree
`af9faad9254a0899b2b54e6c7226b58a016e558e`. ABI2/3/4 CLOSED/REUSE.
**OFFLINE PREPARATION ONLY. No worker ETABS execution and no live authorization.**

## Exact target and original authority

The target JSON binds `PropFrame.GetSectProps(Name="Column_80x80")` to original
ABI4 JSON SHA `be7874f5e1b58806dd547201ce0d7cb0e551b01a12b941778d654767fdbc7d33`,
original sidecar SHA `b67a0d382e94ceac14c371a5959a38ac56e3972190ca6bb818411aec8e46cb25`,
and raw assignment SHA `168de3740f2556617f1e287952891785e077ef11b89ac3aaed7924f2cbb78537`.
That single successful Name235 GetSection read establishes the assigned section
name only. No dimensions, inertia, geometry or current whole-model authority are
inferred from that name. Original receipts and sidecars remain unchanged outside Git.

Candidate source remains `C:\tmp\B-BLOK_Revised.EDB`, SHA
`61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621`.
Historical FC09 source identity remains
`FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F`.
Same path/session identity does not rebind FC09 production authority to the candidate.

## Accepted ABI and existing wrapper reuse

Accepted ABI3 metadata record1 and wrapper record1 cover cPropFrame, declaring
IID `{88AAFE1E-4F8C-43EE-B0BD-3CD28E64D7F8}`. Their raw hashes are respectively
`50b3643c7129d8f08cd8cb602d009c272935b9a52afe2098053714051317ab11` and
`056cd422e9fbc16ab25369dde50d54785dd83493ee7903ffeb0d373692672a87`.

Name BSTR is IN1; twelve pointer-to-c_double parameters are INOUT3; final
pointer-to-signed-Int32 pRetVal is OUT|RETVAL10; transport restype is HRESULT.
Supply only keyword Name. Omit all twelve INOUT values under the original
comtypes 1.4.16 `_fix_inout_args` contract. No replacement generated wrapper,
QueryInterface, casting, alternative attachment, positional injection or overload.

Immediately before the sole proposed invocation, compare exact current owner,
interface/MRO, declaration, numeric flags, output order, pointer/scalar types,
HRESULT restype, existing descriptor, installed dependency bytes/AST/code,
closure, backend prototype and exact bound owner/function against accepted
originals. This is an invocation guard within the one target callback; no new
standalone metadata experiment and no other native factual target is proposed.
**Backend vtable/method IID remains NOT_OBSERVED_NOT_PROBED.**

Require exactly thirteen list/tuple items, twelve exact finite Python floats
(Float64), followed by exact Python int zero. No float/int/bool coercion,
conversion, inferred reference value, correction or axis swapping. Record
original container/scalar types, all twelve values, their float.hex encodings,
original canonical raw hash and typed evidence hash. Preserve diagnostic type/repr
and hex information even on nonfinite/malformed responses. HRESULT exceptions
and transport metadata remain separate from application pRetVal.

## Historical field comparison limits

Original FC09 preflight `column-r1-r0-r1-preflight_20261009_192703.json`, whole SHA
`79a7bca0dd50f42b6d9852d2ed56dfc03d0a1cdb40a1c534ea7071f6e8c4ce00`,
contains a unique exact section fact and its original thirteen-item raw response.
The existing owner's `{raw: ...}` digest independently verifies raw provenance
`etabs-frame-section-mechanics:sha256:c01fc43bb12d97cab7d5f2f89505e8cdf7626689302e79e27ab984e2c6e3c56d`.
Original native response arrays are not copied into Git.

| Field | Raw index | Historical field-unit authority | Comparison rule |
| --- | ---: | --- | --- |
| Area | 0 | NOT_PROVEN | NOT_COMPARABLE |
| As2 | 1 | NOT_PROVEN | NOT_COMPARABLE |
| As3 | 2 | NOT_PROVEN | NOT_COMPARABLE |
| Torsion | 3 | NOT_PROVEN | NOT_COMPARABLE |
| I22 | 4 | Existing reviewed PRESENT L4 policy, m4 | Exact binary64 hex, unchanged qualified context |
| I33 | 5 | Existing reviewed PRESENT L4 policy, m4 | Exact binary64 hex, unchanged qualified context |
| S22 | 6 | NOT_PROVEN | NOT_COMPARABLE |
| S33 | 7 | NOT_PROVEN | NOT_COMPARABLE |
| Z22 | 8 | NOT_PROVEN | NOT_COMPARABLE |
| Z33 | 9 | NOT_PROVEN | NOT_COMPARABLE |
| R22 | 10 | NOT_PROVEN | NOT_COMPARABLE |
| R33 | 11 | NOT_PROVEN | NOT_COMPARABLE |

Every field's raw source, index, units and rule are independently indexed in the
source-bound target. Raw numbers exist for all twelve fields; only I22/I33 have
accepted per-output dimensional/unit evidence. Reuse policy
`COLUMN_R1_GETSECTPROPS_PRESENT_L4_POLICY_V1` only within that scope, requiring
historical/current exact verified unit context. Other outputs remain raw-context
bound, with dimensional units NOT_PROVEN. The existing policy explicitly excludes
Area/As/Torsion/S/Z/R. Neither field labels nor section-name formulas fill this gap.

The [official CSI GetSectProps method reference](https://docs.csiamerica.com/help-files/etabs-api-2016/html/7e0e26e6-6e25-6b5a-c523-003da72307e8.htm)
supports the double parameter order and integer application return contract;
it does not provide missing per-output dimensional-unit authority. The accepted
native ABI3 and wrapper observations provide the installed-version bridge.
No new general source research or claim of CSI support response.

Successful capture qualifies this one named candidate property only. I22/I33
may MATCH or DIFFER; no tolerance fitting. Other ten fields are NOT_COMPARABLE,
engineering equivalence NOT_PROVEN. Whole-model and analysis-result equivalence
remain NOT_PROVEN even if both inertias match. Final integrity failure invalidates
all comparisons while preserving pre-final observations.

## Proposed operator transaction — separately authorized later

External Python/PowerShell/checkout preparation have pinned bytes. The handoff
contains their exact hashes and final committed HEAD/TREE; package pin metadata
is derived evidence, not an original native response. The Python is ready before
commit; final operator Git pins are filled after publishing the reviewed commit.

Prerequisites: exact clean r3m worktree; Python3.14.0/comtypes1.4.16 unoptimized;
pinned dependency; all original ABI2/ABI3/ABI4 JSON/sidecar pairs plus original
FC09 preflight outside Git; verified existing ETABS PID2072 with original process
start UTC `2026-10-09T15:47:08.1780017Z`; exact loaded source path, candidate SHA,
program23.2.0/API2.014, locktrue and accepted present/database m units. No fallback
PID or source. Checkout preparation invokes neither Python nor ETABS and stops
for supervisor review; the separate operator additionally requires an explicit
authorization switch. The switch records operator confirmation, not an issued
supervisor approval.

Before/after: independently hash candidate bytes in PowerShell and Python;
verify Git HEAD/TREE/clean, artifacts, target, original input hashes, exact PID
start, source/session/units/lock via existing gateway ownership. Sole target STA
callback has a30-second bound and one attempt. No nested identity queue reads
inside it; only file SHA guards plus current target metadata/wrapper checks.
Existing gateway identity guards execute outside the target callback. Close the
owned gateway and write an exclusive immutable receipt+sidecar on success or
partial failure. First target/guard/error/timeout stops; no target retry, fallback
or next experiment. Cleanup/final integrity observations are not target retries.

Selection NOT_READ; no independent fresh selection-identity claim. Static closure
contains no Results.Setup/DatabaseTables access or setter. No factual census,
GetSection rerun, other property/object getter, GetPoints/mapping/matrix,
JointDispl/LC_DL/modal/P2 capture, RunAnalysis, StartDesign, Save/SaveAs,
SetPresentUnits, model or selection mutation. Production gateway unchanged.

Existing ABI4 scoped LF rule is preserved; one exact ABI5 target text/eol=lf
rule is added. Real isolated Git checkout regressions exercise autocrlf true/false,
raw SHA/blob equality and CLEAN status while unrelated files retain default EOL.
No hash variants, global config relaxation or assumed-unchanged flags.

Validation and preserved identities are in the offline receipt. LIVE_GETSECTPROPS
NOT_EXECUTED; worker ETABS execution NO; FC09_PRODUCTION_GATE UNCHANGED;
GLOBAL_DELTA NOT_PROVEN; M6_B OPEN; R2_RERUN_READY NO. Stop for package review.
NEXT EXACT CAUSAL EDGE: separate supervisor authorization for the pinned one
GetSectProps read; no authorization for additional getters or a172-point scan.
