from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.features.resolver.live_smoke import (
    C8LiveFeatureResolverSmoke,
    tables_from_probe_report,
)
from tbdy_engine.features.value import FeatureValueStatus
from tbdy_engine.providers.table_registry import TableRegistry


MODAL_TABLE_NAME = "Modal Participating Mass Ratios"
MODAL_COLUMNS = ("Case", "Mode", "Period", "UX", "UY", "SumUX", "SumUY")
ROOT = Path(__file__).resolve().parents[2]
COMPLETE_MODAL_FIXTURE = ROOT / "tests" / "fixtures" / "p1_13_modal_complete_population.json"
HISTORICAL_SAMPLE_FIXTURES = {
    "c8_1_live_units_fixture.json": "82e3449f73b3ea7614eafb4550c6ab12550721f5941b6c81dfa9e3aeb55b225f",
    "c8_3_direct_api_geometry_fixture.json": "9858f2e8b4c70caed63d43cda9e7d3fe975fc9982468fe5475aa393487812ca8",
    "c8_table_headers_fixture.json": "00caa96a89991bec31435ab3fd2d4463e200ab28be25cdcd73a83b48af1dcda5",
}


def _row(
    mode: Any,
    *,
    case: Any = "Modal",
    period: Any = 0.5,
    ux: Any = 0.1,
    uy: Any = 0.2,
    sum_ux: Any = 0.1,
    sum_uy: Any = 0.2,
) -> dict[str, Any]:
    return {
        "Case": case,
        "Mode": mode,
        "Period": period,
        "UX": ux,
        "UY": uy,
        "SumUX": sum_ux,
        "SumUY": sum_uy,
    }


def _table(
    rows: Sequence[Mapping[str, Any]],
    *,
    columns: Sequence[str] = MODAL_COLUMNS,
    reported_row_count: int | None = None,
    parser_status: str = "FETCHED",
    source_row_storage_field_used: str = "rows",
) -> CanonicalTable:
    rows = tuple(dict(row) for row in rows)
    reported = len(rows) if reported_row_count is None else reported_row_count
    return CanonicalTable(
        table_key="modal_participating_mass",
        actual_table_name=MODAL_TABLE_NAME,
        columns=tuple(columns),
        rows=rows,
        units={
            "raw_table_diagnostics": {
                "number_records": reported,
                "parser_status": parser_status,
                "fields": list(columns),
                "table_data_length": len(rows) * len(columns),
            },
            "resolver_row_count": len(rows),
            "source_row_storage_field_used": source_row_storage_field_used,
            "resolver_ingestion_diagnostics": [],
        },
        source="LIVE_ETABS_DISPLAY_TABLE",
    )


def _snapshot(rows: Sequence[Mapping[str, Any]], **table_kwargs: Any):
    resolver = C8LiveFeatureResolverSmoke(
        load_contracts(),
        {"modal_participating_mass": _table(rows, **table_kwargs)},
    )
    return resolver.build_global_snapshot()




def _live_shape_probe_payload() -> dict[str, Any]:
    return {
        "unit_context": {
            "source": "fixture_declared_units",
            "force_unit": "kN",
            "length_unit": "mm",
            "temperature_unit": "C",
            "unit_query_succeeded": True,
            "unit_query_status": "RESOLVED",
            "unit_basis_confidence": "high",
        },
        "tables": [
            {
                "actual_table_name": "Frame Assignments - Summary",
                "fetch_status": "FETCHED",
                "headers": ["UniqueName", "Label", "Story", "Type", "AnalysisSect", "DesignSect", "Length"],
                "row_count_reported": 1,
                "rows": [
                    {
                        "UniqueName": "297",
                        "Label": "B1",
                        "Story": "+14.5",
                        "Type": "Beam",
                        "AnalysisSect": "B40x70",
                        "DesignSect": "B40x70",
                        "Length": 6200,
                    }
                ],
            },
            {
                "actual_table_name": "Frame Section Property Definitions - Concrete Rectangular",
                "fetch_status": "FETCHED",
                "headers": ["Name", "Material", "t2", "t3"],
                "row_count_reported": 1,
                "rows": [{"Name": "B40x70", "Material": "C30", "t2": 400, "t3": 700}],
            },
            {
                "actual_table_name": MODAL_TABLE_NAME,
                "fetch_status": "FETCHED",
                "headers": list(MODAL_COLUMNS),
                "row_count_reported": 1,
                "rows": [_row(1)],
            },
        ],
    }


