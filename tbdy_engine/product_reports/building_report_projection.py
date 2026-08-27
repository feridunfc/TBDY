"""Canonical render-neutral Engineering/Audit projections for Unified Engineering Review.

The projection consumes one already-valid BuildingReportModel and owns no
engineering, regulatory, closure, governing-selection, or compliance authority.
UR-2 adds presentation-read-model metadata only where every value is either:

* copied exactly from canonical upstream data, or
* a deterministic presentation label/group for an exact canonical token, or
* an explicit REPORT_INPUT_GAP describing information the canonical reporting
  contract does not currently carry.

No renderer-facing field in this module calculates an engineering result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import json

from tbdy_engine.coverage.project_reconciliation import ReportContributionRef
from tbdy_engine.product_reports.unified_building_report import BuildingReportModel
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus


class ReportView(StrEnum):
    """Canonical report views."""

    ENGINEERING = "ENGINEERING"
    AUDIT = "AUDIT"


class ReportProjectionIntegrityError(ValueError):
    """Raised when a canonical view cannot preserve BuildingReportModel integrity."""


_COVERAGE_LABELS = {
    "expected_mandatory_instance_count": "Mandatory checks",
    "accounted_instance_count": "Accounted",
    "executed_result_count": "Evaluated",
    "proven_not_applicable_count": "Proven not applicable",
    "blocked_count": "Blocked",
    "no_data_count": "Missing data",
    "unresolved_count": "Unresolved",
    "silent_missing_count": "Silent missing",
    "duplicate_result_count": "Duplicate results",
    "missing_report_binding_count": "Missing report bindings",
    "orphan_report_binding_count": "Orphan report bindings",
    "mandatory_closure_complete": "Mandatory closure complete",
    "population_reconciled": "Population reconciled",
    "report_reconciled": "Report reconciled",
}

_ATTENTION_STATUSES = frozenset(
    {
        "FAIL",
        "BLOCKED",
        "NO_DATA",
        "PARTIAL",
        "NOT_EVALUATED",
        "REANALYSIS_REQUIRED",
    }
)

# Presentation grouping is intentionally exact-token-only. Unknown component
# types remain visible in the appendix population and are never guessed from
# title, slice_id, check id, or source text.
_DOMAIN_SPECS = (
    (
        "model-inventory",
        "Model inventory",
        ("MODEL_INVENTORY",),
        "Canonical inventory contributions.",
    ),
    (
        "loads-mass-cases",
        "Loads / mass / cases / design combinations",
        ("LOADS_AND_MASS", "LOAD_CASE", "DESIGN_COMBINATION"),
        "Canonical load, mass-source, case, and combination contributions.",
    ),
    (
        "global-analysis",
        "Global analysis",
        ("GLOBAL_ANALYSIS",),
        "Canonical modal, base-reaction, drift, irregularity, and related global-analysis contributions.",
    ),
    (
        "structural-system",
        "Structural-system qualification",
        ("STRUCTURAL_SYSTEM",),
        "Canonical structural-system qualification contributions.",
    ),
    (
        "beams",
        "Beams",
        ("BEAM",),
        "Canonical beam contributions.",
    ),
    (
        "columns",
        "Columns",
        ("COLUMN",),
        "Canonical column contributions.",
    ),
    (
        "scwb-joints",
        "SCWB / joints",
        ("SCWB_JOINT", "JOINT"),
        "Canonical joint and SCWB contributions.",
    ),
    (
        "walls",
        "Walls",
        ("WALL",),
        "Canonical wall contributions.",
    ),
    (
        "slab-diaphragm",
        "Slab / diaphragm",
        ("SLAB", "DIAPHRAGM", "SLAB_DIAPHRAGM"),
        "Canonical slab and diaphragm contributions.",
    ),
    (
        "foundation-geotechnical",
        "Foundation / geotechnical",
        ("FOUNDATION", "GEOTECHNICAL"),
        "Canonical foundation and geotechnical contributions.",
    ),
)


def _analysis_basis_row(item: object) -> dict[str, str]:
    """Copy one typed AnalysisBasisRef without interpreting its state."""

    return {
        "instance_id": item.instance_id.value,  # type: ignore[attr-defined]
        "status": item.status.value,  # type: ignore[attr-defined]
        "source_ref": item.source_ref,  # type: ignore[attr-defined]
    }


def _sorted_contributions(model: BuildingReportModel):
    return tuple(
        sorted(
            model.contributions,
            key=lambda item: ReportContributionRef.from_contribution(item).sort_key,
        )
    )


def _coverage_summary(model: BuildingReportModel) -> dict[str, object]:
    """Copy the existing FCR summary exactly; do not derive compliance metrics."""

    payload = model.reconciliation.as_dict()
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ReportProjectionIntegrityError("canonical FCR summary is missing or invalid")
    return dict(summary)


def _coverage_display(summary: dict[str, object]) -> list[dict[str, object]]:
    """Attach presentation labels while copying canonical values exactly."""

    result: list[dict[str, object]] = []
    for key in _COVERAGE_LABELS:
        if key in summary:
            result.append(
                {
                    "canonical_key": key,
                    "label": _COVERAGE_LABELS[key],
                    "value": summary[key],
                }
            )
    for key in sorted(set(summary) - set(_COVERAGE_LABELS)):
        result.append(
            {
                "canonical_key": key,
                "label": "Additional canonical coverage metric",
                "value": summary[key],
            }
        )
    return result


def _analysis_basis_summary(model: BuildingReportModel) -> dict[str, object]:
    """Expose exact FCR analysis-basis accounting needed for dashboard warnings."""

    instance_ids = tuple(
        sorted(item.value for item in model.reconciliation.reanalysis_required_instance_ids)
    )
    return {
        "reanalysis_required_count": len(instance_ids),
        "reanalysis_required_instance_ids": list(instance_ids),
    }


def _binding_sources_by_contribution(model: BuildingReportModel) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for binding in model.report_bindings:
        grouped.setdefault(binding.contribution_ref.value, []).append(binding.source_ref)
    return {key: tuple(sorted(values)) for key, values in grouped.items()}


def _projected_contributions(model: BuildingReportModel) -> list[dict[str, object]]:
    """Copy contribution content and attach exact canonical drill-down identity."""

    binding_sources = _binding_sources_by_contribution(model)
    projected: list[dict[str, object]] = []
    for contribution in _sorted_contributions(model):
        contribution_ref = ReportContributionRef.from_contribution(contribution)
        source_refs = binding_sources.get(contribution_ref.value)
        if not source_refs:
            raise ReportProjectionIntegrityError(
                "canonical contribution has no report binding source identity: "
                + contribution_ref.value
            )
        payload = contribution.as_dict()
        payload["contribution_ref"] = contribution_ref.value
        payload["report_source_refs"] = list(source_refs)
        projected.append(payload)
    return projected


def _status_facets(model: BuildingReportModel) -> list[dict[str, object]]:
    """Count exact contribution statuses; never collapse, rank, or reinterpret them."""

    counts: dict[str, int] = {}
    for contribution in model.contributions:
        counts[contribution.status] = counts.get(contribution.status, 0) + 1
    return [
       {"status": status, "count": counts[status]}
       for status in sorted(counts)
    ]


def _kind_facets(model: BuildingReportModel) -> list[dict[str, object]]:
    """Count exact canonical contribution kinds only."""

    counts: dict[str, int] = {}
    for contribution in model.contributions:
        counts[contribution.contribution_kind] = (
            counts.get(contribution.contribution_kind, 0) + 1
        )
    return [
        {"contribution_kind": kind, "count": counts[kind]}
        for kind in sorted(counts)
    ]


def _component_facets(model: BuildingReportModel) -> list[dict[str, object]]:
    """Group by exact component_type/component_id, preserving project-level None."""

    grouped: dict[tuple[str | None, str | None], list[str]] = {}
    for contribution in model.contributions:
        key = (contribution.component_type, contribution.component_id)
        grouped.setdefault(key, []).append(
            ReportContributionRef.from_contribution(contribution).value
        )

    def sort_key(item: tuple[tuple[str | None, str | None], list[str]]):
        (component_type, component_id), _ = item
        return (
            component_type is None,
            component_type or "",
            component_id is None,
            component_id or "",
        )

    return [
        {
            "component_type": component_type,
            "component_id": component_id,
            "contribution_count": len(refs),
            "contribution_refs": sorted(refs),
        }
        for (component_type, component_id), refs in sorted(
            grouped.items(), key=sort_key
        )
    ]


def _attention_items(
    contributions: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Expose exact attention-state contributions without assigning severity."""

    rows: list[dict[str, object]] = []
    for item in contributions:
        status = item.get("status")
        if status not in _ATTENTION_STATUSES:
            continue
        rows.append(
            {
                "contribution_ref": item["contribution_ref"],
                "title": item.get("title"),
                "status": status,
                "component_type": item.get("component_type"),
                "component_id": item.get("component_id"),
                "warnings": list(item.get("warnings", []))
                if isinstance(item.get("warnings"), list)
                else [],
            }
        )
    return rows


