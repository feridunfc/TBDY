# Column-R1 current state and evidence index

Reconciled 2026-10-10 after PR #201 history-preserving R3H integration and the bounded R3I point-axis source gate. This is an evidence locator and current-state reconciliation, not a new engineering authority, a live receipt or release approval. Historical documents and receipts remain unchanged.

## Accepted repository checkpoint and precedence

| Anchor | Exact identity |
| --- | --- |
| Accepted R3C implementation HEAD before PR #197 | `c045b452aae21a0858d3788a006c71d9f1452fa1` |
| Accepted R3C implementation TREE before PR #197 | `2e7da327f083781fec1c8cde0ed2a43ac2b4698a` |
| Verified pre-integration main | `a7c8bab81eed687051c43b14fbf1e981b797a1e3` |
| Prior integration source branch | `worker/column-r1-r1b-live-candidate` |
| Prior verified source relationship | Nine implementation commits ahead, zero behind pre-integration main; clean worktree; local and remote source HEAD equal |
| Accepted merged main / R3D parent | `ea8bb7aa18214e01d2efe1c28ca56ef2e2cafb64` |
| Accepted merged main TREE | `f23b81cc80435e06913529b62ef4a526d83e04ca` |
| R3D bounded repair branch | `worker/column-r1-r3d-modal-population-completeness` |
| Prior merged main / R3G parent | `b7adc4550f1a02d9ea3cfcca3b6c3232e2573c50` |
| Prior merged main TREE | `8fb52b44302f779c1ac5544e8843e4975e1187ae` |
| Preserved R3F commit | `6d24842bf4a96a18218019c0257cdec04a75ee03` |
| Preserved R3G commit | `ade11d0e55eb620816387b065735d1612c95927c` |
| Prior merged main / R3H parent | `8ed7d4e920bd213e4304849e423b5bd45f47125a` |
| Prior merged main TREE | `821f3070c8e0ac5f4b759a0ffbd86b6d81223206` |
| Prior bounded R3H branch | `worker/column-r1-r3h-reported-total-damping-cqc` |
| Preserved R3H commit | `c9bc7860ef69fccf8d756908a6e0e67d02ab59a2` |
| Latest independently verified main / R3I parent | `74b31465b2a8237a4653713a0bbb1bfa30085f43` |
| Latest independently verified main TREE | `3c74a72094af293ffac410c4f4be09d69dc6b54a` |
| Current bounded R3I branch | `worker/column-r1-r3i-point-global-translation` |

The original documentation-only index commit `84cdb486` and all nine implementation commits were preserved by PR #197's history-preserving merge. The R3D repair starts from that verified merged main; it does not replace or recreate earlier work.

**CURRENT VERIFIED REPO/GIT > LATEST LIVE RECEIPT > LATEST MASTER HANDOFF > CURRENT CANONICAL RECIPE / ARCHITECTURE ADDENDUM > OLDER DOCUMENTS.**

In particular, the initial R0/R1 audit documents and the R0B document's then-valid `R2_READY=YES` are historical checkpoints. Later R3C evidence controls today's gate: **M6-B OPEN; R2_RERUN_READY=NO**. No first READY or current B6 live proof is claimed.

## Accepted architecture and recipe

The accepted architecture remains the existing public-root and owner composition:

- `tbdy_engine/application/project_execution.py`: sole public project execution composition.
- `tbdy_engine/application/column_execution.py` and `column_public_a5.py`: existing Column application/public-A5 owners.
- `packages/etabs_gateway`: sole COM/STA/verified-session owner.
- Existing B4B establishes the analysis state; B5 alone owns controlled analysis; B6 alone owns controlled design. Protected source is immutable and state-changing execution belongs on owned scratch.
- Factual acquisition, reviewed authority, engineering rules, FND2 readiness, FCR denominator reconciliation and passive reporting retain separate responsibilities. Evidence strings supplied by callers cannot issue a qualified result epoch.

External accepted reference documents, verified by their contents (complete files are not tracked in this Git tree):

| Reference | Persistent source locator | Reuse boundary |
| --- | --- | --- |
| `TBDY_Engine_Canonical_Product_Architecture_v2.3_RECONCILED_2026-09-27(8).md` | Library `libfile_6f37322c974c8191a8ceec9b9aa00a34` | Architecture and owner invariants; September source/status anchors are historical |
| `COLUMN_R1_CANONICAL_RECIPE_v3_2026-09-27_POST_LIVE(8).md` | Library `libfile_2820e963d4708191b8da3faa74c8cc0c` | Existing engineering sequence; later repository/authority closures override old status prose |
| `COLUMN_R1_PRODUCT_AUDIT_2026-10-08.md` | Library `libfile_14e0ea0943e48191bae57066bf12465a` | Accepted roadmap reconciliation; later R0/R1/A4/R3B/R3C checkpoints supersede its open-edge snapshot |

