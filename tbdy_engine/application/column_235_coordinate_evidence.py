"""Accepted ABI7 observation adoption; offline files only, no native acquisition."""
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path

ADOPTION_NAME = 'COLUMN_235_ABI7_LIVE_COORDINATES_ADOPTION_2026-10-14.json'
ADOPTION_SHA256 = '75370f7d0c2442d9e66422967d149a5e110e823a058ccb18b0fd698bf4495730'
ORIGINAL_NAME = 'column-r1-r3m-abi7-coordinates_20261014_083705_600_893204f2c8c947248955ba9265ddcfbc.json'
ORIGINAL_SHA256 = '2e16f45f8aa7347fb49a53cd6fd0d9dfd66c93619705ba9f411e8d6bdf3e6bf1'
SIDECAR_SHA256 = '8fef35063195940461627ede28d1535d6be33ab926f10b5bf53a3cde6576ba9f'
CANDIDATE = '61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621'
HISTORICAL = 'FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F'
OPERATOR = {'HEAD':'9f426f5b6376b9c6da984270171556d2e3b2c496','TREE':'c557a517d07fa973a8ea5c2aabb3fbb8d65d34fb'}
METADATA_SHA = '81ca90983b67c9de85c7256c12c6a768ab7e676ae084d8b8de90e386a084730a'
WRAPPER_SHA = 'eca6cba1bbb040d61d9f286ac280ffac62dd294cb82cde299b3124ea3af85c9b'
PHASES = ['COORDINATE_ENTERED','COORDINATE_ABI_CHECK','COORDINATE_WRAPPER_VERIFIED','COORDINATE_INVOKED','COORDINATE_RETURNED','COORDINATE_RESPONSE_VALIDATED']
LIMITS = {'bottom_top':'NOT_DERIVED','regulatory_ln':'NOT_DERIVED','analysis_joint':'NOT_PROVEN','panel_zone':'NOT_PROVEN','B5':None,'B6':None,'GLOBAL_DELTA':'NOT_PROVEN','M6_B':'OPEN','R2_RERUN_READY':False,'real_235_design_ready':False,'additional_native_authorization':'NONE'}

def require(ok, message):
    if not ok: raise ValueError('ABI7 coordinate evidence: '+message)

