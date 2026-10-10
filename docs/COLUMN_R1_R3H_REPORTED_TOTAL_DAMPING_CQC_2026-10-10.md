# R3H - CSI reported total modal damping and FC09 factual CQC

R3H closes the representative `+0.00` offline total-damping/CQC application boundary using the already accepted R3D bytes. M6-B remains OPEN. Global Delta, current uncracked B5 lineage and the joint Delta/R/V engineering statistic remain independent gates.

## Integration before implementation

[PR #200](https://github.com/feridunfc/TBDY/pull/200) preserved R3G `ade11d0e55eb620816387b065735d1612c95927c` through a merge commit. Independently fetched main is `8ed7d4e920bd213e4304849e423b5bd45f47125a`, tree `821f3070c8e0ac5f4b759a0ffbd86b6d81223206`, with exact old main and original R3G parents. Fresh 1410-test integration regression passed, with every prior identity retained, and all three applicable CI checks succeeded before merge.

Fresh exact-main and candidate architecture diagnostics have identical failing identities, full offending paths/symbols, public capabilities, inverse dependency sets, observed legacy exceptions, guard/baseline hashes and B4T allowlist. Both suites have 17 PASS / 5 actual FAIL. [Integration receipt](COLUMN_R1_PR200_INTEGRATION_RECEIPT_2026-10-10.json) records the fresh scoped differential; historical PR #198/#199 dispositions were not reused as continuing waivers. Guards, exception baselines, allowlists and safety owners were not changed.

## Exact CSI source meaning

Authority: `CSI_REPORTED_TOTAL_MODAL_DAMPING_V1`.

- [CSI Damping FAQ, page 2006597](https://wiki.csiamerica.com/display/kb/Damping+FAQ), updated October 8, 2022, identifies the Response Spectrum Modal Information table's per-mode damping and states that effective discrete-damper damping contributes to it.
- [CSI Analysis Reference Manual Rev.15, July 2016](https://docs.csiamerica.com/manuals/etabs/Analysis%20Reference.pdf), Chapter XX, printed page **394**, **Damping and Accelerations**, directly defines the reported damping as the sum of load-case damping, effective Link/Support modal damping and composite Material modal damping. Printed pages 387-388 explain these sources; pages 387 and 390 bind modal damping to CQC coupling. Page 389 establishes F2=0 as all-periodic response. This direct output definition establishes total meaning without assuming missing component contributions are zero.
- Wilson Chapter 15, revision 2014, equations 15.9-15.10 and published Table 15.1 remain the independently tested constant-damping periodic coefficient authority accepted in R3G. The coefficient implementation is reused unchanged.

Native metadata: exact `Response Spectrum Modal Info`, `SpecCase`, `ModalCase`, `Mode`, `Period` in sec, and `DampRatio`, description `The damping ratio.`, native unit blank. CSI's fraction-of-critical-damping definition supplies the dimensionless ratio semantics. Case-only getter damping and spectrum-function damping cannot replace this result-table total. No material/link/case contribution is added to a reported total again.

## Original bytes and factual scope

Original file: `column-r1-r3d-modal_20261010_073229.json`.

SHA256: `83ce2ff7c3a6170e931d2869e212adde93b7c08b25bbf44e9f0c2c663f156b03`.

Complete original raw file: `libfile_3ee6376e3be481919daf1bc5554f2682`. The protected FC09 hash remains `FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F` before and after that historical read. ETABS 23.2.0 / API 2.014, source/session/capture, exact native payload hashes and restored output state are revalidated offline. The receipt is a factual acquisition epoch; it cannot issue a current qualified B5 result epoch.

Each of RSX and RSY has exactly 100 unique native modal rows, modes 1-100, modal case `Modal`, matching the native period/frequency population. Every reported `DampRatio` is **0.05**. Native GetDampConstant also reports 0.05; its equality is a factual comparison, with no reconstruction or assertion of individual material/link component zeros. The original receipt retains one shared identical native metadata header; no overwritten earlier header capture is manufactured.

Existing source settings are CQC, F2=0, no rigid response, RSX U1 only, RSY U2 only, Global coordinate system with angle zero and directional SRSS. The named native table labels and retained getter outputs are reused without invented integer enum meanings.

## Existing-owner implementation

`tbdy_engine/analysis_basis/eq713_response_mechanics.py::CsiReportedTotalModalDamping` is a typed alternative to the preserved `ModalDampingComponents` path. Every record retains exact native text/value, mode, native field, metadata/raw refs, dimensionless ratio and the existing normalization binding containing source model, session, capture, spectrum case, modal case and direction. It cannot self-issue stability qualification. `PeriodicCqcMode` validates the reported record's exact mode and binding. `PeriodicCqcOperator` continues to reject unequal totals, unsupported rigid response and non-CQC methods.

`tbdy_engine/providers/etabs_story_stability_result_provider.py::qualify_native_reported_total_modal_damping` binds exact native definitions and all required modes to actual amplitudes. Wrong cases, duplicates, missing modes, period changes and metadata/unit ambiguity fail closed. No parallel sway or modal architecture is introduced.

`tools/column_r1_r3h_reported_damping_offline.py` reuses R3E normalization, R3F physical aggregate and R3G R/V projection. R3G's historical projection and receipt remain unchanged. The operator uses the native reported cyclic frequency; independently reported period, circular frequency and eigenvalue must have intersecting last-displayed-decimal consistency intervals. No unreported internal ETABS precision is invented.

Both actual 100 x 100 matrices are complete, symmetric, unit diagonal and numerically bounded. Signed physical modal R and V values enter the quadratic independently. Existing native amplitudes already include spectrum scaling/participation/eigenvalue effects; no second factor is applied.

| Separate unsigned statistical magnitude | Value from native reported decimals | Unit |
| --- | ---: | --- |
| RSX R CQC | 256.23299606353487 | kN/m |
| RSY R CQC | 84.76888878898679 | kN/m |
| RSX V CQC | 11424.577470752454 | kN |
| RSY V CQC | 11585.486716434587 | kN |

These are separate single-quantity statistical magnitudes. No signed concurrent earthquake triplet or approved Eq.7.13 ratio is created. The 86 physical Columns and length-weighted R grain remain representative; ordinary Story Forces/Base Reactions are not claimed to be an exact independent reference for Column-only R. An independent 50-digit Decimal calculation verifies the actual separate quadratic results; it does not claim equality to an unavailable native internal CQC aggregate.

## Validation and durable evidence

[R3H offline receipt](COLUMN_R1_R3H_OFFLINE_RECEIPT_2026-10-10.json) records **1489 distinct PASS, zero regression failures/errors/skips**, all 1410 prior identities preserved and 79 new tests. Separate architecture suite remains **17 PASS / 5 unchanged FAIL**, with exact full diagnostic equality. Compile/import and diff check PASS; tested-file and external JUnit hashes are retained. Negative coverage includes native mode/case/metadata/units, case-only damping confusion, double counting, nonfinite damping, unsupported unequal total damping, frequency correspondence and alleged B5/concurrent-state promotion.

Complete derived JSON: `libfile_76e077b9ec548191aabd6761a3fde992`, SHA256 `8c2b632c6f209bc964283090320f12e2987e83cbedecda77da041dfa1f702bf0`, 12,587,932 bytes. It retains both 100-row damping/R/V populations, both full matrices and all existing physical endpoint pairs. The complete raw original, historical R3D/R3E/R3F/R3G receipts and recovered M6 evidence are preserved. Full raw receipt and full JUnit files remain external; durable hashes/locators are in the machine receipts.

Reproduce offline from the published R3H checkpoint:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'C:\Users\FCY\PycharmProjects\tbdy_engine_a37'
    $result = Join-Path 'C:\tmp' ('column-r1-r3h-offline_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json')
    python .\tools\column_r1_r3h_reported_damping_offline.py --receipt 'C:\tmp\column-r1-r3d-modal_20261010_073229.json' --output $result
    if ($LASTEXITCODE -ne 0) { throw 'Offline reconciliation failed; no ETABS action authorized.' }
    Write-Host "Offline receipt: $result"
}
```

## Remaining exact edge

**Capture/qualify physical point-element local-to-global axes for the retained endpoint translations**, through a separate bounded task. The existing common story-translation operator still governs any global Delta; no identity transformation, maximum or average is assumed. Current uncracked B5 lineage and the joint Delta/R/V engineering-statistic decision remain independent and fail-closed.

GLOBAL_DELTA = OPEN. CURRENT_UNCRACKED_B5 = NOT_PROVIDED. JOINT_DELTA_R_V_STATISTIC = PROJECT_DECISION_REQUIRED. M6_B = OPEN. R2_RERUN_READY = NO. ETABS_EXECUTED = NO. SOURCE_MUTATED = NO.
