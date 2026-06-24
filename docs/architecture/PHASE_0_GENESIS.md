# TBDY-NEXT Phase-0 Genesis Boundary

## Objective

Keep the existing TBDY repository and full Git history as the product root.
Add ETABS-MCP as a quarantined, immutable source reference snapshot.

## Performed

- The existing TBDY repository remains the Git root.
- Existing TBDY source files and imports are not moved or rewritten.
- ETABS-MCP tracked source files are placed under `vendor/etabs-mcp`.
- Exact upstream commit, included-file hashes, and explicit generated-artifact exclusions are recorded.
- A persistent vendor verifier is installed under `tools/`.
- Documentation-only locations are created for the future typed gateway.

## Not performed

- No ETABS COM connection is activated.
- No MCP server or `execute_code` surface is activated.
- No vendor runtime is added to `PYTHONPATH` or package discovery.
- No engineering formula, check, `FeatureSnapshot`, or `CheckResult` behavior changes.
- No analysis, unlock, write, push, or merge is performed.

## Immutable vendor rule

`vendor/etabs-mcp` is reference-only. It is guarded by:

```text
provenance/ETABS_MCP_UPSTREAM_SHA256.json
tools/verify_etabs_mcp_vendor.py
```

Production implementation belongs under `packages/etabs_gateway` and must be
independently implemented behind typed contracts.