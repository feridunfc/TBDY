from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import pytest

from tbdy_engine.features import live_etabs_concrete_material_probe as material_probe
from tbdy_engine.features.etabs_com_attach import EtabsAttachAttempt, EtabsAttachResult
from tbdy_engine.features.live_etabs_concrete_material_probe import (
    ConcreteMaterialProbeInput,
    DEFAULT_ACCEPTED_CONCRETE_MATERIAL_MAPPING,
    FixtureConcreteMaterialProbeProvider,
    create_live_etabs_concrete_material_provider,
    probe_concrete_material_feature_snapshots,
    write_concrete_material_attach_failure_outputs,
)
from tbdy_engine.features.live_etabs_geometry_probe import (
    LiveEtabsLengthUnitEvidence,
    read_live_etabs_length_unit_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
ASSIGNMENT_TABLE = "Frame Assignments - Section Properties"
SECTION_TABLE = "Frame Section Property Definitions - Concrete Rectangular"
MATERIAL_TABLE = "Material Properties - Concrete Data"
COMPONENT_TABLE = "Frame Assignments - Summary"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _codes(result) -> set[str]:
    return {
        item["code"]
        for item in _read_json(result.diagnostics_path)
    }


def _unit_evidence(
    *,
    force_unit: str = "kN",
    length_unit: str = "m",
    present_raw: tuple[object, ...] = (4, 6, 2, 0),
    database_raw: tuple[object, ...] = (4, 6, 2, 0),
) -> LiveEtabsLengthUnitEvidence:
    return LiveEtabsLengthUnitEvidence(
        present_force_unit=force_unit,
        present_length_unit=length_unit,
        present_temperature_unit="C",
        database_force_unit=force_unit,
        database_length_unit=length_unit,
        database_temperature_unit="C",
        present_units_raw=present_raw,
        database_units_raw=database_raw,
    )


def _geometry_row(
    *,
    material_name: object = "C35/45",
    component_id: str = "297",
    component_type: str = "beam",
    section_name: str = "SEC",
) -> dict[str, object]:
    assignment_row = {
        "Story": "+14.5",
        "Label": "B1",
        "UniqueName": component_id,
        "SectProp": section_name,
    }
    section_row = {
        "Name": section_name,
        "Material": material_name,
        "t2": "0.4",
        "t3": "0.7",
    }
    return {
        "component_type": component_type,
        "component_id": component_id,
        "story": "+14.5",
        "label": "B1",
        "section": section_name,
        "section_name": section_name,
        "unique_name": component_id,
        "width_mm": 400.0,
        "depth_mm": 700.0,
        "width_mm_unit": "mm",
        "depth_mm_unit": "mm",
        "width_mm_source_column": "t2",
        "depth_mm_source_column": "t3",
        "width_normalization": {
            "raw_value": "0.4",
            "raw_value_type": "str",
            "parsed_value": 0.4,
            "source_unit": "m",
            "target_unit": "mm",
            "normalization_factor_to_mm": 1000.0,
            "normalized_value": 400.0,
            "normalized_unit": "mm",
            "present_units_raw": [4, 6, 2, 0],
            "database_units_raw": [4, 6, 2, 0],
        },
        "depth_normalization": {
            "raw_value": "0.7",
            "raw_value_type": "str",
            "parsed_value": 0.7,
            "source_unit": "m",
            "target_unit": "mm",
            "normalization_factor_to_mm": 1000.0,
            "normalized_value": 700.0,
            "normalized_unit": "mm",
            "present_units_raw": [4, 6, 2, 0],
            "database_units_raw": [4, 6, 2, 0],
        },
        "source_table": SECTION_TABLE,
        "source_table_assignment": ASSIGNMENT_TABLE,
        "source_table_property": SECTION_TABLE,
        "assignment_source_row": assignment_row,
        "property_source_row": section_row,
        "assignment_section_column": "SectProp",
    }


def _fixture_provider(
    *,
    geometry_rows=None,
    section_columns=("Name", "Material", "t2", "t3"),
    material_rows=None,
    material_columns=("Material", "Fc", "SFc"),
    material_table_status="FETCHED",
    unit_evidence=None,
):
    if geometry_rows is None:
        geometry_rows = (_geometry_row(),)
    if material_rows is None:
        material_rows = ({"Material": "C35/45", "Fc": "35000", "SFc": "0"},)
    if unit_evidence is None:
        unit_evidence = _unit_evidence()
    return FixtureConcreteMaterialProbeProvider(
        ConcreteMaterialProbeInput(
            geometry_rows=geometry_rows,
            section_columns=section_columns,
            material_rows=material_rows,
            material_columns=material_columns,
            material_table_status=material_table_status,
            unit_evidence=unit_evidence,
        )
    )


def _run(tmp_path: Path, provider=None, **kwargs):
    return probe_concrete_material_feature_snapshots(
        provider=provider or _fixture_provider(),
        output_dir=tmp_path,
        **kwargs,
    )


# Negative contracts first.

def test_cli_refuses_without_live_opt_in_and_writes_nothing(tmp_path: Path):
    out = tmp_path / "refused"
    completed = subprocess.run(
        [
            sys.executable,
            "tools/probe_live_etabs_concrete_material_features.py",
            "--out",
            str(out),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "--live-etabs" in completed.stderr
    assert not out.exists()


def test_attach_failure_writes_structured_failure_without_snapshot(tmp_path: Path):
    attach_result = EtabsAttachResult(
        status="FAILED",
        strategy=None,
        etabs_object=None,
        sap_model=None,
        attempts=(
            EtabsAttachAttempt(
                strategy="comtypes_get_active_object_etabs_api_object",
                status="FAILED",
                message="No running ETABS instance",
                prog_id="CSI.ETABS.API.ETABSObject",
            ),
        ),
    )

    result = write_concrete_material_attach_failure_outputs(
        output_dir=tmp_path,
        attach_result=attach_result,
    )
    summary = _read_json(result.summary_path)
    diagnostics = _read_json(result.diagnostics_path)

    assert result.status == "FAIL"
    assert not result.feature_snapshot_path.exists()
    assert summary["status"] == "FAIL"
    assert summary["failure_stage"] == "COM_ATTACH"
    assert diagnostics[0]["status"] == "BLOCKED"
    assert diagnostics[0]["code"] == "ETABS_COM_ATTACH_FAILED"


def test_missing_material_table_is_explicit(tmp_path: Path):
    provider = _fixture_provider(
        material_rows=(),
        material_columns=(),
        material_table_status="MISSING",
    )
    result = _run(tmp_path, provider)

    assert result.status == "FAIL"
    assert result.snapshot_count == 0
    assert "MATERIAL_TABLE_MISSING_OR_EMPTY" in _codes(result)


def test_missing_material_column_in_section_table_is_blocked(tmp_path: Path):
    provider = _fixture_provider(section_columns=("Name", "t2", "t3"))
    result = _run(tmp_path, provider)

    assert result.status == "FAIL"
    assert "MATERIAL_TABLE_REQUIRED_COLUMN_MISSING" in _codes(result)


def test_missing_material_column_in_material_table_is_blocked(tmp_path: Path):
    provider = _fixture_provider(
        material_rows=({"Fc": "35000", "SFc": "0"},),
        material_columns=("Fc", "SFc"),
    )
    result = _run(tmp_path, provider)

    assert result.status == "FAIL"
    assert "MATERIAL_TABLE_REQUIRED_COLUMN_MISSING" in _codes(result)


def test_missing_fc_column_is_blocked(tmp_path: Path):
    provider = _fixture_provider(
        material_rows=({"Material": "C35/45", "SFc": "35000"},),
        material_columns=("Material", "SFc"),
    )
    result = _run(tmp_path, provider)

    assert result.status == "FAIL"
    assert "MATERIAL_TABLE_REQUIRED_COLUMN_MISSING" in _codes(result)


def test_missing_material_join_is_explicit_and_exact(tmp_path: Path):
    provider = _fixture_provider(
        geometry_rows=(_geometry_row(material_name="C35/45 "),),
        material_rows=({"Material": "C35/45", "Fc": "35000", "SFc": "0"},),
    )
    result = _run(tmp_path, provider)
    summary = _read_json(result.summary_path)

    assert result.status == "FAIL"
    assert "MATERIAL_DEFINITION_NOT_FOUND" in _codes(result)
    assert summary["material_join_missing_count"] == 1


def test_material_join_does_not_case_fold(tmp_path: Path):
    provider = _fixture_provider(
        geometry_rows=(_geometry_row(material_name="c35/45"),),
        material_rows=({"Material": "C35/45", "Fc": "35000", "SFc": "0"},),
    )
    result = _run(tmp_path, provider)

    assert result.status == "FAIL"
    assert "MATERIAL_DEFINITION_NOT_FOUND" in _codes(result)


def test_duplicate_material_definitions_are_blocked(tmp_path: Path):
    provider = _fixture_provider(
        material_rows=(
            {"Material": "C35/45", "Fc": "35000", "SFc": "0"},
            {"Material": "C35/45", "Fc": "35000", "SFc": "0"},
        )
    )
    result = _run(tmp_path, provider)
    summary = _read_json(result.summary_path)

    assert result.status == "FAIL"
    assert "MATERIAL_DEFINITION_DUPLICATE" in _codes(result)
    assert summary["material_join_duplicate_count"] == 1


def test_missing_section_material_value_is_explicit(tmp_path: Path):
    provider = _fixture_provider(geometry_rows=(_geometry_row(material_name=""),))
    result = _run(tmp_path, provider)

    assert result.status == "FAIL"
    assert "SECTION_MATERIAL_VALUE_MISSING" in _codes(result)


@pytest.mark.parametrize("raw_fc", ["30 MPa", "C30", "35k", "", True])
def test_non_plain_fc_values_are_not_numeric(tmp_path: Path, raw_fc: object):
    provider = _fixture_provider(
        material_rows=({"Material": "C35/45", "Fc": raw_fc, "SFc": "35000"},)
    )
    result = _run(tmp_path, provider)

    assert result.status == "FAIL"
    expected = (
        "CONCRETE_FC_VALUE_MISSING"
        if raw_fc == ""
        else "CONCRETE_FC_VALUE_NOT_NUMERIC"
    )
    assert expected in _codes(result)


@pytest.mark.parametrize("raw_fc", ["NaN", "Infinity", "-Infinity", float("nan")])
def test_non_finite_fc_values_are_blocked(tmp_path: Path, raw_fc: object):
    provider = _fixture_provider(
        material_rows=({"Material": "C35/45", "Fc": raw_fc, "SFc": "35000"},)
    )
    result = _run(tmp_path, provider)

    assert result.status == "FAIL"
    assert "CONCRETE_FC_VALUE_NON_FINITE" in _codes(result)


def test_material_name_strength_inference_is_impossible(tmp_path: Path):
    provider = _fixture_provider(
        material_rows=({"Material": "C35/45", "Fc": "not-a-number", "SFc": "35000"},)
    )
    result = _run(tmp_path, provider)

    assert result.status == "FAIL"
    assert "CONCRETE_FC_VALUE_NOT_NUMERIC" in _codes(result)
    assert result.snapshot_count == 0


def test_missing_runtime_unit_evidence_is_blocked(tmp_path: Path):
    probe_input = ConcreteMaterialProbeInput(
        geometry_rows=(_geometry_row(),),
        section_columns=("Name", "Material", "t2", "t3"),
        material_rows=({"Material": "C35/45", "Fc": "35000", "SFc": "0"},),
        material_columns=("Material", "Fc", "SFc"),
        unit_evidence=None,
    )
    result = _run(tmp_path, FixtureConcreteMaterialProbeProvider(probe_input))

    assert result.status == "FAIL"
    assert "MATERIAL_UNIT_EVIDENCE_MISSING" in _codes(result)


def test_unsupported_force_length_pair_is_blocked(tmp_path: Path):
    provider = _fixture_provider(
        unit_evidence=_unit_evidence(
            force_unit="N",
            length_unit="mm",
            present_raw=(3, 4, 2, 0),
            database_raw=(3, 4, 2, 0),
        )
    )
    result = _run(tmp_path, provider)
    summary = _read_json(result.summary_path)

    assert result.status == "FAIL"
    assert "MATERIAL_STRESS_UNIT_UNSUPPORTED" in _codes(result)
    assert summary["source_force_unit"] == "N"
    assert summary["source_length_unit"] == "mm"
    assert summary["source_stress_unit"] == "N/mm²"


def test_sfc_is_never_used_when_fc_is_missing(tmp_path: Path):
    provider = _fixture_provider(
        material_rows=({"Material": "C35/45", "Fc": None, "SFc": "35000"},)
    )
    result = _run(tmp_path, provider)

    assert result.status == "FAIL"
    assert "CONCRETE_FC_VALUE_MISSING" in _codes(result)
    assert result.snapshot_count == 0


# Positive contracts.

def test_exact_one_to_one_material_join_resolves(tmp_path: Path):
    result = _run(tmp_path)
    summary = _read_json(result.summary_path)

    assert result.status == "OK"
    assert result.snapshot_count == 1
    assert summary["material_join_matched_count"] == 1
    assert summary["material_join_missing_count"] == 0
    assert summary["material_join_duplicate_count"] == 0
    assert summary["fc_resolved_count"] == 1


@pytest.mark.parametrize(
    ("raw_fc", "expected"),
    [
        ("30000", 30.0),
        ("35000", 35.0),
        ("35000.0", 35.0),
        ("+35000", 35.0),
    ],
)
def test_plain_numeric_string_parsing_and_normalization(
    tmp_path: Path,
    raw_fc: str,
    expected: float,
):
    provider = _fixture_provider(
        material_rows=({"Material": "C35/45", "Fc": raw_fc, "SFc": "99999"},)
    )
    result = _run(tmp_path, provider)
    payload = _read_json(result.feature_snapshot_path)
    feature = payload["snapshots"][0]["features"]["concrete_fck_mpa"]

    assert result.status == "OK"
    assert feature["value"] == expected
    assert feature["unit"] == "MPa"
    assert feature["status"] == "RESOLVED"


def test_existing_unit_enums_resolve_4_6_2_to_kn_m_c():
    sap_model = SimpleNamespace(
        GetPresentUnits_2=lambda: (4, 6, 2, 0),
        GetDatabaseUnits_2=lambda: (4, 6, 2, 0),
    )

    evidence, diagnostics = read_live_etabs_length_unit_evidence(sap_model)

    assert diagnostics == ()
    assert evidence is not None
    assert evidence.present_force_unit == "kN"
    assert evidence.present_length_unit == "m"
    assert evidence.present_temperature_unit == "C"


def test_35000_kn_per_m2_normalizes_to_35_mpa(tmp_path: Path):
    result = _run(tmp_path)
    summary = _read_json(result.summary_path)
    payload = _read_json(result.feature_snapshot_path)
    feature = payload["snapshots"][0]["features"]["concrete_fck_mpa"]

    assert feature["value"] == 35.0
    assert summary["source_force_unit"] == "kN"
    assert summary["source_length_unit"] == "m"
    assert summary["source_stress_unit"] == "kN/m²"
    assert summary["target_strength_unit"] == "MPa"
    assert summary["normalization_factor_to_mpa"] == 0.001


def test_raw_and_normalized_provenance_is_preserved(tmp_path: Path):
    result = _run(tmp_path)
    payload = _read_json(result.feature_snapshot_path)
    snapshot = payload["snapshots"][0]
    feature = snapshot["features"]["concrete_fck_mpa"]
    evidence = feature["evidence"][0]
    details = evidence["source_row"]

    assert snapshot["identity"]["assigned_material_name"] == "C35/45"
    assert evidence["raw_value"] == "35000"
    assert evidence["normalized_value"] == 35.0
    assert details["assignment_source_table"] == ASSIGNMENT_TABLE
    assert details["assignment_source_row"]["UniqueName"] == "297"
    assert details["assignment_section_column"] == "SectProp"
    assert details["assigned_section_name"] == "SEC"
    assert details["section_definition_source_table"] == SECTION_TABLE
    assert details["section_definition_source_row"]["Material"] == "C35/45"
    assert details["section_name_column"] == "Name"
    assert details["section_material_column"] == "Material"
    assert details["raw_material_name"] == "C35/45"
    assert details["raw_material_name_type"] == "str"
    assert details["material_definition_source_table"] == MATERIAL_TABLE
    assert details["material_definition_source_row"]["Fc"] == "35000"
    assert details["material_name_column"] == "Material"
    assert details["concrete_strength_column"] == "Fc"
    assert details["raw_fc_value"] == "35000"
    assert details["raw_fc_value_type"] == "str"
    assert details["parsed_value"] == 35000.0
    assert details["present_units_raw"] == [4, 6, 2, 0]
    assert details["database_units_raw"] == [4, 6, 2, 0]
    assert details["source_force_unit"] == "kN"
    assert details["source_length_unit"] == "m"
    assert details["source_stress_unit"] == "kN/m²"
    assert details["normalization_factor_to_mpa"] == 0.001
    assert details["normalized_fc_value"] == 35.0
    assert details["normalized_fc_unit"] == "MPa"
    assert details["normalization_basis"]


class _FakeDatabaseTables:
    def __init__(self, payloads):
        self.payloads = dict(payloads)
        self.requested_tables: list[str] = []

    def GetTableForDisplayArray(self, table_key, *_args):
        self.requested_tables.append(table_key)
        return self.payloads[table_key]


class _ForbiddenDirectApi:
    def __getattr__(self, name):
        raise AssertionError(f"Direct material API must not be accessed: {name}")


def _live_payloads():
    return {
        ASSIGNMENT_TABLE: (
            0,
            ["Story", "Label", "UniqueName", "SectProp"],
            ["+14.5", "B1", "297", "SEC"],
        ),
        SECTION_TABLE: (
            0,
            ["Name", "Material", "t2", "t3"],
            ["SEC", "C35/45", "0.4", "0.7"],
        ),
        MATERIAL_TABLE: (
            0,
            ["Material", "Fc", "SFc"],
            ["C35/45", "35000", "99999"],
        ),
        COMPONENT_TABLE: (
            0,
            ["UniqueName", "Type"],
            ["297", "Beam"],
        ),
    }


def _attached_result(sap_model) -> EtabsAttachResult:
    return EtabsAttachResult(
        status="ATTACHED",
        strategy="comtypes_get_active_object_etabs_api_object",
        etabs_object=object(),
        sap_model=sap_model,
        attempts=(
            EtabsAttachAttempt(
                strategy="comtypes_get_active_object_etabs_api_object",
                status="SUCCESS",
                message="Attached fake ETABS for tests",
                prog_id="CSI.ETABS.API.ETABSObject",
            ),
        ),
    )


def test_live_provider_uses_only_locked_tables_and_never_calls_direct_material_apis(tmp_path: Path):
    database_tables = _FakeDatabaseTables(_live_payloads())
    sap_model = SimpleNamespace(
        DatabaseTables=database_tables,
        GetPresentUnits_2=lambda: (4, 6, 2, 0),
        GetDatabaseUnits_2=lambda: (4, 6, 2, 0),
        PropFrame=_ForbiddenDirectApi(),
        PropMaterial=_ForbiddenDirectApi(),
    )
    provider = create_live_etabs_concrete_material_provider(
        attach_result=_attached_result(sap_model)
    )

    result = _run(tmp_path, provider)

    assert result.status == "OK"
    assert database_tables.requested_tables == [
        ASSIGNMENT_TABLE,
        SECTION_TABLE,
        MATERIAL_TABLE,
        COMPONENT_TABLE,
    ]


def test_offline_fixture_probe_never_attaches_to_etabs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    attached = False

    def forbidden_attach():
        nonlocal attached
        attached = True
        raise AssertionError("Offline fixture probe must not attach to ETABS")

    monkeypatch.setattr(material_probe, "attach_to_running_etabs", forbidden_attach)

    result = _run(tmp_path, _fixture_provider())

    assert result.status == "OK"
    assert attached is False


def test_existing_p7_outputs_are_not_modified_by_separate_material_probe(tmp_path: Path):
    p7_summary = tmp_path / "live_geometry_product_summary.json"
    p7_manifest = tmp_path / "live_geometry_product_manifest.json"
    p7_probe_snapshot = tmp_path / "live_probe" / "feature_snapshot.json"
    p7_product_result = tmp_path / "product" / "artifacts" / "check_results.json"
    for path, content in (
        (p7_summary, "P7-SUMMARY\n"),
        (p7_manifest, "P7-MANIFEST\n"),
        (p7_probe_snapshot, "P7-SNAPSHOT\n"),
        (p7_product_result, "P7-CHECKS\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    result = _run(tmp_path, _fixture_provider())

    assert result.status == "OK"
    assert p7_summary.read_text(encoding="utf-8") == "P7-SUMMARY\n"
    assert p7_manifest.read_text(encoding="utf-8") == "P7-MANIFEST\n"
    assert p7_probe_snapshot.read_text(encoding="utf-8") == "P7-SNAPSHOT\n"
    assert p7_product_result.read_text(encoding="utf-8") == "P7-CHECKS\n"


def test_output_is_deterministic_across_repeated_runs(tmp_path: Path):
    first = _run(tmp_path, _fixture_provider())
    first_payloads = {
        path.name: path.read_text(encoding="utf-8")
        for path in (
            first.feature_snapshot_path,
            first.summary_path,
            first.diagnostics_path,
            first.manifest_path,
        )
    }

    second = _run(tmp_path, _fixture_provider())
    second_payloads = {
        path.name: path.read_text(encoding="utf-8")
        for path in (
            second.feature_snapshot_path,
            second.summary_path,
            second.diagnostics_path,
            second.manifest_path,
        )
    }

    assert first.status == "OK"
    assert second.status == "OK"
    assert first_payloads == second_payloads


def test_unrelated_output_root_file_is_preserved(tmp_path: Path):
    user_note = tmp_path / "user_note.txt"
    user_note.write_text("user-owned\n", encoding="utf-8")

    result = _run(tmp_path, _fixture_provider())
    manifest = _read_json(result.manifest_path)

    assert result.status == "OK"
    assert user_note.read_text(encoding="utf-8") == "user-owned\n"
    assert "user_note.txt" not in manifest["output_files"]
    assert manifest["output_files"] == [
        "feature_snapshot.json",
        "concrete_material_probe_summary.json",
        "concrete_material_probe_diagnostics.json",
        "concrete_material_probe_manifest.json",
    ]


def test_selectors_and_max_rows_are_applied_without_mutation(tmp_path: Path):
    rows = (
        _geometry_row(component_id="297"),
        {
            **_geometry_row(component_id="301"),
            "story": "+17.5",
            "label": "B2",
        },
    )
    provider = _fixture_provider(geometry_rows=rows)

    result = _run(
        tmp_path,
        provider,
        target_story="+17.5",
        target_label="B2",
        target_component="301",
        max_rows=1,
    )
    summary = _read_json(result.summary_path)
    manifest = _read_json(result.manifest_path)

    assert result.status == "OK"
    assert summary["candidate_row_count"] == 2
    assert summary["selected_row_count"] == 1
    assert summary["snapshot_count"] == 1
    assert manifest["selectors"] == {
        "target_story": "+17.5",
        "target_label": "B2",
        "target_component": "301",
        "max_rows": 1,
    }


def test_locked_mapping_contract_is_exact():
    assert DEFAULT_ACCEPTED_CONCRETE_MATERIAL_MAPPING.as_dict() == {
        "section_table_key": SECTION_TABLE,
        "section_name_column": "Name",
        "section_material_column": "Material",
        "material_table_key": MATERIAL_TABLE,
        "material_name_column": "Material",
        "concrete_strength_column": "Fc",
        "source_force_unit": "kN",
        "source_length_unit": "m",
        "source_stress_unit": "kN/m²",
        "target_strength_unit": "MPa",
        "normalization_factor_to_mpa": 0.001,
        "mapping_basis": "explicit_live_source_lock",
    }