The tracked [architecture constitution](architecture/CANONICAL_ARCHITECTURE.md) is an older baseline; its descriptive implementation snapshot is not current Column status. The requested October 8 post-audit recipe v4, master handoff and v2.3 addendum are not present as tracked complete files at the accepted checkpoint; this index does not pretend they are.

Current recipe: verified source/session → factual geometry/materials + reviewed FC09 basis → A3 bounded fixed point/B4B/B5 → A4 semantic continuity → FND2 → truthful READY evaluation → conditional shared B6 → longitudinal rebar/PMM/selection → applicable detailing/transverse/shear → FCR → same-result report/package.

`ONE B5 OWNER != ONE B5 INVOCATION`: A3 may require bounded B5 generations. The accepted live run used two. A blanket `RunAnalysis <= 1` is not a product-completion law. A leaf blocker does not stop legal unrelated Columns; a common hard cut-set still fails closed. `READY=0` means `StartDesign=0`; `READY>0` allows one shared B6 with at most one StartDesign. All 260 READY or PASS are not prerequisites to a first vertical. Full release requires **260 truthful outcomes**, FCR, current report package and independent review. These lifecycle rules do not authorize a run while the present M6-B gate remains open.

## Closed work and exact implementation checkpoints

Do not reopen Package 0, public/software composition, Q1J/Q1N/Q1P/G12, E1/E2/E3/E3A, M5, M6-A aggregate-first principle, R0, R1, A4, R3B combination reconciliation or October 1 reference recovery. Report/package offline implementation already exists in `tbdy_engine/product_reports/building_report_package.py` and the HTML/PDF/XLSX/JSON owners; this is not evidence of B-BLOK engineering release.

| Commit preserved verbatim | Checkpoint and bounded status |
| --- | --- |
| `a8d25058f3b342b975846ce68bc767b2317419d6` | R0 current-source audit; preserved historical evidence, not the final rebind |
| `c7996785ccf30ed71ddb6a7c3eb8b6aeefb04567` | R1 authority boundary / exact synthetic A18 fixtures; historical gate retained |
| `bd1b47f9fdf8b6ad2d8c4948278b9431f65a6af4` | R1B native GetSectProps I22/I33 present-L4 provenance implementation |
| `9f29d5a5f5add26fe3bb2513675430f06fe4076b` | Read-only FC09 R0/R1 preflight; R1 subsequently CLOSED / LIVE PROVEN |
| `a4b4835f398fa3b029e0a22fcaf1a5c88d34b943` | R0B FC09 same-value reviewed rebind / source pin; R0 CLOSED |
| `5aba2eea7893763a92be1f3856e6b0a2ed509ac8` | A4 semantic continuity repair; subsequently CLOSED / LIVE PROVEN |
| `4a6b4f52cc80d741e8c962658ef7e4ddb90adb6a` | R3B exact combo reconciliation / M6 reuse |
| `45e6af4093f8d5b79d1a92596c440d153460ff78` | Recovered exact Prota–ETABS reference; CLOSED / REUSE; 958-test checkpoint |
| `c045b452aae21a0858d3788a006c71d9f1452fa1` | R3C native settings getter, read-only modal capture and aggregate arithmetic; 1035 tests; R3C PARTIAL, M6-B OPEN |

Latest supplied product live facts: 260 components, composition/A38/A39/A40 pass, READY=0. 142 reached `A17:BLOCKED_TS500_STABILITY_COMBO_SCOPE`; this does not predict 142 READY after a repair. A18/A19 leaf limitations remain truthful; this integration changes neither owner. B-BLOK engineering release remains OPEN.

## FC09 authority and original reviewed bytes

See [FC09 rebind authority](B-BLOK-COLUMN-FC09-REBIND-v1.md). It is classified `REVIEWED_PROJECT_AUTHORITY / CURRENT_SOURCE_REBIND`.

| Evidence | Exact SHA256 / binding |
| --- | --- |
| Protected `C:\tmp\B-BLOK_Revised.EDB` | `FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F` |
| Historical reviewed source | `5AA83947C46AE886DD43E8BD2270DAEAC6117AE60BAD1F8CB9ED9874CD3E2A44` |
| Unchanged `C:\tmp\column-r1-reviewed-inputs.py` | `9D7BAE7108C655751C018071E9B17D1D401A21904DAAD140BDBE81566AC9FBBC` |
| `column-r1-r0-r1-preflight_20261009_192703.json` | `79A7BCA0DD50F42B6D9852D2ED56DFC03D0A1CDB40A1C534EA7071F6E8C4CE00`; Library `libfile_322fdc71f1ec8191baee81f91ef93098` |
| Exact 12-combo equality packet | `A24412D2DECB10E715C2A235FE7FDE0545B4422CEEBB428C7540D9D074D18992` |

