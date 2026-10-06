# COLUMN-R1 E0 blocker census

## Scope and provenance

Exact top-level population census from the accepted receipt and slim summary. This is not a census of every nested readiness/evidence blocker.

- Repository HEAD: `951a9b156d53210c7a8520bebfa291a3e3b38ee4`
- Repository TREE: `289fd8e9123a192d260257a270ac62bfeed9faf6`
- Receipt: `receipt(1).json`; SHA256 `034d0c0ed1a98e621f5b64a61e80b65c521825dc6c7c9802d1c4d8d9515db990`
- Summary: `COLUMN_R1_E0_LIVE_SUMMARY.json`; SHA256 `565a59a32cd0073925991ad36353d8c8758b33e3ccab6ba1a83019d3972314e5`
- Local forensic source: `C:\tmp\COLUMN_R1_FINAL_LIVE_951a9b_ATTEMPT2\project-artifact.json` (not loaded; no live access).
- Fields: receipt `$.outcomes[component_id].status`, `.blockers`, `$.component_count`, `$.ready_count`, `$.owner_calls`, `$.composition_checks`; summary `$.columns[*].component_id/status/blockers`, `$.status_counts`, `$.blocker_counts`, `$.blocker_combinations`, `$.receipt_sha256`.
- Verification: all 260 unique IDs and complete status/blocker lists match the receipt exactly; all three summary histograms recompute exactly; receipt byte hash matches. No duplicate blocker within a component.

## Population

| Metric | Count |
|---|---:|
| TOTAL_COLUMNS | 260 |
| READY_COUNT | 0 |
| UNRESOLVED_COUNT | 260 |
| Other top-level statuses | 0 |
| Unique blocker tokens | 12 |
| Blocker occurrences | 450 |
| Exact blocker combinations | 14 |

## Exact token frequencies

Each frequency also equals the number of affected columns. Bxx labels below are display aliases only.

| Alias | Exact token | Columns |
|---|---|---:|
| B01 | `A17:REVIEWED_STORY_TRANSLATION_TOLERANCE_NOT_BOUND` | 142 |
| B02 | `A18:BOTTOM:M2:END_RESTRAINT_RATIO_UNRESOLVED:Eq.7.16 beam-restraint denominator is unresolved/empty` | 101 |
| B03 | `A18:BOTTOM:M2:MISSING_FRAME_FACT:760` | 1 |
| B04 | `A18:BOTTOM:M2:MISSING_FRAME_FACT:761` | 1 |
| B05 | `A18:BOTTOM:M2:MISSING_FRAME_FACT:762` | 1 |
| B06 | `A18:BOTTOM:M2:MISSING_FRAME_FACT:985` | 1 |
| B07 | `A18:BOTTOM:M3:END_RESTRAINT_RATIO_UNRESOLVED:Eq.7.16 beam-restraint denominator is unresolved/empty` | 105 |
| B08 | `A18:TOP:M2:END_RESTRAINT_RATIO_UNRESOLVED:Eq.7.16 beam-restraint denominator is unresolved/empty` | 19 |
| B09 | `A18:TOP:M2:MISSING_FRAME_FACT:760` | 1 |
| B10 | `A18:TOP:M2:MISSING_FRAME_FACT:985` | 1 |
| B11 | `A18:TOP:M3:END_RESTRAINT_RATIO_UNRESOLVED:Eq.7.16 beam-restraint denominator is unresolved/empty` | 21 |
| B12 | `A19:BLOCKED_TS500_REGULATORY_FREE_LENGTH` | 56 |

## Exact combinations / co-occurrence

| Token set | Columns |
|---|---:|
| B01 | 142 |
| B02, B07 | 60 |
| B02, B07, B11, B12 | 11 |
| B07, B12 | 11 |
| B02, B07, B08, B12 | 9 |
| B02, B12 | 9 |
| B02, B07, B08, B11, B12 | 6 |
| B02, B07, B12 | 6 |
| B03, B08, B11, B12 | 1 |
| B04, B07, B08, B11, B12 | 1 |
| B05, B07, B08, B11, B12 | 1 |
| B06, B08, B11, B12 | 1 |
| B09 | 1 |
| B10 | 1 |

