"""Bounded P1A source-unit contract: no COM, inference, or population capture."""
from dataclasses import replace
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest

from unit_contract_fixtures import MODEL, SESSION, CAPTURE, binding, material, section, table, wall
import tbdy_engine.providers.etabs_frame_flexural_base_provider as base
import tbdy_engine.application.column_a18_end_restraint as a18
import tbdy_engine.etabs.oapi.material_properties as mp
from tbdy_engine.providers.frame_section_inertia_normalization import normalize_frame_section_inertia_m4
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.oapi.frame_section_mechanics import FrameSectionMechanicsFact
from tbdy_engine.etabs.oapi.database_tables import fetch_display_table
from tbdy_engine.etabs.safety import EtabsUnitSnapshot, read_etabs_unit_snapshot


def snapshot(*, reverse=False, units=None, metadata=True):
    rows = {
        base.TABLE_FRAME_ASSIGNMENTS: ({"UniqueName":"F1","SectProp":"S"},),
        base.TABLE_RECTANGULAR: ({"Name":"S","Material":"C35","t2":"0.8","t3":"800"},),
        base.TABLE_FRAME_SECTION_SUMMARY: ({"Name":"S","Shape":"Concrete Rectangular","Material":"C35"},),
        base.TABLE_BASIC_MATERIAL: ({"Material":"C35","E1":"34000","G12":"14166.6667"},),
        base.TABLE_CONCRETE: ({"Material":"C35","Fc":"35"},),
    }
    field_units={base.TABLE_RECTANGULAR:{"t2":"m","t3":"mm"},
                 base.TABLE_BASIC_MATERIAL:{"E1":"MPa","G12":"MPa"},base.TABLE_CONCRETE:{"Fc":"MPa"}}
    if units: field_units.update(units)
    tables={name:table(name,tuple(dict(reversed(tuple(row.items()))) for row in r) if reverse else r,
                      field_units.get(name,{})) for name,r in rows.items()}
    return base.FrameFlexuralBaseCaptureSnapshot(
        _issuance_token=base._FRAME_FLEXURAL_BASE_SNAPSHOT_ISSUANCE_TOKEN,
        source_model_ref=MODEL,ownership_proof_ref="synthetic:owned",
        acquisition_context_ref="synthetic:table-capture",session_provenance_ref=SESSION,
        scratch_path="synthetic.edb",present_force_unit=1,present_length_unit=1,
        assignment_rows=tables[base.TABLE_FRAME_ASSIGNMENTS].parsed.rows,
        rectangular_rows=tables[base.TABLE_RECTANGULAR].parsed.rows,
        section_summary_rows=tables[base.TABLE_FRAME_SECTION_SUMMARY].parsed.rows,
        basic_material_rows=tables[base.TABLE_BASIC_MATERIAL].parsed.rows,
        concrete_rows=tables[base.TABLE_CONCRETE].parsed.rows,
        table_unit_provenance={name:tuple(reversed(t.field_unit_provenance)) if reverse else t.field_unit_provenance
                               for name,t in tables.items()} if metadata else {},
        table_metadata_refs={name:t.field_metadata_ref for name,t in tables.items()} if metadata else {},
        table_metadata_raw={name:t.field_metadata_raw for name,t in tables.items()} if metadata else {})


@pytest.mark.parametrize("key",["E","G"])
def test_same_physical_stress_from_N_m_and_kN_m(key):
    n=material(e=33_600_000_000., g=14_000_000_000.)
    kn=material(e=n.modulus_of_elasticity/1000,g=n.shear_modulus/1000,unit="kN/m2")
    a=base._property_stress_to_mpa(n,key,source_model_ref=MODEL,session_ref=SESSION)
    b=base._property_stress_to_mpa(kn,key,source_model_ref=MODEL,session_ref=SESSION)
    assert a == b == {"E": Decimal("33600"), "G": Decimal("14000")}[key]


