name: PRODUCT-SPINE-COL-1 Validation

on:
  push:
    branches:
      - sprint/col-runtime-1-production-runtime
  workflow_dispatch:

permissions:
  contents: read

env:
  FROZEN_BASE: 74d5b6083afed75e44b832336c31755aee482daa

jobs:
  product-spine-col-1:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout exact candidate head
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          ref: ${{ github.sha }}

      - name: Verify frozen-base ancestry and initial hygiene
        shell: bash
        run: |
          test "$(git merge-base "$FROZEN_BASE" HEAD)" = "$FROZEN_BASE"
          test "$(git rev-parse "$FROZEN_BASE")" = "$FROZEN_BASE"
          git diff --check "$FROZEN_BASE"...HEAD
          echo "candidate_head=$(git rev-parse HEAD)"
          echo "frozen_base=$FROZEN_BASE"
          git diff --name-only "$FROZEN_BASE"...HEAD

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install accepted repository test toolchain
        run: |
          python -m pip install --upgrade pip
          python -m pip install \
            pytest \
            pyyaml \
            jsonschema \
            weasyprint==69.0 \
            pydyf==0.12.1 \
            pypdf==6.16.1 \
            pypdfium2==5.12.1 \
            openpyxl==3.1.5 \
            et_xmlfile==2.0.0

      - name: Compile application spine
        run: |
          python -m compileall -q tbdy_engine tests
          python - <<'PY'
          import inspect
          from tbdy_engine.application import ColumnExecutionRequest, ProjectExecutionRequest, execute_project
          assert tuple(inspect.signature(execute_project).parameters) == ("request", "verified_session")
          print(ColumnExecutionRequest, ProjectExecutionRequest, inspect.signature(execute_project))
          PY

      - name: Focused A1-P1 proofs
        run: |
          python -m pytest -q \
            tests/application/test_product_spine_col_1.py \
            tests/regulatory/test_fnd_col_2x_typed_execution_artifact.py \
            tests/design/columns/test_column_longitudinal_selection_policy_factory.py \
            tests/design/columns/test_p8a_b_column_longitudinal_production_composition.py \
            tests/design/columns/test_fnd_col_4_pmm_assessment.py \
            tests/regulatory/test_fnd_col_1_longitudinal_authority.py \
            tests/coverage/test_fcr_1a_project_reconciliation.py \
            tests/product_reports/test_unified_building_report.py

      - name: Candidate broad versus frozen-base broad
        shell: bash
        run: |
          set +e
          python -m pytest -q > /tmp/candidate.log 2>&1
          candidate_rc=$?
          git worktree add --detach /tmp/frozen-base "$FROZEN_BASE"
          (
            cd /tmp/frozen-base
            python -m pytest -q > /tmp/base.log 2>&1
          )
          base_rc=$?
          set -e

          grep -E '^(FAILED|ERROR) |^ERROR collecting ' /tmp/candidate.log | sort -u > /tmp/candidate.sig || true
          grep -E '^(FAILED|ERROR) |^ERROR collecting ' /tmp/base.log | sort -u > /tmp/base.sig || true
          comm -23 /tmp/candidate.sig /tmp/base.sig > /tmp/new.sig || true
          comm -23 /tmp/base.sig /tmp/candidate.sig > /tmp/missing.sig || true

          echo "candidate_pytest_exit=$candidate_rc"
          echo "frozen_base_pytest_exit=$base_rc"
          echo "candidate_failure_signatures:"
          cat /tmp/candidate.sig || true
          echo "frozen_base_failure_signatures:"
          cat /tmp/base.sig || true
          echo "new_failure_signatures:"
          cat /tmp/new.sig || true
          echo "missing_or_changed_inherited_signatures:"
          cat /tmp/missing.sig || true
          echo "candidate_tail:"
          tail -n 80 /tmp/candidate.log || true
          echo "frozen_base_tail:"
          tail -n 80 /tmp/base.log || true

          test ! -s /tmp/new.sig
          test ! -s /tmp/missing.sig
          if [ "$base_rc" -eq 0 ]; then
            test "$candidate_rc" -eq 0
          fi
          git worktree remove --force /tmp/frozen-base

      - name: Final repository hygiene
        shell: bash
        run: |
          git diff --check "$FROZEN_BASE"...HEAD
          git status --porcelain=v1 -uall
          test -z "$(git status --porcelain=v1 -uall)"
