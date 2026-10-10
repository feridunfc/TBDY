"""Exact CSI native output ranges, within the existing reversible owners."""
from types import SimpleNamespace as NS

import pytest

from tbdy_engine.etabs.safety import (
    DatabaseTablesReadTransaction, ResultsSetupReadTransaction,
    EtabsCapabilityError, EtabsStateRestoreError, EtabsStateVerificationError,
)
from test_safety_foundation import FakeDatabaseTables, FakeResultsSetup, FakeSap, FakeNameList


class NativeModes:
    def configure(self, table):
        self.table = table
        self.options = ((True, 1.25, -2.5, 3.75, False, 1, 12, False, 2, 7, 3, 1, 2, 3, 2)
                        if table else (1, 1, False))
        self.original_options = self.options
        self.writes = []
        self.fault = None

    def get_options(self):
        raw = (*self.options, 0)
        if self.fault == 'malformed':
            return raw[:-1]
        if self.fault == 'snapshot_nonzero':
            return (*self.options, 7)
        return raw

    def set_options(self, *args):
        self.writes.append(args)
        restoring = len(self.writes) > 1
        if restoring and self.fault == 'restore_nonzero':
            return 7
        self.options = args
        if restoring and self.fault == 'restore_wrong':
            self.options = (*args[:-1], 4) if self.table else (1, 99, False)
        if not restoring and self.fault == 'temporary_wrong':
            self.options = (*args[:6], 12, *args[7:]) if self.table else (1, 12, False)
        if not restoring and self.fault == 'unrelated_option':
            self.options = (False, *args[1:]) if self.table else (1, 100, True)
        if not restoring and self.fault == 'temporary_nonzero':
            return 6  # partial native mutation must still be restored
        if not restoring and self.fault == 'temporary_none':
            return None
        return 0


class NativeTables(NativeModes, FakeDatabaseTables):
    def __init__(self):
        FakeDatabaseTables.__init__(self)
        self.configure(True)

    def GetOutputOptionsForDisplay(self):
        return self.get_options()

    def SetOutputOptionsForDisplay(self, *args):
        return self.set_options(*args)


class NativeSetup(NativeModes, FakeResultsSetup):
    def __init__(self):
        FakeResultsSetup.__init__(self)
        self.configure(False)

    def GetOptionModeShape(self):
        return self.get_options()

    def SetOptionModeShape(self, *args):
        return self.set_options(*args)


@pytest.fixture(params=['api', 'table'])
def state(request):
    if request.param == 'table':
        owner = NativeTables()
        transaction = DatabaseTablesReadTransaction(owner)
        select = lambda: transaction.select_output('MODAL')
        restored = lambda: owner.cases == ['OLD_CASE'] and owner.combos == ['OLD_COMBO'] and owner.patterns == ['DEAD']
    else:
        owner = NativeSetup()
        sap = FakeSap()
        sap.Results = NS(Setup=owner)
        sap.LoadCases = FakeNameList(['DEAD', 'MODAL'])
        sap.RespCombo = FakeNameList(['COMB'])
        transaction = ResultsSetupReadTransaction(sap)
        select = lambda: transaction.select_case('MODAL')
        restored = lambda: owner.case_flags == {'DEAD': True, 'MODAL': False} and owner.combo_flags == {'COMB': True}
    return NS(owner=owner, transaction=transaction, select=select, restored=restored)


def test_native_100_mode_selection_and_exact_all_scalar_restoration(state):
    s = state
    with s.transaction:
        s.select()
        s.transaction.select_modal_modes((1, 100))
        if s.owner.table:
            assert s.owner.options[4:7] == (False, 1, 100)
            assert s.owner.options[:4] == s.owner.original_options[:4]
            assert s.owner.options[7:] == s.owner.original_options[7:]
        else:
            assert s.owner.options == (1, 100, False)
    assert s.owner.options == s.owner.original_options and s.restored()
    phases = {x['phase']: x for x in s.transaction.diagnostics}
    assert phases['modal_output_snapshot']['raw_response'] == [*s.owner.original_options, 0]
    assert phases['temporary_modal_modes']['success'] is True
    assert phases['modal_output_restore_verify']['success'] is True
    assert len(s.owner.writes) == 2


def test_failing_physical_read_restores_modes_and_selections_and_preserves_cause(state):
    with pytest.raises(RuntimeError, match='getter failure'):
        with state.transaction:
            state.select()
            state.transaction.select_modal_modes((1, 100))
            raise RuntimeError('getter failure')
    assert state.owner.options == state.owner.original_options and state.restored()


@pytest.mark.parametrize('fault', ['temporary_wrong', 'unrelated_option', 'temporary_nonzero', 'temporary_none'])
def test_nonzero_or_inexact_temporary_state_never_reads_and_restores(state, fault):
    state.owner.fault = fault
    read = []
    with pytest.raises(EtabsStateVerificationError):
        with state.transaction:
            state.select()
            state.transaction.select_modal_modes((1, 100))
            read.append(True)
    assert not read and state.restored()
    assert state.owner.options == state.owner.original_options