The preflight proves ETABS 23.2.0/API 2.014, 15/15 native sections with independently qualified I22/I33 L4, no errors and exact FC09 pre/post hashes. `frame_section_mechanics.py` retains the raw tuple, fresh observations, exact source/session/capture bindings and the trusted source/scratch bridge. Authority is `COLUMN_R1_GETSECTPROPS_PRESENT_L4_POLICY_V1`; A18 is not weakened.

`tools/column_r1_bblok_fc09_reviewed_inputs.py` verifies and loads the exact external bytes without editing/relabeling them. Dependencies remain precisely `column_design_basis`, `expected_combo_policy`, `reviewed_vs5_column_axial_context`. A17 is 0.01 mm with ref `B-BLOK-COLUMN-FC09-REBIND-v1`. C35/45 fcd=23.33 MPa, DefaultRebar_500 fyd=434.8 MPa, transverse fywk=500/fywd=434.8 MPa, aggregate=20 mm, high ductility TRUE/limited FALSE and Route-C W PROVEN_NOT_APPLICABLE remain unchanged.

VS5 is policy-only rebound: Crack_SeisX/Crack_SeisY, G/Q/S constituents, RSX/RSY, EDZ, exact coefficients, Max/Min, compression sign -1, reviewed linear superposition, TS498 NO_REDUCTION and TS500 Grav_Ult. Historical forces, modal results and analysis/design result epochs must never be reused. VS5 authorization does not authorize a new Eq.7.13 joint spectrum statistic.

The acceptance harness `tools/run_column_r1_public_acceptance.py` requires FC09 before/after. Its existence and policy are not permission for an R2 rerun now.

## R3B, M5 and recovered M6 evidence

[R3B reconciliation receipt](COLUMN_R1_R3B_RECONCILIATION_RECEIPT_2026-10-09.json) preserves exact selected identities/definitions and the equality digest. Twelve selected rows and twelve full definitions match; this is exact policy reuse, not a newly qualified Eq.7.13 state or a claim that every standard template has been satisfied.

M5 evidence is reused: actual modal horizontal E matters; response-spectrum vertical axial effects cannot be assumed zero. Relevant original external source `Pasted text(20261009-200159).txt`, Library `libfile_a89e1d32e9708191b5042cec9df22330`, SHA256 `914E21E72590C75EE7649AA366790279A4A867AF481FF57B80265E55E67D832B`, is indexed in the R3B receipt. The supervisor reconciliation source `Pasted text(20261009-194744).txt`, Library `libfile_09dd2967d6cc819197ca23a8863e8a55`, SHA256 `925630B84A701B7D51D7954D36EF555A43DD927A5FCC47DB4E4109BB79BEB8F0`, is also indexed there.

M6-A remains the accepted physical aggregate-first principle: `R_n = sum(Ndi,n/li)` over the complete applicable factual Column population before modal combination. Independent member extrema cannot be summed as a replacement.

Recovered source locations:

- [Reference addendum](COLUMN_R1_M6_RECOVERED_REFERENCE_ADDENDUM_2026-10-09.md).
- [Reference receipt](COLUMN_R1_M6_RECOVERED_REFERENCE_RECEIPT_2026-10-09.json).
- `tests/fixtures/column_r1_m6_prota_etabs_reference.json`: exact derived reference projection, SHA256 `49f4848fa8ebf384a48bce0a9109b3f7ebf1da230272693d60ab815dae009ef4`.
- `tools/column_r1_m6_reference_recovery.py` and `tests/application/test_column_r1_m6_reference_recovery.py`: reproducible source checks and regression, not an algorithm reverse-engineering program.

| Original complete file (external, not stored in Git) | SHA256 | Persistent source |
| --- | --- | --- |
| `Pasted text(20261001-041302).txt` | `d0b87f6c98b80b8e1d3516a2f148befe0713c204ed2e8b474cdff95db44a30c1` | Library `libfile_f876b2387fec8191ab5dfcfddcab4151` |
| `tr1-RCColDes.docx` | `d89a69e1647e2078ff9da037fdc9c6e26b320a6f1060b5147e2218d5163751ed` | Library `libfile_d38fc3eecac48191978b7554109c0aa8` |
| `tr1-ColSln.docx` | `0bb29e790038e81fbe2a0c9ccee421b955f196bbfd780a154a04c370b805f5dd` | Library `libfile_de5de29fad848191a0030a35ae127965` |
| `tr1-A2.docx` | `6fae0fd5197cc3e806fd4dcb993393ff2570b96d2a70556078fa30694ff48f2a` | Library `libfile_d96db2fe70608191927bb245d4fe6b9e` |

