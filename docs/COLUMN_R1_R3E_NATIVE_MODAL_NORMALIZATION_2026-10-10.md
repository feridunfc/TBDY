# R3E — native modal amplitude binding

## Exact evidence and scope

Parent implementation: HEAD `7bd7f4bbf9b2992c685f51db45f0b43a11ac633a`, TREE `e609d86df6a9adc5cd5b9fc9063b3ca584ea7150`. R0/R1/A4 and recovered M5/M6-A/R3B evidence remain closed/reused.

Accepted operator receipt `column-r1-r3d-modal_20261010_073229.json`, 41,010,125 bytes, SHA256 `83ce2ff7c3a6170e931d2869e212adde93b7c08b25bbf44e9f0c2c663f156b03`. Complete raw bytes remain external: Library `libfile_3ee6376e3be481919daf1bc5554f2682`. This document does not replace the receipt or issue an analysis-result epoch.

FC09 pre/post SHA is `FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F`. PID 2072, ETABS 23.2.0/API 2.014; active identity and independent present/database observations are unchanged. Both unit systems are kN/m. No worker ETABS execution occurred.

R3D is **CLOSED / LIVE PROVEN for the representative +0.00 factual scope**: 86 Columns, 172 endpoints, 100 modes at every required native physical result grain; 56,800 FrameForce rows and 17,200 JointDispl rows. Filtered Modal/Mode/+0.00/Bottom Story Forces contains 100 rows. The receipt records 263 successful modal output transactions with verified restoration. Initial API mode range is 1–1; initial database range is 1–12. Temporary ranges are 1–100; all original options are restored. The earlier 06:57 receipt remains historical incomplete evidence.

## CSI source law

- [CSI Analysis Reference Manual, Rev.15, July 2016](https://docs.csiamerica.com/manuals/etabs/Analysis%20Reference.pdf): printed p.376 (PDF page 398) establishes unit modal mass; printed p.394 (PDF page 416) defines native modal amplitudes and their multiplication of modal displacement/force/stress responses. Spectrum scaling and damping are already included in the reported acceleration.
- [CSI Response-spectrum analysis FAQ](https://wikicsiamerica.atlassian.net/wiki/spaces/kb/pages/2006323/Response-spectrum%2Banalysis%2BFAQ): modal normalization uses database units; native U1/U2/U3 amplitudes supply the response multipliers.

For a native, database-normalized linear modal response q_n, the numerical per-mode contribution is `Amp_n * q_n`. No extra scale factor, participation factor, eigenvalue, inferred sign or length conversion is introduced. Rounded displayed periods/mass ratios are not used to reconstruct amplitudes. The native field's length-unit metadata is preserved; the field is not relabelled dimensionless.

## Existing-owner implementation

`tbdy_engine/analysis_basis/eq713_response_mechanics.py::bind_database_normalized_native_modal_amplitude` binds the documented contract `CSI_DATABASE_NORMALIZED_MODAL_AMPLITUDE_MULTIPLICATION_V1`. It requires exact typed successful native table metadata and independently observed identical present/database force and length units. It rejects unknown normalization, missing/wrong Amp fields, duplicate metadata, wrong period/length units and unit conversion assumptions. This is source semantics, not new project engineering authority.

Existing signed complete-story aggregate and scalar multiplication helpers remain unchanged. The amplitude carries its raw table ref, mode, source/session/capture, native field unit and metadata ref. Caller-supplied bindings cannot issue a B5 result identity.

`tools/column_r1_r3e_modal_normalization_offline.py` reads only the exact accepted receipt bytes. It independently checks all 275 retained capture-payload hashes, unchanged source/session, observed units, successful native dependency/direction fields and exact 100-mode amplitude populations. It binds RSX/U1 and RSY/U2 from their actual GetLoads outputs. Case SF=10 is not applied again.

The original capture retained only the last shared modal-table metadata payload. RSX's earlier metadata capture UUID/ref is preserved in the original receipt but its complete separate payload is unavailable. The offline review uses the retained, exact common native field header for both cases and identifies its actual ref; it does not recreate the overwritten payload or claim equality of fresh capture UUIDs.

Offline review output: 200 bound amplitudes, SHA256 `1dbee10c395ec4407995e16451850f592b984610a8c07d72b23d329f680ddd1e`. Complete generated JSON is reproducible outside Git using the command below. RSX mode 1=.762376, mode 2=-.353072; RSY mode 1=.361023, unchanged from the native fields.

## Boundaries and next edge

**Native amplitude normalization binding = SOURCE PROVEN / OFFLINE VERIFIED AGAINST LIVE RECEIPT.** Production acquisition is unchanged. The worker did not perform a new live call.

**M6-B remains OPEN.** Complete, topology/length-bound physical R/Delta/V construction, source-exact native CQC treatment, current uncracked B5 execution lineage and the joint Delta/R/V engineering selection law remain separate gates. Station-rich FrameForce populations are not automatically the physical-bottom Column denominator. Story shear is not the length-weighted Column R operand. No aggregate spectrum value, synthetic signed state, phi, sway classification, READY promotion or R2 permission is produced.

The shear-anchored statistical proposal remains **NOT APPROVED / NOT IMPLEMENTED**. Neither native amplitude multiplication nor independent spectrum maxima approve a concurrent or conservative TS500 ratio.

Next work must use the existing complete physical mapping/length owner and qualify the exact aggregate inputs; an explicit project decision is still required for the joint statistic. No further capture or B5 regeneration is automatically requested by this closure.

Offline reproduction only, after checking out the published candidate:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'C:\Users\FCY\PycharmProjects\tbdy_engine_a37'
    $output = Join-Path 'C:\tmp' ('column-r1-r3e-normalization_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json')
    python .\tools\column_r1_r3e_modal_normalization_offline.py --receipt 'C:\tmp\column-r1-r3d-modal_20261010_073229.json' --output $output
    if ($LASTEXITCODE -ne 0) { throw 'Offline normalization review failed — STOP' }
    Write-Host "Offline review: $output; R2 remains unauthorized."
}
```

Validation is recorded separately in `COLUMN_R1_R3E_OFFLINE_RECEIPT_2026-10-10.json`; historical validation receipts are unchanged.
