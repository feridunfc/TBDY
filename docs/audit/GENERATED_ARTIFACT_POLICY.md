# Generated Artifact Policy

## Authority

YAML contracts and Pydantic models are the source of truth for the TBDY Engine v3 contract system.

Generated artifacts are not runtime source of truth. Production runtime code must load contracts through the contract loader and build runtime objects from the current YAML contracts and Pydantic models.

## Committed schema artifacts

`tbdy_engine/contracts/generated/schema/*.schema.json` may be committed as documentation and external contract artifacts.

These schema files are derived from Pydantic models and must be kept fresh by tests. They are not imported by the runtime path.

## Runtime catalog artifacts

`tbdy_engine/contracts/generated/runtime_catalog.json` is not production authority.

If a runtime catalog snapshot is committed for regression coverage, the authoritative committed fixture belongs under `tests/golden/`, not under the production contract directory. The golden fixture must be generated from the contract-first loader default, which means `include_legacy=False`.

## History artifacts

`tbdy_engine/contracts/generated/history/*` is diagnostic output and is excluded from the production gate.

History snapshots are timestamped and should not be treated as release authority. They may be useful during audits, but they must not define production behavior.

## Legacy diagnostics

Legacy-enriched generated artifacts must be explicitly labeled diagnostic.

Any tool that enables legacy contract enrichment must require an explicit opt-in such as `--include-legacy` and must label its output as legacy diagnostic mode.

## Recommended policy

The recommended policy is Option D:

- Commit generated schemas as documentation and external contract artifacts.
- Do not treat generated runtime catalog files under `tbdy_engine/contracts/generated/` as production authority.
- Keep contract-first runtime catalog regression coverage under `tests/golden/`.
- Exclude generated history snapshots from production gates.
- Require explicit legacy opt-in for legacy-enriched generated artifacts.