def normalize(fact):
    return normalize_frame_section_inertia_m4(fact.inertia_33,fact.source_unit_for("I33","L4"),
        source_ref=fact.evidence_ref,source_model_ref=MODEL,session_ref=SESSION,
        subject_key=fact.section_name,output_key="I33",capture_ref=fact.capture_ref,
        raw_response_ref=fact.raw_response_ref)


def test_mm4_and_m4_normalize_identically():
    m=normalize(section(inertia=.03413333333333334,unit="m4"))
    mm=normalize(section(inertia=34133333333.33334,unit="mm4"))
    assert m.inertia_m4==pytest.approx(mm.inertia_m4)
    assert Decimal(mm.factor)==Decimal("1e-12")
    assert mm.source_unit=="mm4" and mm.canonical_unit=="m4"


def test_table_own_units_and_reordered_exact_FieldKey():
    first=base.bind_frame_flexural_base_fact_from_snapshot(snapshot(),"F1")
    reordered=base.bind_frame_flexural_base_fact_from_snapshot(snapshot(reverse=True),"F1")
    assert first.t2_mm==first.t3_mm==Decimal("800")
    assert first.etabs_ec_mpa==Decimal("34000")
    assert first.semantic_payload()==reordered.semantic_payload()
    assert [r["field_key"] for r in first.unit_conversions]==["t2","t3","E1","Fc"]
    assert [r["source_unit"] for r in first.unit_conversions]==["m","mm","MPa","MPa"]
    assert all(r["unit_evidence_ref"].startswith("source-unit:sha256:") for r in first.unit_conversions)


def test_missing_metadata_never_uses_report_or_present_default():
    with pytest.raises(base.FrameFlexuralBaseFactError,match="UNIT_UNQUALIFIED"):
        base.bind_frame_flexural_base_fact_from_snapshot(snapshot(metadata=False),"F1")


@pytest.mark.parametrize("unit",["", "unknown", "[F/L2]", "m", "kN.m"])
def test_unknown_or_wrong_table_units_fail_closed(unit):
    with pytest.raises(base.FrameFlexuralBaseFactError,match="UNIT_UNQUALIFIED"):
        base.bind_frame_flexural_base_fact_from_snapshot(
            snapshot(units={base.TABLE_BASIC_MATERIAL:{"E1":unit}}),"F1")


@pytest.mark.parametrize("change",[
    {"return_code":None},{"return_code":1},{"source_unit":None},
    {"authority_ref":None},{"authority_kind":"REPORT_DEFAULT"},
    {"source_model_ref":"other-model"},{"session_ref":"other-session"},
    {"capture_ref":"other-capture"},{"output_key":"I22"},{"dimension":"L"},
    {"raw_response_ref":"other-response"},{"unit_state_after":"changed-state"},
])
def test_property_binding_errors_fail_closed(change):
    fact=material(); e=fact.unit_provenance[0]
    fact=replace(fact,unit_provenance=(replace(e,**change),fact.unit_provenance[1]))
    with pytest.raises((EtabsOAPIError,base.FrameFlexuralBaseFactError),match="UNIT_UNQUALIFIED"):
        base._property_stress_to_mpa(fact,"E",source_model_ref=MODEL,session_ref=SESSION)


def test_duplicate_exact_field_metadata_fails_closed():
    snap=snapshot(); item=snap.table_unit_provenance[base.TABLE_BASIC_MATERIAL][0]
    # Provider-issued immutable snapshot with deliberately malformed typed evidence.
    object.__setattr__(snap,"table_unit_provenance",{**snap.table_unit_provenance,
                      base.TABLE_BASIC_MATERIAL:(item,item)})
    with pytest.raises(base.FrameFlexuralBaseFactError,match="UNIT_UNQUALIFIED"):
        base.bind_frame_flexural_base_fact_from_snapshot(snap,"F1")


