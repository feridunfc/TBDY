"""Population and exact native metadata gates; never engineering promotion."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
import hashlib
import json
import os

import pytest

from test_column_r1_r3c_modal_read_only import capture, run, tool
from tbdy_engine.etabs.oapi.database_tables import decode_table_field_metadata


@pytest.mark.parametrize('source', ['FrameForce', 'JointDispl'])
@pytest.mark.parametrize('defect', ['mode_1_only', 'missing_100', 'duplicate', 'extra_101', 'wrong_case', 'wrong_object', 'not_Mode', 'wrong_grain'])
def test_physical_mode_population_is_exact_per_object_and_physical_grain(capture, monkeypatch, source, defect):
    attribute = 'read_frame_force_response_from_session' if source == 'FrameForce' else 'read_joint_displ_from_session'
    original = getattr(tool, attribute)
    def getter(*args, **kwargs):
        fact = original(*args, **kwargs)
        rows = list(fact.rows)
        if defect == 'mode_1_only': rows = [r for r in rows if r.step_number == 1]
        elif defect == 'missing_100': rows = [r for r in rows if r.step_number != 100]
        elif defect == 'duplicate': rows.append(rows[0])
        elif defect == 'extra_101': rows.append(replace(rows[0], step_number=101))
        elif defect == 'wrong_case': rows[0] = replace(rows[0], load_case='OTHER')
        elif defect == 'wrong_object': rows[0] = replace(rows[0], **{'object_name' if source=='FrameForce' else 'point_object':'OTHER'})
        elif defect == 'not_Mode': rows[0] = replace(rows[0], step_type='Max')
        elif defect == 'wrong_grain': rows[0] = replace(rows[0], element_name='UNRELATED')
        return replace(fact, rows=tuple(rows))
    monkeypatch.setattr(tool, attribute, getter)
    receipt = run(capture)
    assert receipt['status'] == 'BLOCKED_READ_ONLY_CAPTURE' and receipt['errors']
    assert not receipt['current_b5_qualified'] and not receipt['stability_promotion']


TABLES = ['Response Spectrum Modal Info', 'Modal Periods And Frequencies',
          'Modal Participating Mass Ratios', 'Story Forces']


@pytest.mark.parametrize('table', TABLES)
@pytest.mark.parametrize('defect', ['truncated', 'duplicate', 'extra'])
def test_truncated_or_duplicate_native_tables_never_pass(capture, monkeypatch, table, defect):
    original = tool.fetch_display_table_for_output_from_session
    def getter(session, key, **kwargs):
        fact = original(session, key, **kwargs)
        if key == table:
            rows = list(fact.parsed.rows)
            if defect == 'truncated': rows = rows[:12]
            elif defect == 'duplicate': rows.append(rows[0])
            else: rows.append({**rows[0], 'StepNumber' if key=='Story Forces' else 'Mode':101})
            fact = replace(fact, parsed=replace(fact.parsed, rows=tuple(rows), row_count_reported=len(rows)))
        return fact
    monkeypatch.setattr(tool, 'fetch_display_table_for_output_from_session', getter)
    receipt = run(capture)
    assert receipt['status'] == 'BLOCKED_READ_ONLY_CAPTURE'
    assert 'mode' in receipt['errors'][0]['message']


@pytest.mark.parametrize('defect', ['missing_column', 'duplicate_column', 'missing_endpoint', 'duplicate_endpoint'])
def test_complete_physical_story_population_required(capture, monkeypatch, defect):
    original = tool.fetch_display_table_from_session
    def getter(session, key):
        fact = original(session, key)
        target = 'Column Object Connectivity' if 'column' in defect else 'Point Object Connectivity'
        if key == target:
            rows = fact.parsed.rows[:-1] if defect.startswith('missing') else (*fact.parsed.rows, fact.parsed.rows[0])
            return replace(fact, parsed=replace(fact.parsed, rows=rows, row_count_reported=len(rows)))
        return fact
    monkeypatch.setattr(tool, 'fetch_display_table_from_session', getter)
    receipt = run(capture)
    assert receipt['status'] == 'BLOCKED_READ_ONLY_CAPTURE' and receipt['errors']
    assert not capture.forces and not capture.joints


@pytest.mark.parametrize('table,field,wrong_unit', [
    ('Response Spectrum Modal Info','U1Amp',''),
    ('Response Spectrum Modal Info','U2Amp','mm'),
    ('Response Spectrum Modal Info','Mode','m'),
    ('Modal Periods And Frequencies','Period','Hz'),
    ('Modal Participating Mass Ratios','Mode','m'),
    ('Story Forces','VX','N'),
    ('Story Forces','StepNumber','sec'),
    ('Column Object Connectivity','Length','mm'),
    ('Point Object Connectivity','Z','mm'),
])
def test_native_unit_mismatch_is_not_scaled_or_borrowed(capture, monkeypatch, table, field, wrong_unit):
    original = tool.fetch_table_field_metadata_from_session
    def getter(session, key):
        fact = original(session, key)
        if key == table:
            raw = list(fact.raw_response)
            units = list(raw[5]); units[list(raw[2]).index(field)] = wrong_unit
            raw[5] = units
            return decode_table_field_metadata(tuple(raw), table_name=key)
        return fact
    monkeypatch.setattr(tool, 'fetch_table_field_metadata_from_session', getter)
    receipt = run(capture)
    assert receipt['status'] == 'BLOCKED_READ_ONLY_CAPTURE'
    assert 'unit/definition mismatch' in receipt['errors'][0]['message']


def test_story_rows_filter_exact_case_mode_story_and_bottom_preserving_raw_superset(capture, monkeypatch):
    original = tool.fetch_display_table_for_output_from_session
    def getter(session, key, **kwargs):
        fact = original(session, key, **kwargs)
        if key == 'Story Forces':
            base = fact.parsed.rows[0]
            extras = tuple({**base, **change} for change in (
                {'OutputCase':'ENV_GRAV'}, {'StepType':'Max'}, {'Story':'+3.50'}, {'Location':'Top'}))
            return replace(fact, parsed=replace(fact.parsed, rows=(*fact.parsed.rows, *extras), row_count_reported=104))
        return fact
    monkeypatch.setattr(tool, 'fetch_display_table_for_output_from_session', getter)
    receipt = run(capture)
    assert not receipt['errors']
    assert len(receipt['filtered_modal_story_forces']['ActualModal']['rows']) == 100
    assert len(receipt['facts']['Story Forces@ActualModal']['payload']['parsed']['rows']) == 104
    assert not receipt['current_b5_qualified'] and not receipt['R2_RERUN_READY']


@pytest.mark.parametrize('defect', ['unknown_bottom', 'wrong_period', 'wrong_direction', 'missing_restore', 'contradictory_restore'])
def test_unqualified_source_alignment_and_restoration_fail_closed(capture, monkeypatch, defect):
    if defect == 'wrong_direction':
        original = tool.get_response_spectrum_settings_from_session
        def settings(session, **kwargs):
            fact = original(session, **kwargs)
            changed = tuple(replace(x, outputs=tuple((k, ('U2',) if k=='LoadName' else v) for k,v in x.outputs))
                            if x.method=='GetLoads' else x for x in fact.settings)
            return replace(fact, settings=changed)
        monkeypatch.setattr(tool, 'get_response_spectrum_settings_from_session', settings)
    else:
        original = tool.fetch_display_table_for_output_from_session
        def getter(session, key, **kwargs):
            fact = original(session, key, **kwargs)
            if defect in ('missing_restore', 'contradictory_restore'):
                diagnostics = tuple(x for x in fact.state_diagnostics if x['phase']!='modal_output_restore_verify')
                if defect=='contradictory_restore':
                    diagnostics = (*fact.state_diagnostics, {'phase':'modal_output_restore_verify','success':False})
                return replace(fact, state_diagnostics=diagnostics)
            if key == ('Story Forces' if defect=='unknown_bottom' else 'Modal Periods And Frequencies'):
                rows = tuple({**r, **({'Location':'Unverified'} if defect=='unknown_bottom' else {'Period':'999'})} for r in fact.parsed.rows)
                return replace(fact, parsed=replace(fact.parsed, rows=rows))
            return fact
        monkeypatch.setattr(tool, 'fetch_display_table_for_output_from_session', getter)
    receipt = run(capture)
    assert receipt['status'] == 'BLOCKED_READ_ONLY_CAPTURE' and receipt['errors']


def test_dimensional_native_amplitudes_retained_without_multiplier_or_result_epoch(capture):
    receipt = run(capture)
    for case, direction in [('RSX','U1'), ('RSY','U2')]:
        aligned = receipt['native_amplitude_alignment'][case]
        assert aligned['source_field'] == direction+'Amp' and aligned['source_unit'] == 'm'
        assert aligned['applied_scaling_factor'] is None
        assert 'NOT_QUALIFIED' in aligned['normalization']
        native = receipt['facts']['Response Spectrum Modal Info@'+case]['payload']['parsed']['rows']
        assert native[0]['U1Amp'] == -.2 and native[0]['U2Amp'] == .3
    assert receipt['gate_2'] == 'PROJECT_DECISION_REQUIRED'
    assert not receipt['current_b5_qualified']


def test_historical_success_receipt_fails_exact_100_mode_completeness():
    path = os.getenv('COLUMN_R1_R3D_CAPTURE_TEST_PATH')
    if not path:
        pytest.skip('complete protected-source receipt is external historical evidence')
    raw = Path(path).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '4ea722960a5167bdfee0545b645b1dc2a9dd7992c072f60fc53aca2038f5cac7'
    receipt = json.loads(raw)
    assert receipt['status'].startswith('FACTUAL_CAPTURE_COMPLETE') and receipt['source_unchanged']
    forces = {k:v for k,v in receipt['facts'].items() if ':FrameForce:' in k}
    points = {k:v for k,v in receipt['facts'].items() if ':JointDispl:' in k}
    assert len(forces) == 86 and len(points) == 172
    for key, fact in {**forces, **points}.items():
        rows = fact['payload']['rows']
        assert {r['step_number'] for r in rows} == {1}
        native = NS(rows=tuple(NS(**r) for r in rows), return_code=0, state_diagnostics=())
        with pytest.raises(ValueError, match='mode population differs'):
            tool._physical_modes(native, name=key.split(':')[-1], case='Modal', frame=':FrameForce:' in key)
    rows = receipt['facts']['Story Forces@Modal']['payload']['parsed']['rows']
    bottom = [r for r in rows if r['OutputCase']=='Modal' and r['StepType']=='Mode'
              and r['Story']=='+0.00' and r['Location']=='Bottom']
    with pytest.raises(ValueError, match='mode population differs'):
        tool._unique_modes(bottom, 'StepNumber', 'historical bottom')
