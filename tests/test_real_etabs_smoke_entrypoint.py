from __future__ import annotations

import importlib
from pathlib import Path

from tbdy_engine.design.beams.evaluation_package import BeamDesignModule
from tbdy_engine.runner_v2 import run_engine_v2


def test_beam_runtime_smoke_doc_exists_and_names_artifacts_and_boundaries() -> None:
    doc_path = Path("docs/BEAM_RUNTIME_SMOKE.md")
    assert doc_path.exists()
    text = doc_path.read_text(encoding="utf-8")

    required = [
        "engine_report.json",
        "engine_report.xlsx",
        "BeamEvaluationPackage",
        "CheckAdapter",
        "CheckResult",
        "ReportingFacade",
        "REAL_ETABS_VALIDATION` is not proven in CI",
        "BEAM_RUNTIME_CLOSURE` is not claimed",
        "ETABS",
        "table access / table reader",
        "beam normalizer",
        "context design_metadata",
    ]
    for item in required:
        assert item in text


def test_real_etabs_smoke_entrypoint_imports_without_live_etabs() -> None:
    assert callable(run_engine_v2)
    assert BeamDesignModule.__name__ == "BeamDesignModule"

    connection = importlib.import_module("tbdy_engine.etabs.connection")
    assert callable(connection.check_etabs_connection)
    assert callable(connection.get_sap)

    table_reader = importlib.import_module("tbdy_engine.etabs.table_reader")
    assert callable(table_reader.get_table_df)

    table_access = importlib.import_module("tbdy_engine.etabs.table_access")
    assert callable(table_access.read_etabs_table_on_demand)


def test_beam_normalizer_entrypoints_import_without_live_etabs() -> None:
    normalizer = importlib.import_module("tbdy_engine.etabs.normalizers.beam_design")

    assert callable(normalizer.normalize_beam_design_summary)
    assert callable(normalizer.normalize_beam_flexure_envelope)
    assert callable(normalizer.normalize_beam_shear_envelope)
    assert callable(normalizer.build_beam_context_from_tables)


def test_normalizer_context_shape_matches_beam_design_module_expectation() -> None:
    normalizer = importlib.import_module("tbdy_engine.etabs.normalizers.beam_design")
    context = normalizer.build_beam_context_from_tables(
        {
            "beam_design_summary": [
                {
                    "Story": "S1",
                    "Frame": "B1",
                    "DesignSect": "B30x60",
                    "Status": "OK",
                }
            ],
            "beam_design_summary_source_table": "Concrete Beam Design Summary",
            "beam_flexure_envelope": [
                {
                    "Story": "S1",
                    "Frame": "B1",
                    "M3": 120.0,
                    "Ratio": 0.84,
                    "Status": "OK",
                }
            ],
            "beam_flexure_envelope_source_table": "Concrete Beam Flexure Envelope",
            "beam_shear_envelope": [
                {
                    "Story": "S1",
                    "Frame": "B1",
                    "V2": 44.0,
                    "Ratio": 0.91,
                    "Status": "OK",
                }
            ],
            "beam_shear_envelope_source_table": "Concrete Beam Shear Envelope",
        }
    )

    assert "design_metadata" in context
    assert "beam_design_summary_rows" in context["design_metadata"]
    assert "beam_flexure_grouped" in context["design_metadata"]
    assert "beam_shear_grouped" in context["design_metadata"]

    packages = BeamDesignModule(context).run()
    assert len(packages) == 1
    assert packages[0].component == "B1"
    assert [check.check_type for check in packages[0].checks] == ["beam_geometry", "beam_flexure", "beam_shear"]
