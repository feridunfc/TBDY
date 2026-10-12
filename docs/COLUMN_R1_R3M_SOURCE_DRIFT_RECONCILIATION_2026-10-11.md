# R3M current candidate source reconciliation

The supervisor reports a changed on-disk model at the same path. Historical EDB
recovery is not a prerequisite to investigating the current candidate. No FC09
production authority, result epoch or engineering qualification transfers to it.

| Identity | Source | Authority |
| --- | --- | --- |
| Historical | `C:\tmp\B-BLOK_Revised.EDB`, SHA256 `FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F` | Accepted FC09 evidence only; existing production gate unchanged |
| Current candidate | Same path; supervisor abbreviation `61FA288F...246621` | Candidate investigation only; full 64-hex SHA and current native fact receipt not supplied |

[Derived evidence index](COLUMN_R1_R3M_SOURCE_DRIFT_DERIVED_INDEX_2026-10-11.json)
preserves the two identities, original receipt hashes, observation gaps and the
external candidate script SHA. No original native response is copied or modified.
The original FC09 matrix probe remains byte-identical, SHA256
`3531a45013ab57dd6993ead7b1fa71117a690b3a0f22c14c296cced9e1cb391d`.

## Comparison available now

| Fact | Accepted FC09 evidence | Current candidate | Finding |
| --- | --- | --- | --- |
| Model path | Exact protected path | Same, supervisor reported | Path equality does not establish source equality |
| File SHA | Full FC09 identity | Different `61FA288F...246621`, supervisor reported | Source identity drift is reported; full current SHA not independently available |
| 1044 / LC_DL | Original manual native six components retained under original SHA `ef4bbadc3fb034f59533f6279c816cba8713ab3649950fce12018a8db4f82a29` | 6/6 match at displayed precision, supervisor reported | Bounded single-row comparison; no independently supplied current raw values or precision interval |
| 1044 matrix | Historical native identity matrix | Not observed in a current-source receipt | Historical identity cannot qualify current matrix direction or global semantics |
| Frame population / section assignments | 998 native frames; 998 factual assignments | Not observed | Compare native name sets and each native assigned property |
| Section mechanics | 15 accepted native GetSectProps responses in verified m units | Not observed | Compare all twelve numeric outputs, same units; tight tolerance explicitly retained |
| Physical population | 86 Columns, 172 endpoints; both Base and +0.00 stories | Not observed | Require exact current native column connectivity, per-point story and coordinates |
| Analysis point identities | Original local-result Obj/Elm binding retained | Not observed | Obtain current PointObj.GetElm; retain historical and current names separately |
| Materials, mass, loading, modifiers, releases, constraints, area mesh, analysis settings, panel zones | Partial historical coverage; no complete whole-model invariant | Not observed | Explicit remaining gaps; no conclusion of engineering equivalence |

`ENGINEERING_RELEVANT_PROPERTIES_CHANGED=NOT_ESTABLISHED_CURRENT_NATIVE_FACTS_NOT_OBSERVED`.
This means the evidence cannot yet decide whether they changed. Matching one
displacement row is not an unchanged-model certificate. A SHA difference alone
does not identify an engineering change or distinguish model edits from stored
result/bookkeeping changes. Current analysis-point renumbering is a binding
difference; it alone does not prove changed engineering properties.

## Prepared candidate fact census and matrix scan

`column_r1_r3m_candidate_probe.py` is a separate, repository-external artifact.
It accepts only an explicitly supplied full 64-hex SHA matching the supervisor's
current prefix and suffix and differing from FC09. It does not discover a hash
and automatically confer authority on it. The operator records the full value
as the candidate pin; Python and PowerShell independently check it before and
after. Python also checks it between native matrix reads and during the fact
census. Neither historical EDB bytes nor a restored old ETABS session is required.
The immutable historical receipts are the comparison baseline.

The existing verified PID gateway owns attachment and STA execution. Exact
loaded path, explicit existing PID, ETABS 23.2.0/API 2.014, model lock, consistent
present/database m units, session identity and clean authorized HEAD/TREE are
required. No alternate instance or attachment fallback exists. Original receipt
hashes are checked before and after. Generated native ABI must have the exact
pure-input/output signature before each new getter can be called; unsupported
or malformed ABI stops the probe without speculative argument variants.

