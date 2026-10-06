"""Independent synthetic unit authority, never installed ETABS/v23 semantics."""
from dataclasses import replace

from tbdy_engine.etabs.oapi.contracts import SourceUnitProvenance, WallPropertyFact
from tbdy_engine.etabs.oapi.database_tables import DisplayTableFetchResult, ParsedDisplayTable
from tbdy_engine.etabs.oapi.material_properties import IsotropicMaterialPropertiesFact
from tbdy_engine.etabs.oapi.frame_section_mechanics import FrameSectionMechanicsFact
from tbdy_engine.etabs.safety import RuntimeCaptureStatus

MODEL = "synthetic:model"
SESSION = "synthetic:session"
CAPTURE = "synthetic:property-capture"
STATE = '{"present_units":10,"database_units":6}'


def binding(call, subject, key, dimension, unit, raw_ref, *, model=MODEL,
            session=SESSION, capture=CAPTURE, authority="fixture:independent-units"):
    return SourceUnitProvenance(source_call=call, subject_key=subject, output_key=key,
        dimension=dimension, source_unit=unit, authority_ref=authority,
        authority_version="OFFLINE_SYNTHETIC_1",
        authority_kind=("REVIEWED_FIELD_UNIT_METADATA" if "GetAllFieldsInTable" in call
                        else "REVIEWED_PROPERTY_SOURCE_SEMANTICS"), source_model_ref=model,
        session_ref=session, capture_ref=capture, raw_response_ref=raw_ref,
        return_code=0, unit_state_before=STATE, unit_state_after=STATE,
        qualification="QUALIFIED", reason="INDEPENDENT_SYNTHETIC_AUTHORITY")


def material(name="C35", *, e=34_000_000_000.0, g=14_166_666_666.666666,
             unit="N/m2", model=MODEL, session=SESSION):
    raw=(e, .2, 1e-5, g, 0)
    fact=IsotropicMaterialPropertiesFact(name,e,.2,1e-5,g,0.,0,raw_response=raw,
        source_model_ref=model,session_ref=session,capture_ref=CAPTURE)
    units=tuple(binding("SapModel.PropMaterial.GetMPIsotropic",name,key,"F/L2",unit,
                        fact.raw_response_ref,model=model,session=session) for key in ("E","G"))
    return replace(fact,unit_provenance=units)


def section(name="S", *, inertia=.03413333333333334, unit="m4", model=MODEL, session=SESSION):
    raw=(.64,.5,.5,.05,inertia,inertia,1.,1.,1.,1.,1.,1.,0)
    fact=FrameSectionMechanicsFact(name,*raw[:6],0,raw_response=raw,
        source_model_ref=model,session_ref=session,capture_ref=CAPTURE)
    units=tuple(binding("SapModel.PropFrame.GetSectProps",name,key,"L4",unit,
                        fact.raw_response_ref,model=model,session=session) for key in ("I22","I33"))
    return replace(fact,unit_provenance=units)


def wall(name="W", *, thickness=.4, unit="m"):
    raw=(1,2,"C35/45",thickness,0,"","guid",0)
    fact=WallPropertyFact(name,1,2,"C35/45",thickness,0,"","guid",raw,
                         return_code=0,source_model_ref=MODEL,session_ref=SESSION,capture_ref=CAPTURE)
    item=binding("SapModel.PropArea.GetWall",name,"Thickness","L",unit,fact.raw_response_ref)
    return replace(fact,unit_provenance=(item,))


def table(table_name, rows, units, *, model=MODEL, session=SESSION, capture="synthetic:table-capture"):
    # This is a reviewed synthetic DTO, NOT a decoder for the unsupported ABI.
    keys=tuple(dict.fromkeys(key for row in rows for key in row))
    raw_metadata=tuple((key,unit) for key,unit in units.items())
    fetched=DisplayTableFetchResult(table_name,ParsedDisplayTable(table_name,"ROWS_PARSED",
        field_keys=keys,rows=tuple(rows),row_count_reported=len(rows),return_code=0),
        capture_status=RuntimeCaptureStatus.FULL,field_metadata_raw=raw_metadata,field_unit_status="QUALIFIED")
    bindings=tuple(binding("SapModel.DatabaseTables.GetAllFieldsInTable",table_name,key,
        "L" if unit in {"m","mm","cm"} else "F/L2",unit,fetched.field_metadata_ref,
        model=model,session=session,capture=capture) for key,unit in units.items())
    return replace(fetched,field_unit_provenance=bindings)
