# Column-R1 R3C — bounded native capture and modal aggregate support

Status: **PARTIAL**. Gate 1 arithmetic is offline tested; current FC09 native
contributions, full modal combination and qualified B5 binding are **NOT
PROVEN**. Gate 2 remains **PROJECT_DECISION_REQUIRED**. No product run is
permitted by this package. R0/R1/A4, M6-A and the recovered reference stay closed.

Verified parent HEAD `45e6af4093f8d5b79d1a92596c440d153460ff78`, tree
`ebe359808210b7eab465e0628319aa2c19ba1df4`, branch
`worker/column-r1-r1b-live-candidate`. The remote branch matched this parent
before implementation. Historical evidence documents are preserved unchanged.

Precedence: CURRENT VERIFIED REPO/GIT > LATEST LIVE RECEIPT > LATEST MASTER
HANDOFF > CURRENT CANONICAL RECIPE / ARCHITECTURE ADDENDUM > OLDER DOCUMENTS.

## Sources actually read

| Primary source | Bounded conclusion |
| --- | --- |
| [CSI response-spectrum FAQ](https://wikicsiamerica.atlassian.net/wiki/spaces/kb/pages/2006323/Response-spectrum%2Banalysis%2BFAQ), updated 2022-10-10, RSA output and Signs sections | Native modal amplitudes multiply modal response quantities; modal mass normalization depends on database units. Spectrum extrema of different responses do not represent one concurrent time instant. |
| [CSI base-reaction explanation](https://web.wiki.csiamerica.com/wiki/spaces/kb/pages/2003704/Base%2Breactions%2Bfor%2Bresponse-spectrum%2Banalysis), updated 2022-10-21 | Signed physical reactions are summed within each mode before modal combination. This supports linear aggregate order; it does not identify a Column-only length-weighted R with native base reactions. |
| [ETABS response-spectrum definition help](https://docs.csiamerica.com/help-files/etabs/Menus/Define/Load_Cases/Response_Spectrum.htm) | Case settings include applied U1/U2/U3 acceleration, function, scale, coordinate system, angle, modal/directional methods, damping and eccentricity. Rigid/periodic treatment also matters. |
| [CSI API ETABS v1.pdf (2024)](https://drive.google.com/file/d/1MNG3B_wYWRN8t5eAVryLUhTsfK1E7FPe/view), SHA256 `6ee860c75d37215d6d6c44251e94788709439e155b68a7939e893a66f01dda27`, printed pages 675–698 | Exact response-spectrum getter ByRef names/order, including GetModalComb_1 rigid-response output. Numeric method codes are retained without inventing enum meanings. |
| [TS500.pdf](https://drive.google.com/file/d/1GIaAvx7CDm8PWNmESMKl2GikQcJc1DBH/view), SHA256 `d925114d01a1de2baee63738bc0da0112b547b58526c3394843c36ee66722d44`, printed pages 24–25 | Eq.7.13 uses 1.5 Δ Σ(Ndi/li) / Vfi, uncracked basis and the unfavorable applicable prescribed load alternative. This passage does not define a joint response-spectrum ratio statistic. |

These sources were read narrowly for the present operand contract. No formula
research, Prota recovery or new sway route was opened.

## Implemented boundary

`analysis_execution.py` extends its existing response-spectrum acquisition
owner. One verified STA read captures each of these getters once per case:
GetModalCase, GetLoads, GetModalComb_1, GetDirComb, GetDampType,
GetDampConstant, GetDampInterpolated, GetDampProportional, GetDampOverrides,
GetEccentricity, GetDiaphragmEccentricityOverride. Fresh source/session/present
and database-unit observations bracket the getter group. Version scope is
ETABS 23.2.0 / API 2.014. Raw outputs remain retained. Nonzero return outputs
are factual and unqualified, including inactive damping getters. Settings
capture cannot issue analysis-result lineage.

`eq713_response_mechanics.py` extends the existing subordinate mechanics owner:

- Native amplitude is exact U1Amp/U2Amp/U3Amp, not an acceleration field.
- Modal response, amplitude and physical length must share database-unit
  normalization, modal case, spectrum case, source direction, source/session
  and acquisition binding. These DTOs are computation inputs, not new issuers.
- Complete factual story Column denominator is required. Signed contributions
  and tension/cancellation survive: R_n = Amp_n Σ_j(-P_j,n/li_j).
- Exact source-bound top-minus-bottom translation and signed bottom-cut shear
  may be scaled by the same amplitude. Neither becomes a TS500 scalar here.
- SRSS acts on completed physical R_n aggregates. **CQC, ABS, GMC and other
  methods are rejected by this SRSS helper.** No source-proven native CQC
  coefficient/rigid-response adapter is present in this package. No old method
  name or user conversation supplies the missing live settings.
- All arithmetic outputs remain unqualified for stability. No call to the sway
  kernel, FND2 promotion, READY, B6 or engineering output-state issuer was added.

The pure helper cannot prove native field meanings, physical length applicability,
complete modal population or current B5 freshness from caller-supplied strings.
Those proofs must come from existing factual/controlled-execution owners.

## One bounded local read

`tools/column_r1_r3c_modal_read_only.py` requires explicit FC09 path, actual PID,
representative story and a new outside-repository JSON receipt. It attaches by
canonical verified session with PID fallback disabled, hashes protected bytes
before/after, brackets reads with fresh active identity/unit observations and
uses existing safety-owned reversible output-selection reads. No engineering
model setter, analysis, design, save or unit change is reachable from the tool.

For RSX/RSY it captures native settings and exact native modal-information
field metadata/raw table. The default table key is the existing catalog's
`Response Spectrum Modal Info`; `--modal-info-table` accepts an operator-verified
exact key if the source advertises a different name. It does not guess aliases.

For the **actual GetModalCase dependency**, it captures periods, participating
mass, Story Forces, signed modal FrameForce for the representative story's
complete factual Column population and JointDispl for every physical endpoint.
Column/Point connectivity supplies identity/location evidence. FrameForce and
JointDispl use their existing typed ABI owners; the receipt's capture_payload_ref
hashes the retained typed payload, not a falsely claimed original COM tuple.
Native settings and table owners additionally retain their original raw outputs.

Tables must be FULL, successful, nonempty and restored. Missing modal rows,
metadata, source identity or restoration stops with the exact diagnostic and
partial facts in the receipt. It does not regenerate B5. Geometry tables may
contain the whole source universe; per-object modal reads are confined to one
story. This is not a 260-Column result census.

**Physical FC09 source reads do not supply a matching qualified uncracked B5
AnalysisExecutionResult or owned-scratch/current-result bridge.** Even a complete
receipt remains factual and unqualified. A saved old B5 identity or old receipt
must not be rebound to these reads. The eventual live adapter must capture from
the same current B5 execution's owned scratch, retain the original source bridge,
verify exact current epoch and issue no identity itself.

## Native evidence matrix at worker exit

| Operand / signature | Current FC09 proof |
| --- | --- |
| RSX/RSY are response-spectrum cases | Prior accepted preflight; reused |
| Modal case, loads/functions/scales/CSys/angles | Prepared native getters; current values not read |
| Modal/directional method, damping, eccentricity/overrides/rigid treatment | Prepared native getters; actual values not assumed |
| U1/U2/U3 amplitudes and per-mode normalization | CSI semantics read; exact FC09 metadata/values not read |
| R_n | Pure signed weighted aggregate offline tested; current native values not proven |
| Δ_n | Pure scaling contract offline tested; endpoint/modal projection not live proven |
| V_n | Pure signed scalar scaling offline tested; exact native modal cut rows not live proven |
| Native aggregate comparison | No source identified as exact Column-only Σ(Ndi/li); Story Forces/Base React are not claimed to be R |
| Complete-story/full-mode native CQC/SRSS result | Pending current signature, normalization and matching B5 proof |
| Joint Δ/R/V selection | Project decision required; proposal below remains unapproved |

The existing recovered reference fixture/tests are reused unchanged. Its 32
columns and numbers do not supply FC09 modal normalization or a current epoch.

## Gate 2 — one bounded approval proposal (NOT APPROVED)

Proposal identifier: **FC09_EQ713_SHEAR_ANCHORED_CORRELATED_DESIGN_EFFECT_V1**.
This is a candidate project design statistic, not a claim about a physical
concurrent response or an existing TS500/CSI rule. It is not implemented.

For each explicitly approved X/Y earthquake alternative α, retain a common
vector of qualified signed native modal linear responses. Let d, r, v be the
modal vectors of the accepted physical story translation operator, complete
length-weighted Column axial aggregate and bottom-cut directional shear. Let Cα
be the exact source-supported modal/directional correlation operator for that
alternative, symmetric positive semidefinite. It cannot be guessed from CQC,
SRSS labels or assumed cross-direction independence.

Let (δ0,R0,V0) be the **same-B5** static 1.0G+1.0Q contributions, including only
any EDZ effect explicitly authorized for this stability alternative. Let
σV = sqrt(vᵀ Cα v) > 0 and define two correlated design-effect anchors:

z± = ± Cα v / σV

δ± = δ0 + dᵀ z±; R± = R0 + rᵀ z±; V± = V0 + vᵀ z±.

Then the proposed **project statistic** is

φ_project = max_{approved α, ±} 1.5 |δ±| R± / |V±|.

All operands share one anchor and one B5 basis. R is aggregated before modal
correlation. Anchors are mathematical design-effect projections, not synthetic
ETABS load cases, spectrum signs or concurrent modal time histories. No
protected case/combo or the 12 selected design combinations changes.

**The maximum above governs only this proposed finite design-effect policy.**
It is not a proved upper bound on the physical peak ratio or all possible joint
modal states. Shear anchoring is a deliberate engineering choice and cannot be
approved by this worker. In particular, anticorrelated or low-shear/high-drift
states may govern a different policy. The supervisor must positively accept
its applicability and unfavorable-selection meaning for TS500 before use.

Validity limits / required evidence:

- Complete applicable Column/mode populations, exact physical lengths, station
  signs and displacement projection; accepted A17 story-translation semantics
  apply without a new maximum-drift fallback.
- Qualified current uncracked B5 results for every G/Q/E operand, retained exact
  source/session/owned-scratch bridge and execution proof.
- Native normalization, actual modal/directional methods, modal periods/damping,
  rigid/eccentricity contributions and any method-specific corrections. If a
  quadratic Cα representation is not source-supported, this proposal fails.
- Explicit project approval of X/Y direction mapping, existing orthogonal
  alternatives and EDZ coefficients for **Eq.7.13**, not merely VS5. 1.4G+1.6Q
  concrete-design combos are not substituted for 1.0G+1.0Q.
- Every evaluated R± must remain in the accepted compression/applicability
  scope; every |V±| must be positively qualified and nonzero. No denominator
  floor, clipping tensile Column forces, discarded sign branch or zero-resultant
  spectrum assumption is permitted. Zero shear or missing scope is BLOCKED.
- Route-C W remains PROVEN_NOT_APPLICABLE by FC09 authority, not by inference.

Alternatives considered within this decision, not new work packages:

1. An explicit existing approved native joint-result statistic would supersede
   this proposal; separate ETABS modal maxima do not supply such a statistic.
2. Optimizing φ over a shared modal design domain would require approval of that
   domain and proof of a valid denominator throughout. A domain containing
   V=0 cannot be silently repaired with an arbitrary floor.
3. A ratio of separately combined marginal Δ/R/V extrema is a different project
   statistic and has no automatic concurrency or conservative-bound authority.
   It is not the selected proposal.

**Single exact approval statement sought:** For FC09 TS500 Eq.7.13 1.0G+1.0Q+E,
authorize or reject the shear-anchored correlated design-effect statistic above,
with an explicit source-supported Cα, accepted physical story translation,
X/Y/orthogonal/EDZ alternative schedule and the stated nonzero-shear/compression
validity limits, as the project's unfavorable stability design statistic.

No approval is implied by this document. Gate 1 must independently close before
Gate 2's accepted construction can be used. R2 PRODUCT_ADVANCEMENT_RUN remains
**NOT READY**.

## Final offline verification

**1035 distinct PASS / 0 FAIL / 0 ERROR / 0 SKIP**, including every one of the
prior 958 distinct test identities and 77 new focused regressions. Final
compile/import and diff checks pass. The machine receipt
`COLUMN_R1_R3C_OFFLINE_RECEIPT_2026-10-09.json` records the final tested code
hashes, denominator preservation and JUnit hashes. No live proof is claimed.
