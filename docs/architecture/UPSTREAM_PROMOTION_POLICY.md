# ETABS-MCP Upstream Promotion Policy

The snapshot under `vendor/etabs-mcp` is immutable reference material.

## Never promote directly

- generic `execute_code`,
- same-process sandbox execution,
- unrestricted COM proxies,
- MCP server runtime,
- skill-generated operational code,
- automatic model unlock or analysis execution,
- ambiguous active-instance attachment.

## Required promotion sequence

1. Identify and document the exact upstream behavior.
2. Define the production requirement and typed contract.
3. Independently implement the smallest read-only method.
4. Add fixture tests and deterministic error contracts.
5. Add live ETABS proof tests.
6. Record ETABS version, units, identity, and evidence provenance.
7. Promote through a dedicated reviewed pull request.

Production work belongs under `packages/etabs_gateway`, never under `vendor`.

Vendor refresh is intentionally outside the genesis script and requires a
separate review workflow.