Family co-occurrence: A17 only = 142; A18 without A19 = 62; A18 with A19 = 56; A19 without A18 = 0; A17 with A18/A19 = 0.

## Story identifier groups

Groups use the exact component-ID prefix; no geometric story reconstruction is inferred.

| Prefix | Columns | A17 | A18 | A19 |
|---|---:|---:|---:|---:|
| +0.00 | 86 | 0 | 86 | 26 |
| +14.5 | 19 | 19 | 0 | 0 |
| +4.50 | 83 | 55 | 28 | 26 |
| +9.00 | 72 | 68 | 4 | 4 |

## Causal interpretation and evidence limits

- All 260 do NOT share the same first exposed blocker. The exposed execution-gate partition is A18 = 118 and A17 tolerance = 142. There are no A19-only columns.
- Repository source: `tbdy_engine/application/column_public_a5_second_order.py`, A18/free-length checks at lines 329–345; accumulated-blocker return at lines 435–436; tolerance check at lines 438–443. A18/A19 prerequisite failures return before tolerance is checked. Stage numbering or lexical token order is not a causal ordering.
- A17 is a shared reviewed-authority gap, exposed on 142 columns. The remaining 118 have an earlier exposed prerequisite failure; the summary does not establish their nested tolerance state.
- A18 affects 118 component contexts. Empty/unresolved denominators are exact end/axis-specific symptoms, not permission to assign zero, repair geometry, or invent stiffness. Missing-frame tokens affect six columns referencing four shared frame identities (760, 761, 762, 985). They are six component/end-specific exposures, not six proven independent physical defects.
- A19 occurs on 56 columns, all with A18. Co-occurrence alone does not prove A19 is caused by A18; nested free-length evidence is needed to classify its root. No automatic repair follows from this census.
- `BLOCKED_TS500_EQ7_13_GLOBAL_UNCRACKED_BASIS_NOT_PROVEN` occurs ZERO times in these top-level lists. The current handoff reports it for focus `+14.5:C1:36`; zero top-level occurrences does not prove zero nested occurrences, resolution, or population-wide scope. Whole-system positive proof is a shared authority/evidence concern; exact nested affected-column count remains NOT_ESTABLISHED.
- FND2 readiness is not qualified anywhere (READY_COUNT=0). Receipt `owner_calls.B6=0` and `.StartDesign=0` prove those owners were not invoked. Selection/detailing/transverse/P7 completion is not established by this slim summary. The current handoff reports their absent population; this census does not pretend to independently inspect those nested fields.
- A38/A39/A40 are present and composition checks pass. Reporting must preserve UNRESOLVED; it cannot reinterpret it as engineering PASS or FAIL.

## Next engineering edge (E1)

Review existing story-translation tolerance authority through the repository and project-source corpus, bind only a reviewed value with provenance, and keep the current no-default rule. Do not infer a tolerance from observed displacement noise. E1 alone cannot be assumed to resolve all 260: 118 have earlier exposed A18 prerequisites, including 56 A19 co-occurrences. E2 nested scope remains to be established from local evidence when needed.

## Per-component exact blocker membership

