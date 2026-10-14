"""Read-only application handoff of canonical Column owner results.

The host supplies ORIGINAL in-process ProjectExecutionArtifact objects and an
independently expected scope. No deserializer, issuer, native lifecycle or
engineering calculation is exposed here. HTTP clients only select a handle.
Test transport may produce these objects in tests, never in this module.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from collections.abc import Mapping
import json
import math
from uuid import uuid4

from tbdy_engine.application.project_execution import ProjectExecutionArtifact
from tbdy_engine.design.columns.column_combo_eligibility_projection import ComponentReadinessBinding
from tbdy_engine.design.columns.column_longitudinal_causal_provenance import (
    resolve_qualified_b6_design_refs, require_engine_selected_rebar_design_refs,
)
from tbdy_engine.integration.etabs_design_lineage import DesignLineageQualification
from tbdy_engine.integration.etabs_analysis_lineage import AnalysisLineageQualification
from tbdy_engine.regulatory.fnd_col_2_program import READINESS_KEY
from tbdy_engine.features.column_shear_demand_evidence import build_column_shear_demand_evidence
from tbdy_engine.design.columns.column_design_result_projection import project_factual_design_results_to_component


def exact_data(value):
    """Lossless decimal/text projection of existing public typed output only."""
    if value is None or type(value) in {str, int, bool}:
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        if not value.is_finite(): raise ValueError('Nonfinite owner Decimal.')
        return str(value)
    if type(value) is float:
        if not math.isfinite(value): raise ValueError('Nonfinite owner float.')
        return value
    if hasattr(value, 'as_dict'):
        return exact_data(value.as_dict())
    if is_dataclass(value):
        return {f.name: exact_data(getattr(value, f.name)) for f in fields(value) if not f.name.startswith('_')}
    if isinstance(value, Mapping):
        return {str(k): exact_data(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [exact_data(v) for v in value]
    raise TypeError('Unsupported owner output type: '+type(value).__name__)


def fingerprint(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class QualifiedColumnScope:
    source_model_ref: str
    model_fingerprint: str
    evidence_epoch_id: str
    force_unit: str
    length_unit: str
    shear_evidence_epoch_id: str
    origin: str

    def __post_init__(self):
        if any(type(getattr(self, f.name)) is not str or not getattr(self, f.name).strip() for f in fields(self)):
            raise ValueError('Exact host-owned scope required.')
        if self.origin not in {'QUALIFIED_APPLICATION', 'OFFLINE_TEST_LIFECYCLE'}:
            raise ValueError('Unknown publication origin.')


def _require(test, message):
    if not test: raise ValueError(message)


def validate_owner_project(project, scope):
    _require(type(project) is ProjectExecutionArtifact, 'Original typed project required; serialized authority rejected.')
    _require(type(scope) is QualifiedColumnScope, 'Independent host scope required.')
    _require(project.building_report_model is not None and project.column_denominator is not None,
             'Canonical coverage/report owner artifacts required.')
    _require(bool(project.columns), 'Empty canonical Column population.')
    ids = [c.component_id for c in project.columns]
    _require(len(ids) == len(set(ids)), 'Ambiguous component population.')
    # A B6-qualified sibling may retain a genuinely unresolved component. Never
    # broadcast its engineering readiness or selected cage to that component.
    lineages = []
    for c in project.columns:
        _require((c.model_fingerprint, c.evidence_epoch_id) == (scope.model_fingerprint, scope.evidence_epoch_id), 'Column source/epoch drift.')
        binding = c.readiness_binding
        _require(type(binding) is ComponentReadinessBinding and c.fnd_col_2_execution is not None, 'Original FND2 binding required.')
        _require(binding.readiness is c.fnd_col_2_execution.readiness and binding.component_id == c.component_id,
                 'Readiness object/owner continuity lost.')
        _require((binding.model_fingerprint, binding.evidence_epoch_id) == (scope.model_fingerprint, scope.evidence_epoch_id), 'Readiness epoch drift.')
        if c.a23_demand_states:
            _require(exact_data(c.a23_demand_states) == exact_data(binding.readiness.demand_states), 'A23/readiness demand-state continuity lost.')
        else:
            # An actual A18/A19-blocked component exits before retaining A23.
            # FND2's retained candidate states must not be promoted past it.
            _require(c.controlled_design_result is None and c.selected_rebar is None,
                     'B6/selection without retained qualified A23 states.')
        execution = c.fnd_col_2_execution
        _require(len(execution.readiness_records) == 1, 'Ambiguous readiness execution.')
        record = execution.readiness_records[0]
        quantities = [q for q in execution.snapshot.quantities_for(record.readiness_instance_ref) if q.quantity_key == READINESS_KEY]
        _require(len(quantities) == 1, 'Unique canonical readiness quantity required.')
        q = quantities[0]
        _require(record.plan_identity == execution.snapshot.plan_identity and
                 record.readiness_instance_ref.scope_ref == c.component_id and q.scope_ref == c.component_id and
                 tuple(q.dependency_refs) == tuple(record.dependency_refs) and tuple(q.evidence_refs) == tuple(record.evidence_refs) and
                 q.value.get('status') == binding.readiness.status and tuple(q.provenance[2:]) == tuple(binding.readiness.source_refs),
                 'FND2 snapshot/typed readiness causal binding lost.')
        if c.column_shear_evidence is not None:
            e = c.column_shear_evidence
            # P7 owns a CONTENT-derived force-bundle epoch, distinct from the
            # project EvidenceEpoch. Do not silently equate these contracts.
            _require((e.model_fingerprint, e.evidence_epoch_id, e.force_unit.identifier, e.length_unit.identifier) ==
                     (scope.model_fingerprint, scope.shear_evidence_epoch_id, scope.force_unit, scope.length_unit), 'Result units/source/epoch drift.')
            _require(bool(e.unit_provenance_refs), 'Unit provenance missing.')
            derived = build_column_shear_demand_evidence(model_fingerprint=e.model_fingerprint, rows=e.rows,
                output_names=e.output_names, force_unit=e.force_unit, length_unit=e.length_unit, unit_provenance_refs=e.unit_provenance_refs)
            _require(derived.evidence_epoch_id == e.evidence_epoch_id, 'P7 content epoch drift.')
        if c.controlled_design_result is None:
            _require(c.selected_rebar is None and c.longitudinal_runtime is None, 'Unqualified selection cannot be published.')
            continue
        b6 = c.controlled_design_result
        lineage = b6.design_lineage
        _require(type(lineage) is DesignLineageQualification and lineage.qualified, 'Existing qualified B6 issuer required.')
        parent = lineage.parent_analysis_lineage
        _require(type(parent) is AnalysisLineageQualification and parent.qualified, 'Existing qualified B5 issuer required.')
        _require(lineage.source_model_ref == parent.source_model_ref == scope.source_model_ref, 'Lineage source drift.')
        if c.column_shear_evidence is not None:
            _require(parent.require_qualified_result().identity_ref in c.column_shear_evidence.unit_provenance_refs,
                     'P7/B5 analysis-result continuity lost.')
        _require(lineage.require_qualified_result() is b6.design_result_identity, 'B6 result object continuity lost.')
        _require(lineage.design_state is b6.design_state, 'B6 state object continuity lost.')
        _require((b6.design_state.model_fingerprint, b6.design_state.evidence_epoch_id) ==
                 (scope.model_fingerprint, scope.evidence_epoch_id), 'B6 epoch drift.')
        component_results = project_factual_design_results_to_component(b6.factual_design_results,
            component_id=c.component_id, design_result_identity_ref=b6.design_result_identity.identity_ref,
            design_lineage_qualification_ref=lineage.qualification_ref)
        refs = resolve_qualified_b6_design_refs(component_results)
        _require(refs.design_result_identity_ref == b6.design_result_identity.identity_ref and
                 refs.design_lineage_qualification_ref == lineage.qualification_ref, 'B6 factual provenance drift.')
        if c.longitudinal_selection is not None:
            require_engine_selected_rebar_design_refs(c.longitudinal_selection, b6=refs)
            _require(c.longitudinal_runtime is not None and c.longitudinal_runtime.selection is c.longitudinal_selection,
                     'Canonical selection/runtime continuity lost.')
            if c.selected_rebar is not None:
                _require(c.selected_rebar.material_context_ref == c.longitudinal_runtime.bound_design_basis.material_context.binding_ref,
                         'Selected PMM material context drift.')
        lineages.append(lineage)
    _require(bool(lineages), 'No original qualified B5/B6 application artifact; issuance dependency remains open.')
    for contribution in project.building_report_model.contributions:
        if contribution.component_id in ids:
            values = {f.key: f.value for f in contribution.summary_fields}
            if 'model_fingerprint' in values:
                _require(values['model_fingerprint'] == scope.model_fingerprint and values['evidence_epoch_id'] == scope.evidence_epoch_id,
                         'Coverage report scope drift.')


OWNER_OUTPUTS = (
    ('fnd_col_2_execution', 'FND_COL_2 source-bound executor'),
    ('a23_demand_states', 'column_a23_design_demands / second-order owners'),
    ('longitudinal_selection', 'column_longitudinal_runtime / canonical PMM-selection owners'),
    ('longitudinal_runtime', 'column_longitudinal_runtime / detailing owner'),
    ('column_axial_vs5', 'vs5_column_axial_program.run_vs5_column_axial'),
    ('column_shear_p7', 'column_p7_runtime / VS6 P7 owner'),
    ('column_shear_limited', 'limited-column shear owner'),
    ('transverse_confinement', 'column_transverse_confinement.evaluate_column_transverse_confinement'),
    ('final_transverse_cage', 'column_final_cage / column_vc_runtime'),
    ('free_length', 'TS500 regulatory free-length owner'),
)


def project_column_view(project, scope, component_id):
    """Consume owner results; no governing selection, force math or new status."""
    validate_owner_project(project, scope)
    matches = [c for c in project.columns if c.component_id == component_id]
    _require(len(matches) == 1, 'Exact component identity required.')
    c = matches[0]
    # Full owner payload is retained in JSON. PMM candidate internals can be
    # large; the screen/report consumes the canonical selected result, detailing
    # and exact demand states, not a freshly computed presentation approximation.
    outputs = {}
    for attr, owner in OWNER_OUTPUTS:
        obj = getattr(c, attr)
        if obj is None or obj == (): continue
        if hasattr(obj, 'component_id'):
            _require(obj.component_id == component_id, 'Cross-component owner artifact.')
        if attr == 'longitudinal_runtime':
            obj = {'target_topology': exact_data(obj.target_topology), 'bound_design_basis': exact_data(obj.bound_design_basis),
                   'rebar_intent': exact_data(obj.rebar_intent), 'detailing': exact_data(obj.detailing)}
        if attr == 'longitudinal_selection':
            s = c.longitudinal_selection
            selected_id = None if c.selected_rebar is None else c.selected_rebar.candidate_id
            adequacy = s.adequacy_population
            obj = {'status': s.status, 'blockers': s.blockers, 'selection_contract': exact_data(s.selection_contract),
                   'selected_rebar': exact_data(c.selected_rebar),
                   'selected_required_area_rows': [] if adequacy is None else [exact_data(r) for r in adequacy.required_area_rows if r.candidate_id == selected_id],
                   'selected_pmm_rows': [] if adequacy is None else [exact_data(r) for r in adequacy.pmm_rows if r.candidate_id == selected_id],
                   'selected_adequacy': [] if adequacy is None else [exact_data(r) for r in adequacy.candidate_assessments if r.candidate_id == selected_id]}
        data = exact_data(obj)
        outputs[attr] = {'owner': owner, 'artifact_sha256': fingerprint(data), 'data': data}
    contributions = [exact_data(x) for x in project.building_report_model.contributions if x.component_id == component_id]
    lineage = c.design_lineage
    scope_data = exact_data(scope)
    payload = {'schema': 'column.qualified.owner-result.v1', 'title': ('OFFLINE TEST LIFECYCLE / ' if scope.origin == 'OFFLINE_TEST_LIFECYCLE' else 'NİTELİKLİ UYGULAMA / ')+component_id,
        'scope_identity': scope_data, 'component_id': component_id, 'project_id': project.project_id,
        'application_status': c.status, 'application_blockers': list(c.blockers),
        'fnd2_status': c.readiness_binding.readiness.status,
        'project_status': project.status, 'population_state': project.population_state,
        'owner_outputs': outputs, 'canonical_contributions': contributions,
        'selected_rebar': exact_data(c.selected_rebar), 'demand_states': exact_data(c.a23_demand_states),
        'lineage': None if lineage is None else exact_data(lineage),
        'coverage': exact_data(project.column_denominator),
        'scope': ['Mevcut owner sonuçları iç uygulama nesnelerinden doğrulanarak tüketildi; bu ekranda native lifecycle çalıştırılmadı.',
                  'FND2 readiness, uygulama engelleri ve coverage kararları ayrı tutulur; tam tasarım onayı çıkarılmaz.',
                  'Offline test lifecycle gerçek B-BLOK/235 üretim kanıtı değildir. FC09 gate değişmedi.']}
    payload['result_id'] = 'column-owner-result:sha256:'+fingerprint(payload)
    return payload


class QualifiedColumnChannel:
    """In-process registry, intentionally no HTTP/JSON publication endpoint."""
    def __init__(self):
        self._entries = {}

    def publish(self, project, *, scope, label):
        validate_owner_project(project, scope)
        _require(type(label) is str and bool(label.strip()), 'Publication label required.')
        handles = []
        for c in project.columns:
            view = project_column_view(project, scope, c.component_id)
            handle = uuid4().hex
            self._entries[handle] = (project, scope, c.component_id, fingerprint(view), label)
            handles.append(handle)
        return tuple(handles)

    def catalog(self):
        return [{'handle': h, 'component_id': v[2], 'label': v[4], 'scope_identity': exact_data(v[1])} for h, v in self._entries.items()]

    def consume(self, request):
        _require(type(request) is dict and set(request) == {'handle', 'scope_identity'}, 'Only a qualified handle and exact scope may be selected.')
        _require(request['handle'] in self._entries, 'Unknown qualified artifact; no JSON authority import.')
        project, scope, component, expected_hash, _ = self._entries[request['handle']]
        _require(request['scope_identity'] == exact_data(scope), 'Source/epoch/units mismatch; old result invalidated.')
        result = project_column_view(project, scope, component)
        _require(fingerprint(result) == expected_hash, 'Original owner artifact changed after publication.')
        return result
