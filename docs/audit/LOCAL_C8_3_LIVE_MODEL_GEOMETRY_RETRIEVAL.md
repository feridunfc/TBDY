# C8.3 Live Model Definition Geometry Retrieval

C8.3 is a FeatureResolver smoke patch only. It keeps CheckEngine and CheckResult
out of the live path and does not emit OK/FAIL engineering verdicts.

## Purpose

Manual C8.2 showed model-definition display tables with headers and reported
records but empty TableData. C8.3 adds two safe mechanisms:

1. Deep diagnostics for `GetTableForDisplayArray` return shapes and parser
   strategies.
2. Read-only direct ETABS API/provider fallback for beam width, depth, and
   length when model-definition table rows are unavailable.

## Geometry rule

Geometry may be RESOLVED only from real rows or verified read-only direct API / provider data.
Section-name parsing such as `B40x70 -> 400/700` remains diagnostic-only and is
never used as a feature value.

## Boundary

- CheckEngine executed: false
- CheckResult emitted: false
- OK/FAIL emitted: false
- Rebar/flexure/shear unlocked: false
- Live ETABS path: opt-in only
- Excel/Streamlit/PDF production paths: false

## Manual command

```powershell
python tools/smoke_live_feature_resolver.py `
  --out local_out/c8_3_live_model_geometry_retrieval `
  --live-etabs `
  --target-component 297 `
  --target-label B1 `
  --target-story +14.5 `
  --target-section B40x70
```

## Expected C8.3 live retry outcome

Proceed to manual C9/C10/C11 chain only if:

- unit context is RESOLVED
- beam_width_mm has FULL evidence
- beam_depth_mm has FULL evidence
- beam_length_mm has FULL evidence
- drift/torsion semantic lock remains intact
- no CheckEngine execution occurred during C8.3
- no CheckResult was emitted during C8.3