def _resolver_from_live_shape_payload() -> C8LiveFeatureResolverSmoke:
    bundle = load_contracts()
    payload = _live_shape_probe_payload()
    return C8LiveFeatureResolverSmoke(
        bundle,
        tables_from_probe_report(payload, bundle),
        unit_context=payload["unit_context"],
        target_component="297",
        target_label="B1",
        target_story="+14.5",
        target_section="B40x70",
    )


def _status(snapshot, name: str) -> FeatureValueStatus:
    return snapshot.features[name].status


def _codes(snapshot, name: str) -> set[str]:
    return {diagnostic.code.value for diagnostic in snapshot.features[name].diagnostics}


# R0 registry compatibility.

def test_etabs_aliases_include_live_legacy_and_logical_names_without_duplicates():
    registry = TableRegistry.from_dict(
        {
            "tables": {
                "example": {
                    "live_table_name": "Live Table",
                    "provider_sources": {"etabs": ["Legacy Table", " live   table "]},
                    "logical_name": "Logical Table",
                    "excel_inventory_aliases": ["Excel Sheet"],
                }
            }
        }
    )

    assert registry.aliases_for_key("example", provider="etabs") == (
        "Live Table",
        "Legacy Table",
        "Logical Table",
    )
    assert registry.preferred_actual_name("example", provider="etabs") == "Live Table"


def test_legacy_provider_sources_and_logical_name_remain_supported():
    registry = TableRegistry.from_dict(
        {
            "tables": {
                "legacy": {
                    "provider_sources": {"etabs": ["Legacy Actual"]},
                    "logical_name": "Legacy Logical",
                }
            }
        }
    )
    assert registry.canonical_key_for_alias("Legacy Actual") == "legacy"
    assert registry.canonical_key_for_alias("Legacy Logical") == "legacy"


def test_excel_inventory_aliases_do_not_leak_into_etabs_namespace():
    registry = TableRegistry.from_dict(
        {"tables": {"example": {"live_table_name": "Live Table", "excel_inventory_aliases": ["Excel Only"]}}}
    )
    assert registry.canonical_key_for_alias("Excel Only", provider="etabs") is None
    assert registry.canonical_key_for_alias("Excel Only", provider="excel") == "example"


@pytest.mark.parametrize(
    ("actual_name", "canonical_key"),
    [
        ("Frame Assignments - Summary", "frame_assignments_summary"),
        ("Frame Section Property Definitions - Concrete Rectangular", "concrete_rectangular_frame_sections"),
        (MODAL_TABLE_NAME, "modal_participating_mass"),
    ],
)
def test_verified_live_names_resolve_to_primary_canonical_keys(actual_name: str, canonical_key: str):
    registry = TableRegistry.from_catalog_dir()
    assert registry.canonical_key_for_alias(actual_name) == canonical_key




def test_shared_live_alias_resolves_to_primary_even_when_legacy_is_declared_first():
    registry = TableRegistry.from_dict(
        {
            "tables": {
                "legacy_key": {
                    "live_table_name": "Shared Live Table",
                    "compatibility_alias_for": "primary_key",
                    "legacy_compatibility_alias": True,
                },
                "primary_key": {"live_table_name": "Shared Live Table"},
            }
        }
    )
    assert registry.canonical_key_for_alias("Shared Live Table") == "primary_key"
    assert registry.canonical_key_for_alias("legacy_key") == "legacy_key"
    assert registry.compatibility_keys_for_key("legacy_key") == ("primary_key", "legacy_key")


