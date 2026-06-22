from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from tbdy_engine.product.live_beam_column_minimum_compliance import (
    _summary,
    run_live_beam_column_minimum_compliance,
)


def test_public_summary_import_contract() -> None:
    assert callable(_summary)


def test_zero_executable_checks_report_no_data() -> None:
    tables = {"executive_summary": []}
    result = _summary(
        tables,
        [],
        [],
        [
            {
                "status": "BLOCKED",
                "result_status": "BLOCKED",
                "component_type": "beam",
                "check_id": "blocked",
            }
        ],
    )

    assert result["engineering_status"] == "NO_DATA"
    assert result["engineering_fail"] is False
    assert result["coverage_status"] == "PARTIAL"


def test_unknown_raw_component_type_is_preserved_as_blocked_diagnostic(
    tmp_path: Path,
) -> None:
    source = {
        "component_rows": [{"UniqueName": "U1", "Type": "Cable"}],
        "assignment_rows": [],
        "section_rows": [],
        "material_rows": [],
        "connectivity_rows": [],
        "offset_rows": [],
        "snapshots": [],
        "source_diagnostics": [],
        "unit_evidence": None,
    }

    result = run_live_beam_column_minimum_compliance(
        output_dir=tmp_path,
        attach_runner=lambda: SimpleNamespace(status="ATTACHED", sap_model=object()),
        source_loader=lambda _attach, _work: source,
    )

    diagnostics = json.loads(
        (tmp_path / "artifacts" / "adapter_diagnostics.json").read_text(
            encoding="utf-8"
        )
    )
    unknown = next(
        item for item in diagnostics if item.get("code") == "COMPONENT_TYPE_UNKNOWN"
    )

    assert unknown["status"] == "BLOCKED"
    assert unknown["component_id"] == "U1"
    assert unknown["raw_component_type"] == "Cable"
    assert result["engineering_status"] == "NO_DATA"
    assert result["engineering_fail"] is False
