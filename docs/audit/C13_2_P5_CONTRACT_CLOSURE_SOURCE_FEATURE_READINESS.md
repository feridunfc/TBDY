# C13.2-P5 Contract Closure + Source-to-Feature Readiness Matrix

## Purpose

C13.2-P5 closes the source-contract phase before any FeatureSnapshot,
FeatureResolver, or CheckEngine work. The sprint introduces a stable
`source_feature_readiness_matrix.yaml` plus schema and validator so future work can
see which existing feature IDs have a safe source path and which ones remain
blocked.

This sprint does **not** implement checks, does **not** unlock CheckEngine, and
does **not** change runtime behavior.

## Scope

P5 maps stable source families to existing feature readiness. It distinguishes:

- `READY_DIRECT_SOURCE`
- `READY_DERIVED_SOURCE`
- `READY_SUPPORTING_CONTEXT_ONLY`
- `BLOCKED_NEEDS_LIVE_PROBE`
- `BLOCKED_SEMANTIC_REVIEW`
- `BLOCKED_FEATURE_CONTRACT_MISSING`
- `OUT_OF_SCOPE_UNSUPPORTED`
- `LOCKED_CHECK_NOT_ALLOWED`

No new feature IDs are invented. Where the source capability exists but an
existing canonical feature ID does not, the matrix records the gap explicitly.

## Direct source readiness

The P4-promoted stable sources allow direct source-readiness rows for raw material
properties, story height, pier/wall direct geometry, and several existing frame,
column, modal, and base-reaction features. Direct readiness means only that the
source contract is stable enough for later FeatureSnapshot work.

It does not mean an engineering check can run.

## Derived source readiness

Story elevation is represented as a derived source capability, not a direct
column. P3/P4 established that:

- `Story Definitions` provides `Story`/`Name` and `Height`.
- `Tower and Base Story Definitions` provides `BSElev`.
- story elevation may be derived from `BSElev` plus cumulative story heights.
- `elevation_is_direct_column` remains false.

A future feature contract may add a canonical story elevation feature ID, but P5
records the source capability without inventing that ID.

## Supporting context only

Some verified live sources provide identity, mapping, or context only:

- frame identity and section assignment context
- material list/quantity context
- area/wall/pier identity context
- wall object connectivity and wall topology context

These sources can support future FeatureSnapshot logic but do not independently
produce an engineering feature or check verdict.

## Semantic review blockers

The following remain blocked for semantic review:

- `pier_forces`
- `beam_forces`
- concrete beam design summaries/results
- concrete column design summaries/results
- pier/wall design summaries/results
- ETABS rebar/design output interpretation
- force envelope and governing-result semantics
- combo/envelope/governing result semantics

These may not be marked as direct or derived ready sources for FeatureSnapshot or
CheckEngine use until a separate semantic review sprint proves the meaning.

## Remaining blockers before engineering checks

Before real engineering checks begin, the project still needs:

1. Source-to-feature runtime wiring, without fake defaults.
2. Live FeatureSnapshot proof that the promoted sources become real feature
   values.
3. Unit normalization policy for direct and derived features.
4. Missing/partial feature status policy.
5. Semantic review for design/result/rebar/force/envelope tables.

## Guardrails

P5 keeps the core guardrails:

```yaml
safe_to_implement_checks_now: false
check_unlock_allowed: false
feature_resolver_changed: false
check_engine_changed: false
report_renderer_changed: false
excel_production_input: false
```

P5 is therefore a contract-closure sprint only. It prepares the next phase; it
does not start the CheckEngine phase.

## Unit policy addendum

C13.2-P5 also closes unit handling at contract level. The policy is deliberately
contract-only and does not change `FeatureResolver`, `FeatureSnapshot`,
`CheckEngine`, report rendering, or any engineering formula.

The accepted unit policy is:

- ETABS live source values are accepted in the unit context returned by the live
  ETABS model/API.
- Raw source values must not be silently converted at source-contract level.
- Every source/feature readiness row carries explicit unit metadata:
  - `quantity_kind`
  - `source_unit_policy`
  - `normalized_unit_policy`
  - `default_report_unit`
- Report output may convert values to project default display units only when
  the value carries explicit unit metadata.
- Future FeatureSnapshot work must carry both raw and normalized unit metadata.
- Future CheckEngine work must not consume ambiguous raw numeric values without
  unit metadata.

Default report display units are:

| Quantity | Default report display unit |
|---|---|
| Force | kN |
| Moment | kN.m |
| Global length / elevation | m |
| Section dimensions | mm |
| Deformation / displacement | mm |
| Drift | ratio or percent, explicitly labeled |
| Stress / material strength | MPa |

This addendum does not unlock any check. `safe_to_implement_checks_now` remains
false and `check_unlock_allowed` remains false.