def canonical_hash(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def validate_original_observation(doc):
    """Validate observed protocol after exact original-byte authentication."""
    require(type(doc) is dict,'original object required')
    try:
        require(doc['repository']==OPERATOR,'operator checkpoint differs')
        require(doc['scope']=='ABI7_TWO_EXACT_CANDIDATE_POINT_OBJECT_COORDINATES_ONLY' and doc['native_coordinates_qualified'] is True,'accepted observation scope differs')
        require(doc['status']=='TWO_CANDIDATE_POINT_COORDINATES_VALIDATED_ONLY' and doc['errors']==[],'observation unsuccessful')
        require(doc['source_sha_before']==doc['source_sha_after']==doc['candidate_expected_sha256']==CANDIDATE and doc['historical_source_sha256']==HISTORICAL,'source drift or rebound')
        require(doc['identity_before']==doc['identity_after'],'session/unit/lock drift')
        identity=doc['identity_before'];units=identity['units']
        require(identity['process_id']==doc['pid']==2072 and identity['model_full_path']==doc['source']==r'C:\tmp\B-BLOK_Revised.EDB','wrong observed source/session')
        require(identity['model_locked'] is True and identity['model_fingerprint'] is None,'lock/fingerprint scope differs')
        require(identity['program_version']=='23.2.0' and identity['program_api_version']==2.014,'runtime identity differs')
        require(units['present_length_unit']==units['database_length_unit']==6 and units['present_units_api']=='GetPresentUnits_2','unit identity differs')
        require(doc['getter_gateway_invocations']==1 and doc['target_getter_invocation_attempts']==2 and doc['target_result_getter_invocations']==0 and doc['modal_result_rows']==0 and doc['matrix_records']==[],'bounded acquisition scope differs')
        require(doc['source_authority_rebound'] is False and doc['FC09_production_gate']=='UNCHANGED' and doc['bottom_top_assignment']==doc['regulatory_ln']=='NOT_DERIVED','false engineering promotion')
        require(doc['B5'] is None and doc['B6'] is None and doc['GLOBAL_DELTA']=='NOT_PROVEN' and doc['M6_B']=='OPEN' and doc['R2_RERUN_READY'] is False,'false result qualification')
        require(doc['selection_observation']=='NOT_READ; NO_SELECTION_ACCESS_OR_MUTATION','selection scope differs')
        require(doc['backend_vtable_index_method_IID']=='NOT_OBSERVED_NOT_PROBED','unsupported backend identity')
        records=doc['coordinate_records'];require(type(records) is list and len(records)==2,'exact two records required')
        points=[]
        for index,(name,record) in enumerate(zip(('955','758'),records)):
            require(record['Name']==name and record['CSys']=='Global' and record['phases']==PHASES,'native name/slot/phase mismatch')
            require(record['call_arguments']=={'positional':[],'named':{'Name':name,'CSys':'Global'},'omitted_INOUT':['X','Y','Z']},'keyword binding differs')
            raw=record['raw_response'];require(type(raw) is list and len(raw)==4 and all(type(v) is float and math.isfinite(v) for v in raw[:3]) and type(raw[-1]) is int and raw[-1]==0,'raw type/order/status invalid')
            require(record['native_response_python_type']=='builtins.list' and record['raw_response_scalar_types']==['builtins.float']*3+['builtins.int'],'original scalar/container metadata differs')
            require(type(record['native_return_code']) is int and record['native_return_code']==0 and record['validated_response']==dict(zip(('X','Y','Z','pRetVal'),raw)),'validated response differs')
            require(record['coordinate_unit']=='m' and record['unit_authority']=='CSI_PRESENT_LENGTH_M_CODE6_NO_CONVERSION','coordinate unit unqualified')
            require(canonical_hash(raw)==record['raw_response_sha256'],'raw response hash differs')
            require(canonical_hash({k:record[k] for k in ('native_response_python_type','raw_response','raw_response_scalar_types')})==record['typed_raw_evidence_sha256'],'typed response hash differs')
            m=record['native_metadata'];require(canonical_hash(m['raw_metadata'])==m['raw_metadata_sha256']==METADATA_SHA,'metadata differs')
            require(canonical_hash(record['current_wrapper_raw_metadata'])==record['current_wrapper_raw_sha256']==WRAPPER_SHA,'wrapper differs')
            points.append({'frame_name':'235','native_slot':'Point'+str(index+1),'point_name':name,'CSys':'Global','unit':'m',**dict(zip(('X','Y','Z'),raw[:3])),'application_return_code':0,'original_response_index':index,'raw_response_sha256':record['raw_response_sha256'],'typed_raw_evidence_sha256':record['typed_raw_evidence_sha256']})
        return points
    except (KeyError,TypeError,IndexError) as exc:
        raise ValueError('ABI7 coordinate evidence: malformed original observation') from exc

def adopt_original_bytes(raw, sidecar):
    require(sha256(raw).hexdigest()==ORIGINAL_SHA256 and sha256(sidecar).hexdigest()==SIDECAR_SHA256,'original receipt/sidecar pin differs')
    require(sidecar.decode('ascii')==ORIGINAL_SHA256+'  '+ORIGINAL_NAME+'\n','exact original sidecar required')
    doc=json.loads(raw);points=validate_original_observation(doc)
    return {'schema':'column235.abi7.accepted_coordinates.v1','acceptance':{'status':'ACCEPTED / CLOSED_REUSE','file':'COLUMN_235_ABI7_ORIGINAL_RECEIPT_SUPERVISOR_ACCEPTANCE_2026-10-14(1).md','sha256':'63bed245cf20ceb49b559c2ac11012ddb3e003e58d2cd9fba22ee3b7c9a33f79'},'software_base':{'HEAD':'1440df1b9300f75b1e604204438f5cada9ebd247','TREE':'8c962be58474de12d1aab26b65d177f333e319a0'},'original':{'name':ORIGINAL_NAME,'whole_json_sha256':ORIGINAL_SHA256,'sidecar_bytes_sha256':SIDECAR_SHA256,'capture_HEAD':OPERATOR['HEAD'],'capture_TREE':OPERATOR['TREE'],'started_utc':doc['started_utc'],'finished_utc':doc['finished_utc']},'source':{'candidate_sha256':CANDIDATE,'historical_sha256':HISTORICAL,'model_path':doc['source']},'observed_integrity':{'PID':doc['pid'],'source_before_after_equal':True,'session_units_lock_before_after_equal':True,'model_fingerprint':None,'selection':'NOT_READ','metadata_sha256':METADATA_SHA,'wrapper_sha256':WRAPPER_SHA},'points':points,'qualification_limits':deepcopy(LIMITS),'worker_native_execution':False,'two_read_authorization':'CONSUMED'}

def validate_adoption(doc):
    require(doc['schema']=='column235.abi7.accepted_coordinates.v1' and doc['source']['candidate_sha256']==CANDIDATE and doc['source']['historical_sha256']==HISTORICAL,'derived source/schema differs')
    require(doc['original']['whole_json_sha256']==ORIGINAL_SHA256 and doc['original']['sidecar_bytes_sha256']==SIDECAR_SHA256 and doc['original']['capture_HEAD']==OPERATOR['HEAD'] and doc['original']['capture_TREE']==OPERATOR['TREE'],'original provenance differs')
    require(doc['qualification_limits']==LIMITS and doc['worker_native_execution'] is False and doc['two_read_authorization']=='CONSUMED','false derived qualification')
    require(len(doc['points'])==2,'exact two native slots required')
    for slot,name,point in zip(('Point1','Point2'),('955','758'),doc['points']):
        require(point['native_slot']==slot and point['point_name']==name and point['frame_name']=='235' and point['CSys']=='Global' and point['unit']=='m','derived binding/unit differs')
        require(all(type(point[k]) is float and math.isfinite(point[k]) for k in ('X','Y','Z')),'derived coordinate type differs')
    return deepcopy(doc)

def load_coordinate_adoption(repo):
    data=(Path(repo)/'docs'/ADOPTION_NAME).read_bytes()
    require(sha256(data).hexdigest()==ADOPTION_SHA256,'accepted adoption file differs')
    return validate_adoption(json.loads(data))
