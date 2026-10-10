# Column-R1 current state and evidence index

Reconciled 2026-10-10 after PR #197 integration and for the bounded R3D modal-population repair. This is an evidence locator and current-state reconciliation, not a new engineering authority, a live receipt or release approval. Historical documents and receipts remain unchanged.

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

## R3D current native receipt and completeness finding

Historical source receipt: `column-r1-r3c-modal_20261010_065722.json`, SHA256 **`4ea722960a5167bdfee0545b645b1dc2a9dd7992c072f60fc53aca2038f5cac7`**. Complete raw JSON is external evidence, preserved at Library `libfile_dfd08b0570188191ba381e963b0fa378` (file `file_00000000e030820a8288326e647134f7`); it is not copied into Git. The worker verified the complete raw-file hash and exercised its actual rows in a regression. Do not overwrite it or reinterpret it as a qualified B5 result epoch.

| Current FC09 native observation | Proven scope / limitation |
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

Bounded implementation and negative-test validation are recorded in [R3D offline receipt](COLUMN_R1_R3D_OFFLINE_RECEIPT_2026-10-10.json). **100-mode native physical result coverage and native restoration remain pending the operator's new read.** Even a passing factual read cannot qualify modal normalization, a current uncracked B5 epoch/bridge, a native CQC adapter or the joint Delta/R/V design statistic. No R2/product rerun or TS500/READY promotion is authorized by this repair.

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

**Gate 1:** offline arithmetic passes. The 2026-10-10 receipt now proves the current native case signatures/methods and records amplitudes, but physical mode populations are incomplete as detailed above. Complete physical per-mode R/Delta/V, normalization and B5 lineage remain NOT PROVEN. Native CQC adapter is not implemented. Story Forces/base reactions are not asserted to be exact Column-only length-weighted R.

**Gate 2 / actual OPEN M6-B decision:** qualify one exact unfavorable TS500 Eq.7.13 joint Delta/R/V design statistic for 1.0G+1.0Q+E, including source-supported modal/directional correlation, accepted physical translation, X/Y/orthogonal/EDZ alternatives, sign/applicability and nonzero denominator. Separate spectrum maxima do not prove concurrency or a conservative ratio bound.

`FC09_EQ713_SHEAR_ANCHORED_CORRELATED_DESIGN_EFFECT_V1` is **NOT APPROVED / NOT IMPLEMENTED**. Its mathematical proposal, alternatives and limits remain in the R3C handoff. Neither this index nor integration approves it.

**Missing next evidence:** one new FC09 `+0.00` RSX/RSY read-only receipt with independently verified/restored output options and exact 100-mode physical populations. The existing receipt is preserved as incomplete evidence. Even a complete protected-source receipt cannot issue a qualified B5 epoch. Eventual production use additionally needs the exact current uncracked B5 execution proof and owned-scratch/source bridge; old result identities cannot be rebound.

## Last 1035-test validation and integration scope

The historical R3C offline receipt records **1035 distinct PASS, 1035 executions, zero failures/errors/skips**, preserving all 958 prior test identities plus 77 new regressions, compile/import PASS and diff-check PASS. Its six tested-code hashes bind that earlier implementation. R3D intentionally changes acquisition/tool files and supplies a separate current validation receipt; the historical proof is not relabelled as a current execution.

| Raw validation evidence (outside Git) | SHA256 |
| --- | --- |
| Final JUnit `integrated-final.xml` | `db140a34f030e58bb33670605292e4372bc35e3f3a57a499cc8248b4bda30361` |
| Focused JUnit receipt | `86496e62f96a9c2d8b8258880f6d970198947bd37929361f70dd24593bd34341` |

The complete historical JUnit XMLs and original external test inputs are not committed; the tracked machine receipt is the durable summary/hash locator. The final XML was independently checked against its recorded hash and 1035/0/0/0 counts during initial index preparation. PR #197 added only the original index beyond the accepted nine implementation commits. The later R3D repair has its own bounded diff and current regression receipt. Do not relabel a reused receipt as a newly executed test run.

## Next executable local action for R3D

Only a read-only native modal capture is next. Inspect its receipt before any further run or patch. Do not run PRODUCT_ADVANCEMENT_RUN. Use the actual PID of the ETABS instance already showing the exact protected FC09 file; no PID/name fallback and no source reopening is authorized here.

This command fetches the bounded repair branch, proves accepted merged-main ancestry, and selects that fetched candidate without rewriting local branch history. The worker's final transport receipt pins its exact commit/tree; use those pins when executing. Stop on any failed guard. Execute only once, then inspect the new receipt.

```powershell
cd C:\Users\FCY\PycharmProjects\tbdy_engine_a37
if (git status --porcelain) { throw 'Worktree dirty: STOP' }
git fetch origin worker/column-r1-r3d-modal-population-completeness
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed: STOP' }
$candidate = (git rev-parse origin/worker/column-r1-r3d-modal-population-completeness).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Candidate identity unavailable: STOP' }
git merge-base --is-ancestor ea8bb7aa18214e01d2efe1c28ca56ef2e2cafb64 $candidate
if ($LASTEXITCODE -ne 0) { throw 'Accepted merged main absent: STOP' }
git switch --detach $candidate
if ($LASTEXITCODE -ne 0) { throw 'Exact candidate checkout failed: STOP' }
if ((git rev-parse HEAD).Trim() -ne $candidate) { throw 'HEAD mismatch: STOP' }
if (!(Test-Path .\docs\COLUMN_R1_CURRENT_STATE_AND_EVIDENCE_INDEX.md)) { throw 'Evidence index absent: STOP' }
if (!(Test-Path .\tools\column_r1_r3c_modal_read_only.py)) { throw 'Native capture tool absent: STOP' }
$etabsPid = [int](Read-Host 'Actual PID of ETABS displaying protected FC09')
if ($etabsPid -le 0) { throw 'Invalid actual PID: STOP' }
$receipt = Join-Path 'C:\tmp' ('column-r1-r3d-modal_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json')
python .\tools\column_r1_r3c_modal_read_only.py --source 'C:\tmp\B-BLOK_Revised.EDB' --pid $etabsPid --story '+0.00' --receipt $receipt
if ($LASTEXITCODE -ne 0) { throw "Capture blocked: inspect $receipt; do not rerun analysis" }
Write-Host "Inspect receipt before any next action: $receipt"
```

The tool reads RSX and RSY automatically, uses the exact existing `Response Spectrum Modal Info` table key by default, verifies 100-mode equality against native Modal authority, verifies every required physical Column/end-point read and restores both safety-owned selections and modal output options. It hashes FC09 before/after and issues no qualified analysis epoch. Missing/truncated tables, rows, source metadata or restoration must fail closed. There is no RunAnalysis, StartDesign, Save or SetPresentUnits in this operation.

## Current disposition

PR #197 integration is complete and earlier recovered evidence is preserved. R3D is a bounded population-acquisition repair requiring a new operator read before native completeness is claimed. **M6-B remains OPEN; R3C PARTIAL; B-BLOK engineering release OPEN; R2_RERUN_READY=NO.** The next local read is separate from B5 and subject to receipt review. Full release is 260 truthful outcomes plus FCR/current report package/independent review, not a requirement that all Columns PASS or become READY.