def _presentation_domains(
    contributions: list[dict[str, object]],
J  -> list[dict[str, object]]:
    """Group exact canonical component_type tokens for presentation only."""

    token_to_domain: dict[str, str] = {}
    for domain_id, _, tokens, _ in _DOMAIN_SPECS:
        for token in tokens:
            token_to_domain[token] = domain_id

    grouped: dict[str, list[str]] = {
        domain_id: [] for domain_id, _, _, _ in _DOMAIN_SPECS
    }
    grouped["appendices"] = []

    for item in contributions:
        ref = str(item["contribution_ref"])
        component_type = item.get("component_type")
        domain_id = (
            token_to_domain.get(component_type, "appendices")
            if isinstance(component_type, str)
            else "appendices"
        )
        grouped[domain_id].append(ref)

    result = [
        {
            "domain_id": domain_id,
            "label": label,
            "canonical_component_types": list(tokens),
            "description": description,
            "contribution_refs": grouped[domain_id],
            "contribution_count": len(grouped[domain_id]),
        }
        for domain_id, label, tokens, description in _DOMAIN_SPECS
    ]
    result.append(
        {
            "domain_id": "appendices",
            "label": "Appendices / complete detailed populations",
            "canonical_component_types": [],
            "description": (
                "Canonical contributions without an exact supported presentation-domain "
                "component_type token. No domain is inferred from names or identifiers."
            ),
            "contribution_refs": grouped["appendices"],
            "contribution_count": len(grouped["appendices"]),
        }
    )
    return result


def _basis_value(model: BuildingReportModel, key: str) -> object:
    for entry in model.project_basis.entries:
        if entry.key == key:
            return entry.value
    return None


def _report_context(model: BuildingReportModel) -> dict[str, object]:
    """Copy explicit report context when the canonical basis carries it."""

    return {
        "data_classification": _basis_value(model, "report_data_classification"),
        "report_phase": _basis_value(model, "report_phase"),
    }


def _action_register(model: BuildingReportModel) -> dict[str, list[object]]:
    """Copy action-reconciliation identifiers only; never synthesize remediation."""

    reconciliation = model.reconciliation.as_dict()
    keys = (
        "required_action_finding_ids",
        "missing_action_finding_ids",
        "duplicate_action_finding_ids",
        "orphan_action_binding_finding_ids",
    )
    result: dict[str, list[object]] = {}
    for key in keys:
        value = reconciliation.get(key)
        result[key] = list(value) if isinstance(value, list) else []
    return result


def _report_input_gaps() -> list[dict[str, str]]:
    """Declare presentation inputs absent from the current canonical contract."""

    return [
        {
            "gap_id": "PROJECT_IDENTITY_DETAIL",
            "status": "REPORT_INPUT_GAP",
            "needed_for": "Professional cover / project identity",
            "detail": (
                "BuildingReportModel has project_id/title and ProjectBasisLedger, but no "
                "typed client, address, engineer, revision, or issue metadata contract."
            ),
        },
        {
            "gap_id": "EXPLICIT_ENGINEERING_DOMAIN",
            "status": "REPORT_INPUT_GAP",
            "needed_for": "Stable engineering-domain navigation",
            "detail": (
                "SliceReportContribution has no first-class engineering_domain field. "
                "UR-2 groups only exact component_type tokens and leaves unknown tokens "
                "in appendices without fuzzy inference."
            ),
        },
        {
            "gap_id": "TYPED_RESULT_CONTEXT",
            "status": "REPORT_INPUT_GAP",
            "needed_for": "Story / direction / case-combo / demand-capacity summary",
            "detail": (
                "Story, direction, case/combo, demand, capacity, and ratio are not "
                "first-class typed contribution slots; they may exist only as canonical "
                "ReportField/ReportTable data and are rendered without reinterpretation."
            ),
        },
        {
            "gap_id": "ACTION_REMEDIATION_RECORDS",
            "status": "REPORT_INPUT_GAP",
            "needed_for": "Required actions / remediation register",
            "detail": (
                "Canonical reconciliation can expose action finding identities, but the "
                "report contract does not yet carry structured remediation text, owner, "
                "required input, closure state, or reanalysis flag."
            ),
        },
        {
            "gap_id": "MODEL_EPOCH_TOP_LEVEL",
            "status": "REPORT_INPUT_GAP",
            "needed_for": "Cover-level model / evidence epoch identity",
            "detail": (
                "BuildingReportModel has SourceManifest provenance but no typed top-level "
                "model fingerprint / EvidenceEpoch presentation field."
            ),
        },
    ]


def _validate_view_accounting(model: BuildingReportModel, view: ReportView) -> None:
    """Fail closed if canonical view metadata would hide a bound contribution."""

    missing: list[str] = []
    for contribution in model.contributions:
        if view.value not in contribution.render_views:
            missing.append(ReportContributionRef.from_contribution(contribution).value)
    if missing:
        raise ReportProjectionIntegrityError(
            f"mandatory bound contribution excludes canonical {view.value} view: "
            + ", ".join(sorted(missing))
        )


def _presentation_contract() -> dict[str, object]:
    return {
        "projection_only": True,
        "renderer_neutral": True,
        "engineering_recalculation_allowed": False,
        "status_reinterpretation_allowed": False,
        "governing_selection_change_allowed": False,
        "global_compliance_verdict_emitted": False,
        "compliance_percentage_emitted": False,
        "remediation_synthesis_allowed": False,
        "fuzzy_domain_inference_allowed": False,
    }


@dataclass(frozen=True, slots=True)
class BuildingReportProjection:
    """Immutable deterministic projection of one canonical BuildingReportModel."""

    view: ReportView
    _model: BuildingReportModel = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.view, ReportView):
            raise TypeError("view must be ReportView")
        if not isinstance(self._model, BuildingReportModel):
            raise TypeError("_model must be BuildingReportModel")
        _validate_view_accounting(self._model, self.view)

    @property
    def report_id(self) -> str:
        return self._model.report_id

    @property
    def project_id(self) -> str:
        return self._model.project_id

    @property
    def report_integrity_status(self) -> str:
        return self._model.report_integrity_status

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema_version": "building_report_projection.ur_2.v2",
            "artifact_type": "BUILDING_REPORT_PROJECTION",
            "view": self.view.value,
            "report_id": self._model.report_id,
            "project_id": self._model.project_id,
            "title": self._model.title,
            "report_integrity_status": self._model.report_integrity_status,
        }

    def as_dict(self) -> dict[str, object]:
        basis_refs = tuple(
            sorted(
                self._model.reconciliation.analysis_basis_refs,
                key=lambda item: item.instance_id.value,
            )
        )
        contributions = _projected_contributions(self._model)
        coverage_summary = _coverage_summary(self._model)
        common: dict[str, object] = {
            "project_basis": self._model.project_basis.as_dict(),
            "coverage_summary": coverage_summary,
            "coverage_display": _coverage_display(coverage_summary),
            "analysis_basis_summary": _analysis_basis_summary(self._model),
            "status_facets": _status_facets(self._model),
            "contribution_kind_facets": _kind_facets(self._model),
            "component_facets": _component_facets(self._model),
            "contributions": contributions,
            "attention_items": _attention_items(contributions),
            "presentation_domains": _presentation_domains(contributions),
            "report_context": _report_context(self._model),
            "action_register": _action_register(self._model),
            "report_input_gaps": _report_input_gaps(),
            "presentation_contract": _presentation_contract(),
        }

        payload = self._identity_dict()
        payload.update(common)

        if self.view is ReportView.ENGINEERING:
            payload["analysis_basis_warnings"] = [
                _analysis_basis_row(item)
                for item in basis_refs
                if item.status is not AnalysisBasisStatus.MATCH
            ]
            return payload

        if self.view is ReportView.AUDIT:
            payload["coverage_reconciliation"] = self._model.reconciliation.as_dict()
            payload["analysis_basis_refs"] = [
                _analysis_basis_row(item) for item in basis_refs
            ]
            payload["report_bindings"] = [
                {
                    "source_ref": item.source_ref,
                    "contribution_ref": item.contribution_ref.value,
                }
                for item in self._model.report_bindings
            ]
            payload["source_manifest"] = self._model.source_manifest.as_dict()
            return payload

        raise ReportProjectionIntegrityError(
            f"unsupported report view: {self.view!r}"
        )

    def to_json(self) -> str:
        return json.dumps(
            self.as_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"


def project_building_report_view(
    model: BuildingReportModel,
    view: ReportView,
) -> BuildingReportProjection:
    """Project one canonical BuildingReportModel into ENGINEERING or AUDIT."""

    if not isinstance(model, BuildingReportModel):
        raise TypeError("model must be BuildingReportModel")
    if not isinstance(view, ReportView):
        raise ReportProjectionIntegrityError(
            "supports only ReportView.ENGINEERING and ReportView.AUDIT"
        )
    return BuildingReportProjection(view=view, _model=model)


__all__ = [
    "BuildingReportProjection",
    "ReportProjectionIntegrityError",
    "ReportView",
    "project_building_report_view",
]
