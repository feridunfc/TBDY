# Column-R1 R3J — global displacement source-route reconciliation

Date: 2026-10-11. Scope: offline primary-source research and existing-owner inspection.

**Disposition: BLOCKED_EXACT_GLOBAL_DISPLACEMENT_SOURCE_SEMANTICS.**
The ETABS point-object global reporting convention is established. The exact
ETABS 23.2/API 2.014 `Joint Displacements` DatabaseTables field/basis/result-grain
contract is not yet established. The alternative PointElm matrix contract
remains unsupported. No global endpoint vectors or story Delta are issued.

## Integration prerequisite

[PR #202](https://github.com/feridunfc/TBDY/pull/202) merged R3I with original
commit ancestry preserved and 3/3 applicable CI SUCCESS. Independently fetched
post-merge main HEAD is `67e97215daeecb7e8ad84609656f3a1f6c64cc42` and TREE is `b398e969e8256d2c6e1d01110f5e4694ca6233b4`;
its parents are exact prior main `74b31465...` and original R3I `e3d06aa...`.
The main tree is exactly the original R3I tree. R3J started from that verified
merge. [Fresh integration receipt](COLUMN_R1_PR202_INTEGRATION_RECEIPT_2026-10-11.json)
records all 1489 accepted identities freshly PASS, no unresolved external skips,
and exact unchanged 17 PASS / 5 actual architecture FAIL diagnoses. The scoped
acceptance applies only to PR #202; the five failures remain debt.
The R3I source gate remains a factual blocked finding after integration.

## Primary-source findings and exact limits

| Primary CSI source | Established finding | Limit |
| --- | --- | --- |
| [ETABS Output Conventions: Displacements](https://docs.csiamerica.com/help-files/etabs/Output_Conventions/Displacements.htm) | Point-object displacement reporting uses global coordinates for ordinary point objects. Positive translations follow positive global axes. | The page does not identify `DatabaseTables.GetTableForDisplayArray`, specific FieldKeys or the `Results.JointDispl` element layer. It cannot relabel the retained local API records. |
| [ETABS Panel Zone Output](https://docs.csiamerica.com/help-files/etabs/Output_Conventions/Panel_Zone_Output.htm) | Panel-zone point-object displacements also use global coordinates. Beam-column and brace-column reporting selects the column-connected joint; beam-brace reporting selects the beam-connected joint. Internal panel-zone deformations have a separate local convention. | Current assignments and exact table-row/physical-element binding have not been captured. A joint-object identity is insufficient to invent the generated analysis-point choice. |
| [CSI Analysis Reference Manual, Rev.15, Chapter IV, printed p.47 / PDF p.69](https://docs.csiamerica.com/manuals/etabs/Analysis%20Reference.pdf) | Analysis joint displacement output is described in the joint-local system. | Preserve the distinction from ETABS point-object presentation. The sources do not themselves define where DatabaseTables applies the presentation conversion. This is a missing layer-specific contract, not permission to choose a basis from header spelling. |
| [ETABS enhancements, 21.2 database tables section](https://www.csiamerica.com/products/etabs/enhancements/20-20.0.0) | CSI names `Joint Displacements` and the separate `Joint Displacements - Absolute` as analysis-results database tables used for display/export. | Table existence does not prove its fields, coordinate basis or exact modal-row grain for the current API version. The absolute table is not silently substituted. |
| [CSI ETABS torsional-irregularity article](https://web.wiki.csiamerica.com/wiki/spaces/etabs/pages/1474589/Torsional%2BIrregularities%2Bcheck%2Bfor%2BResponse%2BSpectrum%2BAnalysis%2BRSA) | CSI describes accessing mode-related joint displacement values through the Joint Displacements presentation table. | The described procedure includes separately scaled per-mode combinations. It does not establish direct `OutputCase=Modal` 1–100 API rows or authorize creating combinations in FC09. No ASCE drift-average rule is imported into TS500 story translation. |
| [ETABS Labels and Unique Names](https://docs.csiamerica.com/help-files/etabs/Keyboard_Commands_and_Special_Features/Labels_and_Unique_Names.htm) | Labels repeat across stories; unique object names identify objects within the model. | Story/label alone or coincident coordinates cannot replace the exact 172 endpoint identities. |
| [PointElm.GetTransformationMatrix](https://docs.csiamerica.com/help-files/etabs-api-2016/html/ce6f071d-6809-d05e-7fe2-b2968ba6c9f2.htm) | The signature has a point-element Name and returned double-array Value. | The inspected page supplies types, without array ordering, multiplication direction or exact applicability to JointDispl Elm components. It adds no authority beyond R3I. |

The modern CSI modal article was fetched directly because the search service's
open operation returned an empty shell. Its actual HTML contains the described
table procedure. Raw fetched-byte SHA256/size and URLs are in the machine
receipt; no full copyrighted page is committed. Public primary sources establish
presentation-level facts; the table-specific global route is still an inference
that must be checked, not an approved numerical contract.

## Existing native evidence and owners

The exact original R3D capture SHA256 is
`83ce2ff7c3a6170e931d2869e212adde93b7c08b25bbf44e9f0c2c663f156b03`.
Its factual scope is 86 Columns, 172 endpoints, 100 modes and 17,200 signed
local JointDispl rows. Reused R3I retains all 172 object/element identity pairs.
**Global qualified endpoint rows remain 0; global top-minus-bottom pairs remain
0/8,600.** No extra amplitude, spectrum scaling or CQC statistic is computed.

The existing capture contains metadata for seven tables, including Point Object
Connectivity and Column Object Connectivity. It contains no `Joint Displacements`
table payload or field metadata and no panel-zone assignment/point-axis matrix
facts. Point Object Connectivity has 987 rows; Column Object Connectivity has
260 rows. The accepted +0.00 slice and its endpoint names are retained. Neither
table's coordinate fields establish displacement axes or panel-zone assignments.

Reuse these owners when the source contract closes:

- `tbdy_engine/etabs/oapi/database_tables.py`: native table parsing and exact
  eight-output GetAllFieldsInTable metadata ABI; independent descriptions/units
  bind by exact FieldKey, never header position or display units.
- `tbdy_engine/etabs/oapi/__init__.py`: session-bound table adapters.
- Gateway/safety DatabaseTablesReadTransaction and existing modal-range
  transaction: case selection, 1–100 output range, verified restoration.
- `tbdy_engine/etabs/oapi/joint_displacement_results.py`: retained local native
  API facts; do not change their semantics.
- `column_shear_topology.py`, `etabs_story_stability_result_provider.py`, and
  `story_relative_translation.py`: existing physical binding, factual provider
  and common-story engineering owners. No parallel owner is introduced.

No existing registry entry or typed consumer defines the exact Joint Displacements
global table contract. An existing generic reader can preserve unknown raw facts;
it cannot grant their engineering meaning or issue a current B5 epoch.

## Exact remaining contract

For the preferred table route, establish all of the following together:

1. An applicable CSI definition that the exact `Joint Displacements` table read
   through GetTableForDisplayArray reports point-object global translations,
   including the rule for rotated point-local axes.
2. Actual exact FieldKeys, descriptions and length-unit strings for identity,
   case, step/mode and X/Y/Z translations. `Ux/Uy/Uz` are possible spellings,
   not established field names. Local U1/U2/U3 cannot be renamed by assumption.
3. The output grain: direct signed Modal modes 1–100 versus combined/enveloped
   spectrum quantities or per-mode load combinations. No combo creation.
4. Unique point-object to physical column-connected analysis-point binding;
   native panel-zone applicability and unambiguous 172×100 / 86×100 coverage.
   Do not filter displacement rows by +0.00 alone: bottom and top endpoints have
   different point stories.
5. The existing session/source/capture and reversible output-range restoration
   contract. Missing/duplicate modes, multiple unresolved element grains,
   truncated tables, nonfinite values and unqualified units must block.

If that route cannot be source-qualified, obtain the exact PointElm nine-value
layout and local/global equation instead. LinkObj equations, default alignment,
matching names, orthogonality, a determinant of +1 and force-based reverse
engineering are not applicable PointElm authority.

## Focused CSI support request — draft only, not sent

Subject: ETABS 23.2 API 2.014 — Joint Displacements table global basis and PointElm matrix definition

We are qualifying signed per-mode endpoint translations for an offline
engineering workflow. Please provide an applicable ETABS v1 definition for
the following contracts, preferably a manual/API reference or a reproducible
rotated-point-axis example.

1. For `DatabaseTables.GetTableForDisplayArray("Joint Displacements", ...)`,
   are translation values in global X/Y/Z or the returned analysis point's local
   axes? Which exact FieldKeys and GetAllFieldsInTable descriptions/units identify
   each direction in ETABS 23.2? Does this remain true after a nonzero point-local
   axis assignment? Please distinguish this table from Results.JointDispl and
   Joint Displacements - Absolute.
2. For a selected existing modal case, what are the exact case/step/mode fields,
   and how are individual signed modes returned? Please distinguish direct modal
   case rows from scaled mode combinations and response-spectrum statistics.
3. With a beam-column or brace-column panel zone, which generated analysis
   point does each table row represent? How can its point-object unique name
   and exact column-connected point element be verified through API/table facts?
4. For `PointElm.GetTransformationMatrix(Name, ref Value)`, please define
   `Value[0..8]` ordering and the explicit multiplication equation connecting
   JointDispl's exact Elm U1/U2/U3 to global X/Y/Z. Does the matrix transform
   local to global or global to local? Please include one nonsymmetric rotation
   example, such as a +90-degree local-axis rotation, with both the returned
   array and expected transformed vector. State applicability to advanced axes
   and generated panel-zone points.

We will preserve existing local facts until the contract is qualified. No
protected-model mutation, analysis or design run is requested by this inquiry.

## Validation

R3J changes documentation/evidence only. Code, tools, tests, workflows and
safety-owner files are byte-identical to verified post-PR202 main. The 1489
accepted PASS identities are reused from the fresh PR202 execution, not
claimed as a new R3J run. A fresh exact-67e97215-main versus R3J negative
comparison executed both 22-test suites: each 17 PASS / 5 actual FAIL, with
identical complete diagnostics, guard hashes and allowlist; no new failure or
exception. Fresh compile/import, source-disposition/gate review and diff-check
PASS. No transform tests were added or counted.

See the [machine source-route receipt](COLUMN_R1_R3J_SOURCE_ROUTE_RECEIPT_2026-10-11.json)
for source snapshots, exact identities, failure sets and independent open gates.
This validation supports the documentation record; it does not close the
blocked source contract or constitute global displacement acceptance.

## Disposition and next causal edge

**R3J source research completed for the currently accessible sources; the
global displacement source gate remains BLOCKED.** The next edge is the exact
table-specific CSI definition above (preferred) or the direct PointElm matrix
definition. No transform, schema guessing, production patch, synthetic-transform
PASS claim, new native command or automatic capture is issued at this gate.
This support draft has not been sent to any person or service.

Retain: R3H separate R/V CQC CLOSED / REUSE; common story Delta NOT_PROVEN;
CURRENT_B5 NOT_PROVIDED; joint Delta/R/V PROJECT_DECISION_REQUIRED; M6-B OPEN;
R2_RERUN_READY=NO; B-BLOK engineering OPEN; Column-R1 software CLOSED.

Once primary authority closes the contract, implement within the existing owners
and prepare a bounded, separately authorized native acquisition for missing facts.
Then prove exact population/physical binding. Global per-column vectors alone
still do not close common story translation, current B5 lineage or M6-B.
