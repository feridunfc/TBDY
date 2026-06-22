"""Bounded C14.1-P1 check and candidate-result helpers."""
from __future__ import annotations
from collections.abc import Mapping, Sequence
from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.features.live_etabs_geometry_probe import LENGTH_TO_MM_FACTOR, LiveEtabsLengthUnitEvidence
from tbdy_engine.product._minimum_compliance_util import _feature_value, _feature_evidence, _text, _finite, _number
_CONNECTIVITY_TABLE = 'Beam Object Connectivity'
_OFFSET_TABLE = 'Frame Assignments - End Length Offsets'

def _column_derived_results(snapshot: Mapping[str, object]) -> tuple[CheckResult, CheckResult]:
    width = _feature_value(snapshot, 'column_width_mm')
    depth = _feature_value(snapshot, 'column_depth_mm')
    evidence = _feature_evidence(snapshot, 'column_width_mm') + _feature_evidence(snapshot, 'column_depth_mm')
    component = str(snapshot.get('component_id', ''))
    identity = snapshot.get('identity') if isinstance(snapshot.get('identity'), Mapping) else {}
    story, section = (_text(identity.get('story')) or None, _text(identity.get('section')) or None)
    if not _finite(width) or not _finite(depth) or float(width) <= 0 or (float(depth) <= 0):
        return (CheckResult(check_id='column_geometry_min_area', component=component, component_type='column', story=story, section=section, status=CheckStatus.NO_DATA, evidence=evidence, messages=('Resolved positive dimensions are required',), code_ref='TBDY 2018 7.3.1.1'), CheckResult(check_id='column_geometry_aspect_ratio', component=component, component_type='column', story=story, section=section, status=CheckStatus.NO_DATA, evidence=evidence, messages=('Resolved positive dimensions are required',), code_ref='TBDY 2018 7.3.1.2'))
    width_f, depth_f = (float(width), float(depth))
    area = width_f * depth_f
    aspect = min(width_f, depth_f) / max(width_f, depth_f)
    return (CheckResult(check_id='column_geometry_min_area', component=component, component_type='column', story=story, section=section, status=CheckStatus.OK if area >= 75000.0 else CheckStatus.FAIL, value=area, limit=75000.0, ratio=area / 75000.0, ratio_type='actual_over_minimum', pass_rule='actual_over_minimum', unit='mm2', evidence=evidence, messages=('C14.1-P1 locked column area check',), code_ref='TBDY 2018 7.3.1.1'), CheckResult(check_id='column_geometry_aspect_ratio', component=component, component_type='column', story=story, section=section, status=CheckStatus.OK if aspect >= 0.4 else CheckStatus.FAIL, value=aspect, limit=0.4, ratio=aspect / 0.4, ratio_type='actual_over_minimum', pass_rule='actual_over_minimum', unit='', evidence=evidence, messages=('C14.1-P1 locked column aspect-ratio check',), code_ref='TBDY 2018 7.3.1.2'))

def _evaluate_absolute_beam_depth(depth_mm: object, *, unit_supported: bool=True) -> str:
    if depth_mm is None:
        return 'NO_DATA'
    if not unit_supported or not _finite(depth_mm):
        return 'BLOCKED'
    return 'OK' if float(depth_mm) >= 300.0 else 'FAIL'

def _evaluate_depth_vs_slab(depth_mm: object, slab_mm: object, *, relationship_supported: bool) -> str:
    if not relationship_supported:
        return 'BLOCKED'
    if depth_mm is None or slab_mm is None:
        return 'NO_DATA'
    if not _finite(depth_mm) or not _finite(slab_mm):
        return 'BLOCKED'
    return 'OK' if float(depth_mm) >= 3.0 * float(slab_mm) else 'FAIL'

def _evaluate_web_detailing_trigger(depth_mm: object, clear_span_mm: object, *, semantics_locked: bool) -> str:
    if clear_span_mm is None or depth_mm is None:
        return 'NO_DATA'
    if not _finite(clear_span_mm) or not _finite(depth_mm) or float(clear_span_mm) <= 0:
        return 'BLOCKED'
    if not semantics_locked:
        return 'BLOCKED'
    return 'REQUIRED' if float(depth_mm) > float(clear_span_mm) / 4.0 else 'NOT_REQUIRED'

