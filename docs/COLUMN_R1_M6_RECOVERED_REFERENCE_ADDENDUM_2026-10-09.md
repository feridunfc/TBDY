# Column-R1 — recovered Prota/ETABS reference and M6-B handoff

This bounded addendum restores the October 1 example omitted from the R3B
receipt. It preserves that receipt and historical canonical documents. It does
not supply new engineering values or a new stability method.

Verified implementation base:

- HEAD: `4a6b4f52cc80d741e8c962658ef7e4ddb90adb6a`
- TREE: `ff50b0ae57b32c2ac4c9d14931cced3f67e05d2c`
- Branch: `worker/column-r1-r1b-live-candidate`
- R0, R1, A4, Package 0 and Q1J/Q1N/Q1P/G12 remain closed.
- A18/A19 and the A3/B5 analysis lifecycle are unchanged.

Precedence remains CURRENT VERIFIED REPO/GIT > LATEST LIVE RECEIPT > LATEST
MASTER HANDOFF > CURRENT CANONICAL RECIPE / ARCHITECTURE ADDENDUM > OLDER
DOCUMENTS. Old conversation statuses cannot replace current repository truth.

## Exact recovered sources

These are the actual October 1 user-supplied files, not similarly named Drive
examples. Exact original SHA256 values and Library identities are preserved in
`tests/fixtures/column_r1_m6_prota_etabs_reference.json` and in the machine
receipt accompanying this addendum.

| Original file | Verified content | What it proves |
| --- | --- | --- |
| `Pasted text(20261001-041302).txt` | ETABS Column Forces, 5,585 text lines / 5,568 result rows, two stories with 16 columns each | Factual exported P/V/T/M values, stations and Max/Min distinctions |
| `tr1-RCColDes.docx` | Prota C25/S420 example, 32 column design tables with 19 combinations each | Printed per-column NTop/NBot and M1/M2 for each numbered combination |
| `tr1-ColSln.docx` | Four story/direction sway rows | Critical combination 6 for X, 10 for Y; printed drift, axial total, shear and Q |
| `tr1-A2.docx` | Post-analysis report with Ex+/Ex-/Ey+/Ey- modal-superposition effects | Separate displacement report, not an Eq.7.13 modal-aggregation contract |

The checked-in projection contains all 32 columns, Prota rows 1/6/10, ETABS
G+Q and paired seismic X/Y Max/Min at stations 0/3, plus the four sway rows.
It does not duplicate the complete original export. The tool can re-read all
four exact original files and require equality with the complete projection.

## Reproduced comparison

For this particular historical example, the previous comparison uses
Story+Column identity, `NBot = -P@Station 0`, `NTop = -P@Station 3`, Prota M1
against ETABS M2, and Prota M2 against ETABS M3. These station/direction choices
are example-specific; the current production topology owner must still prove
physical bottom/top and local axes for FC09.

| Story / direction | Prota sway report axial total, tonf | Sum of rounded Prota NBot, tonf | Sum of independent ETABS Min-P, tonf |
| --- | ---: | ---: | ---: |
| ST1 / X, combination 6 | 587.795 | 587.796 | 877.5327 |
| ST2 / X, combination 6 | 295.073 | 295.072 | 401.6103 |
| ST1 / Y, combination 10 | 587.796 | 587.797 | 877.5320 |
| ST2 / Y, combination 10 | 295.072 | 295.070 | 401.6092 |

The ETABS labels `Gc+Qc+Ez+Ex-` and `Gc+Qc+Ez+Ey-` identify the reported
historical comparison pair. They are not parsed as coefficient/sign authority
and are not promoted to current Eq.7.13 stability combinations.

The 0.001–0.002 tonf difference between the two Prota totals is retained as
printed rounding. The much larger ETABS difference is independently reproduced.
The example therefore rules out using independent member extrema to reproduce
this reported story design total. It does not expose Prota's internal modal
aggregation algorithm or prove exact ETABS/Prota seismic case equivalence.

The sway report prints h=350 cm, drift=1.44/1.76 mm, Q=0.010308/0.012086,
and Prevented. Printed rounded operands do not reproduce the printed Q exactly.
No hidden precision is reverse-engineered and no average-drift authority is
transferred to the current A15 uniform-translation owner.

## Recovered decisions versus raw proof

