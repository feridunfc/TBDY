# R3F physical-bottom signed native modal aggregates

Bounded offline closure for the accepted FC09 `+0.00` capture. R3D/R3E and the recovered M6 reference are reused. No ETABS operation, new result acquisition, CQC, stability-state promotion or engineering-statistic approval was performed.

## Integration and source scope

PR [#198](https://github.com/feridunfc/TBDY/pull/198) was merged with both original R3D/R3E commits preserved. Verified remote main/base is `26155744efcc3e708544bf4bd6b2f6836d21160c`, tree `69b345ba07d9fa719729b547daa5975c7eb6c6fb`. R3F branch: `worker/column-r1-r3f-physical-modal-aggregate`.

[Integration receipt](COLUMN_R1_PR198_INTEGRATION_RECEIPT_2026-10-10.json) records complete baseline/candidate diagnostic sets, guard/baseline hashes, sensitive-import review, exact JUnit hashes and all three successful GitHub checks. The five architecture tests still fail; their offending paths, symbols and full violation sets are exactly unchanged. Supervisor's scoped differential acceptance applied to PR #198 only. It is not a continuing waiver; no guard, baseline or allowlist was changed.

The exact external receipt `column-r1-r3d-modal_20261010_073229.json` has SHA256 `83ce2ff7c3a6170e931d2869e212adde93b7c08b25bbf44e9f0c2c663f156b03`, 41,010,125 bytes. Library locator `libfile_3ee6376e3be481919daf1bc5554f2682`. It remains external, including all 56,800 native FrameForce rows. The reconciliation validates the original bytes, all 275 retained payload hashes, observed present/database kN/m, unchanged exact FC09 source/session, output restoration and factual-only epoch. RSX/U1 and RSY/U2 are read from settings, not inferred from names.

## Physical station and length authority

The existing `column_shear_topology.py` now exposes its shared factual endpoint resolver, without issuing a full shear-topology bundle or requiring manufactured section/beam/offset facts. It identifies bottom by actual Z and retains I/J connectivity, coordinates, object/coordinate lengths and raw geometry/metadata references. Existing full-topology offset and clear-length logic remains in its original owner.

The existing `etabs_story_stability_result_provider.py` adds an exact native selector. CSI API ETABS v1 (2024), FrameForce, printed pp.123–124, SHA256 `6ee860c75d37215d6d6c44251e94788709439e155b68a7939e893a66f01dda27`, defines ObjSta from object I and ElmSta from element I. Thus physical bottom is exactly ObjSta=0 for bottom-I, or exactly full object length for bottom-J. Native element identity and ElmSta are retained. Each physical grain must contain all 100 modes; one unique endpoint row per Column/mode is required. Duplicate, truncated, missing, nonfinite and ambiguous states raise a typed blocker retaining Column/raw source identity. There is no first, nearest, min/max or absolute-force fallback.

**TS500 (2000), printed p.20/PDF p.27 defines `li` as axis-to-axis Column length.** Original PDF SHA256: `d925114d01a1de2baee63738bc0da0112b547b58526c3394843c36ee66722d44`. Net/free `ln` is a distinct definition. The existing response-mechanics owner binds this exact authority to the full physical axis length only after exact positive equality of native object length, endpoint coordinate distance and vertical axis separation. Inclined/projection, disputed coordinates, wrong units/authority and clear/end-offset-corrected lengths fail closed.

End offsets are not present in this receipt. Their values are not assumed zero. They are not subtracted from axis-to-axis `li`; their absence prevents a claim about clear length or offset-corrected mechanics, not this source-defined full-axis operand. Unknown insertion/eccentric-axis corrections receive no authorization from this package.

Actual scope: **86 Columns, 172 endpoints, 100 modes; 8,600 exact physical-bottom rows.** All 86 bottoms are I, with ObjSta=ElmSta=0. All reconciled axis lengths are 5.15 m. Their equality is a factual check after the independent TS500 length definition, not the authority for choosing `li`.

## Native normalization and dimensions

Reuse the accepted R3E contract `CSI_DATABASE_NORMALIZED_MODAL_AMPLITUDE_MULTIPLICATION_V1`. CSI Analysis Reference, Rev.15 (July 2016), printed pp.376/394 (PDF pp.398/416), [official source](https://docs.csiamerica.com/manuals/etabs/Analysis%20Reference.pdf), defines unit-modal-mass normalization and multiplication of modal force/displacement/stress response by the reported amplitude to obtain that mode's response-spectrum contribution. The [CSI FAQ](https://wikicsiamerica.atlassian.net/wiki/spaces/kb/pages/2006323/Response-spectrum+analysis+FAQ) binds normalization to database units.

This is the source-defined **modal-coordinate-to-response map**, not multiplication of two unrelated physical measurements. In notation, for the normalized basis `phi_n` and native coordinate `q_alpha,n`, linearity gives `F(q_alpha,n phi_n) = q_alpha,n F(phi_n)`. The normalized basis response is paired with its native coordinate; it is not an independent ordinary member-load force to which a length conversion is applied. CSI expressly defines the product as a modal contribution of the original response quantity. For FrameForce that resulting quantity is force `[F]`; its full-axis quotient is `[F]/[L]`, here kN/m.

The native amplitude field header **m is retained**, including metadata/raw references; it is never relabelled dimensionless. The OAPI's generic FrameForce `[F]` header is also preserved. The normalization interpretation comes from CSI's paired-basis multiplication law, not from treating ordinary kN times m as kN or inventing a corrective scale. This implementation supports only the independently observed identical present/database unit system; it does not authorize mixed-unit conversion, alternate eigenvector normalization or arbitrary exported modal data. No second SF=10, participation factor, eigenvalue, mass correction or fabricated sign is applied.

## Signed aggregate and strict remaining gates

For each spectrum case and mode, existing `aggregate_native_modal_column_axial` computes `R_alpha,n = sum_j(-P_eigen,j,n * Amp_alpha,n / li_j)`. The native negative-compression convention becomes positive `Nd` through exactly one negation. Signed tension, negative amplitudes and cancellation remain. Complete-story signed physical summation precedes any modal correlation. Every vector retains 86 contributions and exact normalization/source/session/capture/raw force/geometry/length-authority bindings.

RSX has 100 vectors and RSY has 100 vectors. These are modal contributions, not final spectral maxima or simultaneous time states. Representative numerical checks, kN/m:

| Case | Mode 1 | Mode 2 |
| --- | ---: | ---: |
| RSX | 190.1010858713851 | 68.98067314130364 |
| RSY | 90.02233061448032 | -147.10870182616733 |

[Offline receipt](COLUMN_R1_R3F_OFFLINE_RECEIPT_2026-10-10.json) records validation, numerical-result digest and source limits. No native exact weighted aggregate was available for an independent comparison; tests independently reconstruct the complete physical sums from the retained native rows. No Story Forces or Section Cut value is relabelled as weighted `R`.

**R3F closes the representative physical-bottom/axis-length/signed-per-mode operand boundary only.** CQC remains OPEN. Current qualified uncracked B5 is NOT PROVIDED. The joint Delta/R/V selection law remains PROJECT_DECISION_REQUIRED. `FC09_EQ713_SHEAR_ANCHORED_CORRELATED_DESIGN_EFFECT_V1` remains NOT_APPROVED / NOT_IMPLEMENTED. A18/A19, selected design combinations and protected FC09 are unchanged. No sway/FND2 READY, B6 or product-rerun permission is issued.

## Reproduce offline on Windows

After checking out the published R3F HEAD/tree recorded in the delivery, run this single script block. It uses the already accepted raw receipt and writes a new result outside Git. No ETABS process or PID is needed.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'C:\Users\FCY\PycharmProjects\tbdy_engine_a37'
    $output = Join-Path 'C:\tmp' ('column-r1-r3f-physical-r_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json')
    python .\tools\column_r1_r3f_physical_modal_aggregate_offline.py --receipt 'C:\tmp\column-r1-r3d-modal_20261010_073229.json' --output $output
    if ($LASTEXITCODE -ne 0) { throw 'R3F offline reconciliation failed — STOP' }
    Write-Host "Offline result: $output"
}
```

Next bounded edge is R3G: source-exact CQC treatment of the signed complete physical modal vectors, including independently qualified Delta/V operand bindings. This requires its own source/setting proof. The existing read-only capture cannot issue a qualified B5 epoch, and CQC alone cannot approve the joint engineering statistic. **M6-B OPEN; R2_RERUN_READY=NO.**
