# COLUMN-R1 R3L — accepted schema and precise global route

Disposition: **native schema CLOSED; global coordinate contract BLOCKED**.
This is an offline adoption, source reconciliation and acquisition design.
No ETABS execution, result recapture, global vector or engineering Delta is issued.
R3D–R3K findings are reused; no general source research is reopened.

## Immutable P1 adoption

Supervisor accepted the operator's original
`column-r1-r3k-schema_20261011_130341_474.json` at SHA256
`ff0aef659643b6d30954f5c6289efcf896666ba0fe6e6358179fad63c6707eb4`.
The original JSON and sidecar remain outside Git and are read without modification.
The [derived index](COLUMN_R1_R3L_P1_DERIVED_INDEX_2026-10-11.json) contains hashes
and observations, not copies of original raw getter responses. The adoption tool
recomputes whole-file/sidecar hashes, both canonical raw hashes, all field counts,
unique keys, raw-versus-decoded metadata, source SHA, identity hashes and native
unit observations. It requires the exact R3K HEAD/TREE and clean capture anchor.
All checks pass against the original bytes, rather than the supervisor summary.

The available-tables hash is the canonical hash of the retained empty response
placeholder: **no GetAvailableTables call was observed**. Its ABI was unavailable;
this does not establish absence or emptiness of Joint Displacements. In contrast,
GetAllFieldsInTable was observed with return code 0, table version 1 and 14 fields.
Ux/Uy/Uz have native unit m; Rx/Ry/Rz have rad. The original PID is 2072,
ETABS 23.2.0 / API 2.014. Protected FC09 SHA, full identity, lock and independently
observed present/database units are unchanged before/after in that receipt.
These are historical P1 observations, not a current session or B5 attestation.

## Three evidence layers and the missing bridge

Reuse the accepted [R3J source report](COLUMN_R1_R3J_GLOBAL_DISPLACEMENT_SOURCE_ROUTE_2026-10-11.md)
and its [source snapshot receipt](COLUMN_R1_R3J_SOURCE_ROUTE_RECEIPT_2026-10-11.json).
No repeated public search is claimed. Source URLs and retrieval hashes remain
those already archived in R3J.