| Historical comparison | Prota sum, tonf | Sum of independent ETABS Min-P extrema, tonf |
| --- | ---: | ---: |
| ST1 / X | 587.795 | 877.5327 |
| ST2 / X | 295.073 | 401.6103 |
| ST1 / Y | 587.796 | 877.5320 |
| ST2 / Y | 295.072 | 401.6092 |

The 32-column example supports the recovered aggregate warning and internal Prota report consistency. It provides no current FC09 epoch, native modal normalization or approved joint Delta/R/V selection law. Original files may be supplied locally at `C:\tmp\column-r1-m6-reference` for exact-source verification; rounded report values do not authorize hidden-algorithm inference.

## R3D historical incomplete receipt and repair

Historical source receipt: `column-r1-r3c-modal_20261010_065722.json`, SHA256 **`4ea722960a5167bdfee0545b645b1dc2a9dd7992c072f60fc53aca2038f5cac7`**. Complete raw JSON is external evidence, preserved at Library `libfile_dfd08b0570188191ba381e963b0fa378` (file `file_00000000e030820a8288326e647134f7`); it is not copied into Git. The worker verified the complete raw-file hash and exercised its actual rows in a regression. Do not overwrite it or reinterpret it as a qualified B5 result epoch.

| Historical 06:57 FC09 observation | Proven scope / limitation |
| --- | --- |
| RSX / RSY loads | U1 only / U2 only; actual dependency `Modal` |
| Modal / directional combination | CQC / SRSS; damping 0.05; eccentricity 0.05 |
| Reference population | 100 native modes in modal periods / spectrum modal amplitude tables |
| `+0.00` physical population | 86 factual Columns; 172 physical endpoints |
| API FrameForce / JointDispl | Every object read contains only Mode 1: **incomplete** |
| Story Forces | Modal rows cover modes 1–12, plus unrelated combination rows: **incomplete** |
| Protected disk source | Exact FC09 SHA before and after; unchanged |
| Previous status label | `FACTUAL_CAPTURE_COMPLETE_PENDING_NORMALIZATION_B5_AND_JOINT_RULE` **does not prove mode-population completeness** |

The existing R3C tool selected cases but did not inspect or set either native modal output range. CSI API ETABS v1 (2024), SHA256 `6ee860c75d37215d6d6c44251e94788709439e155b68a7939e893a66f01dda27`, documents two independent controls: `Results.Setup.Get/SetOptionModeShape` (pp.265–266 / 286–287) and `DatabaseTables.Get/SetOutputOptionsForDisplay` (pp.910–913 / 936–939). **The old receipt did not retain their initial values.** A starting range of 1–1 or 1–12 must not be claimed as directly observed. The proven code gap is uncontrolled native ranges plus absent exact population validation; the next receipt records before/temporary/restored values and decides whether range selection closes the native truncation.

R3D extends the existing `ResultsSetupReadTransaction` and `DatabaseTablesReadTransaction`, under their existing acquisition lock. Each requested modal read snapshots the exact successful native ABI, selects inclusive 1–100, verifies the complete options tuple, performs the read, then restores and verifies every original scalar and result-selection flag. The database setter changes only `IsAllModes`, `StartMode`, `EndMode`; all base-reaction, buckling, history and combination options remain exact. Failed option restoration is a hard failure; case/combo restoration is still attempted. Ordinary callers that do not request a modal range retain their existing behavior.

`tools/column_r1_r3c_modal_read_only.py` now requires exact 100-mode equality per physical Column/element/station grain and physical endpoint/element grain, complete 86/172 connectivity coverage, and exact mode equality in amplitude, period, mass and filtered bottom-story shear tables. Story Forces candidates require exact `OutputCase=Modal`, `StepType=Mode`, `Story=+0.00`, native `Location=Bottom`; raw unrelated rows remain in the receipt. Native field metadata, observed present/database units, direction-specific load settings and mode/period alignment are retained and checked. Native `U1Amp/U2Amp/U3Amp` are dimensional length values in this receipt: **no multiplier, sign, normalization or unit scaling is invented**.

