# Column-R1 R0: current-source authority reconciliation

Audit base: main `a7c8bab81eed687051c43b14fbf1e981b797a1e3`, tree
`c09a825569feec35cf7416398b743f711162d2be`. Offline audit, 2026-10-08.
Package 0, Q1J, Q1N, Q1P and G12 remain closed. No live access or source edit.

R0 is complete as an authority-state audit. **FC09 execution applicability is
not approved by this audit.** The companion JSON records evidence hashes and
the exact classifications below. Preservation/integrity and engineering
applicability are separate decisions.

## Source and input evidence

Historical reviewed source:
`5AA83947C46AE886DD43E8BD2270DAEAC6117AE60BAD1F8CB9ED9874CD3E2A44`.

Latest preserved physical-source evidence:
`FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F`.
`COLUMN_R1_POST_Q1P_LIVE.zip` contains equal source pre/post hashes and
`SOURCE_UNCHANGED=true`. Its receipt has zero RunAnalysis calls and no
qualified B5 result identity. This is evidence of the file at that capture,
not a new hash measurement, current in-memory identity, or result epoch.
The separately recorded source-model reference explicitly describes target
reference identity, not physical bytes or in-memory state.

The recovered `column-r1-reviewed-inputs.py` has SHA256
`9D7BAE7108C655751C018071E9B17D1D401A21904DAAD140BDBE81566AC9FBBC`,
exactly the accepted input digest. It was inspected through AST, not executed.
Both `PROTECTED_SOURCE_SHA256` and `COMBO_SNAPSHOT.source_sha256` still bind
the historical 5AA source. A matching input digest proves unchanged bytes;
it does not approve those bytes for FC09. Same filename/path is insufficient.

## Classification

| Required output | Disposition | Exact scope / reason |
|---|---|---|
| `FC09_SOURCE_IDENTITY` | `REUSE_AS_IS` | Latest preserved physical-file evidence only; no result-epoch promotion or fresh measurement. |
| `A17_TOLERANCE_APPLICABILITY` | `REVIEW_REQUIRED` | The approved 0.01 mm tolerance document explicitly pins 5AA and the old reviewed-input digest. Its historical approval remains intact; FC09 scope is unapproved. |
| `DESIGN_BASIS_APPLICABILITY` | `REVIEW_REQUIRED` | Material strengths, aggregate and ductility are supplied by the old project/report review; there is no explicit FC09 review binding. |
| `EXPECTED_COMBO_POLICY_APPLICABILITY` | `REVIEW_REQUIRED` | The exact 12-combo snapshot is 5AA-bound. No current FC09 combo-definition/selection evidence is substituted. |
| `VS5_APPLICABILITY` | `REVIEW_REQUIRED` | Reviewed Nd/Ndm case identities, signs, reduction and superposition depend on that historical review and result basis. |
| `W_APPLICABILITY` | `REVIEW_REQUIRED` | Route-C W is historically `PROVEN_NOT_APPLICABLE`; no FC09 factual reason/review has been supplied. |
| `HARNESS_PIN_STATUS` | `REBIND_REQUIRED` | Existing public harness correctly requires 5AA. Rebinding is conditional on project review and exact accepted input identity, not a blind hash edit. |
| accepted reviewed-input **integrity** hash | `REUSE_AS_IS` | 9D7BAE bytes verified. Their FC09 **engineering applicability** remains subject to the rows above. |
| historical 5AA combo/result numerics as FC09 truth | `OBSOLETE` | Preserve as historical evidence; do not promote to the changed source. |

No production pin, approval document, combo, tolerance or design value was
changed. The old wrapper remains a valid historical, fail-closed wrapper.

## Exact bounded review packet

Each question below permits **approve unchanged for FC09 / reject / require
specified additional evidence**. No answer is inferred from the source path.
Review must name the full FC09 digest, reviewer, date, evidence references and
the authorized scope. Rejecting a row leaves that authority blocked; it does
not trigger a replacement engineering method.