| Component ID | Status | Blockers | First exposed gate |
|---|---|---|---|
| `+0.00:C1:235` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C10:271` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C104:211` | UNRESOLVED | B02, B07, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C105:212` | UNRESOLVED | B02, B07, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C106:213` | UNRESOLVED | B02, B07, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C107:214` | UNRESOLVED | B02, B07, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C108:215` | UNRESOLVED | B02, B07, B08, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C109:228` | UNRESOLVED | B02, B07, B08, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C11:272` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C110:233` | UNRESOLVED | B02, B07, B08, B12 | A18 (A19 co-occurs) |
| `+0.00:C111:241` | UNRESOLVED | B02, B07, B08, B12 | A18 (A19 co-occurs) |
| `+0.00:C112:250` | UNRESOLVED | B02, B07, B08, B12 | A18 (A19 co-occurs) |
| `+0.00:C113:259` | UNRESOLVED | B02, B07, B08, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C12:273` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C13:274` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C15:280` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C16:281` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C17:282` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C18:283` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C19:284` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C2:236` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C20:216` | UNRESOLVED | B02, B07, B08, B12 | A18 (A19 co-occurs) |
| `+0.00:C21:217` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C22:218` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C23:219` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C24:220` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C25:221` | UNRESOLVED | B02, B07, B08, B12 | A18 (A19 co-occurs) |
| `+0.00:C26:222` | UNRESOLVED | B02, B07, B08, B12 | A18 (A19 co-occurs) |
| `+0.00:C27:223` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C28:224` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C29:225` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C30:226` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C31:227` | UNRESOLVED | B02, B07, B08, B12 | A18 (A19 co-occurs) |
| `+0.00:C32:229` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C33:230` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C34:231` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C35:232` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C36:234` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C37:240` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C38:244` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C39:249` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C40:251` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C41:252` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C42:253` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C43:254` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C44:255` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C45:256` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C46:257` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C47:258` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C48:260` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C49:261` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C5:239` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C50:262` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C51:263` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C52:264` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C53:265` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C54:266` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C55:267` | UNRESOLVED | B02, B07, B08, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C56:268` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C57:269` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C58:270` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C59:275` | UNRESOLVED | B02, B07, B08, B12 | A18 (A19 co-occurs) |
| `+0.00:C6:245` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C60:279` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C61:285` | UNRESOLVED | B02, B07, B08, B12 | A18 (A19 co-occurs) |
| `+0.00:C62:288` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C63:289` | UNRESOLVED | B02, B07, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C64:290` | UNRESOLVED | B02, B07, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C65:291` | UNRESOLVED | B02, B07, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C66:292` | UNRESOLVED | B02, B07, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C67:293` | UNRESOLVED | B02, B07, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C68:294` | UNRESOLVED | B02, B07, B08, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C7:246` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C73:276` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C74:287` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C75:295` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C76:296` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C77:237` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C78:238` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C8:247` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C82:242` | UNRESOLVED | B02, B07, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C83:243` | UNRESOLVED | B02, B07, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C86:277` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C87:278` | UNRESOLVED | B02, B07 | A18 |
| `+0.00:C88:210` | UNRESOLVED | B02, B07, B08, B11, B12 | A18 (A19 co-occurs) |
| `+0.00:C9:248` | UNRESOLVED | B02, B07 | A18 |
| `+14.5:C1:36` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C10:45` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C11:46` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C12:47` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C13:48` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C15:50` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C16:51` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C17:52` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C18:53` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C19:54` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C2:37` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C5:40` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C6:41` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C7:42` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C73:49` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C77:38` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C78:39` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C8:43` | UNRESOLVED | B01 | A17 tolerance |
| `+14.5:C9:44` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C1:152` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C10:188` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C104:128` | UNRESOLVED | B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C105:129` | UNRESOLVED | B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C106:130` | UNRESOLVED | B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C107:131` | UNRESOLVED | B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C108:132` | UNRESOLVED | B02, B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C109:145` | UNRESOLVED | B02, B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C11:189` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C110:150` | UNRESOLVED | B02, B12 | A18 (A19 co-occurs) |
| `+4.50:C111:158` | UNRESOLVED | B02, B12 | A18 (A19 co-occurs) |
| `+4.50:C112:167` | UNRESOLVED | B02, B12 | A18 (A19 co-occurs) |
| `+4.50:C113:176` | UNRESOLVED | B02, B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C12:190` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C13:191` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C15:197` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C16:198` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C17:199` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C18:200` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C19:201` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C2:153` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C20:133` | UNRESOLVED | B02, B12 | A18 (A19 co-occurs) |
| `+4.50:C21:134` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C22:135` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C23:136` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C24:137` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C25:138` | UNRESOLVED | B02, B12 | A18 (A19 co-occurs) |
| `+4.50:C26:139` | UNRESOLVED | B02, B12 | A18 (A19 co-occurs) |
| `+4.50:C27:140` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C28:141` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C29:142` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C30:143` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C31:144` | UNRESOLVED | B02, B12 | A18 (A19 co-occurs) |
| `+4.50:C32:146` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C33:147` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C34:148` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C35:149` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C36:151` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C37:157` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C38:161` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C39:166` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C40:168` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C41:169` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C42:170` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C43:171` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C44:172` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C45:173` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C46:174` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C47:175` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C48:177` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C49:178` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C5:156` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C50:179` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C51:180` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C52:181` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C53:182` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C54:183` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C55:184` | UNRESOLVED | B02, B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C56:185` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C57:186` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C58:187` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C59:192` | UNRESOLVED | B02, B12 | A18 (A19 co-occurs) |
| `+4.50:C6:162` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C60:196` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C61:202` | UNRESOLVED | B02, B12 | A18 (A19 co-occurs) |
| `+4.50:C62:203` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C63:204` | UNRESOLVED | B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C64:205` | UNRESOLVED | B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C65:206` | UNRESOLVED | B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C66:207` | UNRESOLVED | B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C67:208` | UNRESOLVED | B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C68:209` | UNRESOLVED | B02, B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C7:163` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C73:193` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C77:154` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C78:155` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C8:164` | UNRESOLVED | B01 | A17 tolerance |
| `+4.50:C82:159` | UNRESOLVED | B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C83:160` | UNRESOLVED | B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C86:194` | UNRESOLVED | B09 | A18 |
| `+4.50:C87:195` | UNRESOLVED | B10 | A18 |
| `+4.50:C88:127` | UNRESOLVED | B02, B07, B12 | A18 (A19 co-occurs) |
| `+4.50:C9:165` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C1:72` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C10:103` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C11:104` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C12:105` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C13:106` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C15:110` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C16:111` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C17:112` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C18:113` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C19:114` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C2:73` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C20:55` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C21:56` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C22:57` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C23:58` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C24:59` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C25:60` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C26:61` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C27:62` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C28:63` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C29:64` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C30:65` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C31:66` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C32:67` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C33:68` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C34:69` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C35:70` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C36:71` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C37:77` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C38:78` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C39:83` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C40:84` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C41:85` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C42:86` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C43:87` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C44:88` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C45:89` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C46:90` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C47:91` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C48:92` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C49:93` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C5:76` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C50:94` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C51:95` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C52:96` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C53:97` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C54:98` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C55:99` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C56:100` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C57:101` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C58:102` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C59:107` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C6:79` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C60:109` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C61:115` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C62:116` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C63:117` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C64:118` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C65:119` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C66:120` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C67:121` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C68:122` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C69:123` | UNRESOLVED | B06, B08, B11, B12 | A18 (A19 co-occurs) |
| `+9.00:C7:80` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C70:124` | UNRESOLVED | B04, B07, B08, B11, B12 | A18 (A19 co-occurs) |
| `+9.00:C71:125` | UNRESOLVED | B05, B07, B08, B11, B12 | A18 (A19 co-occurs) |
| `+9.00:C72:126` | UNRESOLVED | B03, B08, B11, B12 | A18 (A19 co-occurs) |
| `+9.00:C73:108` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C77:74` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C78:75` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C8:81` | UNRESOLVED | B01 | A17 tolerance |
| `+9.00:C9:82` | UNRESOLVED | B01 | A17 tolerance |