| Layer | Established authority | Exact limitation |
| --- | --- | --- |
| CSI [Displacements](https://docs.csiamerica.com/help-files/etabs/Output_Conventions/Displacements.htm) | Ordinary point-object reporting uses global coordinates, with positive translations along positive global axes. | Does not name the DatabaseTables API, FieldKeys, or conversion from analysis-joint local output. |
| CSI [Panel Zone Output](https://docs.csiamerica.com/help-files/etabs/Output_Conventions/Panel_Zone_Output.htm) | Point-object displacement reporting remains global; beam-column/brace-column uses the column-connected joint, beam-brace the beam-connected joint. | Does not supply this model's assignments, generated-joint identities or a table-row element binding. |
| Original ETABS 23.2 P1 schema | UniqueName identifies an associated point object **if one exists**. Story is associated with the point element. Ux/Uy/Uz describe X/Y/Z joint displacement. Modal StepType is Mode; StepNumber is mode number. | Does not explicitly say global X/Y/Z, guarantee one element per associated object, or identify the generated analysis joint represented by a row. |

The combined evidence strongly suggests the presentation table route, but this
is an **inference**, not a layer-specific coordinate contract. Schema association
with a point object does not prove that the API applies the presentation basis
conversion, nor that all associated generated points collapse to its reported
point-object joint. The accepted analysis reference distinguishes joint-local
analysis output (Rev.15, printed p.47 / PDF p.69). Neither X/Y/Z wording nor an
object UniqueName resolves that distinction for this API/table/version.

Thus GLOBAL_COORDINATE_CONTRACT remains BLOCKED. No schema-derived transpose,
identity matrix, local-to-global relabeling or coordinate-nearest matching is
introduced. PointElm remains the alternative with its ordering/direction and
JointDispl applicability gates unchanged.

## Modal grain

Native modal **field semantics are proven**: Mode and mode number. StepType Mode
also occurs for buckling, so it alone does not identify the accepted modal case.
OutputCase may name either a case or combination. CaseType's description gives
no exact modal display token. StepLabel is blank outside the stated staged
construction grain. No P1 result rows establish an actual CaseType token, signed
eigenvector population, record multiplicity or output-range coverage.

MODAL_RESULT_GRAIN_CONTRACT remains BLOCKED until applicable table authority
links the existing Modal case to direct signed individual modal shapes and the
exact CaseType token, with no spectrum envelope, scaled combination or unsigned
magnitude interpretation. P2 rows must then independently prove all modes 1–100.
Schema success cannot supply those rows or a fresh analysis epoch.

## Exact physical binding plan

The [derived physical plan](COLUMN_R1_R3L_PHYSICAL_BINDING_PLAN_2026-10-11.json)
reuses original R3D SHA
`83ce2ff7c3a6170e931d2869e212adde93b7c08b25bbf44e9f0c2c663f156b03`.
It retains 86 factual Columns in the accepted +0.00 column slice, 172 exact
endpoint objects, 100 modes, 17,200 existing local JointDispl identities and
8,600 expected physical top/bottom pairs. Existing topology owner determines
top/bottom from exact native connectivity and reviewed geometry. Coordinates
orient an already identified physical column; they never substitute an identity.

Each column's UniquePtI/UniquePtJ is joined exactly to Point Object Connectivity
UniqueName. Duplicate, missing or substituted names block. The point object's
own Story is retained separately from the column Story: actual top objects are
+0.00 and bottom objects are Base. **Never filter both endpoints to +0.00.**
Each accepted local Elm is an observation, not proof of the future table's Elm.

After a source-qualified object/element Story bridge, match prospective table
rows by the complete key:
`(Story, UniqueName, OutputCase, CaseType, StepType, integral StepNumber)`.
Require exact retained endpoint name and its verified element-story relation,
OutputCase=the existing accepted Modal case, separately qualified CaseType token,
StepType=Mode and an integer mode in 1–100. StepLabel must be blank. Labels are
corroborative only. Keep unrelated raw rows in evidence; exclude them from the
172-endpoint subset only through a documented exact identity filter. No duplicate
selection, first/last pick, averaging, rounding or assumed one-to-one mapping.
An equal duplicate still blocks. Each endpoint must have exactly 100 rows; each
of 86 columns must have both physical endpoint rows for each of 100 modes.

P1 has no element identifier field beyond an associated-object identity. Prove,
for every endpoint, native panel-zone absence or its exact assignment/type and
connectivity rule, the column-connected analysis joint, and how this table row
selects that joint. A native assignment list must establish complete coverage and
the meaning of omitted assignments; absence from an unqualified list is not proof.
For assigned zones preserve every generated joint and its connected column/beam/
brace identities. Require an applicable API/table definition of the exact mapping
to the table row. If the 14-field table cannot disambiguate those joints, obtain
an applicable CSI mapping contract or a separately reviewed native mapping getter;
do not invent an Elm FieldKey or a getter signature. Beam-brace or mixed/unknown
connectivity cannot be silently treated as column-connected. The R3D object/Elm
name equality and coincident coordinates do not prove this result-layer bridge.

PHYSICAL_POINT_BINDING and PANEL_ZONE_APPLICABILITY remain BLOCKED. The physical
object topology is retained and proven; the new table-result binding is open.

## CSI support addendum — DRAFT / NOT SENT

Preserve all four questions in the R3J support draft, including the PointElm
fallback. Attach the following exact missing question if authorized to submit:

For ETABS 23.2.0 / API 2.014, does
`DatabaseTables.GetTableForDisplayArray("Joint Displacements", ...)` return
Ux/Uy/Uz in the global coordinate system under the ETABS Output Conventions,
including nonzero/advanced point-local axes? Please explicitly identify the
conversion boundary from joint-local analysis results to this database table.
The native version-1 schema identifies an associated point object if one exists
but names only X/Y/Z directions. Is this the same reported joint defined by Panel
Zone Output, or can multiple generated analysis joints produce rows associated
with one UniqueName? Please give the exact native means to prove the table row's
column-connected analysis-joint identity and Story for each endpoint. For a direct
existing modal case, provide the exact CaseType token and confirm signed individual
Mode/StepNumber shapes, normalization and multiplicity, distinct from buckling,
per-mode combinations and response-spectrum envelopes. Please cite an applicable
versioned CSI definition or provide a rotated-axis/panel-zone example whose API
table output and analysis-point binding establish these contracts.

No CSI answer is claimed. Any positive answer must be archived with its date,
complete original text, authority reference and applicable program/API scope.
No request has been sent by the worker.

## Downstream state

The [separate P2 design](COLUMN_R1_R3L_P2_CAPTURE_DESIGN_2026-10-11.md) is prepared
but blocked before authorization. Offline rejection tests exercise schema drift,
mode identity, duplicate endpoints, panel ambiguity and false global promotion.
They do not establish engineering authority or supply native result rows.
GLOBAL_ENDPOINT_MODAL_ROWS=0; GLOBAL_STORY_DELTA=NOT_PROVEN;
CURRENT_B5=NOT_PROVIDED; JOINT_DELTA_R_V=PROJECT_DECISION_REQUIRED;
M6_B=OPEN; R2_RERUN_READY=NO; ETABS_EXECUTED_BY_WORKER=NO;
SOURCE_MUTATED=NO. Column-R1 software remains CLOSED; B-BLOK engineering OPEN.

Next exact causal edge: obtain and archive the applicable CSI table-coordinate,
signed modal grain and panel-zone/result-element bridge. Then review the minimal
binding facts and selection plan before proposing a separately authorized P2.
