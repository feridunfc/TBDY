# C13.2-P1 Architecture Guardrail Hotfix

## Purpose

C13.2-P1 is a verification gate only. It uses Excel/JSON inventory as probe target evidence and never as production input or source of truth.

## Guardrails enforced

- Excel inventory cannot produce `VERIFIED_LIVE` in parse-only mode.
- `VERIFIED_LIVE` requires live ETABS proof: live table fetch, live headers, expected header validation, and sample rows/meaningful empty proof.
- Default behavior probes only families/tables observed in the Excel/JSON inventory.
- The tool does not probe every internal `FAMILY_RULE` by default.
- Absent known families are omitted by default.
- `--include-planned-families` may report absent known families as `PLANNED`, but planned rows have no live candidates and are never fetched.
- Design/force/rebar output sources remain `SEMANTIC_REVIEW` and cannot unlock checks.
- `safe_to_implement_checks_now` is always `false`.
- No catalogs, schemas, FeatureResolver, CheckEngine, or product report renderer are changed.

## Files changed

- `tools/probe_excel_guided_live_contract_sources.py`
- `tests/c13_2_p1/test_excel_guided_live_source_probe.py`
- `docs/audit/C13_2_P1_EXCEL_GUIDED_LIVE_SOURCE_VERIFICATION.md`
- `docs/audit/C13_2_P1_ARCHITECTURE_GUARDRAIL_HOTFIX.md`
- `c13_2_p1_changed_files.txt`

## Validation

Local package validation:

```text
python -m compileall -q tools tests: PASS
pytest tests/c13_2_p1 -q: 14 passed
```

Repository validation still required after applying the patch into the full repo:

```powershell
python -m compileall -q tbdy_engine tests tools
pytest tests/c13_2_p0 -q
pytest tests/c13_2_p1 -q
pytest tests/c13_1 -q
pytest tests/c13_0 -q
```

## Recommended live command

```powershell
python tools/probe_excel_guided_live_contract_sources.py `
  --excel-inventory path\to\etabs_export.xlsx `
  --out local_out/c13_2_p1_excel_guided_live_probe `
  --live-etabs `
  --probe-profile verification_gate `
  --max-candidate-tables-per-family 3 `
  --max-sample-rows 50 `
  --preferred-output-case Crack_SeisY_UpSoil
```

Do not use `--include-planned-families` for the acceptance live run unless the goal is only to list planned absent families. Planned absent families are not live-fetched.

## Final hygiene metadata hotfix

Every `source_promotion_recommendation.json` row now carries explicit Excel/live-fetch provenance metadata:

```yaml
observed_in_excel: true | false
planned_without_excel_evidence: true | false
live_fetch_allowed: true | false
```

Rules:

- `observed_in_excel` is true only when the family appears in the Excel/JSON inventory and the row is not a planned-absent row.
- `planned_without_excel_evidence` is true only for explicit `--include-planned-families` planned-absent rows.
- `live_fetch_allowed` is false for all planned-absent rows.
- Default `verification_gate` remains inventory-scoped and does not generate absent-family rows.

Cache artifacts are intentionally excluded from the release package.

## Semantic promotion hotfix addendum

After live verification, `VERIFIED_LIVE` is additionally gated by semantic
source-role validation.  Generic keyword/header matches are not enough.

- `material_properties` cannot be verified by `Material List by Story`.
- `frame_section_material_assignments` cannot be verified by `Frame Assignments - Section Properties` without a `Material` header.
- Context-only families such as `material_list_by_story` and
  `frame_section_assignments` may be verified only as context sources with
  `check_unlock_allowed: false`.
