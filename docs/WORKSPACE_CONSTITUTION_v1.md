# Workspace Constitution v1

C2 defines product/workspace state without implementing engine logic.

## Source rules

- `ETABS_LIVE` is the only production source.
- `FAKE_PROVIDER` is tests only.
- `EXCEL_FIXTURE` is tests/debug/regression only and must never become production input.
- `JSON_FIXTURE` is tests/debug/regression only and must never become production input.

## State families

The workspace state tracks model, element, feature, coverage, check and report state independently. Coverage runnability is separate from CheckResult status. A blocked coverage item cannot emit OK, and reports cannot be complete before checks have run or before `check_results_json` exists.

## Boundary

Workspace state is orchestration/product metadata only. It must not contain CheckResult objects, formulas, check logic, ETABS table names, combo regex, provider implementation, runtime/DAG/scheduler code, or CheckEngine logic.
