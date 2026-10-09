# B-BLOK-COLUMN-FC09-REBIND-v1

## Current-source project authority

Classification: **REVIEWED_PROJECT_AUTHORITY / CURRENT_SOURCE_REBIND**.
Authority: supervisor's explicit FC09 SAME-VALUE REBIND decision supplied
2026-10-09 in `COLUMN-R1 — R0B FC09 REBIND → R2 READY`.
This document records that decision; it introduces no engineering values.
Historical review documents and accepted input bytes remain historical evidence.

| Identity | Exact binding |
| --- | --- |
| Historical reviewed B-BLOK source (5AA) | `5AA83947C46AE886DD43E8BD2270DAEAC6117AE60BAD1F8CB9ED9874CD3E2A44` |
| Current protected B-BLOK source (FC09) | `FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F` |
| Protected EDB | `C:\tmp\B-BLOK_Revised.EDB` |
| Accepted external inputs | `C:\tmp\column-r1-reviewed-inputs.py` |
| Accepted external input SHA256 | `9D7BAE7108C655751C018071E9B17D1D401A21904DAAD140BDBE81566AC9FBBC` |
| Successful live preflight receipt | `column-r1-r0-r1-preflight_20261009_192703.json` |
| Receipt SHA256 | `79A7BCA0DD50F42B6D9852D2ED56DFC03D0A1CDB40A1C534EA7071F6E8C4CE00` |
| Proven R1 live candidate HEAD | `9f29d5a5f5add26fe3bb2513675430f06fe4076b` |
| Proven R1 live candidate TREE | `6e174f86c0dd5f3e6badd98bc1c8cf20fab82a89` |

## R1 closed / live proven

The receipt reports `PASS_NATIVE_PENDING_R0_REVIEW`, ETABS **23.2.0**, API
**2.014**, exact PID **2072**, **15 / 15** factual native sections with two
independent qualified `I22 / L4` and `I33 / L4` bindings, and empty errors.
The protected source hash before and after is exactly FC09.
The native property authority is
`COLUMN_R1_GETSECTPROPS_PRESENT_L4_POLICY_V1`, issued as
`REVIEWED_PROPERTY_SOURCE_SEMANTICS` for exact
`SapModel.PropFrame.GetSectProps` successful native output captures.
R1 is **CLOSED / LIVE PROVEN**. This rebind neither modifies that owner nor A18.

## Same-value project rebind for FC09

| Reviewed policy | FC09 authorization |
| --- | --- |
| A17 absolute translation tolerance | `0.01 mm`; source ref `B-BLOK-COLUMN-FC09-REBIND-v1` |
| Concrete | `C35/45`, `fcd = 23.33 MPa` |
| Longitudinal steel | `DefaultRebar_500`, `fyd = 434.8 MPa` |
| Transverse steel | `DefaultRebar_500`, `fywk = 500 MPa`, `fywd = 434.8 MPa` |
| Maximum aggregate | `20.0 mm` |
| High ductility applicability | `TRUE` |
| Limited ductility applicability | `FALSE` |
| Route-C W | `PROVEN_NOT_APPLICABLE` |

These unchanged dependency values are authorized for FC09 by this current
project authority. Their original review refs and artifact identity remain
intact; historical bytes are not edited or relabeled. Route-C W is rebound
by the explicit supervisor review, not inferred from absence of a wind pattern.

## Exact combo reuse

The supervisor accepted the FC09 live-versus-historical comparison:
**12 / 12 selected rows EXACT MATCH** and
**12 / 12 complete combo definitions EXACT MATCH**.
The canonical equality packet SHA256 is
`A24412D2DECB10E715C2A235FE7FDE0545B4422CEEBB428C7540D9D074D18992`.
This equality digest is the supplied review packet identity, not a hash of the
preflight receipt or a newly inferred definition of canonicalization.
Reuse the existing exact `ExpectedConcreteDesignComboPolicy` unchanged,
including its exact constituents, types, factors and review provenance:

- Crack_SeisX, Crack_SeisX_Soil, Crack_SeisX_Up, Crack_SeisX_UpSoil
- Crack_SeisY, Crack_SeisY_Soil, Crack_SeisY_Up, Crack_SeisY_UpSoil
- Grav_Service, Grav_TempNeg, Grav_TempPos, Grav_Ult

## VS5 policy-only rebind

Reuse the accepted `ReviewedVs5ColumnAxialContext` unchanged for FC09:
Crack_SeisX / Crack_SeisY final combinations; G = LC_DL + LC_SDL + LC_WDL;
Q = LC_LL + LC_DDL; S = LC_S; horizontal E = RSX / RSY; vertical E = EDZ;
all existing exact baseline/fixed/target coefficients; allowed final steps
Max / Min; compression sign -1; reviewed linear superposition TRUE;
TS498 `NO_REDUCTION`; TS500 context Grav_Ult (including unchanged gamma_mc).
No response-spectrum zero-resultant assumption or new force semantics is added.

**Historical Nd/Ndm forces, modal results, AnalysisResultIdentity,
DesignResultIdentity and all historical result epochs must never be reused.**
R2 must generate fresh qualified analysis/design results and bind current
facts through the existing canonical owners. The preflight is factual evidence,
not a READY/B6 result or a substitute result epoch.

## Implementation and R2 gate

`tools/column_r1_bblok_fc09_reviewed_inputs.py` delegates verification and
loading to the existing accepted-input loader. It preserves the request and
exact dependency scope: `column_design_basis`, `expected_combo_policy`,
`reviewed_vs5_column_axial_context`. Only the A17 tolerance binding changes to
this current authority. Every other reviewed field/value remains unchanged.
The wrapper's explicit FC09 authority metadata and this document establish
current-source authorization without relabeling the external artifact.
No P7, Vc, final-cage or short-column authority is manufactured.

The canonical `tools/run_column_r1_public_acceptance.py` requires exact FC09
before execution and again after execution. Source verification is not weakened.
Following offline PASS on the clean rebind candidate, R0 is **CLOSED / FC09
REBIND IMPLEMENTED** and **R2_READY = YES**. No ETABS run is performed by the
worker preparing this candidate.

Next live mode: **PRODUCT_ADVANCEMENT_RUN**, through the existing public root
and canonical owned-scratch lifecycle. A3 may invoke bounded B5 generations
required by its fixed-point algorithm: ONE B5 OWNER is not ONE B5 INVOCATION.
There is no global `RunAnalysis <= 1` completion rule or default first-leaf-
blocker stop. Common hard cut-sets retain their fail-closed behavior.
READY = 0 means StartDesign = 0; READY > 0 permits one shared B6 and at most
one StartDesign, followed by legal READY Columns downstream and same-result
report delivery. All 260 READY are not required. Missing applicable downstream
route authority remains truthful and is handled only if exposed.
This authorization does not assert first READY, B6 live execution, 260 PASS,
or completed Column release.
