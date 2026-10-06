"""Reviewed GetAllFieldsInTable ABI, identity binding, and read-only scope.

All values are synthetic offline fixtures; they are not B-BLOK unit authority.
"""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest

import tbdy_engine.etabs.oapi.database_tables as owner
import tbdy_engine.etabs.safety as safety
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.providers.etabs_frame_flexural_base_provider import (
    _table_quantity, FrameFlexuralBaseFactError,
)

TABLE = "Frame Section Property Definitions - Concrete Rectangular"
MODEL = "synthetic:source.edb"
SESSION = "synthetic:session"
CAPTURE = "synthetic:metadata-capture"
UNITS_OBSERVATION = '{"observation":"synthetic:actual-unit-state"}'


def raw(keys=("Name", "t2", "t3"), units=("", "m", "mm")):
    return (2, len(keys), list(keys), ["Field " + k for k in keys],
            ["Description " + k for k in keys], list(units), [False] * len(keys), 0)


def metadata(value=None):
    return owner.decode_table_field_metadata(raw() if value is None else value, table_name=TABLE)


def display():
    # Display field order is intentionally different from metadata field order.
    class DisplayOnly:
        def GetTableForDisplayArray(self, *args):
            return ([], 2, ["t3", "Name", "t2"], 1, ["800", "S", "0.8"], 0)
    return owner.fetch_display_table(DisplayOnly(), TABLE)


def bound(meta=None, **overrides):
    context = dict(field_dimensions={"t2":"L", "t3":"L"}, source_model_ref=MODEL,
        session_ref=SESSION, capture_ref=CAPTURE, unit_state_before=UNITS_OBSERVATION,
        unit_state_after=UNITS_OBSERVATION)
    context.update(overrides)
    return owner.bind_display_table_field_units(display(), metadata() if meta is None else meta, **context)


def quantity(result, key):
    capture_input = SimpleNamespace(table_unit_provenance={TABLE:result.field_unit_provenance},
        table_metadata_refs={TABLE:result.field_metadata_ref}, source_model_ref=MODEL,
        session_provenance_ref=SESSION, acquisition_context_ref=CAPTURE)
    return _table_quantity(capture_input, TABLE, result.parsed.rows[0], (key,), "L")


def test_exact_eight_item_output_order_and_raw_retention():
    value = raw(); result = metadata(value)
    assert owner.FIELD_METADATA_OUTPUT_ORDER == ("TableVersion","NumberFields","FieldKey",
        "FieldName","Description","UnitsString","IsImportable","pRetVal")
    assert result.status == "PARSED_EXACT_FIELD_METADATA"
    assert (result.table_version,result.number_fields,result.return_code) == (2,3,0)
    assert result.field_metadata("t2") == {"FieldKey":"t2", "FieldName":"Field t2",
        "Description":"Description t2", "UnitsString":"m", "IsImportable":False}
    saved = deepcopy(result.raw_response)
    value[2][1] = "changed-after-return"
    assert result.raw_response == saved and result.field_keys[1] == "t2"


@pytest.mark.parametrize("value", [None,0,{},"eight?",(),raw()[:-1],raw()+(0,)])
def test_unknown_ABI_shape_fails_closed(value):
    result = owner.decode_table_field_metadata(value, table_name=TABLE)
    assert result.status == "UNIT_UNQUALIFIED:FIELD_METADATA_ABI_SHAPE"
    assert not result.field_keys


@pytest.mark.parametrize("ret", [None,False,True,0.0,1,-1,"0"])
def test_success_requires_exact_integer_zero(ret):
    result = metadata(raw()[:-1]+(ret,))
    assert result.status == "UNIT_UNQUALIFIED:FIELD_METADATA_RETURN_CODE"
    assert result.raw_response[-1] == ret
    assert bound(result).field_unit_status.startswith("UNIT_UNQUALIFIED")


@pytest.mark.parametrize("slot", [2,3,4,5,6])
def test_NumberFields_matches_every_parallel_array(slot):
    value = list(raw());value[slot] = value[slot][:-1]
    result = metadata(tuple(value))
    assert result.status == "UNIT_UNQUALIFIED:FIELD_METADATA_ARRAY_LENGTH"
    assert bound(result).field_unit_provenance == ()


@pytest.mark.parametrize("slot,value", [(0,False),(0,-1),(0,2.0),(1,True),(1,-1),(1,"3")])
def test_invalid_version_or_count_rejected(slot,value):
    response = list(raw());response[slot] = value
    assert metadata(response).status == "UNIT_UNQUALIFIED:FIELD_METADATA_VERSION_OR_COUNT"


