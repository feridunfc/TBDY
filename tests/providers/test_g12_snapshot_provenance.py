"""Offline fixtures qualify the existing seam, not live B-BLOK quantities."""
from collections import Counter
from copy import deepcopy

import pytest

import tbdy_engine.providers.etabs_area_contributor_provider as area_owner
import tbdy_engine.providers.etabs_frame_flexural_base_provider as owner
from test_etabs_area_contributor_a38_material_authority import _row
from test_etabs_frame_flexural_base_snapshot import _install_environment, _rows_fixture


def _capture(context, scratch):
    return owner.capture_frame_flexural_base_snapshot(context=context, owned_scratch=scratch)


def _material(snapshot, name="C35"):
    return area_owner._capture_area_material_facts(
        rows=(_row("A", material=name),), material_snapshot=snapshot,
        model_fingerprint="model:a38", evidence_epoch_id="epoch:a38",
        session_provenance_ref=snapshot.session_provenance_ref,
    )[0]


def _replace_bindings(snapshot, bindings):
    fields = {name: getattr(snapshot, name) for name in (
        "source_model_ref", "ownership_proof_ref", "acquisition_context_ref",
        "session_provenance_ref", "scratch_path", "present_force_unit",
        "present_length_unit", "assignment_rows", "rectangular_rows",
        "section_summary_rows", "basic_material_rows", "concrete_rows",
        "table_metadata_refs", "table_metadata_raw",
    )}
    return owner.FrameFlexuralBaseCaptureSnapshot(
        _issuance_token=owner._FRAME_FLEXURAL_BASE_SNAPSHOT_ISSUANCE_TOKEN,
        **fields, table_unit_provenance={
            **snapshot.table_unit_provenance, owner.TABLE_BASIC_MATERIAL: bindings,
        },
    )


def test_e1_only_snapshot_reproduces_exact_missing_g12_binding(monkeypatch):
    context, scratch, _ = _install_environment(monkeypatch)
    snapshot = _capture(context, scratch)
    bindings = snapshot.table_unit_provenance[owner.TABLE_BASIC_MATERIAL]
    e1_only = _replace_bindings(snapshot, tuple(b for b in bindings if b.output_key == "E1"))
    assert "G12" in snapshot.table_metadata_raw[owner.TABLE_BASIC_MATERIAL][2]
    assert snapshot.basic_material_rows[0]["G12"] == 13_750_000
    with pytest.raises(owner.FrameFlexuralBaseFactError,
                       match="^UNIT_UNQUALIFIED:MISSING_OR_DUPLICATE_FIELD_METADATA$"):
        owner._table_quantity(e1_only, owner.TABLE_BASIC_MATERIAL,
                              snapshot.basic_material_rows[0], ("G12",), "F/L2")
    assert _material(e1_only).resolution is area_owner.AreaMaterialResolution.BASIC_MECHANICAL_PROPERTIES_UNRESOLVED


@pytest.mark.parametrize("g_key", ["G12", "Shear Modulus", "G", "g12"])
def test_exact_g12_alias_uses_own_unit_with_reordered_metadata_and_real_consumer(monkeypatch, g_key):
    rows = _rows_fixture()
    row = rows[owner.TABLE_BASIC_MATERIAL][0]
    row["E1"] = 33_000_000_000
    row.pop("G12")
    row[g_key] = 13_750
    original = deepcopy(rows)
    metadata_calls = Counter()

    def reverse(_table, raw):
        return raw[:2] + tuple(tuple(reversed(array)) for array in raw[2:7]) + raw[7:]

    context, scratch, display_calls = _install_environment(
        monkeypatch, rows=rows, metadata_units={"E1": "N/m2", g_key: "MPa"},
        metadata_calls=metadata_calls, raw_metadata_transform=reverse,
    )
    snapshot = _capture(context, scratch)
    bindings = {b.output_key: b for b in snapshot.table_unit_provenance[owner.TABLE_BASIC_MATERIAL]}
    assert set(bindings) == {"E1", g_key}
    assert bindings["E1"].source_unit == "N/m2"
    assert bindings[g_key].source_unit == "MPa"
    assert bindings["E1"].evidence_ref != bindings[g_key].evidence_ref
    assert bindings[g_key].source_call == "SapModel.DatabaseTables.GetAllFieldsInTable"
    assert owner.bind_frame_flexural_base_fact_from_snapshot(snapshot, "F1").etabs_ec_mpa == 33_000
    material = _material(snapshot)
    assert material.resolution is area_owner.AreaMaterialResolution.CONCRETE_PROVEN
    assert material.factual_ec_mpa == 33_000 and material.factual_gc_mpa == 13_750
    assert material.concrete_fck_mpa == 35
    assert rows == original
    assert tuple(dict(row) for row in snapshot.basic_material_rows) == original[owner.TABLE_BASIC_MATERIAL]
    assert metadata_calls == Counter({table: 1 for table in owner._DIMENSIONAL_FIELDS})
    assert sum(display_calls.values()) == 5


