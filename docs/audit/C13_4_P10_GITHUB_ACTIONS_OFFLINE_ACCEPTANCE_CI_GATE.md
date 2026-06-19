# C13.4-P10 GitHub Actions Offline Acceptance CI Gate

## 1. Sprint purpose

C13.4-P10 adds GitHub Actions CI enforcement for the existing C13.4-P9 offline product acceptance gate.

The workflow runs on:

- pull requests targeting `main`;
- pushes to `main`.

The workflow delegates acceptance execution to the single canonical P9 CLI command:

```bash
python tools/run_offline_product_acceptance.py --out local_out/c13_4_ci_offline_acceptance
```

## 2. Why this sprint is offline

The workflow must run without ETABS. It does not call ETABS, Excel production inputs, Streamlit, live providers, FeatureResolver, P3 adapter, MinimalCheckEngine, CheckEngine, P4 runner, P5 renderer, P6 product smoke API, P7 validator API, or P8 golden regression API directly.

The only product acceptance execution path in CI is the P9 CLI.

## 3. Why CI delegates to P9 instead of duplicating commands

P9 is the canonical offline acceptance gate. CI must not reimplement the P1-P9 command list because duplication creates drift between local acceptance and CI acceptance.

By delegating to P9:

- local and CI execution use the same command plan;
- CI validates the real user-facing gate;
- lower-pipeline command changes remain centralized in P9;
- P10 stays workflow enforcement only.

## 4. Trigger policy

The workflow is:

```text
.github/workflows/c13_4_offline_acceptance.yml
```

Required triggers:

```yaml
on:
  pull_request:
    branches:
      - main
  push:
    branches:
      - main
```

## 5. Job policy

The workflow has one job:

```yaml
jobs:
  offline-acceptance:
    runs-on: ubuntu-latest
```

Required steps in order:

1. checkout;
2. setup Python;
3. install dependencies;
4. run offline acceptance gate;
5. upload acceptance artifacts.

## 6. Python version policy

The workflow uses Python 3.11:

```yaml
python-version: "3.11"
```

## 7. Dependency installation strategy

Repository dependency files were inspected before choosing the install strategy.

No usable dependency manifest was found at:

- `pyproject.toml`
- `requirements-dev.txt`
- `requirements.txt`

Therefore P10 uses the narrow explicit test/runtime install needed by the current offline acceptance chain:

```bash
python -m pip install --upgrade pip
python -m pip install pytest pyyaml jsonschema
```

This avoids adding or changing dependency files in this sprint.

## 8. Acceptance artifact upload policy

The workflow uploads acceptance output even when acceptance fails:

```yaml
if: always()
uses: actions/upload-artifact@v4
with:
  name: c13-4-offline-acceptance
  path: local_out/c13_4_ci_offline_acceptance
```

This preserves:

- `offline_product_acceptance_report.json`;
- P9-generated golden regression output;
- P8-generated product smoke and validation artifacts.

## 9. Workflow contract test coverage

P10 adds:

```text
tests/c13_4_p10/test_github_actions_offline_acceptance_workflow.py
```

The tests validate:

- workflow file exists;
- workflow name is exact;
- pull request and push triggers target `main`;
- one job named `offline-acceptance` exists;
- job runs on `ubuntu-latest`;
- checkout step exists;
- setup-python step exists;
- Python version is `3.11`;
- workflow runs exactly the P9 CLI command;
- workflow does not duplicate lower-level pytest commands;
- workflow does not directly call P6/P7/P8 product scripts;
- artifact upload has `if: always()`;
- artifact name and path match the contract;
- workflow contains no ETABS, Excel production, Streamlit, or final building compliance terms.

The tests avoid adding YAML parser dependencies by validating the workflow as text.

## 10. Explicitly excluded engineering scope

P10 excludes:

- ETABS live fetching;
- Excel production input;
- Streamlit UI;
- FeatureResolver execution;
- direct P3 adapter execution;
- direct MinimalCheckEngine execution;
- direct CheckEngine execution;
- direct P4 runner execution;
- direct P5 report renderer execution;
- direct P6 product smoke API import;
- direct P7 bundle validator API import;
- direct P8 golden regression API import;
- new engineering checks;
- beam flexure;
- beam shear;
- rebar adequacy;
- capacity design;
- governing combo selection;
- force envelope selection;
- SCWB;
- column PMM;
- drift compliance;
- modal mass checks;
- column area checks;
- column aspect ratio checks;
- final building compliance verdict.

## 11. Acceptance outputs

Required local acceptance commands:

```bash
python -m compileall -q tbdy_engine tools tests
python tbdy_engine/tools/validate_contract_constitution.py
python tools/audit_legacy_boundary.py
pytest -q tests/c13_4_p1
pytest -q tests/c13_4_p2
pytest -q tests/c13_4_p3
pytest -q tests/c13_4_p4
pytest -q tests/c13_4_p5
pytest -q tests/c13_4_p6
pytest -q tests/c13_4_p7
pytest -q tests/c13_4_p8
pytest -q tests/c13_4_p9
pytest -q tests/c13_4_p10
python tools/run_offline_product_acceptance.py --out local_out/c13_4_p10_offline_acceptance
```

Connector implementation note: this patch was authored through the GitHub connector. Local acceptance commands were not executed in this session, so no PASS is claimed here.

Current recorded status:

| Command | Status |
| --- | --- |
| `python -m compileall -q tbdy_engine tools tests` | NOT_RUN_IN_CONNECTOR_SESSION |
| `python tbdy_engine/tools/validate_contract_constitution.py` | NOT_RUN_IN_CONNECTOR_SESSION |
| `python tools/audit_legacy_boundary.py` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p1` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p2` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p3` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p4` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p5` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p6` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p7` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p8` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p9` | NOT_RUN_IN_CONNECTOR_SESSION |
| `pytest -q tests/c13_4_p10` | NOT_RUN_IN_CONNECTOR_SESSION |
| P9 offline acceptance CLI | NOT_RUN_IN_CONNECTOR_SESSION |