def test_unknown_alias_remains_unresolved_and_canonical_key_still_resolves():
    registry = TableRegistry.from_catalog_dir()
    assert registry.canonical_key_for_alias("Unknown Production Table") is None
    assert registry.canonical_key_for_alias("modal_participating_mass") == "modal_participating_mass"


def test_probe_report_maps_all_three_verified_live_names_without_explicit_canonical_keys():
    payload = [
        {
            "actual_table_name": "Frame Assignments - Summary",
            "fetch_status": "FETCHED",
            "headers": ["UniqueName", "Type", "AnalysisSect", "DesignSect"],
            "row_count_reported": 1,
            "rows": [{"UniqueName": "1", "Type": "Beam", "AnalysisSect": "B40x70", "DesignSect": "B40x70"}],
        },
        {
            "actual_table_name": "Frame Section Property Definitions - Concrete Rectangular",
            "fetch_status": "FETCHED",
            "headers": ["Name", "Material", "t2", "t3"],
            "row_count_reported": 1,
            "rows": [{"Name": "B40x70", "Material": "C30", "t2": 0.4, "t3": 0.7}],
        },
        {
            "actual_table_name": MODAL_TABLE_NAME,
            "fetch_status": "FETCHED",
            "headers": list(MODAL_COLUMNS),
            "row_count_reported": 1,
            "rows": [_row(1)],
        },
    ]
    tables = tables_from_probe_report(payload, load_contracts())
    assert [table.table_key for table in tables] == [
        "frame_assignments_summary",
        "concrete_rectangular_frame_sections",
        "modal_participating_mass",
    ]


def test_catalog_compatibility_families_are_primary_first_and_bidirectional():
    registry = TableRegistry.from_catalog_dir()
    assert registry.compatibility_keys_for_key("frame_assignments_summary") == (
        "frame_assignments_summary",
        "frame_assignments",
    )
    assert registry.compatibility_keys_for_key("frame_assignments") == (
        "frame_assignments_summary",
        "frame_assignments",
    )
    assert registry.compatibility_keys_for_key("concrete_rectangular_frame_sections") == (
        "concrete_rectangular_frame_sections",
        "frame_section_properties",
    )
    assert registry.compatibility_keys_for_key("modal_results") == (
        "modal_participating_mass",
        "modal_results",
    )


def test_primary_probe_tables_register_exact_same_objects_under_legacy_keys():
    resolver = _resolver_from_live_shape_payload()
    assert resolver._table("frame_assignments_summary") is resolver._table("frame_assignments")
    assert resolver._table("concrete_rectangular_frame_sections") is resolver._table("frame_section_properties")
    assert resolver._table("modal_participating_mass") is resolver._table("modal_results")


def test_legacy_input_tables_register_exact_same_objects_under_primary_keys():
    bundle = load_contracts()
    legacy_tables = [
        CanonicalTable(
            table_key="frame_assignments",
            actual_table_name="Frame Assignments - Summary",
            columns=("UniqueName",),
            rows=({"UniqueName": "297"},),
            units={},
            source="TEST",
        ),
        CanonicalTable(
            table_key="frame_section_properties",
            actual_table_name="Frame Section Property Definitions - Concrete Rectangular",
            columns=("Name",),
            rows=({"Name": "B40x70"},),
            units={},
            source="TEST",
        ),
        CanonicalTable(
            table_key="modal_results",
            actual_table_name=MODAL_TABLE_NAME,
            columns=MODAL_COLUMNS,
            rows=(_row(1),),
            units={},
            source="TEST",
        ),
    ]
    resolver = C8LiveFeatureResolverSmoke(bundle, legacy_tables)
    assert resolver._table("frame_assignments") is resolver._table("frame_assignments_summary")
    assert resolver._table("frame_section_properties") is resolver._table("concrete_rectangular_frame_sections")
    assert resolver._table("modal_results") is resolver._table("modal_participating_mass")