1. **A17 tolerance:** Does the project reviewer approve the existing
   `0.01 mm` absolute tolerance, only for signed Column-end relative
   translation equality, for the FC09 source? Evidence packet:
   `docs/B-BLOK-COLUMN-A17-TOL-v1.md`, original 5AA approval and the FC09
   source receipt. This does not approve sway or an uncracked result epoch.
2. **Design basis:** Are the existing C35/45 `fcd=23.33 MPa`,
   DefaultRebar_500 longitudinal `fyd=434.8 MPa`, transverse `fywk=500 MPa`
   / `fywd=434.8 MPa`, maximum aggregate `20 mm`, and high-ductility=true /
   limited-ductility=false review applicable unchanged to FC09? Evidence:
   the exact 9D7BAE file's `_column_design_basis`, its project/report and
   aggregate review references, plus a reviewer-supplied FC09 assignment /
   project-basis binding. This audit supplies no missing current assignment.
3. **Expected design combos:** Are the 12 exact historical selected Strength
   combos and their complete constituent/type/factor definitions still the
   approved FC09 design policy? The names are Crack_SeisX,
   Crack_SeisX_Soil, Crack_SeisX_Up, Crack_SeisX_UpSoil, Crack_SeisY,
   Crack_SeisY_Soil, Crack_SeisY_Up, Crack_SeisY_UpSoil, Grav_Service,
   Grav_TempNeg, Grav_TempPos and Grav_Ult. Evidence: the original
   `COMBO_SNAPSHOT` and combo review plus exact source-bound current
   definitions/selection supplied for review. Names alone are insufficient.
   Design-combo approval does not authorize a synthetic/static GQE/GQW
   stability state; the historical seismic leaves include RSX/RSY.
4. **VS5:** Does the reviewer affirm the existing `_vs5_context` for FC09,
   including Crack_SeisX/Y Nd/Ndm binding, the listed G/Q/S/EDZ/RSX/RSY
   constituents and coefficients, Max/Min acceptance, compression sign -1,
   reviewed linear superposition, NO_REDUCTION policy and Grav_Ult TS500
   context? Evidence: exact historical context and its review references plus
   current case definitions and physical/result applicability. No historical
   forces, modal signs or result epochs are carried across by this approval.
5. **Route-C W:** Is `PROVEN_NOT_APPLICABLE` still the reviewed W action-family
   state for FC09? Require the exact current project/factual reason and scope,
   not the mere presence/absence of an old W-named combo.
6. **Reviewed-input artifact and harness:** After rows 1-5 are resolved, which
   exact immutable input artifact/review manifest is accepted for FC09, with
   which byte digest? The original 9D7BAE artifact may remain preserved, but
   its embedded 5AA source may not be relabelled silently. Only a concrete
   approved binding permits a bounded harness/wrapper pin change. Do not
   specify a new accepted digest before approved bytes exist.

Historical references inspected in the recovered bytes include
`review:column-r1:B-BLOK:2026-09-27`,
`review:column-r1:B-BLOK:current-12-exact-design-combos:2026-09-27`,
`review:column-r1:B-BLOK:aggregate-max:20mm:2026-09-27`, and
`review:column-r1:B-BLOK:route-c-w:PROVEN_NOT_APPLICABLE:2026-09-27`.
The report reference is
`gdrive:1rrUjxEP2kk20EFR5INSyIxlDlAEPXeIF:Yapisal_Tasarim_Raporu_v2_Kapsamli.docx`;
this audit records its reference, not a new review of that report.

`REVIEW_REQUIRED_ITEMS = A17_FC09, DESIGN_BASIS_FC09, COMBOS_FC09,
VS5_FC09, ROUTE_C_W_FC09, ACCEPTED_INPUT_FC09_BINDING`.

The independent R1 offline audit may continue. R2 is not ready or authorized
until the required source and native-property authorities are resolved.