def test_provenance_change_creates_new_identity_without_changing_raw_values():
    fact=material()
    changed=replace(fact,unit_provenance=tuple(replace(b,authority_ref="fixture:review-two")
                                              for b in fact.unit_provenance))
    assert changed.raw_response==fact.raw_response
    assert changed.raw_response_ref==fact.raw_response_ref
    assert changed.evidence_ref!=fact.evidence_ref
    assert changed.unit_provenance[0].evidence_ref!=fact.unit_provenance[0].evidence_ref


def test_table_provenance_changes_derived_evidence_not_physical_state():
    one=snapshot(); two=snapshot()
    object.__setattr__(two,"table_unit_provenance",{name:tuple(replace(b,authority_ref="review:2") for b in values)
                                                for name,values in two.table_unit_provenance.items()})
    a=base.bind_frame_flexural_base_fact_from_snapshot(one,"F1")
    b=base.bind_frame_flexural_base_fact_from_snapshot(two,"F1")
    assert a.semantic_state_ref==b.semantic_state_ref
    assert a.unit_conversions!=b.unit_conversions
    assert a.evidence_ref!=b.evidence_ref


def test_A18_refuses_borrowed_base_units_and_accepts_own_binding():
    qualified=section()
    borrowed=SimpleNamespace(base_fact=SimpleNamespace(present_length_unit=6,source_model_ref=MODEL,
                                session_provenance_ref=SESSION),
                              section_mechanics=replace(qualified,unit_provenance=()))
    with pytest.raises(a18._Unresolved,match="UNIT_UNQUALIFIED"):
        a18._inertia_m4(borrowed,"F1","M3")
    borrowed.section_mechanics=qualified
    assert a18._inertia_m4(borrowed,"F1","M3")[0]==pytest.approx(qualified.inertia_33)


@pytest.mark.parametrize("output",["E","G"])
def test_E_G_refuses_borrowed_table_units(output):
    raw=replace(material(),unit_provenance=())
    with pytest.raises(base.FrameFlexuralBaseFactError,match="UNIT_UNQUALIFIED"):
        base._property_stress_to_mpa(raw,output,source_model_ref=MODEL,session_ref=SESSION)


def test_old_anomalous_tuples_stay_raw_unqualified():
    raw=(34_000_000_000_000.,.2,9.999999747378752e-6,14_166_666_666_666.668,0)
    fact=mp.IsotropicMaterialPropertiesFact("C35/45",*raw[:4],0.,0,raw_response=raw)
    assert fact.raw_response==raw and fact.modulus_of_elasticity==raw[0]
    assert not fact.unit_provenance and fact.success
    with pytest.raises(EtabsOAPIError,match="UNIT_UNQUALIFIED"):
        fact.source_unit_for("E","F/L2")
    section_raw=(6.400000000000001e-7,5.333332586666775e-7,5.333332586666774e-7,
        5.770665470952372e-14,3.413333333333333e-14,3.413333333333333e-14,
        8.533333333333331e-11,8.533333333333331e-11,1.2800000000000002e-10,
        1.2800000000000002e-10,.00023094010767585026,.00023094010767585026,0)
    sec=FrameSectionMechanicsFact("Column_80x80",*section_raw[:6],0,raw_response=section_raw)
    assert sec.raw_response==section_raw and sec.area==section_raw[0]
    assert sec.inertia_33==3.413333333333333e-14
    with pytest.raises(EtabsOAPIError,match="UNIT_UNQUALIFIED"):
        sec.source_unit_for("I33","L4")
    w=replace(wall(thickness=.0004),unit_provenance=())
    assert w.thickness==.0004
    with pytest.raises(EtabsOAPIError,match="UNIT_UNQUALIFIED"):
        w.source_unit_for("Thickness","L")


def test_raw_properties_cannot_be_relabelled_by_changing_only_numeric_value():
    with pytest.raises(EtabsOAPIError,match="RAW_PROPERTY_VALUE_MISMATCH"):
        replace(material(),modulus_of_elasticity=34000.)


