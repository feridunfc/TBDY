# ETABS-MCP — Reference Only

`vendor/etabs-mcp` is a policy-filtered tracked source snapshot of one recorded
upstream commit. Generated Python bytecode/cache files are excluded explicitly and
recorded in provenance. It is not part of the production runtime.

Do not:

- edit files under the vendor snapshot,
- place the vendor path on `PYTHONPATH`,
- include it in package discovery,
- activate its MCP server, sandbox, or `execute_code` surface.

Verify the invariant with:

```powershell
python tools/verify_etabs_mcp_vendor.py
```