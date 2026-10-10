# R3G — source-exact periodic CQC and physical modal operands

Disposition: **PARTIAL**. R3F is merged and reused. Constant-total-damping
periodic CQC mechanics and representative factual global bottom-cut V are
implemented and tested. Actual FC09 CQC magnitudes and global story Delta
remain blocked by specific missing source facts. M6-B remains OPEN.

## Verified integration base

PR [#199](https://github.com/feridunfc/TBDY/pull/199) preserved original R3F
`6d24842bf4a96a18218019c0257cdec04a75ee03` with a merge commit,
`b7adc4550f1a02d9ea3cfcca3b6c3232e2573c50`. Remote main was fetched and its
tree `8fb52b44302f779c1ac5544e8843e4975e1187ae`, parents and R3F ancestry
verified. R3G starts from this main on
`worker/column-r1-r3g-source-exact-cqc-modal-operands`.

[PR #199 integration receipt](COLUMN_R1_PR199_INTEGRATION_RECEIPT_2026-10-10.json)
records independent exact current-baseline diagnostic equality and all three
GitHub checks SUCCESS. PR #198 was not treated as a blanket waiver. The five
negative architecture tests remain actual FAIL, unchanged technical debt.
Original R3D/R3E/R3F/M6 receipts are byte-identical and remain tracked.

## Exact source authority and implemented scope

1. [CSI Analysis Reference Manual, Rev.15, July 2016](https://docs.csiamerica.com/manuals/etabs/Analysis%20Reference.pdf),
   Chapter XX, printed pp.387–390: total modal damping includes load-case,
   composite material and link/support contributions; F2=0 selects entirely
   periodic response; CQC references Wilson, Der Kiureghian and Bayo (1981).
   Zero damping in every mode gives the explicit SRSS limit. This does not
   authorize SRSS as a substitute for an unsupported CQC setting.
2. [Edward L. Wilson, Chapter 15, revised July 13, 2014](https://edwilson.org/bookshelf/2005/2005%20Chapter%2015%20MODIFIED%202014.pdf),
   printed p.15-8, equations 15.9–15.10: constant-damping periodic CQC
   quadratic and coefficient. The author's published five-mode coefficient
   table, printed p.15-11, was visually inspected and independently tested.
3. CSI API ETABS v1 (2024), SHA256
   `6ee860c75d37215d6d6c44251e94788709439e155b68a7939e893a66f01dda27`,
   JointDispl printed pp.147–150: translations are point-element local
   U1/U2/U3. Physical global endpoint coordinates do not establish those
   local axes. The original PDF remains external; it is not copied into Git.

For constant qualified **total** damping zeta and frequency ratio
`r = min(omega_i, omega_j) / max(omega_i, omega_j)`:

```
rho_ij = 8 zeta^2 (1+r) r^(3/2)
         / ((1-r^2)^2 + 4 zeta^2 r (1+r)^2)
CQC(q) = sqrt(sum_i sum_j rho_ij q_i q_j)
```

`PeriodicCqcOperator` extends existing `eq713_response_mechanics.py`. It requires
complete ordered modes, positive source frequencies, matching native
source/session/capture/case/direction/normalization, named native CQC and F2=0.
Every mode must have independent case, material and link/support damping
contributions with refs, including source-proven zeros. Unequal total damping
and every nonzero-F2 rigid treatment are unsupported and rejected. Method
integers are not decoded. Signed modal terms remain signed in the quadratic.
Scaled arithmetic avoids intermediate response-square overflow; a negative
quadratic fails without absolute value or clipping. A return is the statistical
magnitude of one physical quantity and cannot issue a stability state.

The source coefficient benchmark uses published angular frequencies
13.87, 13.93, 43.99, 44.19, **54.41** rad/s and zeta=0.05. Coefficients are
published to three decimals; the test uses a 0.0005 absolute rounding tolerance.
Synthetic complete 100×100 matrices are verified for symmetry, exact diagonal,
signed quadratic behavior and population integrity. **No current FC09 100×100
matrix or CQC R/Delta/V magnitude is issued.**

## Exact accepted FC09 receipt reconciliation

Input remains `column-r1-r3d-modal_20261010_073229.json`, SHA256
`83ce2ff7c3a6170e931d2869e212adde93b7c08b25bbf44e9f0c2c663f156b03`,
external at `libfile_3ee6376e3be481919daf1bc5554f2682`.
The source remains exact FC09
`FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F`.
No live session was accessed by this worker. Its historical protected-source
receipt is factual and supplies no current qualified uncracked B5 epoch.

`tools/column_r1_r3g_modal_operands_offline.py` verifies exact original bytes,
all retained raw-payload hashes, source/session/unit invariants and all R3E/R3F
contracts before extending the reconciliation:

| Operand / setting | Current bounded result |
| --- | --- |
| Native named case settings | RSX U1 / RSY U2; Global; angle 0; Modal; CQC; directional SRSS; `RigidResp=No`; successful getter F2=0. Labels come from the actual native table, not invented enum meanings. |
| Period/frequency population | 100 native rows; sec / cyc/sec / rad/sec / rad2/sec2 metadata; periods match native amplitudes exactly at reported precision. Original decimal strings retained; no unrounded internal-frequency claim. |
| R | Reused R3F: 86 physical bottoms, 5.15 m source axis lengths, 100 signed aggregate-first modes per case. |
| V | 100 unique +0.00 / Bottom / Modal / Mode rows per case. Native VX is global X and VY global Y with kN metadata. One matching native amplitude is applied; no second SF. Unrelated combinations, other stories and top cuts are excluded. |
| Endpoint population | 172 physical endpoints × 100 modes = 17,200 signed point-local rows; 86 × 100 = 8,600 physical top/bottom pairs preserved, with exact raw refs. |
| Delta | **BLOCKED_POINT_LOCAL_TO_GLOBAL_AXES_NOT_CAPTURED**. Unknown endpoint local axes are not relabelled global X/Y and are not silently subtracted in a presumed common basis. |
| CQC application | **BLOCKED_TOTAL_PER_MODE_MATERIAL_AND_LINK_SUPPORT_DAMPING_NOT_CAPTURED**. Observed case damping 0.05 is retained; missing other contributions are not manufactured as zero. |

First-mode factual values: RSX R=190.1010858713851 kN/m,
V=8838.7923282192 kN; RSY R=90.02233061448032 kN/m,
V=1982.0907851472 kN. These are signed mode contributions, not spectrum
magnitudes or design-state triplets. Ordinary Story Forces is used only for
its physical shear; it is not an independent reference for Column-only R.

Global endpoint transformations are necessary before a source-qualified Delta
can be constructed. After that, reuse the existing complete-population common
story-translation operator and reviewed A17 tolerance. Torsional nonuniformity
must fail closed; averaging or selecting a maximum individual drift is not
authorized. The existing operator's qualified B5 requirements are not weakened
or satisfied by invented refs.

## Validation and preserved independent gates

[R3G machine receipt](COLUMN_R1_R3G_OFFLINE_RECEIPT_2026-10-10.json) records
**1410 distinct PASS / 1410 executions / zero new failures, errors or skips**,
all 1297 prior test identities preserved, 113 new tests and 113 focused PASS.
The separate architecture suite is **17 PASS / five pre-existing FAIL**;
complete diagnostic sets, guard hashes, baseline and allowlist are unchanged
from the exact merged main tree. Compile/import includes the canonical gateway
package and passes; diff-check passes. Sensitive safety owners, guard files,
engineering values, A18/A19 and live acquisition code are unchanged.

The separate joint Delta/R/V engineering-statistic decision remains
**PROJECT_DECISION_REQUIRED**. Separate CQC magnitudes do not become a signed
concurrent state, an approved Eq.7.13 ratio or a proved conservative bound.
G/Q, EDZ, orthogonal alternatives, unfavorable selection, compression,
nonzero denominator and current uncracked B5 lineage retain independent gates.
The shear-anchored proposal remains NOT_APPROVED / NOT_IMPLEMENTED.
M6-B OPEN; R2_RERUN_READY=NO; no READY promotion.

## Next exact causal edge and offline reproduction

**Next source fact:** source-qualified total modal damping for RSX/RSY modes
1–100, including case/material/link-support contributions or positive factual
proof that the latter contributions are zero. The existing 0.05 getter alone
cannot close this edge. Point local-to-global transformations are a separate
explicit Delta blocker; the joint engineering rule and B5 epoch remain separate.
No new ETABS capture or product run is authorized by this document.

The complete derived operand JSON is external at
`libfile_83de99a7a5748191847395991ab17405`; its hash is in the machine receipt.
It preserves every native endpoint pair and both 100-row operand vectors;
original receipts remain intact. Reproduce it offline from the published R3G
checkpoint in one PowerShell invocation, with no PID or interactive input:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'C:\Users\FCY\PycharmProjects\tbdy_engine_a37'
    $result = Join-Path 'C:\tmp' ('column-r1-r3g-offline_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json')
    python .\tools\column_r1_r3g_modal_operands_offline.py --receipt 'C:\tmp\column-r1-r3d-modal_20261010_073229.json' --output $result
    if ($LASTEXITCODE -ne 0) { throw 'Offline reconciliation failed; no ETABS action authorized.' }
    Write-Host "Offline receipt: $result"
}
```