def test_actual_live_shape_tables_resolve_beam_without_direct_api_geometry_fallback():
    resolver = _resolver_from_live_shape_payload()
    beam = resolver.build_beam_snapshot()

    assert beam.identity == {
        "component": "297",
        "label": "B1",
        "story": "+14.5",
        "section": "B40x70",
    }
    assert beam.features["beam_width_mm"].value == pytest.approx(400.0)
    assert beam.features["beam_depth_mm"].value == pytest.approx(700.0)
    assert beam.features["beam_length_mm"].value == pytest.approx(6200.0)
    assert beam.features["beam_width_mm"].evidence[0].source_table == "frame_section_properties"
    assert beam.features["beam_length_mm"].evidence[0].source_table == "frame_assignments"
    assert resolver._geometry_direct_api_report["used"] is False


def test_product_source_tables_preserve_actual_names_and_are_not_table_missing():
    outputs = _resolver_from_live_shape_payload().build_all()
    tables = outputs.product_report_source_tables["tables"]

    assignment = tables["frame_assignments"]
    section = tables["frame_section_properties"]
    assert assignment["actual_table_name"] == "Frame Assignments - Summary"
    assert section["actual_table_name"] == "Frame Section Property Definitions - Concrete Rectangular"
    assert assignment["row_count"] > 0
    assert section["row_count"] > 0
    assert assignment["raw_table_diagnostics"]["parser_status"] != "TABLE_MISSING"
    assert section["raw_table_diagnostics"]["parser_status"] != "TABLE_MISSING"


def test_dedicated_complete_fixture_resolves_modal_population():
    payload = json.loads(COMPLETE_MODAL_FIXTURE.read_text(encoding="utf-8"))
    assert payload["metadata"]["population_scope"] == "complete_fixture_population"
    assert payload["metadata"]["live_100_row_evidence_claim"] is False
    bundle = load_contracts()
    snapshot = C8LiveFeatureResolverSmoke(bundle, tables_from_probe_report(payload, bundle)).build_global_snapshot()
    assert snapshot.features["modal_sum_ux"].status == FeatureValueStatus.RESOLVED
    assert snapshot.features["modal_sum_uy"].status == FeatureValueStatus.RESOLVED
    assert snapshot.features["modal_sum_ux"].value == pytest.approx(0.9999)
    assert snapshot.features["modal_sum_uy"].value == pytest.approx(0.9999)
    assert snapshot.features["modal_sum_ux"].evidence[0].source_row["governing_mode"] == 99
    assert snapshot.features["modal_sum_uy"].evidence[0].source_row["governing_mode"] == 100


@pytest.mark.parametrize(("fixture_name", "expected_sha256"), HISTORICAL_SAMPLE_FIXTURES.items())
def test_historical_sample_fixtures_are_byte_stable_and_fail_closed(fixture_name: str, expected_sha256: str):
    path = ROOT / "tests" / "fixtures" / fixture_name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256
    payload = json.loads(path.read_text(encoding="utf-8"))
    modal_source = next(
        table for table in payload["tables"]
        if table.get("actual_table_name") == MODAL_TABLE_NAME
    )
    assert "sample_rows_limited" in modal_source
    assert "rows" not in modal_source

    bundle = load_contracts()
    snapshot = C8LiveFeatureResolverSmoke(bundle, tables_from_probe_report(payload, bundle)).build_global_snapshot()
    for feature_name in ("modal_sum_ux", "modal_sum_uy"):
        assert snapshot.features[feature_name].status != FeatureValueStatus.RESOLVED
        assert "MODAL_SOURCE_INCOMPLETE" in _codes(snapshot, feature_name)


# R1 modal ingestion.

def test_complete_one_case_table_resolves_both_features_and_global_identity():
    snapshot = _snapshot([_row(1, sum_ux=0.55, sum_uy=0.45), _row(2, sum_ux=0.91, sum_uy=0.92)])
    assert snapshot.component_type == "global"
    assert snapshot.component_id == "GLOBAL"
    assert snapshot.features["modal_sum_ux"].status == FeatureValueStatus.RESOLVED
    assert snapshot.features["modal_sum_uy"].status == FeatureValueStatus.RESOLVED
    assert snapshot.features["modal_sum_ux"].value == pytest.approx(0.91)
    assert snapshot.features["modal_sum_uy"].value == pytest.approx(0.92)