def _web_trigger_result(snapshot: Mapping[str, object], candidate: Mapping[str, object] | None, *, semantics_locked: bool) -> tuple[CheckResult, str]:
    depth = _feature_value(snapshot, 'beam_depth_mm')
    clear_span = candidate.get('candidate_clear_span_mm') if candidate else None
    result_status = _evaluate_web_detailing_trigger(depth, clear_span, semantics_locked=semantics_locked)
    canonical_status = CheckStatus.BLOCKED if result_status == 'BLOCKED' else CheckStatus.NO_DATA if result_status == 'NO_DATA' else CheckStatus.WARNING
    identity = snapshot.get('identity') if isinstance(snapshot.get('identity'), Mapping) else {}
    trigger_ratio = 4.0 * float(depth) / float(clear_span) if _finite(depth) and _finite(clear_span) and (float(clear_span) != 0) else None
    result = CheckResult(check_id='beam_web_reinforcement_detailing_trigger', component=str(snapshot.get('component_id', '')), component_type='beam', story=_text(identity.get('story')) or None, section=_text(identity.get('section')) or None, status=canonical_status, value=trigger_ratio, limit=1.0 if trigger_ratio is not None else None, ratio=trigger_ratio, ratio_type='value_over_limit' if result_status in {'REQUIRED', 'NOT_REQUIRED'} else None, pass_rule='detailing_trigger', unit='ratio', evidence=[candidate] if candidate else (), messages=(result_status,), code_ref='TBDY 2018 7.4.1.1(c)')
    return (result, result_status)

def _clear_span_candidate(component_id: str, connectivity: Mapping[object, Sequence[Mapping[str, object]]], offsets: Mapping[object, Sequence[Mapping[str, object]]], unit_evidence: object) -> Mapping[str, object] | None:
    length_rows, offset_rows = (connectivity.get(component_id, ()), offsets.get(component_id, ()))
    if len(length_rows) != 1 or len(offset_rows) != 1:
        return None
    length_raw = length_rows[0].get('Length')
    offset_i_raw, offset_j_raw = (offset_rows[0].get('OffsetI'), offset_rows[0].get('OffsetJ'))
    numbers = tuple((_number(value) for value in (length_raw, offset_i_raw, offset_j_raw)))
    if any((value is None for value in numbers)):
        return None
    length_value, offset_i_value, offset_j_value = numbers
    length_unit = unit_evidence.present_length_unit if isinstance(unit_evidence, LiveEtabsLengthUnitEvidence) else None
    factor = LENGTH_TO_MM_FACTOR.get(str(length_unit)) if length_unit is not None else None
    if factor is None:
        return {'status': 'BLOCKED', 'reason': 'Unsupported or missing length-unit evidence', 'length_raw': length_raw, 'offset_i_raw': offset_i_raw, 'offset_j_raw': offset_j_raw}
    centerline = float(length_value) * factor
    offset_i, offset_j = (float(offset_i_value) * factor, float(offset_j_value) * factor)
    candidate = centerline - offset_i - offset_j
    return {'status': 'PARTIAL', 'source_tables': [_CONNECTIVITY_TABLE, _OFFSET_TABLE], 'join_key': component_id, 'length_raw': length_raw, 'offset_i_raw': offset_i_raw, 'offset_j_raw': offset_j_raw, 'source_length_unit': length_unit, 'normalization_factor_to_mm': factor, 'centerline_length_mm': centerline, 'offset_i_mm': offset_i, 'offset_j_mm': offset_j, 'candidate_clear_span_mm': candidate, 'semantic_status': 'NOT_LOCKED'}

def _blocked_result(snapshot: Mapping[str, object], check_id: str, code: str, message: str, *, code_ref: str | None, value: object=None, limit: object=None, unit: str | None=None, evidence: Sequence[object]=()) -> CheckResult:
    identity = snapshot.get('identity') if isinstance(snapshot.get('identity'), Mapping) else {}
    return CheckResult(check_id=check_id, component=str(snapshot.get('component_id', '')), component_type=str(snapshot.get('component_type', '')), story=_text(identity.get('story')) or None, section=_text(identity.get('section')) or None, status=CheckStatus.BLOCKED, value=value, limit=limit, unit=unit, evaluation_level=EvaluationLevel.NO_DATA, evidence=evidence, messages=(f'{code}: {message}',), code_ref=code_ref)

def _copy_result(result: CheckResult, check_id: str, code_ref: str | None) -> CheckResult:
    return CheckResult(check_id=check_id, component=result.component, component_type=result.component_type, story=result.story, section=result.section, status=result.status, value=result.value, limit=result.limit, demand=result.demand, capacity=result.capacity, ratio=result.ratio, ratio_type=result.ratio_type, pass_rule=result.pass_rule, unit=result.unit, evaluation_level=result.evaluation_level, evidence=result.evidence, messages=result.messages, code_ref=code_ref, diagnostics=result.diagnostics)

def _record(result: CheckResult, *, result_status: str | None=None, candidate: Mapping[str, object] | None=None) -> dict[str, object]:
    payload = result.as_dict()
    payload['result_status'] = result_status or result.status.value
    if candidate is not None:
        payload['candidate_clear_span)] = dict(candidate)
    return payload
__all__ = ['_column_derived_results', '_evaluate_absolute_beam_depth', '_evaluate_depth_vs_slab', '_evaluate_web_detailing_trigger', '_web_trigger_result', '_clear_span_candidate', '_blocked_result', '_copy_result', '_record', '_feature_value', '_feature_evidence']
