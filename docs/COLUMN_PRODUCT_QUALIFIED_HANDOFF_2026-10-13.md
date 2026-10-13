# Column product: canonical typed-result handoff

Continuation of reviewed `d57d5e7ddaaee9d1dd87c1c5b78af36cdb2ce886`, tree
`a342f66a7f3aed50d7d73cbefca85f0c8065dbc5`, on the same worker branch.
PR #208 remains draft and unmerged. This is a read-only application consumer,
not a new lineage issuer or a live calculation launcher.

The existing production `project_execution.execute_project` lifecycle owns
acquisition, controlled analysis, qualified B5, controlled B6 and engineering
sequencing. It is NOT called by HTTP or the UI. Original in-process results
may be handed to `QualifiedColumnChannel.publish(project, scope=..., label=...)`
and `make_server(repo, qualified_channel=channel)`. The existing screen then
offers exact component/variant handles. `Hesapla` validates and consumes the
existing owner result; PDF/HTML/JSON consume that same result. There is no
serialized artifact import, HTTP publisher or replacement issuer.

The host scope includes source-model ref, model fingerprint, project
EvidenceEpoch, P7 content-derived force-bundle epoch, force/length units and
origin. The two epochs are different existing contracts. Publication checks
the original B5/B6 qualification classes, state/result object continuity,
canonical FND2 snapshot/quantity/provenance binding, original B6 component
projection, selected-rebar causal provenance and P7 content/B5/unit binding.
Every consume revalidates the objects and checks their published digest.

Draft/review input remains a separate contract. Client values cannot obtain
B5/B6 authority, alter a registered result or copy a sibling's selected cage.
Changing context, source, epoch, units or submitting unsupported editable
values invalidates the workspace result before rejection. A new force,
material or cage result requires the existing owner to evaluate a new
qualified input and publish its original typed output. No live issuer is
hidden behind the button.

## Offline proof

`tests/product_reports/test_column_qualified_workspace.py` reuses the existing
`test_column_public_mixed_vertical` test lifecycle. Only its already-existing
test native transport is mocked. FND2, PMM/selection, longitudinal detailing,
VS5 axial, P7, Vc, final cage, confinement and A38-A40 owners remain real.
Instrumentation wraps original functions and delegates unchanged; no decision,
readiness, capacity or selected cage is injected.

The first supported component reaches canonical ENGINE_SELECTED_REBAR and
applicable axial/shear evaluations. The other component retains its actual
A18/A19 unresolved end-restraint/free-length result. Doubling only reviewed
shear spacing from 100 to 200 mm produces a changed confinement-owner shear
capacity. Both variants and the owner-blocked sibling use the same server,
screen and export endpoints. Their source is OFFLINE_TEST_LIFECYCLE, never235.

FND2 READY does NOT close all engineering: PROVIDED_ASH_NOT_AVAILABLE,
SPECIAL_TIE_DETAILING_FACTS_NOT_AVAILABLE and FINAL_DETAILING_REQUIRED remain
the real owners' results. Ash is not inferred from Asw. There is no new
governing selector: exact owner demand states, case/end/station identities,
selected-candidate PMM/required-area decisions and all canonical coverage
contributions are retained in the manifest and report.

## Real235 ordered dependencies

| Required datum/artifact | Exact existing owner/contract | Existing evidence | Exact missing proof | Specific decision / operator dependency |
| --- | --- | --- | --- | --- |
| Section assignment | ABI-4 GetSection235 | Accepted candidate Column_80x80 receipt | None in its accepted scope | REUSE; no getter rerun |
| I22/I33 | ABI-5 GetSectProps / native m4 provenance | Accepted binary64 match in this named section only | Other ten properties lack comparable historical authority | REUSE two inertias; no section-name geometry reconstruction |
| Endpoint object names | ABI-6 FrameObj.GetPoints235 | Prepared pinned package at98f15e0 | No live original receipt | Separate supervisor authorization for that existing one-call package only; no bottom/top inference |
| Dimensions, coordinates, local axes, offsets and connected beam restraints | StrictColumnTopologyBundle / A18-A19 source-bound contracts |235 assignment and inertias only | Source-bound topology, orientation, clear length and incident beam/member stiffness population | Separate bounded factual acquisition review after endpoint receipt; GetPoints alone cannot qualify topology |
| Concrete/steel identity and design strengths | UsedRcMaterialPopulation + ReviewedColumnDesignBasis / BoundColumnDesignBasis | No current235 qualified material binding | Same-source material usage and explicit fcd/fyd/fywd/aggregate/ductility reviews | Read-only material facts separately; engineer reviews design strengths and ductility, with units and refs |
| Current design actions | qualified AnalysisLineageQualification / B5 + canonical A23 demands | Historical FC09 local modal archive, separately current61FA candidate | Current61FA analysis input/result continuity, exact case/end/station, combination definitions and force semantics | Existing B4B/B5 issuance requires separately authorized controlled analysis on owned scratch if no qualified artifact exists; UI cannot issue it; protected original remains unchanged |
| Modal stability action | A17 / TS5007.13 stability runtime | M6-A/R3D accepted factual scope | M6-B source-authorized modal action and combination law | Specific engineering/source decision before modal stability authority; not a factual getter or software guess |
| PMM and canonical longitudinal selection | original qualified B6 + column_longitudinal_runtime | Named section facts only | Current-source selected design-combo scope, B6 lineage, required-rebar rows, catalog/intent and material binding | Existing B6 issuance would require separately authorized controlled StartDesign on owned scratch if absent; never called by this UI |
| Axial scope | ReviewedVs5ColumnAxialContext / exact Ndm binding | No qualified235 design-force bundle | G/Q/S/E membership, compression sign, reduction policy and final-combination mapping | Engineer approves explicit member load binding and TS498 policy; current B5 forces remain a separate prerequisite |
| P7, Vc, final cage and confinement | ReviewedColumnP7RuntimeContext / ReviewedColumnVcRuntimeContext / ReviewedColumnFinalCageContext / A36 | No qualified235 cage/shear bindings | Exact paired end demand states, D-amplified authority, short-column applicability, actual cage and independent Ash/detailing facts | Engineer reviews those exact selectors and cage facts; no Asw-to-Ash substitution, no guessed station or response-spectrum concurrency |
| Engineering readiness and coverage | existing FND2, A38-A40, FCR report owners | Actual235 remains blocked | All applicable original owner results on current source/epochs | Consume the original ProjectExecutionArtifact only after those owners run through their authorized lifecycle |

ABI2-5 CLOSED/REUSE. ABI6 operator HEAD/pins and scoped LF rule unchanged.
No new getter package was implemented. Its existing package is the smallest
pending native edge, not a prerequisite for this offline software work.

Launch the default offline workspace: `python tools/start_column_product.py`.
It starts with no qualified current235 artifact; imports/reviews cannot create
one. Full current235 engineering integration/readiness is **NOT COMPLETE**:
trusted issuance dependencies above still require separate authorization.

WORKER_ETABS=NO; new native getters=0; FC09 gate UNCHANGED;
GLOBAL_DELTA=NOT_PROVEN; M6-B=OPEN; R2_RERUN_READY=NO.
