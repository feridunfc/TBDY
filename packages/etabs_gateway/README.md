# Typed ETABS Gateway

Phase-1.7 deterministic offline acceptance gate is active.

## Current implementation

- immutable typed gateway contracts,
- dedicated STA worker and lazy COM apartment lifecycle,
- read-only running-instance attachment,
- application/model/unit context extraction,
- deterministic session orchestration,
- canonical fixture/replay with SHA-256 integrity,
- repository-level offline acceptance report,
- source architecture boundary scanning,
- phase-manifest validation,
- vendor checksum verification,
- one-command JSON-capable acceptance CLI.

Run the complete ETABS-free gate from the repository root:

```powershell
python tools/verify_etabs_gateway_offline.py `
  --json-out local_out/etabs_gateway_offline_acceptance.json
```

The command checks:

1. fixture schema and SHA-256 integrity,
2. canonical deterministic fixture JSON,
3. production source import/call ownership boundaries,
4. active phase and fail-closed manifest boundaries,
5. immutable vendored ETABS-MCP checksums.

A PASS proves only that the offline gateway contracts, deterministic replay,
source boundaries, provenance, and vendor integrity are internally consistent.
It does not prove live ETABS compatibility, model correctness, analysis/design
result correctness, or TBDY compliance.
