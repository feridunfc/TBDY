# Column-R1 R3I: exact point-axis source gate

Disposition: **BLOCKED_EXACT_POINT_MATRIX_SOURCE_SEMANTICS**. This is a bounded source/fact result, not a global displacement implementation, engineering approval or request to repeat modal acquisition. No production/test/preflight file changed.

## Integrated base

[PR #201](https://github.com/feridunfc/TBDY/pull/201) preserves original R3H `c9bc7860ef69fccf8d756908a6e0e67d02ab59a2`. Independently fetched main is `74b31465b2a8237a4653713a0bbb1bfa30085f43`, tree `3c74a72094af293ffac410c4f4be09d69dc6b54a`, with parents exact prior main `8ed7d4e` and original R3H. All three applicable GitHub checks succeeded. [Fresh integration receipt](COLUMN_R1_PR201_INTEGRATION_RECEIPT_2026-10-10.json) records all 1489 accepted PASS identities, exact complete five-guard diagnostic equality, unchanged guard/baseline/allowlist hashes and sensitive import review. Five architecture tests remain actual FAIL; no continuing waiver is created.

## Exact existing factual scope

The complete original `column-r1-r3d-modal_20261010_073229.json`, Library `libfile_3ee6376e3be481919daf1bc5554f2682`, has SHA256 `83ce2ff7c3a6170e931d2869e212adde93b7c08b25bbf44e9f0c2c663f156b03`. All 275 captured payload hashes were independently rechecked. All 172 endpoint getter facts contain exactly the unique Modal modes 1–100, with exact physical point-object and result-element identities: 17,200 signed point-LOCAL rows. No point local-axis assignment or transformation matrix fact exists. The Point Object Connectivity fields are UniqueName, IsAuto, Story, PointBay, IsSpecial, X, Y, Z, GUID. Coordinates do not establish axes.

The 172 returned Obj/Elm name pairs happen to match. This proves the retained result identity pairs; it does not prove orientation equivalence. Existing R3F/R3G owners retain 8,600 physical LOCAL endpoint pairs. **Qualified global endpoint rows = 0; qualified global top-minus-bottom vectors = 0; global story Delta/CQC(Delta) not supplied.** The [machine receipt](COLUMN_R1_R3I_OFFLINE_RECEIPT_2026-10-10.json) retains every exact endpoint/raw-response binding.

## Source result and precise stop

The project CSI API ETABS v1.pdf (2024), SHA256 `6ee860c75d37215d6d6c44251e94788709439e155b68a7939e893a66f01dda27`, was checked at exact JointDispl, PointObj/PointElm matrix, mapping and local-axis pages. Matrix pages 3044–3045 (PointObj) and 2931–2932 (PointElm) were rendered and visually checked. They supply these C# signatures:

- PointObj.GetTransformationMatrix(string Name, ref double[] Value, bool IsGlobal = true).
- PointElm.GetTransformationMatrix(string Name, ref double[] Value).

Their parameter/return sections give types, without the returned array layout, direction or conversion equation. The official [2016 PointObj](https://docs.csiamerica.com/help-files/etabs-api-2016/html/9479def8-531a-3fa7-70ce-c4315e97c292.htm), [2016 PointElm](https://docs.csiamerica.com/help-files/etabs-api-2016/html/ce6f071d-6809-d05e-7fe2-b2968ba6c9f2.htm) and [2015 PointObj](https://docs.csiamerica.com/help-files/etabs-api-2015/html/42d19dd3-87cb-1c5f-ed81-5df85499a04b.htm) pages corroborate the signatures but do not fill this semantic gap. No Python return tuple was invented.

CSI Analysis Reference Manual Rev.15 Chapter IV establishes joint-local output and the right-handed intrinsic 3→2→1 joint-angle procedure. PointObj.GetLocalAxes pages 3013–3014 explicitly describe basic angles in degrees and the advanced flag. This is reusable authority for basic point-OBJECT orientation; no accepted endpoint angle/advanced fact or result-ELEMENT applicability proof is present. The PointElm local-angle parameter descriptions do not independently specify their convention. An angle-derived route is not silently promoted.

The explicit local-to-global equation documented for a Link getter was not borrowed for point getters. Orthogonality and determinant checks cannot decide between a rotation and its transpose; both can pass. RSX/RSY Global load settings, vertical Columns, matching names, or absent axis assignments in an uncaptured table do not supply that missing source contract.

**Next exact source edge:** an applicable CSI ETABS v1 statement defining the returned PointElm.GetTransformationMatrix Value ordering and conversion equation between the exact JointDispl Elm local U1/U2/U3 and Global X/Y/Z. This direct-element contract avoids assuming inheritance of point-object axes. A PointObj alternative must independently prove its orientation applies to that exact result element.

The R3I instruction requires a source stop when matrix semantics are unsupported. Therefore no transform kernel, speculative transpose, getter wrapper or new live execution command is issued. Identity/nonidentity/transpose/advanced-axis transformation regressions belong to the later source-authorized implementation and were not claimed PASS here. The existing 1489 identities were freshly executed and all remain PASS; compile/import and diff-check PASS. The changes in this branch are documentation/evidence only.

## Preserved gates and later read scope

R3H representative R/V CQC remains CLOSED / REUSE. Current qualified uncracked B5 is NOT_PROVIDED; common story translation uses the existing uniform-translation/current-B5 law, with no mean, maximum drift or unreviewed reference substitute. Joint Delta/R/V selection remains PROJECT_DECISION_REQUIRED, M6-B OPEN, R2_RERUN_READY=NO. No historical factual receipt issues a current B5 epoch or concurrent state.

After the source contract closes, the missing native facts remain a separate bounded operator read: exact FC09 protected SHA, +0.00, the 172 identities retained in the machine receipt, verified existing PID/path/session, getter-only before/after identity/unit and disk-hash guards. It must use the existing verified gateway and factual OAPI owner; no RunAnalysis, StartDesign, Save, SetPresentUnits, result-option/selection change, model mutation or automatic execution. A command is withheld at the current source gate; do not repeat the 100-mode capture or start R2.