@pytest.mark.parametrize("fault", ["missing", "duplicate", "wrong-key"])
def test_bad_g12_metadata_fails_closed_without_retry_or_borrowing_e1(monkeypatch, fault):
    calls = Counter()

    def corrupt(table, raw):
        if table != owner.TABLE_BASIC_MATERIAL:
            return raw
        raw = list(raw)
        arrays = [list(array) for array in raw[2:7]]
        index = arrays[0].index("G12")
        if fault == "missing":
            for array in arrays:
                array.pop(index)
            raw[1] -= 1
        elif fault == "duplicate":
            for array in arrays:
                array.append(array[index])
            raw[1] += 1
        else:
            arrays[0][index] = "G13"
        raw[2:7] = arrays
        return tuple(raw)

    context, scratch, _ = _install_environment(
        monkeypatch, metadata_calls=calls, raw_metadata_transform=corrupt,
    )
    with pytest.raises(owner.FrameFlexuralBaseFactError, match="UNIT_UNQUALIFIED"):
        _capture(context, scratch)
    assert calls == Counter({owner.TABLE_RECTANGULAR: 1, owner.TABLE_BASIC_MATERIAL: 1})


def test_duplicate_g12_snapshot_binding_is_rejected_by_real_quantity_consumer(monkeypatch):
    context, scratch, _ = _install_environment(monkeypatch)
    snapshot = _capture(context, scratch)
    bindings = snapshot.table_unit_provenance[owner.TABLE_BASIC_MATERIAL]
    g12 = next(b for b in bindings if b.output_key == "G12")
    duplicate = _replace_bindings(snapshot, bindings + (g12,))
    with pytest.raises(owner.FrameFlexuralBaseFactError,
                       match="^UNIT_UNQUALIFIED:DUPLICATE_OR_INVALID_FIELD_METADATA$"):
        owner._table_quantity(duplicate, owner.TABLE_BASIC_MATERIAL,
                              snapshot.basic_material_rows[0], ("G12",), "F/L2")
    assert _material(duplicate).resolution is area_owner.AreaMaterialResolution.BASIC_MECHANICAL_PROPERTIES_UNRESOLVED


@pytest.mark.parametrize("empty_value", [None, ""])
def test_blank_g12_for_unrelated_material_stays_raw_and_unresolved(monkeypatch, empty_value):
    rows = _rows_fixture()
    rows[owner.TABLE_BASIC_MATERIAL] += ({"Material": "Rebar", "E1": 200_000_000, "G12": empty_value},)
    original = deepcopy(rows)
    context, scratch, _ = _install_environment(monkeypatch, rows=rows)
    snapshot = _capture(context, scratch)
    assert _material(snapshot).resolution is area_owner.AreaMaterialResolution.CONCRETE_PROVEN
    assert _material(snapshot, "Rebar").resolution is area_owner.AreaMaterialResolution.BASIC_MECHANICAL_PROPERTIES_UNRESOLVED
    with pytest.raises(owner.FrameFlexuralBaseFactError, match="^UNIT_UNQUALIFIED:MISSING_FIELD_VALUE$"):
        owner._table_quantity(snapshot, owner.TABLE_BASIC_MATERIAL,
                              snapshot.basic_material_rows[1], ("G12",), "F/L2")
    assert rows == original
    assert snapshot.basic_material_rows[1]["G12"] == empty_value


def test_nonempty_g12_alias_still_takes_precedence_over_blank_primary_key(monkeypatch):
    rows = _rows_fixture()
    rows[owner.TABLE_BASIC_MATERIAL][0].update(G12=None, **{"Shear Modulus": 13_750})
    context, scratch, _ = _install_environment(
        monkeypatch, rows=rows, metadata_units={"Shear Modulus": "MPa"},
    )
    snapshot = _capture(context, scratch)
    bindings = snapshot.table_unit_provenance[owner.TABLE_BASIC_MATERIAL]
    assert {b.output_key for b in bindings} == {"E1", "Shear Modulus"}
    assert _material(snapshot).factual_gc_mpa == 13_750
    assert snapshot.basic_material_rows[0]["G12"] is None


def test_ambiguous_g12_display_keys_fail_closed(monkeypatch):
    rows = _rows_fixture()
    rows[owner.TABLE_BASIC_MATERIAL][0]["g12"] = 13_750_000
    context, scratch, _ = _install_environment(monkeypatch, rows=rows)
    with pytest.raises(owner.FrameFlexuralBaseFactError, match="^UNIT_UNQUALIFIED:AMBIGUOUS_FIELD_KEY$"):
        _capture(context, scratch)
