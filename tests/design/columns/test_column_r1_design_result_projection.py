from __future__ import annotations

from decimal import Decimal

import pytest

from tbdy_engine.design.columns.column_design_result_projection import (
    ColumnDesignResultProjectionError,
    project_factual_design_results_to_component,
)
from tbdy_engine.features.column_design_rebar_evidence import (
    FactualColumnDesignResultPopulation,
    FactualColumnDesignResultRow,
)


def _row(component: str, uid: str, row_id: str) -> FactualColumnDesignResultRow:
    return FactualColumnDesignResultRow(
        source_row_id=row_id,
        component_id=component,
        unique_name=uid,
        story="Story1",
        label=component.split(":")[1],
        assigned_section="C50x50",
        design_section="C50x50",
        my_option=2,
        pmm_combo="ULS",
        location_mm=Decimal("0"),
        pmm_area_mm2=Decimal("2400"),
        error_summary="",
        warning_summary="",
        model_fingerprint="model:1",
        evidence_epoch_id="epoch:1",
        source_refs=(f"row:{row_id}",),
    )


def _population() -> FactualColumnDesignResultPopulation:
    return FactualColumnDesignResultPopulation(
        model_fingerprint="model:1",
        evidence_epoch_id="epoch:1",
        expected_component_ids=("Story1:C1:1", "Story1:C2:2"),
        attempted_component_ids=("Story1:C1:1", "Story1:C2:2"),
        captured_component_ids=("Story1:C1:1", "Story1:C2:2"),
        reported_result_row_count=3,
        rows=(
            _row("Story1:C1:1", "1", "r1"),
            _row("Story1:C1:1", "1", "r2"),
            _row("Story1:C2:2", "2", "r3"),
        ),
        source_refs=("b6:population",),
    )


def test_projection_keeps_all_and_only_target_rows_with_exact_identity_refs() -> None:
    result = project_factual_design_results_to_component(
        _population(),
        component_id="Story1:C1:1",
        design_result_identity_ref="design-result:sha256:" + "1" * 64,
        design_lineage_qualification_ref="design-lineage-qualification:sha256:" + "2" * 64,
    )
    assert result.capture_complete
    assert result.expected_component_ids == ("Story1:C1:1",)
    assert tuple(row.source_row_id for row in result.rows) == ("r1", "r2")
    assert "design-result:sha256:" + "1" * 64 in result.source_refs
    assert any(ref.startswith("column-design-result-projection:sha256:") for ref in result.source_refs)


def test_projection_fails_closed_for_component_outside_b6_scope() -> None:
    with pytest.raises(ColumnDesignResultProjectionError, match="not in the qualified B6 result scope"):
        project_factual_design_results_to_component(
            _population(),
            component_id="Story1:C9:9",
            design_result_identity_ref="design-result:test",
            design_lineage_qualification_ref="design-lineage:test",
        )