@pytest.mark.parametrize("slot", [2,3,4,5])
def test_BSTR_arrays_are_not_coerced(slot):
    value = list(raw());value[slot][0] = 5
    assert metadata(value).status == "UNIT_UNQUALIFIED:FIELD_METADATA_STRING_ARRAY_TYPE"


@pytest.mark.parametrize("flag", [0,-1,1,None,"False"])
def test_VARIANT_BOOL_array_requires_bool(flag):
    value = list(raw());value[6][0] = flag
    assert metadata(value).status == "UNIT_UNQUALIFIED:FIELD_METADATA_IMPORTABLE_TYPE"


def test_duplicate_exact_FieldKey_rejected():
    result = metadata(raw(keys=("t2","t2"), units=("m","mm")))
    assert result.status == "UNIT_UNQUALIFIED:FIELD_METADATA_DUPLICATE_FIELDKEY"
    with pytest.raises(EtabsOAPIError):result.field_metadata("t2")


@pytest.mark.parametrize("key", ["", " t2", "t2 "])
def test_blank_or_noncanonical_FieldKey_rejected(key):
    result = metadata(raw(keys=(key,),units=("m",)))
    assert result.status == "UNIT_UNQUALIFIED:FIELD_METADATA_INVALID_FIELDKEY"


def test_exact_FieldKey_mapping_survives_display_projection_and_metadata_reorder():
    first = bound()
    shuffled = raw(keys=("t3","Name","t2"),units=("mm","","m"))
    second = bound(metadata(shuffled))
    assert quantity(first,"t2") == quantity(second,"t2") == Decimal("800")
    assert quantity(first,"t3") == quantity(second,"t3") == Decimal("800")
    assert first.parsed.field_keys == ("t3","Name","t2")
    assert first.field_metadata_ref != second.field_metadata_ref
    assert first.field_unit_provenance[0].evidence_ref != second.field_unit_provenance[0].evidence_ref


@pytest.mark.parametrize("unit", ["", " ","unknown","[L]","m ","MPa","kN-m"])
def test_blank_unknown_wrong_units_block_only_that_field_without_default(unit):
    result = bound(metadata(raw(units=("",unit,"mm"))))
    assert result.field_unit_status == "UNIT_UNQUALIFIED"
    assert result.field_unit_provenance[0].source_unit == unit
    with pytest.raises(FrameFlexuralBaseFactError,match="UNIT_UNQUALIFIED"):quantity(result,"t2")
    assert quantity(result,"t3") == Decimal("800")
    assert result.parsed.rows[0]["t2"] == "0.8"


def test_binding_is_case_sensitive_and_never_uses_FieldName_alias():
    value = list(raw());value[2][1] = "T2";value[3][1] = "t2"
    result = bound(metadata(value))
    with pytest.raises(FrameFlexuralBaseFactError,match="UNIT_UNQUALIFIED"):quantity(result,"t2")
    assert quantity(result,"t3") == Decimal("800")


@pytest.mark.parametrize("overrides", [dict(unit_state_before=None),dict(unit_state_after=None),
    dict(unit_state_after='{"observation":"changed"}'),dict(source_model_ref=""),
    dict(session_ref=""),dict(capture_ref="")])
def test_missing_context_or_unit_drift_never_borrows_report_units(overrides):
    result = bound(**overrides)
    assert result.field_unit_status == "UNIT_UNQUALIFIED"
    with pytest.raises(FrameFlexuralBaseFactError,match="UNIT_UNQUALIFIED"):quantity(result,"t2")


def test_table_identity_must_match_display_exactly():
    with pytest.raises(EtabsOAPIError,match="TABLEKEY_MISMATCH"):
        bound(replace(metadata(),table_name="Another table"))


@pytest.mark.parametrize("context", [dict(source_model_ref="other"),dict(session_ref="other"),
                                      dict(capture_ref="other")])
def test_capture_context_mismatch_is_not_rebound(context):
    with pytest.raises(EtabsOAPIError,match="MISMATCH"):bound(replace(metadata(),**context))


def test_tampered_decoded_values_do_not_override_preserved_raw_tuple():
    changed = replace(metadata(),units_strings=("","mm","mm"))
    result = bound(changed)
    assert result.field_unit_status == "UNIT_UNQUALIFIED:FIELD_METADATA_RAW_CONFLICT"
    assert result.field_unit_provenance == () and result.field_metadata_raw == metadata().raw_response


def test_zero_fields_is_valid_empty_metadata_but_cannot_qualify_t2():
    result = metadata((2,0,[],[],[],[],[],0))
    assert result.status == "PARSED_EXACT_FIELD_METADATA"
    assert bound(result).field_unit_status == "UNIT_UNQUALIFIED"


