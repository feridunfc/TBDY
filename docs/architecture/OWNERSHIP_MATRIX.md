# TBDY-NEXT Ownership Matrix

| Concern | Authoritative owner |
|---|---|
| Existing engineering source and Git history | TBDY repository |
| `FeatureSnapshot`, evidence, and coverage | TBDY engineering kernel |
| `CheckInput`, checks, and `CheckResult` | TBDY engineering kernel |
| Engineering audit and report semantics | TBDY engineering kernel |
| ETABS COM/STA lifecycle | Future typed ETABS gateway |
| Explicit ETABS read methods | Future typed ETABS gateway |
| Raw source contracts | Gateway–kernel boundary |
| Request/response contracts | `contracts/` |
| CLI, local API, and desktop entry points | `apps/` |
| ETABS-MCP upstream source | `vendor/etabs-mcp`, reference-only |

## Forbidden dependencies

- Check code must not import ETABS COM infrastructure.
- Check code must not know ETABS table names.
- The gateway must not emit `CheckResult` or contain TBDY formulas.
- Reporting must not recompute engineering decisions.
- Production code must not import the vendored ETABS-MCP runtime.
- Generic code execution must not be exposed to a live ETABS model.
- Identity resolution must never silently select the first ambiguous match.

## Planned runtime flow

```text
Typed Request
  -> Application Use Case
  -> Check Scope / Required Features
  -> Source Planner
  -> Typed ETABS Gateway
  -> Raw Evidence Bundle
  -> Identity and Topology Resolution
  -> Feature Resolvers
  -> FeatureSnapshot
  -> Coverage
  -> CheckInput
  -> Check Engine
  -> CheckResult
  -> Assessment
  -> Reporting
```