The fact census reads FrameObj.GetNameList/GetSection/GetPoints,
PropFrame.GetSectProps, and PointObj.GetLabelFromName/GetCoordCartesian/GetElm.
It compares accepted frame assignments and section properties, and the exact
172 historical endpoint stories, global coordinates and 86 Column endpoint
pairs. Numeric comparison uses relative and absolute tolerance 1e-12 in the
same verified native units; strings/connectivity are exact. Native raw responses,
generated ABI and canonical response hashes stay in the new external receipt.
The historical Column endpoint orientation is not repaired or reversed on a
mismatch. Geometry/story/connectivity drift or duplicate current element
mapping stops the matrix stage. Changed section properties remain visible and
do not prevent a bounded candidate investigation of otherwise identical physical
endpoints. Missing fact categories remain unobserved even if every measured
comparison matches.

For each independently verified current endpoint, the probe reads the actual
nine-value PointElm.GetTransformationMatrix using the current native associated
element, retaining its historical element separately. It does not assume an
object name is an element name or use nearest-coordinate matching. PointObj.GetElm
does not by itself prove the column-connected panel-zone internal-joint contract.
That applicability remains BLOCKED.

The matrix ABI, successful return code, nine finite values, orthogonality,
determinant and unchanged source/session/units/selection are required. Identity
and nonidentity are matrix observations only. NOT_FOUND requires all 172 valid
observations and all integrity checks. Partial or failed scans are NOT_OBSERVED.
No offline synthetic result is relabelled as a native observation.

Only when LC_DL is already the sole selected case with no selected combinations
may the existing JointDispl getter read a nonidentity endpoint. Otherwise the
static comparison stage is blocked without changing selection. Exact Obj/Elm,
one LC_DL row, Single Value/0 grain and six finite components are required.
The two unqualified products T times Ulocal and transpose(T) times Ulocal are
retained separately. An eligible nonzero translation must separate the candidates
by more than the verified GUI rounding quantum plus numerical margin. The
output identifies exact Story/UniqueName/LC_DL and refuses duplicate GUI rows.
Identity-only, zero-displacement or indistinguishable candidates do not qualify
global coordinates.

## Operator prerequisites and command

Both operator files stay outside Git. Use the reviewed Python/comtypes
environment, the exact clean R3M checkout specified in the separately supplied
PowerShell artifact, and original unchanged R0 preflight, R3D and manual receipts
at their documented `C:\tmp` paths. Inspect the existing ETABS PID 2072 and loaded
model path before attaching. Record the current full candidate SHA independently
and pass it explicitly. Record the existing GUI translation unit m and decimal
places. Do not change units, result selections, model state or lock. No concurrent
operator edits are permitted during the read. Create a fresh external receipt;
the script never overwrites an original. Its total budget is 900 seconds; the
fact census is bounded to 300 seconds and 2000 records, individual matrix/static
STA calls to 30 seconds. A timeout invalidates the receipt and disallows continuation.

```powershell
& 'C:\tmp\column_r1_r3m_candidate_operator.ps1' `
  -CandidateSha256 '<FULL_64_HEX_CURRENT_CANDIDATE_SHA>' `
  -GuiDecimalPlaces <EXISTING_GUI_DECIMAL_PLACES>
```

The placeholders are deliberately not executable. The supplied PowerShell
artifact verifies the exact external Python SHA, PID, source SHA and checkout,
and passes the full candidate pin into Python. No live execution is performed
by the worker. This prepared command does not authorize P2 or production.

## Boundaries and next evidence

No RunAnalysis, StartDesign, Save, SetPresentUnits, model/analysis-state mutation,
Results.Setup setter, DatabaseTables selection mutation, modal recapture or
global result-table acquisition exists in this package. With a getter-only
transaction there is no selection restoration setter: a changed selection
invalidates the receipt. CSI support remains an unsent draft.

`NONIDENTITY_POINT_FOUND=NOT_OBSERVED_PENDING_OPERATOR_SCAN`.
`GLOBAL_ENDPOINT_MODAL_ROWS=0`, `GLOBAL_STORY_DELTA=NOT_PROVEN`,
`CURRENT_B5=NOT_PROVIDED`, `JOINT_DELTA_R_V=PROJECT_DECISION_REQUIRED`,
`M6_B=OPEN`, `R2_RERUN_READY=NO`, `ETABS_EXECUTED_BY_WORKER=NO`.

Next exact causal edge: original current-candidate fact-census/matrix receipt
and sidecar, bound to the full new SHA and exact verified session. Compare its
observed properties and gaps with FC09 without rebinding authority. If an
eligible nonidentity/nonzero LC_DL endpoint exists, obtain its exact GUI row
and precision to discriminate the two hypotheses. If all 172 valid matrices
are identity, close only this current candidate population as NOT_FOUND and
propose a separate nonidentity experiment; do not invent PASS.