@pytest.mark.parametrize('fault', ['malformed', 'snapshot_nonzero'])
def test_unknown_native_option_abi_never_mutates_modes(state, fault):
    state.owner.fault = fault
    with pytest.raises(EtabsCapabilityError):
        with state.transaction:
            state.select()
            state.transaction.select_modal_modes((1, 100))
    assert not state.owner.writes and state.restored()


@pytest.mark.parametrize('fault', ['restore_nonzero', 'restore_wrong'])
def test_failed_mode_restore_is_hard_failure_but_selection_restore_is_still_attempted(state, fault):
    state.owner.fault = fault
    with pytest.raises(EtabsStateRestoreError) as caught:
        with state.transaction:
            state.select()
            state.transaction.select_modal_modes((1, 100))
            raise RuntimeError('physical read failed')
    assert state.restored()
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert any(x['phase'] == 'modal_output_restore_verify' and x['success'] is False
               for x in caught.value.details['state_diagnostics'])


@pytest.mark.parametrize('mode_range', [(0, 100), (1, 0), (100, 1), (True, 100), [1, 100], (1, 100, 101)])
def test_invalid_range_never_runs_native_temporary_set(state, mode_range):
    with pytest.raises(ValueError):
        with state.transaction:
            state.select()
            state.transaction.select_modal_modes(mode_range)
    assert state.restored() and state.owner.options == state.owner.original_options
    assert len(state.owner.writes) == 1  # safe exact restoration only


@pytest.mark.parametrize('reader', ['FrameForce', 'JointDispl'])
def test_existing_native_result_readers_use_range_and_return_restored_diagnostics(monkeypatch, reader):
    import tbdy_engine.etabs.oapi.eq713_response_results as frame
    import tbdy_engine.etabs.oapi.joint_displacement_results as joint
    setup = NativeSetup()
    sap = FakeSap()
    calls = []
    def force(name, item_type):
        assert setup.options == (1, 100, False)
        calls.append((name, item_type))
        return (100, ['C1']*100, [0.]*100, ['E1']*100, [0.]*100, ['MODAL']*100,
                ['Mode']*100, list(range(1, 101)), *([[-1.]*100]*6), 0)
    def displacement(name, item_type):
        assert setup.options == (1, 100, False)
        calls.append((name, item_type))
        return (100, ['P1']*100, ['E1']*100, ['MODAL']*100, ['Mode']*100,
                list(range(1, 101)), *([[0.001]*100]*6), 0)
    sap.Results = NS(Setup=setup, FrameForce=force, JointDispl=displacement)
    sap.LoadCases = FakeNameList(['DEAD', 'MODAL'])
    sap.RespCombo = FakeNameList(['COMB'])
    execute = lambda session, fn, **kwargs: fn(None, sap)
    monkeypatch.setattr(frame, '_execute_verified_read', execute)
    monkeypatch.setattr(joint, '_execute_verified_read', execute)
    monkeypatch.setattr(joint, 'EtabsVerifiedSession', NS)
    if reader == 'FrameForce':
        fact = frame.read_frame_force_response_from_session(NS(), frame_name='C1', case_name='MODAL', modal_mode_range=(1, 100))
    else:
        fact = joint.read_joint_displ_from_session(NS(), point_object='P1', output_name='MODAL', output_kind='case', modal_mode_range=(1, 100))
    assert len(fact.rows) == 100 and len(calls) == 1
    assert setup.options == setup.original_options
    assert any(x['phase'] == 'modal_output_restore_verify' and x['success'] is True for x in fact.state_diagnostics)


def test_existing_table_reader_sets_100_modes_for_read_then_restores_every_option():
    from tbdy_engine.etabs.oapi.database_tables import fetch_display_table_for_output
    owner = NativeTables()
    native_read = owner.GetTableForDisplayArray
    def read(*args):
        assert owner.options[4:7] == (False, 1, 100)
        return native_read(*args)
    owner.GetTableForDisplayArray = read
    fact = fetch_display_table_for_output(owner, 'Story Forces', preferred_output_case='MODAL', modal_mode_range=(1, 100))
    assert owner.options == owner.original_options
    assert owner.cases == ['OLD_CASE'] and owner.combos == ['OLD_COMBO']
    assert any(x['phase'] == 'temporary_modal_modes' and x['success'] is True for x in fact.state_diagnostics)
    assert any(x['phase'] == 'modal_output_restore_verify' and x['success'] is True for x in fact.state_diagnostics)


def test_missing_native_mode_getter_fails_before_mode_change_restoring_selection(state):
    setattr(state.owner, 'GetOutputOptionsForDisplay' if state.owner.table else 'GetOptionModeShape', None)
    with pytest.raises(EtabsCapabilityError):
        with state.transaction:
            state.select()
            state.transaction.select_modal_modes((1, 100))
    assert not state.owner.writes and state.restored()
