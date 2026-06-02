"""
BeamModelContext kontrat testleri.
"""

import pytest
from tbdy_engine.design.beams.context import (
    BeamGeometryInput,
    BeamMaterialInput,
    BeamMetadata,
    BeamModelContext,
    validate_beam_model_context,
    is_valid_beam_model_context,
)


# =============================================================================
# Helpers
# =============================================================================

def _valid_geometry():
    return BeamGeometryInput(
        bw_mm=300.0,
        h_mm=500.0,
        d_mm=450.0,
        cover_mm=40.0,
        Ln_mm=5000.0,
    )


def _valid_material():
    return BeamMaterialInput(
        fck_mpa=30.0,
        fcd_mpa=20.0,
        fctd_mpa=1.27,
        fyk_mpa=420.0,
        fyd_mpa=365.0,
        fywd_mpa=365.0,
    )


def _valid_metadata():
    return BeamMetadata(
        label="B101",
        story="S1",
        section_name="B30x50",
        source="etabs_provider",
    )


def _valid_context():
    return BeamModelContext(
        beam_id="B101_S1",
        geometry=_valid_geometry(),
        material=_valid_material(),
        metadata=_valid_metadata(),
    )


# =============================================================================
# Test 1: Valid context passes
# =============================================================================

def test_valid_context_passes():
    ctx = _valid_context()
    assert is_valid_beam_model_context(ctx)
    assert validate_beam_model_context(ctx) == ()


# =============================================================================
# Test 2: Missing beam_id fails
# =============================================================================

def test_missing_beam_id_fails():
    ctx = BeamModelContext(
        beam_id="",
        geometry=_valid_geometry(),
        material=_valid_material(),
        metadata=_valid_metadata(),
    )
    assert not is_valid_beam_model_context(ctx)
    errors = validate_beam_model_context(ctx)
    assert "beam_id" in errors


# =============================================================================
# Test 3: Missing label fails
# =============================================================================

def test_missing_label_fails():
    meta = _valid_metadata()
    meta = BeamMetadata(
        label="",
        story=meta.story,
        section_name=meta.section_name,
        source=meta.source,
    )
    ctx = BeamModelContext(
        beam_id="B101_S1",
        geometry=_valid_geometry(),
        material=_valid_material(),
        metadata=meta,
    )
    assert not is_valid_beam_model_context(ctx)
    errors = validate_beam_model_context(ctx)
    assert "metadata.label" in errors


# =============================================================================
# Test 4: Invalid geometry dimension fails
# =============================================================================

@pytest.mark.parametrize("field,value", [
    ("bw_mm", 0.0),
    ("bw_mm", -100.0),
    ("h_mm", 0.0),
    ("d_mm", 0.0),
    ("cover_mm", -1.0),
    ("Ln_mm", 0.0),
])
def test_invalid_geometry_fails(field, value):
    geom_dict = {
        "bw_mm": 300.0,
        "h_mm": 500.0,
        "d_mm": 450.0,
        "cover_mm": 40.0,
        "Ln_mm": 5000.0,
    }
    geom_dict[field] = value
    geom = BeamGeometryInput(**geom_dict)

    ctx = BeamModelContext(
        beam_id="B101_S1",
        geometry=geom,
        material=_valid_material(),
        metadata=_valid_metadata(),
    )
    assert not is_valid_beam_model_context(ctx)
    errors = validate_beam_model_context(ctx)
    assert any(f"geometry.{field}" in e for e in errors)


# =============================================================================
# Test 5: Invalid material fails
# =============================================================================

@pytest.mark.parametrize("field,value", [
    ("fck_mpa", 0.0),
    ("fcd_mpa", 0.0),
    ("fctd_mpa", 0.0),
    ("fyk_mpa", -1.0),
    ("fyd_mpa", 0.0),
    ("fywd_mpa", 0.0),
])
def test_invalid_material_fails(field, value):
    mat_dict = {
        "fck_mpa": 30.0,
        "fcd_mpa": 20.0,
        "fctd_mpa": 1.27,
        "fyk_mpa": 420.0,
        "fyd_mpa": 365.0,
        "fywd_mpa": 365.0,
    }
    mat_dict[field] = value
    mat = BeamMaterialInput(**mat_dict)

    ctx = BeamModelContext(
        beam_id="B101_S1",
        geometry=_valid_geometry(),
        material=mat,
        metadata=_valid_metadata(),
    )
    assert not is_valid_beam_model_context(ctx)
    errors = validate_beam_model_context(ctx)
    assert any(f"material.{field}" in e for e in errors)


# =============================================================================
# Test 6: No reinforcement fields on BeamModelContext
# =============================================================================

def test_no_reinforcement_fields_on_context():
    """BeamModelContext reinforcement alanları içermez."""
    ctx = _valid_context()
    ctx_dict = ctx.__dict__

    forbidden = [
        "top_As", "bottom_As", "stirrup",
        "provided_area", "selected_area",
        "As_required", "reinforcement",
    ]
    for field in forbidden:
        assert field not in ctx_dict, (
            f"BeamModelContext should not have '{field}' field"
        )


# =============================================================================
# Test 7: label is accessible via property
# =============================================================================

def test_label_property():
    ctx = _valid_context()
    assert ctx.label == "B101"
    assert ctx.story == "S1"
    assert ctx.section_name == "B30x50"


# =============================================================================
# Test 8: Immutability
# =============================================================================

def test_context_is_immutable():
    ctx = _valid_context()
    with pytest.raises(Exception):
        ctx.beam_id = "changed"  # frozen dataclass


# =============================================================================
# Test 9: Serialization round-trip
# =============================================================================

def test_serialization_roundtrip():
    import json
    from dataclasses import asdict

    ctx = _valid_context()
    d = asdict(ctx)
    js = json.dumps(d)
    loaded = json.loads(js)

    assert loaded["beam_id"] == "B101_S1"
    assert loaded["geometry"]["bw_mm"] == 300.0
    assert loaded["material"]["fck_mpa"] == 30.0
    assert loaded["metadata"]["label"] == "B101"


# =============================================================================
# Test 10: Boundary scan — no forbidden terms
# =============================================================================

def test_context_no_forbidden_terms():
    """context.py forbidden terimler içermez."""
    import inspect
    import tbdy_engine.design.beams.context as ctx_module

    source = inspect.getsource(ctx_module)
    forbidden = [
        "comtypes", "SapModel", "FrameForce",
        "provided_area", "selected_area",
        "As_required", "Mpr", "Ve_capacity",
        "ReportingFacade", "CheckAdapter", "streamlit",
    ]
    for term in forbidden:
        assert term not in source, (
            f"Forbidden term '{term}' found in context.py"
        )
