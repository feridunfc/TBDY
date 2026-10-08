# Column-R1 R1: native I22/I33 authority boundary

Base main: `a7c8bab81eed687051c43b14fbf1e981b797a1e3` / tree
`c09a825569feec35cf7416398b743f711162d2be`. Offline audit, 2026-10-08.

**R1 = REVIEW_REQUIRED. No native production patch was implemented.**

## Exact gap and existing patterns

`tbdy_engine/etabs/oapi/frame_section_mechanics.py` already preserves a
successful 13-item GetSectProps raw tuple, independent I22/I33 numerical
values, source/session/capture references and cached unit observations.
`get_frame_section_mechanics_from_session` emits no unit provenance and
does not take fresh observations around the getter. A18 correctly refuses
both outputs with `MISSING_OR_DUPLICATE_OUTPUT_BINDING`.

The inspected source-authority census is deliberately limited:

| Existing evidence | Authorized scope | GetSectProps authority? |
|---|---|---|
| Q1N policy and `material_properties.py` | GetMPIsotropic E/G, F/L2, reviewed 23.2.0 / OAPI 2.014 present/display semantics | No; policy explicitly excludes other getters. |
| Q1P policy and session GetWall owner in `object_model.py` | GetWall Thickness, L, reviewed current-version compatibility | No; policy explicitly excludes other native getters. |
| Existing source-unit patch specification `COLUMN_R1_P1A_UNIT_OWNER_PATCH_SPEC.md` | GetSectProps inertia has L4 engineering dimension and verified ABI order | No; the document explicitly retains the installed-v23 source-semantics prerequisite. |
| `SourceUnitProvenance`, inertia normalization and A18 | Exact per-output/context validation and mm4/cm4/m4 downstream conversion | No; these validate supplied authority, rather than issuing CSI semantics. |
| `unit_contract_fixtures.py` | Independent `OFFLINE_SYNTHETIC_1` test authority | No installed ETABS authority. |

No method-specific accepted GetSectProps source-unit policy was found in
this bounded repository/reference scope. This is not a claim that CSI has
no such documentation. ABI identity, units that look plausible, the generic
transport rule and another getter's project policy cannot supply the missing
accepted method/version authority.

## Exact bounded approval packet

**Approval question:** Does the project reviewer approve a specifically
identified GetSectProps policy for ETABS 23.2.0 / OAPI 2.014, covering only
`I22` and `I33`, dimension `L4`, in freshly verified PRESENT/DISPLAY length
units raised to the fourth power, on one stable verified acquisition?

An affirmative artifact must identify the CSI-primary method/dimensional
and transport references, and explicitly accept their current-version
applicability through a scoped project compatibility policy where necessary.
Do not assert a literal CSI v23 mapping that the primary artifact does not
state. The existing Q1N/Q1P policy identifiers may not be reused or broadened.
If the reviewer cannot provide that authority, retain `REVIEW_REQUIRED`.

The approval must exclude Area/As2/As3/Torsion/S/Z/R outputs, historical
anomalous tuples, numerical factor fitting, results/sway/k/lambda, any
candidate and all live execution. It is authority for a subsequent bounded
implementation, not qualification of previously unobserved getter values.

## Subsequent patch boundary, conditional on approval

Extend the existing `get_frame_section_mechanics_from_session` owner only;
retain decoder, raw tuple, timeout and verified callback. Reuse the Q1N/Q1P
fresh-observation pattern on the existing gateway, not a second attachment
or a nested queued read. Issue separate I22 and I33 records, bound to each
output's own L4 source unit, exact section, raw response, model, session and
capture. Qualification requires stable fresh before/after identity/unit state
and zero native return. Keep all raw values unchanged.

The owned-scratch caller paths are
`etabs_frame_eq713_population_provider.py`'s factual population acquisitions;
both currently pass the verified session and assigned section to this getter.
They already have the trusted context and owned scratch used for material
E/G acquisition. Any eventual same-capture bridge must reuse those factory
identities and preserve observed active scratch identity; copying a cached
protected-source path cannot establish that equivalence. No bridge or caller
change was implemented before authority approval.

A18 and `normalize_frame_section_inertia_m4` remain unchanged. They must
continue requiring exact own GetSectProps output/context provenance. E1/G12,
native E/G, another property, base enums, report defaults and numerical
magnitudes remain unusable substitutes.

## Offline work completed while authority remains blocked

The new `test_frame_section_inertia_authority_boundary.py` exercises the
actual existing getter through a fake verified callback: one raw call, exact
tuple unchanged, both outputs unqualified despite cached valid units. It
also checks the existing DTO and real A18 consumer with independent
synthetic I22/I33 bindings: distinct identities, output/dimension/context
checks, missing/duplicate bindings, state drift, unsupported units and no
cross-property borrowing.

The shared mixed-vertical fixture now supplies its unchanged physical
inertias with exact raw tuple, context and independent synthetic per-output
bindings. This restores the existing E1/E2 and mixed-vertical regression
paths through the real A18 owner. Test assertions and production gates were
not relaxed. Synthetic success does not qualify the native getter.

Fresh native before/after acquisition qualification and real native positive
I22/I33 binding tests are **deferred pending authority**. Contract-level
synthetic drift tests do not claim those production behaviors exist.

Validation: 46 new authority-boundary tests; 483 tests in the focused
native/source-unit/A18/A3/B5/B6/Q1N/Q1P/metadata regression group; 7
reviewed-input binding, 2 E2 whole-system and 1 mixed-vertical test also pass.
The groups overlap on the 46 new tests: **493 distinct tests PASS**, 539
executions. The five inherited integrated fixture failures reproduced before
alignment are resolved. Final failures: zero. Compile/import and
`git diff --check` pass. No native Windows COM qualification was attempted.

`PRODUCTION_PATCH = NO`, `LIVE_EXECUTED = NO`, `RunAnalysis = 0`.
`NEXT_ACTIVE_EDGE = GETSECTPROPS_I22_I33_METHOD_SPECIFIC_AUTHORITY_REVIEW`
alongside the independent R0 FC09 project review. R1 is not closed as a
successful native wiring patch and R2 is not ready or authorized.