def test_max_cumulative_not_last_row_and_governing_rows_may_differ():
    snapshot = _snapshot(
        [
            _row(10, period=0.1, sum_ux=0.70, sum_uy=0.75),
            _row(65, period=0.02, sum_ux=0.9999, sum_uy=0.95),
            _row(100, period=0.007, sum_ux=0.9998, sum_uy=0.9999),
        ]
    )
    ux = snapshot.features["modal_sum_ux"]
    uy = snapshot.features["modal_sum_uy"]
    assert ux.value == pytest.approx(0.9999)
    assert uy.value == pytest.approx(0.9999)
    assert ux.evidence[0].source_row["governing_mode"] == 65
    assert uy.evidence[0].source_row["governing_mode"] == 100


def test_unsorted_rows_and_intermediate_low_rows_do_not_change_maximum():
    snapshot = _snapshot(
        [
            _row(100, sum_ux=0.9998, sum_uy=0.9999),
            _row(1, sum_ux=0.54, sum_uy=0.12),
            _row(99, sum_ux=0.9999, sum_uy=0.9989),
            _row(50, sum_ux=0.80, sum_uy=0.70),
        ]
    )
    assert snapshot.features["modal_sum_ux"].evidence[0].source_row["governing_mode"] == 99
    assert snapshot.features["modal_sum_uy"].evidence[0].source_row["governing_mode"] == 100


def test_full_row_cardinality_mismatch_fails_closed():
    snapshot = _snapshot([_row(1), _row(2)], reported_row_count=100)
    for name in ("modal_sum_ux", "modal_sum_uy"):
        assert _status(snapshot, name) != FeatureValueStatus.RESOLVED
        assert "MODAL_ROW_COUNT_MISMATCH" in _codes(snapshot, name)


def test_sample_only_rows_fail_closed_even_when_sample_count_matches_reported_count():
    snapshot = _snapshot([_row(1)], source_row_storage_field_used="sample_rows_limited", parser_status="FIXTURE_SAMPLE_ROWS")
    assert _status(snapshot, "modal_sum_ux") != FeatureValueStatus.RESOLVED
    assert "MODAL_SOURCE_INCOMPLETE" in _codes(snapshot, "modal_sum_ux")


def test_missing_table_is_never_resolved():
    snapshot = C8LiveFeatureResolverSmoke(load_contracts(), {}).build_global_snapshot()
    assert snapshot.features["modal_sum_ux"].status == FeatureValueStatus.MISSING
    assert snapshot.features["modal_sum_uy"].status == FeatureValueStatus.MISSING


def test_empty_table_fails_closed():
    snapshot = _snapshot([])
    assert _status(snapshot, "modal_sum_ux") != FeatureValueStatus.RESOLVED
    assert _status(snapshot, "modal_sum_uy") != FeatureValueStatus.RESOLVED


@pytest.mark.parametrize("missing_column", ["SumUX", "SumUY"])
def test_missing_cumulative_column_fails_closed(missing_column: str):
    columns = tuple(column for column in MODAL_COLUMNS if column != missing_column)
    row = _row(1)
    row.pop(missing_column)
    snapshot = _snapshot([row], columns=columns)
    assert _status(snapshot, "modal_sum_ux") != FeatureValueStatus.RESOLVED
    assert _status(snapshot, "modal_sum_uy") != FeatureValueStatus.RESOLVED