def test_Temp_optional_ABI_binding_offline_with_fresh_observations(monkeypatch):
    calls=[]
    class Prop:
        def GetMPIsotropic(self, Name, E=0., U=0., A=0., G=0., Temp=0.):
            calls.append((Name,E,U,A,G,Temp))
            return (34_000.,.2,1e-5,14_166.6667,0)
    class FakeSession: pass
    session=FakeSession()
    from tbdy_engine.etabs.safety import EtabsSessionIdentity
    units=EtabsUnitSnapshot(present_units=10,present_force_unit=3,present_length_unit=6,
                           present_observation_status="OBSERVED_CONSISTENT")
    session.identity=EtabsSessionIdentity(16664,"fixture",2.014,"ETABS","23.2.0","fixture",
                                        0.,r"C:\synthetic\source.edb",None,"UNAVAILABLE",True,units)
    session._gateway_session=object()
    observations=[]
    def identity_read(*args,**kwargs):
        observations.append("fresh")
        return replace(session.identity,units=replace(units))
    monkeypatch.setattr(mp,"read_session_identity",identity_read)
    monkeypatch.setattr(mp,"EtabsVerifiedSession",FakeSession)
    def read(s,callback,**kwargs):
        assert s is session
        return callback(object(),SimpleNamespace(PropMaterial=Prop()))
    monkeypatch.setattr(mp,"_execute_verified_read",read)
    fact=mp.get_isotropic_material_properties_from_session(session,material_name="C",temperature=25.)
    assert calls==[("C",0.,0.,0.,0.,25.)]
    assert fact.temperature==25. and len(fact.unit_provenance)==2
    assert observations==["fresh","fresh"]


def test_display_read_does_not_add_metadata_getter_or_fallback():
    calls=[]
    class Tables:
        def GetTableForDisplayArray(self,*args):
            calls.append("GetTableForDisplayArray")
            return {"ret":0,"fields":["E1"],"number_records":1,"data":["34000"]}
        def GetAllFieldsInTable(self,*args):
            raise AssertionError("no new calls authorized")
    result=fetch_display_table(Tables(),"T")
    assert calls==["GetTableForDisplayArray"]
    assert result.field_unit_status=="UNIT_UNQUALIFIED:FIELD_METADATA_NOT_ACQUIRED"
    assert result.field_unit_provenance==() and result.field_metadata_raw==()


def test_unit_snapshot_retains_existing_four_reads_and_allows_distinct_contexts():
    calls=[]
    class Units:
        def GetPresentUnits(self): calls.append("P"); return 10
        def GetDatabaseUnits(self): calls.append("D"); return 6
        def GetPresentUnits_2(self): calls.append("P2"); return (3,6,2,0)
        def GetDatabaseUnits_2(self): calls.append("D2"); return (4,6,2,0)
    u=read_etabs_unit_snapshot(Units())
    assert calls==["P2","D2","P","D"]
    assert u.present_observation_status==u.database_observation_status=="OBSERVED_CONSISTENT"
    assert len(u.raw_unit_reads)==4 and not u.diagnostics


@pytest.mark.parametrize("raw,enum",[((3,6,2),10),((3,6,2,1),10),((3,6,2,0),6),((3.5,6,2,0),10),((True,6,2,0),10)])
def test_unit_observation_missing_return_or_enum_conflict_is_unqualified(raw,enum):
    class Units:
        def GetPresentUnits(self): return enum
        def GetPresentUnits_2(self): return raw
    u=read_etabs_unit_snapshot(Units())
    assert u.present_observation_status=="UNIT_UNQUALIFIED"
    assert dict(u.raw_unit_reads)["GetPresentUnits_2"]==repr(raw)


