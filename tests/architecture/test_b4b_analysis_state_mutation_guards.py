from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OAPI = ROOT / "tbdy_engine" / "etabs" / "oapi" / "frame_modifiers.py"
MODEL_LOCK_OAPI = ROOT / "tbdy_engine" / "etabs" / "oapi" / "model_lock.py"
INTEGRATION = ROOT / "tbdy_engine" / "integration" / "etabs_analysis_state_mutation.py"

FORBIDDEN = {
    "RunAnalysis",
    "SetRunCaseFlag",
    "DeleteResults",
    "StartDesign",
    "SetModelIsLocked",
    "SetPresentUnits",
    "SetPresentUnits_2",
    "GetActiveObject",
    "CreateObject",
    "win32com",
    "comtypes",
}


def _text(path: Path) -> str:
    # The repository contains inherited UTF-8 BOM Python sources.  Architecture
    # census must parse them without treating unrelated BOM debt as B4B drift.
    return path.read_text(encoding="utf-8-sig")


def test_b4b_production_files_forbid_execution_and_second_com_path():
    for path in (OAPI, INTEGRATION):
        source = _text(path)
        for token in FORBIDDEN:
            assert token not in source, f"{token} must not appear in {path}"


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def test_model_lock_raw_call_is_confined_to_factual_oapi():
    production = ROOT / "tbdy_engine"
    call_sites = []
    for path in production.rglob("*.py"):
        tree = ast.parse(_text(path), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            dotted = _dotted(node.func)
            if dotted.rsplit(".", 1)[-1] == "SetModelIsLocked":
                call_sites.append(
                    (path.relative_to(ROOT).as_posix(), dotted)
                )

    assert call_sites == [
        (
            "tbdy_engine/etabs/oapi/model_lock.py",
            "model_api.SetModelIsLocked",
        )
    ]
    assert "SetModelIsLocked" not in _text(INTEGRATION)
    assert "etabs_gateway.mutation_transport" in _text(MODEL_LOCK_OAPI)


def test_b4b_integration_consumes_owned_scratch_and_b4a_identity_chain():
    source = _text(INTEGRATION)
    assert "OwnedScratchContext" in source
    assert "RequestedDerivedStateManifest" in source
    assert "_establish_derived_state_from_verified_readback" in source
    assert "compare_derived_state_manifests" in source
    assert "build_analysis_state_identity_from_derived_state" in source


def test_raw_frame_modifier_setters_exist_only_in_typed_oapi_module():
    production = ROOT / "tbdy_engine"
    call_sites = []
    for path in production.rglob("*.py"):
        tree = ast.parse(_text(path), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "SetModifiers":
                    call_sites.append(path.relative_to(ROOT).as_posix())
    assert set(call_sites) <= {
        "tbdy_engine/etabs/oapi/frame_modifiers.py",
        "tbdy_engine/etabs/oapi/area_modifiers.py",
    }


def test_b4b_private_positive_establishment_token_is_not_publicly_reexported():
    init_files = [
        ROOT / "tbdy_engine" / "integration" / "__init__.py",
        ROOT / "tbdy_engine" / "etabs" / "oapi" / "__init__.py",
    ]
    for path in init_files:
        source = _text(path)
        assert "_POSITIVE_ESTABLISHMENT_ISSUER_TOKEN" not in source


def test_b4b_surface_names_preserve_object_property_distinction():
    source = _text(OAPI)
    assert 'FRAME_OBJECT = "FRAME_OBJECT"' in source
    assert 'FRAME_SECTION_PROPERTY = "FRAME_SECTION_PROPERTY"' in source
    assert "effective/composed stiffness modifier" in source
    assert "PropFrame" in source
    assert "FrameObj" in source