def test_numeric_strings_parse_without_percent_conversion():
    snapshot = _snapshot([_row("1", period="0.56", ux="0.5", uy="0.4", sum_ux="0.95", sum_uy="0.96")])
    assert snapshot.features["modal_sum_ux"].value == pytest.approx(0.95)
    assert snapshot.features["modal_sum_uy"].value == pytest.approx(0.96)

    percent_like = _snapshot([_row("1", period="0.56", ux="0.5", uy="0.4", sum_ux="95", sum_uy="96")])
    assert percent_like.features["modal_sum_ux"].value == pytest.approx(95.0)
    assert percent_like.features["modal_sum_uy"].value == pytest.approx(96.0)


@pytest.mark.parametrize("bad_value", ["not-a-number", float("nan"), float("inf"), float("-inf")])
def test_non_numeric_or_non_finite_required_values_fail_closed(bad_value: Any):
    snapshot = _snapshot([_row(1, sum_ux=bad_value)])
    assert _status(snapshot, "modal_sum_ux") != FeatureValueStatus.RESOLVED
    assert "MODAL_CUMULATIVE_VALUE_INVALID" in _codes(snapshot, "modal_sum_ux")


def test_ux_and_uy_are_never_substituted_for_missing_cumulative_columns():
    row = _row(1, ux=0.9999, uy=0.9999)
    row.pop("SumUX")
    row.pop("SumUY")
    columns = tuple(column for column in MODAL_COLUMNS if column not in {"SumUX", "SumUY"})
    snapshot = _snapshot([row], columns=columns)
    assert _status(snapshot, "modal_sum_ux") != FeatureValueStatus.RESOLVED
    assert _status(snapshot, "modal_sum_uy") != FeatureValueStatus.RESOLVED


def test_multiple_modal_cases_do_not_silently_merge():
    snapshot = _snapshot([_row(1, case="Modal-A"), _row(2, case="Modal-B")])
    for name in ("modal_sum_ux", "modal_sum_uy"):
        assert _status(snapshot, name) != FeatureValueStatus.RESOLVED
        assert "MODAL_MULTIPLE_CASES_UNSUPPORTED" in _codes(snapshot, name)


def test_evidence_preserves_governing_case_mode_period_column_row_and_population():
    source_rows = [
        _row(1, period="0.56", sum_ux="0.5441", sum_uy="0.122"),
        _row(99, period="0.0071", sum_ux="0.9999", sum_uy="0.9989"),
        _row(100, period="0.007", sum_ux="0.9999", sum_uy="0.9999"),
    ]
    snapshot = _snapshot(source_rows)
    ux_evidence = snapshot.features["modal_sum_ux"].evidence[0]
    uy_evidence = snapshot.features["modal_sum_uy"].evidence[0]

    assert ux_evidence.source_table == "modal_participating_mass"
    assert ux_evidence.actual_table_name == MODAL_TABLE_NAME
    assert ux_evidence.source_column == "SumUX"
    assert ux_evidence.raw_value == "0.9999"
    assert ux_evidence.normalized_value == pytest.approx(0.9999)
    assert ux_evidence.unit == "ratio"
    assert ux_evidence.output_case == "Modal"
    assert ux_evidence.source_row["aggregation"] == "max_cumulative"
    assert ux_evidence.source_row["governing_mode"] == 99
    assert ux_evidence.source_row["governing_period"] == pytest.approx(0.0071)
    assert ux_evidence.source_row["governing_row_index"] == 1
    assert dict(ux_evidence.source_row["governing_source_row_items"]) == source_rows[1]
    assert "row_index=1" in ux_evidence.source_row["governing_row_reference"]
    assert ux_evidence.source_row["full_row_population_count"] == 3
    assert ux_evidence.source_row["reported_row_count"] == 3
    assert uy_evidence.source_row["governing_mode"] == 100
    assert uy_evidence.source_row["governing_row_index"] == 2


def test_parser_failure_never_emits_resolved_feature():
    snapshot = _snapshot([_row(1)], parser_status="ROW_PARSE_PARTIAL")
    assert _status(snapshot, "modal_sum_ux") != FeatureValueStatus.RESOLVED
    assert "MODAL_SOURCE_INCOMPLETE" in _codes(snapshot, "modal_sum_ux")