Bounded implementation and negative-test validation are recorded in [R3D offline receipt](COLUMN_R1_R3D_OFFLINE_RECEIPT_2026-10-10.json). The historical pending-live status was closed by the later 07:32 operator receipt below. Historical receipts remain unchanged.

## Current R3D live proof and R3E normalization binding

Accepted R3D implementation HEAD `7bd7f4bbf9b2992c685f51db45f0b43a11ac633a`, TREE `e609d86df6a9adc5cd5b9fc9063b3ca584ea7150`; 1199 distinct PASS, zero failures/errors/skips, preserving all 1035 prior identities.

Latest receipt: `column-r1-r3d-modal_20261010_073229.json`, SHA256 `83ce2ff7c3a6170e931d2869e212adde93b7c08b25bbf44e9f0c2c663f156b03`, complete raw file external at Library `libfile_3ee6376e3be481919daf1bc5554f2682`. **R3D CLOSED / LIVE PROVEN at +0.00**, 86 factual Columns/172 endpoints, exact 100-mode physical grains, source/session/units unchanged, all 263 modal output transactions restored. Initial API mode range 1–1 and table range 1–12 are now directly observed; temporary ranges 1–100 close the truncation. This receipt is factual, not a B5 result epoch.

[R3E native normalization closure](COLUMN_R1_R3E_NATIVE_MODAL_NORMALIZATION_2026-10-10.md) records the exact CSI source law and the existing-owner binder. Database-normalized native Amp multiplies the signed native modal response directly within independently observed identical present/database units. Native length metadata, signs and raw refs remain intact. No second SF/participation/eigenvalue scaling is applied. The offline tool binds 200 actual amplitudes from the exact receipt bytes, with no ETABS access or engineering promotion. Current validation is in [R3E offline receipt](COLUMN_R1_R3E_OFFLINE_RECEIPT_2026-10-10.json).

R3E validation: **1238 distinct PASS / 1238 executions / zero failures, errors or skips**, preserving all 1199 prior identities and adding 39 native-normalization regressions. Focused suite 81 PASS; compile/import and diff-check PASS. The machine receipt records exact tested-code and external JUnit hashes. Historical 958/1035/1199 receipts remain intact.

## R3C owners and gate boundaries

See [R3C modal handoff](COLUMN_R1_R3C_MODAL_GATE_HANDOFF_2026-10-09.md) and [offline validation receipt](COLUMN_R1_R3C_OFFLINE_RECEIPT_2026-10-09.json).

| Existing owner / tool | Implemented boundary |
| --- | --- |
| `tbdy_engine/etabs/oapi/analysis_execution.py::get_response_spectrum_settings_from_session` | Typed native getters; raw outputs, actual method codes, fresh version/source/session/unit observations; no result issuer |
| `tbdy_engine/analysis_basis/eq713_response_mechanics.py::aggregate_native_modal_column_axial` | Native amplitude times signed complete-story weighted Column aggregate, before modal norm; unqualified arithmetic |
| Same file `native_modal_scalar_contribution` | Bound signed modal physical top-minus-bottom translation or exact bottom-cut shear scaling |
| Same file `srss_native_modal_aggregates` | Explicit SRSS arithmetic only; CQC/ABS/GMC rejected, no inferred method adapter |
| `tools/column_r1_r3c_modal_read_only.py` | One representative-story protected FC09 RSX/RSY native settings/table/modal capture; exact PID and pre/post hash guards; JSON outside Git |
| `tbdy_engine/providers/etabs_story_stability_result_provider.py` / `tbdy_engine/application/column_stability_runtime.py` | Existing stability composition remains fail closed; no speculative output-state promotion |

CSI sources and source-PDF hashes/pages are retained in the handoff/receipt. Original CSI API PDF SHA256 is `6ee860c75d37215d6d6c44251e94788709439e155b68a7939e893a66f01dda27`; TS500 PDF SHA256 is `d925114d01a1de2baee63738bc0da0112b547b58526c3394843c36ee66722d44`. These complete PDFs are external evidence, not tracked raw files.

**Gate 1, current after R3H:** representative 100-mode populations, native normalization and physical signed R are proven by R3D/R3E/R3F. R3G adds exact global bottom-cut V and the constant-total-damping, all-periodic CQC operator. R3H qualifies already captured `DampRatio` through CSI's direct total-damping output definition (Rev.15 printed p.394) and applies both actual 100 x 100 matrices to separate R/V vectors. Independent material/link reconstruction is no longer required for this authoritative total path. Global Delta remains blocked by absent point local-to-global axes; the existing common story-translation semantics and B5 requirements remain strict. Story Forces/base reactions are not asserted to be exact Column-only R. Separate CQC magnitudes do not approve a joint statistic.

