"""Original external receipt adoption; explicit private offline run, no native code."""
from copy import deepcopy
import json
import os
from pathlib import Path
import pytest
from tbdy_engine.application.column_235_coordinate_evidence import adopt_original_bytes, validate_original_observation, ORIGINAL_SHA256

@pytest.fixture
def pair():
    p=Path(os.environ['COLUMN_235_ABI7_ORIGINAL_RECEIPT'])
    return p.read_bytes(),Path(str(p)+'.sha256').read_bytes()

def test_original_pair_adopts_only_two_named_global_coordinates(pair):
    doc=adopt_original_bytes(*pair)
    assert [(p['point_name'],p['X'],p['Y'],p['Z']) for p in doc['points']]==[('955',74.0,22.3,-5.15),('758',74.0,22.3,0.0)]
    assert doc['original']['whole_json_sha256']==ORIGINAL_SHA256
    assert doc['qualification_limits']['regulatory_ln']=='NOT_DERIVED'

@pytest.mark.parametrize('part',[0,1])
def test_original_byte_drift_is_rejected(pair,part):
    data=list(pair);data[part]+=b' ';assert data[part]!=pair[part]
    with pytest.raises(ValueError):adopt_original_bytes(*data)

@pytest.mark.parametrize('fault',['source','session','units','lock','checkpoint','errors','attempts','selection','matrix','modal','global','ln','slot','csys','keyword','phase','raw_type','bool_status','finite','raw_hash','typed_hash','metadata','wrapper'])
def test_semantic_mismatch_rejects_without_any_getter(pair,fault):
    d=json.loads(pair[0]);p=d['coordinate_records'][0]
    if fault=='source':d['source_sha_after']='0'*64
    elif fault=='session':d['identity_after']['process_id']=1
    elif fault=='units':d['identity_before']['units']['present_length_unit']=4;d['identity_after']=deepcopy(d['identity_before'])
    elif fault=='lock':d['identity_before']['model_locked']=False;d['identity_after']=deepcopy(d['identity_before'])
    elif fault=='checkpoint':d['repository']['HEAD']='0'*40
    elif fault=='errors':d['errors']=['failure']
    elif fault=='attempts':d['target_getter_invocation_attempts']=3
    elif fault=='selection':d['selection_observation']='CHANGED'
    elif fault=='matrix':d['matrix_records']=[{}]
    elif fault=='modal':d['modal_result_rows']=1
    elif fault=='global':d['GLOBAL_DELTA']='PROVEN'
    elif fault=='ln':d['regulatory_ln']=5.15
    elif fault=='slot':d['coordinate_records'].reverse()
    elif fault=='csys':p['CSys']='Local'
    elif fault=='keyword':p['call_arguments']['positional']=['955']
    elif fault=='phase':p['phases'].pop()
    elif fault=='raw_type':p['raw_response'][0]=74
    elif fault=='bool_status':p['native_return_code']=False
    elif fault=='finite':p['raw_response'][0]=float('nan')
    elif fault=='raw_hash':p['raw_response_sha256']='0'*64
    elif fault=='typed_hash':p['typed_raw_evidence_sha256']='0'*64
    elif fault=='metadata':p['native_metadata']['raw_metadata']['method']='Other'
    elif fault=='wrapper':p['current_wrapper_raw_metadata']['code_semantics_sha256']='0'*64
    with pytest.raises(ValueError):validate_original_observation(d)