The recovered October 1 04:24 UTC assistant response records CQC, directional
combination `SRS`, SGN100/30, and combination 6 as
`Gc+Qc+0.30Ez+Ex-+0.30Ey+`. These are recovered conversation statements, not
newly verified raw ETABS case-setting definitions. Preserve the literal `SRS`;
do not silently expand it to SRSS or bind those settings to FC09. The model
version used by the old chat is not exposed by this retrieval.

The latest R3B supervisor instructions already accept M6-A independently of
this recovered example: build the complete signed physical column aggregate
per mode, `R_n = sum(Ndi,n/li)`, then apply source-authorized modal combination.
Reuse that accepted decision. The result is a modal aggregate design effect,
not a synchronous time-history state. M5's nonzero horizontal-E vertical
resultant remains accepted; the zero-resultant shortcut remains rejected.

## Current owner connection and bounded result

| Existing owner | Reusable capability | Missing qualification |
| --- | --- | --- |
| `etabs_story_stability_result_provider.py` | Signed physical-bottom column summation and complete-story topology | Current supported slice is an exact static state; Story Forces P is not automatically weighted Column-only R |
| `eq713_response_results.py` | Typed FrameForce local generalized-force acquisition with case/mode rows | Modal eigenvector rows are not automatically spectrum-scaled RS contributions |
| `analysis_execution.py` | Response-spectrum modal dependency and B5 lineage | Current preflight does not contain complete FC09 scales, modal/directional methods or damping |
| `eq713_response_mechanics.py` | Positive mode-participation evidence for A3/E2 | No aggregate design-force or joint Delta/R/V qualification |
| `stability_combo_basis.py`, `stability_output_state.py`, `column_stability_runtime.py` | Exact existing static combination and signed Single Value continuity | Do not relabel spectral Max/Min effects as physically concurrent states |
| `sway_stability.py` | Existing Eq.7.13 calculation and reviewed W applicability | Consume qualified operands only; no method rewrite |

No recovered raw source or accepted decision supplies the complete joint
Delta/R/V rule. No production patch can truthfully close M6-B on this evidence.
The offline recovery is closed; M6-A is reused; M6-B remains open. This is the
first unresolved engineering decision, not a request to research sway again.

**Exact project authority required:** For FC09 TS500 Eq.7.13 G+Q+E, specify and
approve the statistical design-effect branch rule that joins Delta_i, the
accepted aggregate-first R=sum(Ndi/li), and Vfi—including G/Q, EDZ and X/Y
alternatives—and the governing phi selection, without asserting physical
concurrency or assembling independent member extrema.

After that rule is supplied, materialize only its required operands through the
existing owners: complete qualified Column population, each applicable li,
verified direction and spectrum scaling/method, and the same current uncracked
B5 AnalysisResultIdentity/execution proof. The old report, raw export and modal
epochs must never be passed as current FC09 results. Native ETABS capability
has not been exhaustively live-proven unavailable.

The existing R3B four-combo snow 1.0 versus accepted 0.2 discrepancy is unchanged
and remains a separate source/policy correction decision. This recovery does
not authorize EDB changes or erase that finding.

## Reproduction and exit

```powershell
python .\tools\column_r1_m6_reference_recovery.py

# Optional: prove all four exact original files reproduce the checked-in data.
python .\tools\column_r1_m6_reference_recovery.py --source-directory 'C:\tmp\column-r1-m6-reference'
```

These commands are offline and make no ETABS call. Regression results, file
hashes and the preserved prior-test denominator are in the accompanying JSON
receipt. Historical documents and the prior R3B receipt remain unchanged.

```text
RECOVERED_REFERENCE = CLOSED / ORIGINAL_BYTES_REPRODUCED
M6_A = REUSE_ACCEPTED_AGGREGATE_FIRST_PRINCIPLE
M6_B = BLOCKED_PROJECT_AUTHORITY_REQUIRED
A17_142 = NO_READY_PROMOTION_FROM_REFERENCE
PRODUCTION_PATCH = NO
LIVE_EXECUTED = NO
R2_RERUN_READY = NO
NEXT_LIVE = NOT_AUTHORIZED
```

After authorized closure of the actual remaining cut-sets, continue the same
PRODUCT_ADVANCEMENT_RUN. All 260 need not be READY: READY=0 means StartDesign=0;
READY>0 permits one shared B6 and at most one StartDesign for the legal READY
leaves. Report/package implementation remains available; release requires 260
truthful outcomes, not 260 PASS or 260 READY.