**Gate 2 / actual OPEN M6-B decision:** qualify one exact unfavorable TS500 Eq.7.13 joint Delta/R/V design statistic for 1.0G+1.0Q+E, including source-supported modal/directional correlation, accepted physical translation, X/Y/orthogonal/EDZ alternatives, sign/applicability and nonzero denominator. Separate spectrum maxima do not prove concurrency or a conservative ratio bound.

`FC09_EQ713_SHEAR_ANCHORED_CORRELATED_DESIGN_EFFECT_V1` is **NOT APPROVED / NOT IMPLEMENTED**. Its mathematical proposal, alternatives and limits remain in the R3C handoff. Neither this index nor integration approves it.

**Remaining evidence:** endpoint local-to-global transforms and an applicable common physical story Delta; qualified current uncracked B5 execution proof/owned-scratch bridge; explicitly approved joint engineering selection. R3H reported total damping and separate CQC R/V are no longer missing representative edges. A protected-source read cannot issue a B5 epoch; old result identities cannot be rebound. No further live run is authorized here.

## Last 1035-test validation and integration scope

The historical R3C offline receipt records **1035 distinct PASS, 1035 executions, zero failures/errors/skips**, preserving all 958 prior test identities plus 77 new regressions, compile/import PASS and diff-check PASS. Its six tested-code hashes bind that earlier implementation. R3D intentionally changes acquisition/tool files and supplies a separate current validation receipt; the historical proof is not relabelled as a current execution.

| Raw validation evidence (outside Git) | SHA256 |
| --- | --- |
| Final JUnit `integrated-final.xml` | `db140a34f030e58bb33670605292e4372bc35e3f3a57a499cc8248b4bda30361` |
| Focused JUnit receipt | `86496e62f96a9c2d8b8258880f6d970198947bd37929361f70dd24593bd34341` |

The complete historical JUnit XMLs and original external test inputs are not committed; the tracked machine receipt is the durable summary/hash locator. The final XML was independently checked against its recorded hash and 1035/0/0/0 counts during initial index preparation. PR #197 added only the original index beyond the accepted nine implementation commits. The later R3D repair has its own bounded diff and current regression receipt. Do not relabel a reused receipt as a newly executed test run.

## PR #198 integration and representative R3F closure

Verified remote main after PR #198: `26155744efcc3e708544bf4bd6b2f6836d21160c`, tree `69b345ba07d9fa719729b547daa5975c7eb6c6fb`. Its parents are accepted main `ea8bb7aa` and R3E `c6bcca7`; both original commits `7bd7f4bbf9b2992c685f51db45f0b43a11ac633a` and `c6bcca7e4a39bd366f3cb7f140ba4bad07aff393` are ancestors. Both closure receipts, all recovered M6 sources/projections and this index are present on verified main. R3F starts from that main on `worker/column-r1-r3f-physical-modal-aggregate`.

