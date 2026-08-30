"""Semantic factual ETABS concrete-column design-result acquisition for P8A.

The provider owns canonical component binding, source-unit conversion,
EvidenceEpoch/provenance, row identity, and full-population accounting. Exact
``DesignConcrete.GetSummaryResultsColumn`` invocation and 14-slot CSI ABI
validation are owned by ``tbdy_engine.etabs.oapi.concrete_design``.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Sequence

from tbdy_engine.etabs.oapi.concrete_design import (
    ConcreteColumnSummaryFact,
    decode_summary_results_column_response,
    read_summary_results_column,
)
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.safety import read_etabs_unit_snapshot
from tbdy_engine.etabs.source_units import (
    EtabsLengthUnit,
    EtabsSourceUnitError,
    convert_length,
    decode_csi_length_unit,
)
from tbdy_engine.features.column_concrete_design_evidence import (
    ColumnDesignResultIdentity,
    ColumnTopologyEvidenceEnvelope,
    ComponentBindingStatus,
    bind_column_design_result_identity,
)
from tbdy_engine.features.column_design_rebar_evidence import (
    FactualColumnDesignResultPopulation,
    FactualColumnDesignResultRow,
)
from tbdy_engine.providers.etabs_concrete_design_section_provider import (
    ConcreteColumnDesignSectionPopulation,
)

SOURCE_API = "DesignConcrete.GetSummaryResultsColumn"
SOURCE_ITEM_TYPE = "Objects(default)"
SOURCE_UNIT_API = "GetPresentUnits_2"

_RESULT_ARRAY_NAMES = (
    "FrameName", "MyOption", "Location", "PMMCombo", "PMMArea", "PMMRatio",
    "VMajorCombo", "AVMajor", "VMinorCombo", "AVMinor", "ErrorSummary", "WarningSummary",
)


class EtabsConcreteColumnDesignResultProviderError(RuntimeError):
    """Raised when exact factual design-result acquisition cannot close."""


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsConcreteColumnDesignResultProviderError(f"{label} must be an exact nonblank string")
    return value


def _optional_text(value: Any, label: str) -> str | None:
    if value in (None, ""):
        return None
    return _text(value, label)


def _int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise EtabsConcreteColumnDesignResultProviderError(f"{label} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise EtabsConcreteColumnDesignResultProviderError(f"{label} must be an integer") from exc
    if result != value and str(result) != str(value):
        raise EtabsConcreteColumnDesignResultProviderError(f"{label} must be an exact integer")
    return result


def _decimal(value: Any, label: str, *, nonnegative: bool = False) -> Decimal:
    if value is None or isinstance(value, bool):
        raise EtabsConcreteColumnDesignResultProviderError(f"{label} must be finite numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise EtabsConcreteColumnDesignResultProviderError(f"{label} must be finite numeric") from exc
    if not result.is_finite():
        raise EtabsConcreteColumnDesignResultProviderError(f"{label} must be finite numeric")
    if nonnegative and result < 0:
        raise EtabsConcreteColumnDesignResultProviderError(f"{label} must be >= 0")
    return Decimal(0) if result == 0 else result.normalize()


def _decimal_payload(value: Decimal) -> str:
    return format(value, "f")


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    refs = tuple(dict.fromkeys(_text(value, label) for value in values))
    if not refs:
        raise EtabsConcreteColumnDesignResultProviderError(f"{label} must be nonempty")
    return refs


def _snapshot_key(snapshot: Any) -> tuple[Any, ...]:
    return (
        getattr(snapshot, "present_units_api", None),
        getattr(snapshot, "database_units_api", None),
        getattr(snapshot, "present_units", None),
        getattr(snapshot, "database_units", None),
        getattr(snapshot, "present_force_unit", None),
        getattr(snapshot, "present_length_unit", None),
        getattr(snapshot, "present_temperature_unit", None),
        getattr(snapshot, "database_force_unit", None),
        getattr(snapshot, "database_length_unit", None),
        getattr(snapshot, "database_temperature_unit", None),
    )


def _source_row_id(*, frame_name: str, source_index: int, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {
            "source_api": SOURCE_API,
            "source_item_type": SOURCE_ITEM_TYPE,
            "frame_name": frame_name,
            "source_index": source_index,
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "column-design-result-row:sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class DecodedSummaryResultsColumn:
    reported_row_count: int
    rows: tuple[FactualColumnDesignResultRow, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.reported_row_count, bool)
            or not isinstance(self.reported_row_count, int)
            or self.reported_row_count < 0
        ):
            raise EtabsConcreteColumnDesignResultProviderError(
                "reported_row_count must be an integer >= 0"
            )
        rows = tuple(self.rows)
        if any(not isinstance(item, FactualColumnDesignResultRow) for item in rows):
            raise TypeError("rows must contain FactualColumnDesignResultRow")
        if len(rows) != self.reported_row_count:
            raise EtabsConcreteColumnDesignResultProviderError(
                "decoded result-row count does not equal NumberItems"
            )
        object.__setattr__(self, "rows", rows)


def _promote_summary_fact(
    fact: ConcreteColumnSummaryFact,
    *,
    component_id: str,
    unique_name: str,
    story: str,
    label: str,
    assigned_section: str,
    design_section: str,
    source_length_unit: EtabsLengthUnit,
    model_fingerprint: str,
    evidence_epoch_id: str,
    source_refs: Sequence[str],
) -> DecodedSummaryResultsColumn:
    component = _text(component_id, "component_id")
    frame_name = _text(unique_name, "unique_name")
    story_name = _text(story, "story")
    label_name = _text(label, "label")
    assigned = _text(assigned_section, "assigned_section")
    designed = _text(design_section, "design_section")
    model_ref = _text(model_fingerprint, "model_fingerprint")
    epoch_ref = _text(evidence_epoch_id, "evidence_epoch_id")
    refs = _refs(source_refs, "source_ref")
    source_length_unit = EtabsLengthUnit(source_length_unit)
    if fact.requested_frame_name != frame_name:
        raise EtabsConcreteColumnDesignResultProviderError(
            "OAPI summary fact does not match requested canonical UniqueName"
        )

    length_to_mm = convert_length(Decimal(1), source=source_length_unit, target=EtabsLengthUnit.MM)
    area_to_mm2 = length_to_mm * length_to_mm
    rows: list[FactualColumnDesignResultRow] = []
    for item in fact.rows:
        returned_frame = _text(item.frame_name, "FrameName")
        option = _int(item.my_option, "MyOption")
        if option not in (1, 2):
            raise EtabsConcreteColumnDesignResultProviderError("MyOption must be exact CSI Check=1 or Design=2")
        location_source = _decimal(item.location, "Location", nonnegative=True)
        pmm_area_source = _decimal(item.pmm_area, "PMMArea", nonnegative=True)
        pmm_ratio = _decimal(item.pmm_ratio, "PMMRatio")
        avmajor = _decimal(item.avmajor, "AVMajor")
        avminor = _decimal(item.avminor, "AVMinor")
        pmm_combo = _optional_text(item.pmm_combo, "PMMCombo")
        vmajor_combo = _optional_text(item.vmajor_combo, "VMajorCombo")
        vminor_combo = _optional_text(item.vminor_combo, "VMinorCombo")
        if not isinstance(item.error_summary, str) or not isinstance(item.warning_summary, str):
            raise EtabsConcreteColumnDesignResultProviderError(
                "ErrorSummary/WarningSummary must preserve exact CSI strings"
            )
        payload = {
            "FrameName": returned_frame,
            "MyOption": option,
            "Location": _decimal_payload(location_source),
            "PMMCombo": pmm_combo,
            "PMMArea": _decimal_payload(pmm_area_source),
            "PMMRatio": _decimal_payload(pmm_ratio),
            "VMajorCombo": vmajor_combo,
            "AVMajor": _decimal_payload(avmajor),
            "VMinorCombo": vminor_combo,
            "AVMinor": _decimal_payload(avminor),
            "ErrorSummary": item.error_summary,
            "WarningSummary": item.warning_summary,
            "source_length_unit": source_length_unit.value,
        }
        row_id = _source_row_id(frame_name=frame_name, source_index=item.source_index, payload=payload)
        row_ref = f"CSI:{SOURCE_API}:{frame_name}:row:{item.source_index}:{row_id}"
        rows.append(
            FactualColumnDesignResultRow(
                source_row_id=row_id,
                component_id=component,
                unique_name=frame_name,
                story=story_name,
                label=label_name,
                assigned_section=assigned,
                design_section=designed,
                my_option=option,
                pmm_combo=pmm_combo,
                location_mm=location_source * length_to_mm,
                pmm_area_mm2=pmm_area_source * area_to_mm2,
                error_summary=item.error_summary,
                warning_summary=item.warning_summary,
                model_fingerprint=model_ref,
                evidence_epoch_id=epoch_ref,
                source_refs=tuple(dict.fromkeys((*refs, row_ref))),
            )
        )
    return DecodedSummaryResultsColumn(fact.reported_row_count, tuple(rows))


def decode_summary_results_column(
    raw: Any,
    *,
    component_id: str,
    unique_name: str,
    story: str,
    label: str,
    assigned_section: str,
    design_section: str,
    source_length_unit: EtabsLengthUnit,
    model_fingerprint: str,
    evidence_epoch_id: str,
    source_refs: Sequence[str],
) -> DecodedSummaryResultsColumn:
    """Compatibility seam: delegate raw CSI ABI decoding to the OAPI owner."""
    frame_name = _text(unique_name, "unique_name")
    try:
        fact = decode_summary_results_column_response(raw, requested_frame_name=frame_name)
    except EtabsOAPIError as exc:
        raise EtabsConcreteColumnDesignResultProviderError(str(exc)) from exc
    return _promote_summary_fact(
        fact,
        component_id=component_id,
        unique_name=frame_name,
        story=story,
        label=label,
        assigned_section=assigned_section,
        design_section=design_section,
        source_length_unit=source_length_unit,
        model_fingerprint=model_fingerprint,
        evidence_epoch_id=evidence_epoch_id,
        source_refs=source_refs,
    )


def capture_concrete_column_design_results(
    sap_model: Any,
    *,
    topology: ColumnTopologyEvidenceEnvelope,
    design_sections: ConcreteColumnDesignSectionPopulation,
    session_provenance_ref: str,
) -> FactualColumnDesignResultPopulation:
    if not isinstance(topology, ColumnTopologyEvidenceEnvelope):
        raise TypeError("topology must be ColumnTopologyEvidenceEnvelope")
    if not isinstance(design_sections, ConcreteColumnDesignSectionPopulation):
        raise TypeError("design_sections must be ConcreteColumnDesignSectionPopulation")
    session_ref = _text(session_provenance_ref, "session_provenance_ref")
    if (
        design_sections.model_fingerprint != topology.model_fingerprint
        or design_sections.evidence_epoch_id != topology.evidence_epoch_id
    ):
        raise EtabsConcreteColumnDesignResultProviderError(
            "topology and design-section population must share model fingerprint/EvidenceEpoch"
        )

    columns = tuple(sorted(topology.topology.columns, key=lambda item: (item.component_id, item.unique_name)))
    expected_ids = tuple(item.component_id for item in columns)
    expected_names = tuple(item.unique_name for item in columns)
    if not expected_ids or len(expected_ids) != len(set(expected_ids)):
        raise EtabsConcreteColumnDesignResultProviderError(
            "canonical topology component population must be nonempty and unique"
        )
    if len(expected_names) != len(set(expected_names)):
        raise EtabsConcreteColumnDesignResultProviderError("canonical topology FrameName population must be unique")
    if (
        set(design_sections.expected_component_ids) != set(expected_ids)
        or set(design_sections.expected_frame_names) != set(expected_names)
    ):
        raise EtabsConcreteColumnDesignResultProviderError(
            "design-section population does not cover the exact canonical topology"
        )

    design_concrete = getattr(sap_model, "DesignConcrete", None)
    if design_concrete is None:
        raise EtabsConcreteColumnDesignResultProviderError(f"{SOURCE_API} is unavailable")
    before = read_etabs_unit_snapshot(sap_model)
    if getattr(before, "present_units_api", None) != SOURCE_UNIT_API:
        raise EtabsConcreteColumnDesignResultProviderError(
            f"{SOURCE_API} requires explicit {SOURCE_UNIT_API} source-unit provenance"
        )
    try:
        source_length_unit = decode_csi_length_unit(before.present_length_unit)
    except EtabsSourceUnitError as exc:
        raise EtabsConcreteColumnDesignResultProviderError(
            "design-result source length unit is unavailable/outside reviewed scope"
        ) from exc

    attempted_ids: list[str] = []
    captured_ids: list[str] = []
    all_rows: list[FactualColumnDesignResultRow] = []
    reported_total = 0
    population_refs: list[str] = [
        session_ref,
        *topology.source_refs,
        *design_sections.source_refs,
        f"CSI:{SOURCE_UNIT_API}:length={source_length_unit.value}",
    ]

    for column in columns:
        attempted_ids.append(column.component_id)
        section_row = design_sections.by_component_id(column.component_id)
        if (
            section_row.unique_name != column.unique_name
            or section_row.story != column.story
            or section_row.label != column.column_label
            or section_row.assigned_section != column.section
        ):
            raise EtabsConcreteColumnDesignResultProviderError(
                "design-section row does not bind to the same canonical topology identity"
            )
        request_ref = f"CSI:{SOURCE_API}:{SOURCE_ITEM_TYPE}:{column.unique_name}"
        result_identity = ColumnDesignResultIdentity(
            frame_name=column.unique_name,
            story=column.story,
            label=column.column_label,
            model_fingerprint=topology.model_fingerprint,
            evidence_epoch_id=topology.evidence_epoch_id,
            result_design_section=None,
            source_refs=(request_ref,),
        )
        binding = bind_column_design_result_identity(
            result=result_identity,
            topology=topology,
            design_section=section_row.design_section_evidence,
        )
        if binding.status is not ComponentBindingStatus.BOUND:
            raise EtabsConcreteColumnDesignResultProviderError(
                f"component identity binding blocked for {column.unique_name!r}: {binding.status.value}"
            )
        try:
            fact = read_summary_results_column(design_concrete, column.unique_name)
        except EtabsOAPIError as exc:
            raise EtabsConcreteColumnDesignResultProviderError(str(exc)) from exc
        decoded = _promote_summary_fact(
            fact,
            component_id=column.component_id,
            unique_name=column.unique_name,
            story=column.story,
            label=column.column_label,
            assigned_section=column.section,
            design_section=section_row.design_section,
            source_length_unit=source_length_unit,
            model_fingerprint=topology.model_fingerprint,
            evidence_epoch_id=topology.evidence_epoch_id,
            source_refs=tuple(dict.fromkeys((
                session_ref,
                *topology.source_refs,
                *section_row.source_refs,
                *binding.source_refs,
                request_ref,
            ))),
        )
        if decoded.reported_row_count == 0:
            raise EtabsConcreteColumnDesignResultProviderError(
                f"canonical column {column.unique_name!r} has no existing concrete-design result rows"
            )
        reported_total += decoded.reported_row_count
        all_rows.extend(decoded.rows)
        captured_ids.append(column.component_id)
        population_refs.extend(ref for row in decoded.rows for ref in row.source_refs)

    after = read_etabs_unit_snapshot(sap_model)
    if _snapshot_key(after) != _snapshot_key(before):
        raise EtabsConcreteColumnDesignResultProviderError(
            "ETABS unit provenance changed during design-result acquisition"
        )
    try:
        after_length_unit = decode_csi_length_unit(after.present_length_unit)
    except EtabsSourceUnitError as exc:
        raise EtabsConcreteColumnDesignResultProviderError(
            "post-capture source length unit is unavailable/outside reviewed scope"
        ) from exc
    if after_length_unit is not source_length_unit:
        raise EtabsConcreteColumnDesignResultProviderError(
            "source length unit changed during design-result acquisition"
        )

    population = FactualColumnDesignResultPopulation(
        model_fingerprint=topology.model_fingerprint,
        evidence_epoch_id=topology.evidence_epoch_id,
        expected_component_ids=expected_ids,
        attempted_component_ids=tuple(attempted_ids),
        captured_component_ids=tuple(captured_ids),
        reported_result_row_count=reported_total,
        rows=tuple(all_rows),
        source_refs=tuple(dict.fromkeys(population_refs)),
    )
    if not population.capture_complete:
        raise EtabsConcreteColumnDesignResultProviderError(
            "design-result population did not close exact full-capture accounting"
        )
    return population


__all__ = [
    "SOURCE_API",
    "SOURCE_ITEM_TYPE",
    "SOURCE_UNIT_API",
    "DecodedSummaryResultsColumn",
    "EtabsConcreteColumnDesignResultProviderError",
    "capture_concrete_column_design_results",
    "decode_summary_results_column",
]
