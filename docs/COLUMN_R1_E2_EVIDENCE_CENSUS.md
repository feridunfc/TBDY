# COLUMN-R1 E2 — existing whole-system authority / canonical gate census

## Decision

EDGE: E2 / REUSE_AS_IS. Production patch needed: **NO**.
Starting HEAD: `1afe6a5baf08af496910734695e3eb901c9fd9bb`.
Starting TREE: `2cf7655ebfa06132f85b64f25199cae456fa0ebd`.
Worktree was clean; `checkpoint/column-r1-e1-20260927` on origin matched HEAD.

The supplied `BLOCKED_TS500_EQ7_13_GLOBAL_UNCRACKED_BASIS_NOT_PROVEN`
is emitted by the deliberately limited I2/I3 audit in
`design/columns/stability_stiffness_basis.py`, not by the whole-system owner.
Its `proves_uncracked` property always returns False. This remains correct:
unit assigned-frame bending modifiers cannot prove a whole-system state.

`regulatory/fnd_col_2.py:evaluate_column_design_readiness` retains this audit
inside the result. `design/columns/column_design_readiness.py` uses canonical
second-order blockers/state bases on the public stateful path; it does not
promote the limited audit status into a canonical blocker.
The new public-root test proves that a fixture can have READY/MATCH and empty
`blocked_items` while this limited audit status remains unchanged.

## Required contributor census

All paths below are relative to `tbdy_engine/`.

| Required evidence | Existing acquisition / composition | Qualification requirement |
|---|---|---|
| Complete Frame denominator | `providers/etabs_frame_eq713_population_provider.py:capture_frame_eq713_factual_population` | Exact `FrameObj.GetNameList`; supported and residual rows partition every identity once. |
| Frame scope and identity | Same provider: exact assignment/object-type facts, snapshot, residual structural facts, line-spring universe when applicable | Factual type/section/material/role, no name-derived participation; residual rows cannot disappear. |
| Complete Area denominator | `providers/etabs_area_contributor_provider.py:capture_area_contributor_population_from_session` | Exact `AreaObj.GetNameList`; supported and typed-out-of-slice rows account for every identity once. |
| Area scope and identity | Same provider: property family, orientation, local axes, diaphragm, assignment, overwrite, property/object modifiers, material facts | Same model/epoch/session for every row; exact material/property identities and physical parameters. |
| Frame gross/current basis | Frame base snapshot, section mechanics, releases, isotropic material, property/object modifiers | Preserved factual material E/G and gross/current physical section basis; supported end conditions; immutable-state continuity. |
| Area gross/current basis | Simple property thickness/formulation, material basis, overwrite qualification, property/object vectors | Gross geometry/thickness and homogeneous property qualified; non-unity AreaObj vector remains unsupported without slot authority. |
| Whole population disposition | `application/column_public_a5.py:_build_a3` → `analysis_basis/eq713_uncracked_analysis_state.py:Eq713PopulationDisposition` | Exact Frame and Area denominator reconciliation; every row qualified and applicable contributors equal qualified contributors. |
| Qualified analysis generation | `_analysis_basis_refs`, `_run_a3_generation`, `_prove_post_continuity` in the same composer | Frame/Area/disposition provenance → verified target manifest → exact qualified B5 child identity → unchanged factual populations/physical basis. |

Actual B-BLOK Frame/Area counts and per-object dispositions are not present in
the slim summary/receipt and are **NOT re-enumerated or invented** here.
The table identifies the exact required universe and owners, not a synthetic
replacement for the actual model population. No source EDB was accessed.

## Participation and mode census

- Frame modes: AXIAL, SHEAR_2, SHEAR_3, TORSION, FLEXURE_2, FLEXURE_3.
- `analysis_basis/eq713_frame_mechanics.py` resolves the supported straight,
  strictly vertical, no-release Column horizontal-translation slice: shear and
  flexure participate; local-1 axial/torsional modes have explicit exclusion.
- Other unresolved supported Frame modes require factual response plus
  conjugate physical stiffness through `eq713_response_mechanics.py`.
  Zero/missing response is not a non-participation certificate.
- Area modes: F11/F22/F12 membrane; M11/M22/M12 plate; V13/V23 transverse shear.
- Semi-rigid concrete Floor in-plane modes require positive participation.
  Membrane has explicit plate/transverse-shear non-applicability.
  ShellThick unresolved modes require qualified response evidence.
- Supported Wall mode mapping requires factual pier/spandrel role and default
  local-axis evidence; unknown plate/shear participation remains blocked.
- NULL/no-property and typed residual applicability stay with their existing
  factual owners. Unsupported formulation/material/scope remains explicit.
- Existing dispositions are unchanged: TARGETED_UNCRACKED,
  PROVEN_NON_PARTICIPATING_MODE, PROVEN_NOT_APPLICABLE, BLOCKED_UNSUPPORTED.
- `_b4b_targets` normalizes only authority-targeted modes, preserves other
  modes, and checks shared-property consistency. Final `a3.positive` is still
  mandatory after any response-subset convergence.

## Exact evidence/composition conclusion

The existing public path already binds whole-system evidence before A17:
complete contributor acquisition → mode dispositions → target/readback and
qualified B5 generation → whole A3 positive → post continuity → canonical A17.
`column_stability_runtime.py` checks qualified B5 and matching result/proof/
story/direction/output identities before passing operands to the frozen Eq.7.13 owner.

The accepted slim evidence reports only
`A17:REVIEWED_STORY_TRANSLATION_TOLERANCE_NOT_BOUND` for `+14.5:C1:36`.
It reports acquisition=1, scratch=1, B5=2, B6=0, StartDesign=0.
That top-level result does not enumerate every nested field. The source trace
and offline reproduction distinguish the limited nested audit from an actual
canonical blocker; no new acquisition/composition/identity/classification/
unsupported-mode/human-authority seam has been proven missing for E2.

Missing **live evidence**: the real B-BLOK post-E1 signed-translation/canonical
readiness result. No new engineering value or default is introduced.
No claim is made that real story translations satisfy the approved tolerance.

## Focused validation and next gate

- Existing authority/provider/response/provenance/public-root group: **128 PASS**.
- E1 binding, typed residual Frame/Area and architecture guards: **65 PASS**.
- New public-root E2 gate regression: **2 PASS**.
- Synthetic full Frame universe: 8; factual synthetic Area universe: 0.
  Separate existing provider/whole-system/response tests cover nonempty Areas,
  unsupported residuals, unknown modes, population and identity failures.
- Positive fixture: real whole-system False → True, READY/MATCH focus with
  approved E1 tolerance/provenance, exact next production call shared B6.
- Negative fixture: same whole-system qualification without tolerance stays
  A17 UNRESOLVED and never calls B6. The second Column remains A18/A19 unresolved.
- B6 observation deliberately stops before downstream rebar selection. No
  optional shear/final-cage/A35 authority is supplied to obtain this readiness.

Only this census and the regression test change. Production logic, A17 value,
A18/A19, Eq.7.13 mathematics and report architecture are unchanged.
Real B-BLOK READY requires the later explicitly authorized public-root live run.
After persistence, use the existing acceptance harness and E1 reviewed-input
wrapper; the delivery handoff records the exact candidate SHA/tree and command.