def test_timestamp_changes_are_not_unit_drift():
    fact=material(); b=fact.unit_provenance[0]
    one=json.dumps({"present_units":10,"observed_utc":"2026-10-04T01:00:00Z"})
    two=json.dumps({"present_units":10,"observed_utc":"2026-10-04T01:00:01Z"})
    changed=replace(fact,unit_provenance=(replace(b,unit_state_before=one,unit_state_after=two),))
    assert base._property_stress_to_mpa(changed,"E",source_model_ref=MODEL,session_ref=SESSION)==Decimal("34000")
    u=EtabsUnitSnapshot(present_units=10)
    assert u==replace(u,raw_unit_reads=(("observation_time","different"),))


@pytest.mark.parametrize("unit", ["m", "unsupported", "kN.m"])
def test_property_unknown_or_wrong_unit_never_enters_stress_conversion(unit):
    with pytest.raises(base.FrameFlexuralBaseFactError, match="UNIT_UNQUALIFIED"):
        base._property_stress_to_mpa(material(unit=unit), "E",
                                    source_model_ref=MODEL, session_ref=SESSION)


def test_explicit_table_unit_record_cannot_qualify_a_property_output():
    fact = material()
    borrowed = replace(fact.unit_provenance[0],
                       source_call="SapModel.DatabaseTables.GetAllFieldsInTable",
                       authority_kind="REVIEWED_FIELD_UNIT_METADATA")
    fact = replace(fact, unit_provenance=(borrowed,))
    with pytest.raises(base.FrameFlexuralBaseFactError, match="UNIT_UNQUALIFIED"):
        base._property_stress_to_mpa(fact, "E", source_model_ref=MODEL, session_ref=SESSION)


@pytest.mark.parametrize("code", [None, 1, False])
def test_missing_table_data_success_code_cannot_supply_qualified_rows(monkeypatch, code):
    fetched = table("T", ({"E1": "34000"},), {"E1": "MPa"})
    fetched = replace(fetched, parsed=replace(fetched.parsed, return_code=code))
    monkeypatch.setattr(base, "fetch_display_table_from_session", lambda *a, **k: fetched)
    with pytest.raises(base.FrameFlexuralBaseFactError, match="UNIT_UNQUALIFIED"):
        base._rows(SimpleNamespace(verified_session=object()), "T")


def test_wall_raw_value_cannot_be_rescaled_while_retaining_old_raw_provenance():
    with pytest.raises(EtabsOAPIError, match="RAW_WALL_PROPERTY_VALUE_MISMATCH"):
        replace(wall(thickness=.0004), thickness=.4)


def test_layered_wall_thickness_cannot_be_qualified():
    original = wall()
    raw = (original.wall_type, 6, original.material_name, original.thickness,
           original.color, original.notes, original.guid, 0)
    layered = replace(original, shell_type=6, raw_response=raw, thickness_applicable=True)
    layered = replace(layered, unit_provenance=tuple(
        replace(item, raw_response_ref=layered.raw_response_ref) for item in layered.unit_provenance))
    with pytest.raises(EtabsOAPIError, match="UNIT_UNQUALIFIED"):
        layered.source_unit_for("Thickness", "L")


def test_area_material_missing_field_units_stays_unresolved_with_raw_rows():
    from tbdy_engine.providers.etabs_area_contributor_provider import (
        _capture_area_material_facts, AreaMaterialResolution)
    snap = snapshot(metadata=False)
    raw_rows = snap.basic_material_rows
    result = _capture_area_material_facts(
        rows=(SimpleNamespace(property_state=SimpleNamespace(material_name="C35")),),
        material_snapshot=snap, model_fingerprint="synthetic:model-fingerprint",
        evidence_epoch_id="synthetic:epoch", session_provenance_ref=SESSION)
    assert result[0].resolution == AreaMaterialResolution.BASIC_MECHANICAL_PROPERTIES_UNRESOLVED
    assert result[0].factual_ec_mpa is result[0].factual_gc_mpa is None
    assert result[0].basic_mechanical_row == dict(raw_rows[0])
    assert any("UNIT_UNQUALIFIED" in ref for ref in result[0].source_refs)
    assert result[0].unit_conversions == ()