[PR #198 integration receipt](COLUMN_R1_PR198_INTEGRATION_RECEIPT_2026-10-10.json) preserves complete diagnostic equality for all five pre-existing negative architecture guard failures, including paths/symbols/observed exception sets, unchanged guard/allowlist/baseline hashes and sensitive safety/binder import review. Three GitHub checks succeeded. **The five guard tests remain FAIL and explicit technical debt.** Supervisor authorized a scoped baseline differential for PR #198 only; no continuing waiver, disabled guard or expanded exception is created.

[R3F closure](COLUMN_R1_R3F_PHYSICAL_MODAL_AGGREGATE_CLOSURE_2026-10-10.md) and [R3F offline receipt](COLUMN_R1_R3F_OFFLINE_RECEIPT_2026-10-10.json) close the representative `+0.00` physical-bottom/axis-length/signed-per-mode operand boundary. The exact external 07:32 receipt and all retained raw payload refs are revalidated, not reacquired. Shared `column_shear_topology.py` geometry and `etabs_story_stability_result_provider.py` native selector bind 86 Columns × 100 modes = 8,600 unique physical-bottom rows. All actual bottoms are I at ObjSta=ElmSta=0. TS500 p.20 explicitly defines axis-to-axis `li`; full native object/coordinate/vertical axis lengths reconcile exactly at 5.15 m. Clear lengths/end offsets are not substituted or assumed zero. Source PDF digest and the native normalization dimensional interpretation are in the closure.

`tools/column_r1_r3f_physical_modal_aggregate_offline.py` reuses R3E and existing `aggregate_native_modal_column_axial` to retain 100 signed RSX and 100 signed RSY vectors, complete individual contributions, actual native amplitude m header/metadata and all source/session/capture/force/geometry references. Negative P is compression; one negation maps to Nd, preserving tension cancellation. No additional spectrum factor, CQC, concurrent modal state or B5 epoch is issued. The full numerical reconciliation JSON and JUnit files remain external, with hashes in the offline receipt; the 41 MB original raw file remains at its existing locator.

## PR #199 integration and historical R3G partial checkpoint

R3F was independently integrated through [PR #199](https://github.com/feridunfc/TBDY/pull/199), merge `b7adc4550f1a02d9ea3cfcca3b6c3232e2573c50`. Fetched remote main has tree `8fb52b44302f779c1ac5544e8843e4975e1187ae`, exactly the accepted R3F tree; original `6d24842bf4a96a18218019c0257cdec04a75ee03` is an ancestor. All R3D/R3E/R3F/M6 receipts remain byte-identical. [PR #199 integration receipt](COLUMN_R1_PR199_INTEGRATION_RECEIPT_2026-10-10.json) records fresh exact path/symbol/exception-set non-expansion and 3/3 CI SUCCESS. The five historical guard failures remain actual debt; PR #198 was not used as a blanket waiver.

[R3G source/physical-operand record](COLUMN_R1_R3G_SOURCE_CQC_PHYSICAL_OPERANDS_2026-10-10.md) and [R3G offline receipt](COLUMN_R1_R3G_OFFLINE_RECEIPT_2026-10-10.json): **PARTIAL**, 1410 distinct PASS, preserving every prior 1297 identity and adding 113 tests. Separate architecture suite 17 PASS / 5 unchanged FAIL, with complete violation-set equality and no guard/baseline/allowlist edits. Compile/import and diff-check PASS.

Existing `eq713_response_mechanics.py::PeriodicCqcOperator` implements Wilson's source coefficient for equal total damping and CSI F2=0, signed quadratic arithmetic, complete matching modes and explicit unsupported-setting rejection. The independent published coefficient table and synthetic complete 100×100 behavior are tested. **At the historical R3G checkpoint no actual FC09 matrix or magnitude was issued:** its then-missing total-damping interpretation is superseded by R3H's direct CSI output definition below. The historical receipt remains unchanged.

Existing `etabs_story_stability_result_provider.py::qualify_native_modal_story_shear` binds exact +0.00/Bottom/Modal/Mode VX-global-X or VY-global-Y metadata and one matching native amplitude. Both cases have 100 signed V contributions. `qualify_native_modal_endpoint_rows` preserves 17200 point-local rows and the offline adapter retains 8600 physical endpoint pairs. CSI JointDispl is point-local; missing local-to-global transforms are not defaulted to identity. No global Delta scalar is formed, no average/maximum drift is substituted, and the existing common story-translation/B5 contract is unchanged.

`tools/column_r1_r3g_modal_operands_offline.py` verifies the exact accepted 07:32 bytes and retained payload hashes, reuses R3E/R3F, and emits mode/R/V/period/native amplitude/source/physical-grain refs while leaving Delta and total damping explicitly absent. Actual native table labels establish CQC/SRSS/No rigid response without undocumented integer interpretation. The full derived JSON is external at `libfile_83de99a7a5748191847395991ab17405`; original raw input remains `libfile_3ee6376e3be481919daf1bc5554f2682`. Hashes are retained in the R3G receipt. No current B5 epoch, statistical joint-state approval, full-260 proof, ETABS access or R2 authorization is created.

## PR #200 integration and accepted R3H closure

[PR #200](https://github.com/feridunfc/TBDY/pull/200) merged R3G preserving `ade11d0e55eb620816387b065735d1612c95927c`. Fetched remote main `8ed7d4e920bd213e4304849e423b5bd45f47125a` has tree `821f3070c8e0ac5f4b759a0ffbd86b6d81223206`. [Fresh integration receipt](COLUMN_R1_PR200_INTEGRATION_RECEIPT_2026-10-10.json) retains 1410 PASS, exact full architecture diagnostic equality against b7adc455, unchanged guards/baseline/allowlists, 3/3 CI SUCCESS and original source ancestry. Five architecture tests remain actual FAIL and explicit debt; this fresh disposition is scoped to PR #200.

[R3H closure](COLUMN_R1_R3H_REPORTED_TOTAL_DAMPING_CQC_2026-10-10.md) and [current offline receipt](COLUMN_R1_R3H_OFFLINE_RECEIPT_2026-10-10.json) bind `CSI_REPORTED_TOTAL_MODAL_DAMPING_V1` in the existing response-mechanics and story-result owners. CSI Damping FAQ page 2006597 and Rev.15 p.394 establish native result-table total meaning. Both cases have 100 unique `DampRatio=0.05` rows; no case/material/link damping is added again and no fictional zero components are created. The original component-based path and R3G projection remain preserved.

Current validation: **1489 distinct PASS / 1489 executions / zero regression failures, errors or skips**. All 1410 prior identities are preserved; 79 new regressions pass. Separate architecture suite **17 PASS / 5 actual unchanged FAIL**, with exact full diagnostic equality and no guard/baseline/allowlist changes. Compile/import, evidence hashes and diff check PASS. The current receipt binds the five tested code/test files and preserves every historical receipt hash.

Separate CQC magnitudes from actual native reported decimals: RSX R **256.23299606353487 kN/m**, RSY R **84.76888878898679 kN/m**, RSX V **11424.577470752454 kN**, RSY V **11585.486716434587 kN**. Full matrices, source/session/capture/metadata/raw refs, native amplitudes and dimensions are retained. An independent high-precision Decimal quadratic verifies each result. These separate magnitudes do not constitute a concurrent triplet or TS500 result.

Complete current derived JSON: `libfile_76e077b9ec548191aabd6761a3fde992`, SHA256 `8c2b632c6f209bc964283090320f12e2987e83cbedecda77da041dfa1f702bf0`. The complete original remains `libfile_3ee6376e3be481919daf1bc5554f2682`; historical R3G JSON remains `libfile_83de99a7a5748191847395991ab17405`. Full raw files/JUnit XMLs are external; their durable hashes and test-file/identity records are in the machine receipts. No historical receipt is relabelled as a new run.

## PR #201 integration and current R3I source gate

[PR #201](https://github.com/feridunfc/TBDY/pull/201) merged original R3H with commit `74b31465b2a8237a4653713a0bbb1bfa30085f43`; independently fetched main has the exact R3H tree `3c74a72094af293ffac410c4f4be09d69dc6b54a`. Original R3H is an ancestor and R3D–R3H receipts remain byte-identical. [Fresh PR #201 integration receipt](COLUMN_R1_PR201_INTEGRATION_RECEIPT_2026-10-10.json) records all 1489 accepted PASS identities, complete exact-main architecture violation equality, unchanged guards/baselines/allowlists, sensitive import review and 3/3 CI SUCCESS. The five architecture tests remain actual FAIL; earlier dispositions were not standing waivers.

[R3I source gate](COLUMN_R1_R3I_POINT_AXIS_SOURCE_GATE_2026-10-10.md) and [machine receipt](COLUMN_R1_R3I_OFFLINE_RECEIPT_2026-10-10.json) record the exact bounded result: all 275 original payload hashes verified, 172 point-local endpoints × 100 modes, no captured point-axis/matrix facts, zero qualified global endpoint/top-minus-bottom rows. The exact CSI API v1 point matrix pages establish signatures but do not specify Value flattening or conversion direction; matching Obj/Elm names and point coordinates do not prove orientation applicability. The basic PointObj angle convention is documented but is not a current PointElm orientation proof. No production/test/preflight changes or speculative matrix/angle transformation were introduced.

The next source edge is a CSI ETABS v1 definition of PointElm.GetTransformationMatrix Value ordering and the conversion equation for the exact JointDispl Elm local components to Global X/Y/Z. Until it closes, no new live command is issued. The eventual read scope remains the existing 172 endpoints only, through the verified gateway with protected FC09/PID/path/session/unit/hash guards and no mutations. No broad modal capture or R2 run is authorized.

## Existing offline replay / next source action

Reproduce current bounded facts/CQC with `tools/column_r1_r3h_reported_damping_offline.py` and the single-block offline Windows command in the R3H record. It verifies the accepted original bytes, preserves native normalization and reports the independent Delta/B5/joint-statistic gates. No PID, interactive input, new ETABS capture or product run is needed.

Next bounded source edge: **exact CSI point-element matrix Value ordering/direction authority**, then the missing physical endpoint-axis facts and existing applicable common story Delta operator. R3I is BLOCKED at the source gate; no new capture command is available. Current uncracked B5 execution lineage and the joint Delta/R/V selection law remain independent open gates. `FC09_EQ713_SHEAR_ANCHORED_CORRELATED_DESIGN_EFFECT_V1` remains NOT_APPROVED / NOT_IMPLEMENTED. Representative 86-Column facts do not qualify the full 260-Column population. **R3H representative offline CQC boundary CLOSED; M6-B OPEN; R2_RERUN_READY=NO; no ETABS/product run authorized.**