def test_metadata_getter_exact_TableKey_only_one_call_and_unchanged_output():
    value = tuple(tuple(v) if isinstance(v,list) else v for v in raw())
    class MetadataOnly:
        def __init__(self):self.calls=[]
        def GetAllFieldsInTable(self,TableKey):
            self.calls.append(TableKey)
            assert len(self.calls) == 1, "No second call or fallback"
            return value
        def __getattr__(self,name):raise AssertionError("Unexpected native call "+name)
    db = MetadataOnly();result = owner.fetch_table_field_metadata(db,TABLE)
    assert db.calls == [TABLE]
    assert result.raw_response == value
    assert result == metadata(value)
    assert result.status == "PARSED_EXACT_FIELD_METADATA"


def test_native_exception_preserved_without_retry_or_fallback():
    class Failure:
        calls=0
        def GetAllFieldsInTable(self,TableKey):
            assert TableKey == TABLE
            self.calls+=1;raise RuntimeError("synthetic failure")
    db = Failure();result = owner.fetch_table_field_metadata(db,TABLE)
    assert db.calls == 1
    assert result.status == "UNIT_UNQUALIFIED:FIELD_METADATA_GETTER_FAILED:RuntimeError:synthetic failure"
    assert result.raw_response == ()
    assert bound(result).field_unit_status == result.status
    assert bound(result).field_unit_provenance == ()


@pytest.mark.parametrize("dimensions", [{0:"L"},{" t2":"L"},{"t2":None},{"t2":" L"}])
def test_invalid_explicit_field_dimension_contract_fails_closed(dimensions):
    with pytest.raises(EtabsOAPIError,match="INVALID_FIELD_DIMENSION_CONTRACT"):
        bound(field_dimensions=dimensions)


def test_display_table_behavior_remains_unchanged_without_implicit_metadata():
    class DisplayOnly:
        def __init__(self):self.calls=[]
        def GetTableForDisplayArray(self,*args):
            self.calls.append(args);return ([],2,["Name","t2"],1,["S","0.8"],0)
        def GetAllFieldsInTable(self,*args):raise AssertionError("No implicit metadata read")
    db = DisplayOnly();before = owner.fetch_display_table(db,TABLE)
    assert len(db.calls) == 1 and before.parsed.rows == ({"Name":"S","t2":"0.8"},)
    assert before.field_unit_status == "UNIT_UNQUALIFIED:FIELD_METADATA_NOT_ACQUIRED"
    after = owner.bind_display_table_field_units(before,metadata(),field_dimensions={"t2":"L"},
        source_model_ref=MODEL,session_ref=SESSION,capture_ref=CAPTURE,
        unit_state_before=UNITS_OBSERVATION,unit_state_after=UNITS_OBSERVATION)
    assert after.parsed is before.parsed and after.raw_response is before.raw_response
    assert after.signature_attempts is before.signature_attempts
    assert after.field_metadata_ref == metadata().raw_response_ref


@pytest.mark.parametrize("capture_ref", [None, "field-metadata-capture:caller-owned-event"])
def test_session_read_uses_existing_STA_and_only_metadata_capability(monkeypatch, capture_ref):
    class Session:
        identity=SimpleNamespace(model_full_path=MODEL,process_id=73)
    class MetadataOnly:
        calls=0
        def GetAllFieldsInTable(self,TableKey):
            assert TableKey == TABLE
            self.calls+=1
            assert self.calls == 1, "No second call or fallback"
            return raw()
    session=Session();db=MetadataOnly();seen=[]
    def fake_read(actual,callback,*,operation,timeout_seconds):
        assert actual is session
        seen.append((operation,timeout_seconds))
        return callback(object(),SimpleNamespace(DatabaseTables=db))
    monkeypatch.setattr(safety,"EtabsVerifiedSession",Session)
    monkeypatch.setattr(safety,"_execute_verified_read",fake_read)
    result=owner.fetch_table_field_metadata_from_session(session,TABLE,capture_ref=capture_ref)
    assert db.calls == 1 and seen == [("oapi_database_tables_get_all_fields_in_table",30.0)]
    assert result.source_model_ref == MODEL and result.session_ref == "etabs-session:pid:73"
    assert result.capture_ref.startswith("field-metadata-capture:")
    if capture_ref is not None:
        assert result.capture_ref == capture_ref
    assert result.status == "PARSED_EXACT_FIELD_METADATA"


def test_unknown_session_is_rejected_before_any_callback():
    with pytest.raises(TypeError,match="EtabsVerifiedSession"):
        owner.fetch_table_field_metadata_from_session(object(),TABLE)
