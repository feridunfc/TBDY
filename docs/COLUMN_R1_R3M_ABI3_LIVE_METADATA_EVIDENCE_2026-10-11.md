# R3M ABI-3 original getter-free metadata receipt verified

ABI3_LIVE_METADATA is RECEIPT_VERIFIED_CLOSED. This is original generated COM
metadata evidence from the operator's single bounded STA observation, not live
getter qualification. Native factual/result getter invocation counts are zero.
No worker ETABS execution, subsequent operator execution or automatic retry occurred.

Original JSON:
`column-r1-r3m-abi3-metadata_20261011_222037_269_84ded0e2a7c047c1a7d07fd6e6d61369.json`.
Whole-byte SHA256:
`11355e6860ba435e1275a7251efb0a5701268e4293c98c58a9231b2194f5b5be`.
Original sidecar byte SHA256:
`3aac65362db7c6de5a63fb8625a96185104e7091ac50ced9e1b3b49ac6cf5797`.
Whole JSON hash, sidecar hash/content and all eight canonical raw metadata hashes
were independently recomputed. Originals remain unchanged outside Git. Only
selected derived facts and hashes are recorded here and in the derived adoption
index; original metadata trees and native responses are not copied into Git.

Capture HEAD `c66bb0e6ce574ff3f667e324660d26c8e0cb055e`, TREE
`794dac8a5cf3a408cf9609ba7523d122254f38b5`. Exact external Python SHA256
`b46144d729c0f539fa629752f14a5149905746bc551370f6cc5d1eca5725acc4`
matches the offline-qualified artifact. Its clean Git/source/original-evidence
pre/post guards passed with errors empty. The capture ran 2026-10-11
19:20:37.567562–19:20:38.285348 UTC, on PID2072, ETABS23.2.0/API2.014,
Python3.14.0/comtypes1.4.16. Accepted original ABI-2 JSON/sidecar hashes and
identity were independently reverified against the supplied original ABI-2 pair.
ABI-1/ABI-2 remain CLOSED; GetNameList was not rerun.

## Eight observed declarations

Each existing owner resolved through `__com_interface__`. For each method there
is exactly one `_ComMemberSpec` in `_methods_`; inherited IDispatch/IUnknown
metadata causes no matching ambiguity. `_disp_methods_` is absent throughout
these observed MROs. HRESULT transport, final LP_c_long OUT|RETVAL and exact
ordered parameters/ctypes/SAFEARRAY structure agree with the pinned source
comparators. Actual target method callables were neither accessed nor invoked.

| Getter | Observed numeric flags in parameter order | Metadata status |
| --- | --- | --- |
| FrameObj.GetSection | 1, 3, 3, 10 | OBSERVED_LIVE / source-compatible |
| PropFrame.GetSectProps | 1, twelve ×3, 10 | OBSERVED_LIVE / source-compatible |
| FrameObj.GetPoints | 1, 3, 3, 10 | OBSERVED_LIVE / source-compatible |
| PointObj.GetLabelFromName | 1, 3, 3, 10 | OBSERVED_LIVE / source-compatible |
| PointObj.GetCoordCartesian | 1, 3, 3, 3, 17, 10 | OBSERVED_LIVE / source-compatible |
| PointObj.GetElm | 1, 3, 10 | OBSERVED_LIVE / source-compatible |
| PointElm.GetTransformationMatrix | 1, 3, 10 | OBSERVED_LIVE / source-compatible |
| Results.JointDispl | 1, 1, twelve ×3, 10 | OBSERVED_LIVE / metadata-only |

The derived adoption index records exact parameter names, original flags, IIDs,
scalar/array ctypes classes, declared output order and independent raw hashes.
GetSectProps I22/I33 provenance/order is preserved. JointDispl NumberResults and
all eleven parallel arrays are declared INOUT; the declared ItemTypeElm is
c_long, but no enum selection or result scope is inferred from its type.

GetCoordCartesian X/Y/Z are observed INOUT=3 before CSys. CSys has flag17
(IN|OPTIONAL) and the original default `Global`. This confirms the historical
second positional string cannot be treated as the CSys slot. The named input
plan remains offline-qualified against dependency source; the actual remaining
bound-wrapper code/closure identity is NOT_YET_OBSERVED. No replacement wrapper,
new native call or speculative overload was introduced.

GetElm has an observed scalar BSTR byref declaration. This does not prove
one-to-one physical/analysis-joint mapping or panel-zone applicability.
GetTransformationMatrix has an observed SAFEARRAY(Double) byref declaration;
no actual nine-value matrix, component order or transformation direction was
observed. JointDispl output array metadata supplies no actual case/mode row grain,
modal multiplicity, signed displacement or physical result binding.

## Integrity and limits

Current candidate source before/after SHA256 is exactly
`61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621`.
Loaded path, PID attachment strategy, ETABS version/API, session identity, locked
model and accepted present/database units match each other and original ABI-2.
Historical FC09 identity stays separate:
`FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F`.
FC09 production gate is UNCHANGED; source authority was not rebound.

Selection was NOT READ in this metadata scope. An independent selection
before/after comparison is not claimed. The pinned artifact has no selection
access/setter, no Results.Setup or DatabaseTables access, no model/analysis/design/
save/unit mutation and no attachment fallback. One metadata callback produced
8 records, errors=[]; native return codes and responses for these target getters
remain NOT_OBSERVED. Matrix/result row counts are zero.

Fresh offline regression and negative architecture results are recorded in
`COLUMN_R1_R3M_ABI3_LIVE_METADATA_ADOPTION_2026-10-11.json`. All 1949 accepted
PASS identities and their files are preserved, including the earlier 1856.
No new implementation/test/guard change is part of this documentation-only
adoption. Existing six real architecture FAIL remain FAIL, with unchanged full
violation sets and protected surface hashes. Original artifact hashes remain
unchanged; the capture wrapper remains bound to its original checkpoint and is
not retargeted or proposed for a rerun.

NEXT EXACT CAUSAL EDGE: offline prepare remaining actual bound-wrapper
code/closure qualification against these observed declarations. Any new
operator metadata/getter execution requires its own bounded authorized scope.
LIVE_GETTER_CONTRACTS QUALIFIED=0; FULL_FACT_CENSUS NOT_AUTHORIZED;
172_MATRIX_SCAN NOT_AUTHORIZED; P2_GLOBAL_CAPTURE NOT_AUTHORIZED.
GLOBAL_DELTA NOT_PROVEN; M6_B OPEN; R2_RERUN_READY NO; worker ETABS NO.
