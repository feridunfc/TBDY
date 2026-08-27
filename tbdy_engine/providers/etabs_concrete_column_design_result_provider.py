"""Read-only factual ETABS concrete-column design-result acquisition for VS6-P8A.

This provider consumes only canonical F0 column topology/design-section owners and
reads already-existing ``DesignConcrete.GetSummaryResultsColumn`` results.  It
never starts design/analysis, mutates model state, invents component identity,
selects a governing row, or promotes a regulatory verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Sequence

from tbdy_engine.etabs.safety import read_etabs_unit_snapshot
from tbdy_engine.etabs.source_units import (
    EtabsLengthUnit,
    EtabsSourceUnitError,
    convert_length,
    decode_csi_length_unit,
)
from tbdy_engine.features.column_concrete_design_evidence import (
    ColumnDesignComponentBinding,
    ColumnDesignResultIdentity,
    ColumnTopologyEvidenceEnvelope,
    ComponentBindingStatus,
    bind_column_design_result_identity,
)
from tbdy_engine.providers.etabs_concrete_design_section_provider import (
    ConcreteColumnDesignSectionPopulation,
)


SOURCE_API = "DesignConcrete.GetSummaryResultsColumn"
SOURCE_ITEM_TYPE = "Objects(default)"
SOURCE_UNIT_API = "GetPresentUnits_2"
_RESULT_ARRAY_NAMES = (
    "FrameName",
    "MyOption",
    "Location",
    "PMMCombo",
    "PMMArea",
    "PMMRatio",
    "VMajorCombo",
    "AVMajor",
    "VMinorCombo",
    "AVMinor",
    "ErrorSummary",
    "WarningSummary",
)


class EtabsConcreteColumnDesignResultProviderError(RuntimeError):
    """Raised when the factual result population cannot be proven complete."""


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsConcreteColumnDesignResultProviderError(
            f"{label} must be an exact nonblank string"
        )
    return value


def _optional_text(value: Any, label: str) -> str | None:
    if value in (None, ""):
        return None
    return _text(value, label)


def _decimal(value: Any, label: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise EtabsConcreteColumnDesignResultProviderError(f"{label} must be finite")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise EtabsConcreteColumnDesignResultProviderError(f"{label} must be finite") from exc
    if not result.is_finite():
        raise EtabsConcreteColumnDesignResultProviderError(f"{label} must be finite")
    if result == 0:
        return Decimal(0)
    return result.normalize()


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


def _source_row_id(*, frame_name: str, source_index: int, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {
            "source_api": SOURCE_API,
            "item_type": SOURCE_ITEM_TYPE,
            "frame_name": frame_name,
            "source_index": source_index,
            "row": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "concrete-column-design-result-row:sha256:" + hashlib.sha256(encoded).hexdigest()


def _unit_snapshot_key(snapshot: Any) -> tuple[Any, ...]:
    return (
        snapshot.present_units_api,
        snapshot.present_units,
        snapshot.present_force_unit,
        snapshot.present_length_unit,
        snapshot.present_temperature_unit,
    )


def _decimal_payload(value: Decimal) -> str:
    return format(value, "f")


@dataclass(frozen=True, slots=True)
class ConcreteColumnDesignResultRow:
    """One untouched positional result row with exact source identity."""

    source_row_id: str
    source_index: int
    frame_name: str
    my_option: int
    location_source: Decimal
    pmm_combo: str | None
    pmm_area_source: Decimal
    pmm_ratio: Decimal
    vmajor_combo: str | None
    avmajor_source: Decimal
    vminor_combo: str | None
    avminor_source: Decimal
    error_summary: str
    warning_summary: str
    source_length_unit: EtabsLengthUnit
    source_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_row_id", _text(self.source_row_id, "source_row_id"))
        if isinstance(self.source_index, bool) or not isinstance(self.source_index, int) or self.source_index < 0:
            raise EtabsConcreteColumnDesignResultProviderError("source_index must be an integer >= 0")
        object.__setattr__(self, "frame_name", _text(self.frame_name, "FrameName"))
        if self.my_option not in (1, 2):
            raise EtabsConcreteColumnDesignResultProviderError("MyOption must be exact CSI Check=1 or Design=2")
        if self.location_source < 0:
            raise EtabsConcreteColumnDesignResultProviderError("Location must be >= 0")
        if self.pmm_area_source < 0:
            raise EtabsConcreteColumnDesignResultProviderError("PMMArea must be >= 0")
        object.__setattr__(self, "source_length_unit", EtabsLengthUnit(self.source_length_unit))
        object.__setattr__(self, "source_ref", _text(self.source_ref, "source_ref"))

    @property
    def is_design_row(self) -> bool:
        return self.my_option == 2

    @property
    def location_mm(self) -> Decimal:
        return convert_length(
            self.location_source,
            source=self.source_length_unit,
            target=EtabsLengthUnit.MM,
        )

    @property
    def pmm_area_mm2(self) -> Decimal:
        scale = convert_length(
            Decimal(1),
            source=self.source_length_unit,
            target=EtabsLengthUnit.MM,
        )
        return self.pmm_area_source * scale * scale


@dataclass(frozen=True, slots=True)
class CapturedConcreteColumnDesignResult:
    """Complete result rows for exactly one canonical strict-topology column."""

    component_id: str
    unique_name: str
    story: str
    label: str
    assigned_section: str
    design_section: str
    binding: ColumnDesignComponentBinding
    row_count_reported: int
    rows: tuple[ConcreteColumnDesignResultRow, ...]
    model_fingerprint: str
    evidence_epoch_id: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "component_id",
            "unique_name",
            "story",
            "label",
            "assigned_section",
            "design_section",
            "model_fingerprint",
            "evidence_epoch_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.binding, ColumnDesignComponentBinding) or not self.binding.bound:
            raise EtabsConcreteColumnDesignResultProviderError(
                "design-result component must carry an exact F0 BOUND identity"
            )
        if self.binding.component_id != self.component_id or self.binding.unique_name != self.unique_name:
            raise EtabsConcreteColumnDesignResultProviderError("component binding identity mismatch")
        rows = tuple(self.rows)
        if self.row_count_reported <= 0 or self.row_count_reported != len(rows):
            raise EtabsConcreteColumnDesignResultProviderError(
                "reported/captured design-result row counts must be equal and nonzero"
            )
        if any(row.frame_name != self.unique_name for row in rows):
            raise EtabsConcreteColumnDesignResultProviderError(
                "result FrameName must equal the exact requested canonical UniqueName"
            )
        indexes = tuple(row.source_index for row in rows)
        if indexes != tuple(range(self.row_count_reported)):
            raise EtabsConcreteColumnDesignResultProviderError(
                "result source indexes must preserve the complete API population"
            )
        row_ids = tuple(row.source_row_id for row in rows)
        if len(row_ids) != len(set(row_ids)):
            raise EtabsConcreteColumnDesignResultProviderError("result row identities must be unique")
        object.__setattr__(self, "rows", rows)
        refs = tuple(_text(ref, "source_ref") for ref in self.source_refs)
        if not refs or len(refs) != len(set(refs)):
            raise EtabsConcreteColumnDesignResultProviderError("source_refs must be nonempty and unique")
        object.__setattr__(self, "source_refs", refs)

    @property
    def design_rows(self) -> tuple[ConcreteColumnDesignResultRow, ...]:
        return tuple(row for row in self.rows if row.is_design_row)


@dataclass(frozen=True, slots=True)
class ConcreteColumnDesignResultPopulation:
    """Exact complete result population for all canonical columns in one epoch."""

    model_fingerprint: str
    evidence_epoch_id: str
    source_api: str
    source_item_type: str
    source_unit_api: str
    source_length_unit: EtabsLengthUnit
    expected_component_ids: tuple[str, ...]
    components: tuple[CapturedConcreteColumnDesignResult, ...]
    expected_component_count: int
    attempted_component_count: int
    captured_component_count: int
    reported_result_row_count: int
    captured_result_row_count: int
    session_provenance_ref: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        if self.source_api != SOURCE_API or self.source_item_type != SOURCE_ITEM_TYPE:
            raise EtabsConcreteColumnDesignResultProviderError("design-result source identity mismatch")
        if self.source_unit_api != SOURCE_UNIT_API:
            raise EtabsConcreteColumnDesignResultProviderError("design-result unit source must be GetPresentUnits_2")
        object.__setattr__(self, "source_length_unit", EtabsLengthUnit(self.source_length_unit))
        expected_ids = tuple(sorted(_text(item, "expected_component_id") for item in self.expected_component_ids))
        if not expected_ids or len(expected_ids) != len(set(expected_ids)):
            raise EtabsConcreteColumnDesignResultProviderError("expected component population must be nonempty and unique")
        object.__setattr__(self, "expected_component_ids", expected_ids)
        components = tuple(sorted(self.components, key=lambda item: item.component_id))
        component_ids = tuple(item.component_id for item in components)
        if component_ids != expected_ids:
            raise EtabsConcreteColumnDesignResultProviderError(
                "captured design-result population does not exactly cover canonical topology"
            )
        if any(
            item.model_fingerprint != self.model_fingerprint
            or item.evidence_epoch_id != self.evidence_epoch_id
            for item in components
        ):
            raise EtabsConcreteColumnDesignResultProviderError("component model/evidence epoch mismatch")
        object.__setattr__(self, "components", components)
        expected_count = len(expected_ids)
        if (
            self.expected_component_count != expected_count
            or self.attempted_component_count != expected_count
            or self.captured_component_count != expected_count
        ):
            raise EtabsConcreteColumnDesignResultProviderError("component population counters do not prove full capture")
        reported_rows = sum(item.row_count_reported for item in components)
        captured_rows = sum(len(item.rows) for item in components)
        if self.reported_result_row_count != reported_rows or self.captured_result_row_count != captured_rows:
            raise EtabsConcreteColumnDesignResultProviderError("result-row population counters do not reconcile")
        if reported_rows != captured_rows:
            raise EtabsConcreteColumnDesignResultProviderError("reported/captured result-row totals differ")
        object.__setattr__(self, "session_provenance_ref", _text(self.session_provenance_ref, "session_provenance_ref"))
        refs = tuple(_text(ref, "source_ref") for ref in self.source_refs)
        if not refs or len(refs) != len(set(refs)):
            raise EtabsConcreteColumnDesignResultProviderError("population source_refs must be nonempty and unique")
        object.__setattr__(self, "source_refs", refs)

    @property
    def capture_complete(self) -> bool:
        return (
            self.expected_component_count
            == self.attempted_component_count
            == self.captured_component_count
            == len(self.components)
            and self.reported_result_row_count == self.captured_result_row_count
        )

    @property
    def design_result_row_count(self) -> int:
        return sum(len(item.design_rows) for item in self.components)

    def by_component_id(self, component_id: str) -> CapturedConcreteColumnDesignResult:
        key = _text(component_id, "component_id")
        matches = tuple(item for item in self.components if item.component_id == key)
        if len(matches) != 1:
            raise KeyError(f"expected one design-result component_id={key}, got {len(matches)}")
        return matches[0]


def _parse_summary_results_column(raw: Any, *, requested_frame_name: str, source_length_unit: EtabsLengthUnit) -> tuple[int, tuple[ConcreteColumnDesignResultRow, ...]]:
    if not isinstance(raw, (tuple, list)) or len(raw) != 14:
        raise EtabsConcreteColumnDesignResultProviderError(
            "GetSummaryResultsColumn returned unsupported COM result shape; expected 14 values"
        )
    number_items = _int(raw[0], "NumberItems")
    if number_items <= 0:
        raise EtabsConcreteColumnDesignResultProviderError(
            "GetSummaryResultsColumn returned no result rows for a canonical column"
        )
    ret = raw[13]
    if isinstance(ret, bool) or not isinstance(ret, int) or ret != 0:
        raise EtabsConcreteColumnDesignResultProviderError(
            f"GetSummaryResultsColumn returned nonzero/invalid code {ret!r}"
        )
    arrays = raw[1:13]
    if any(not isinstance(values, (tuple, list)) for values in arrays):
        raise EtabsConcreteColumnDesignResultProviderError(
            "GetSummaryResultsColumn returned non-array result members"
        )
    lengths = tuple(len(values) for values in arrays)
    if any(length != number_items for length in lengths):
        raise EtabsConcreteColumnDesignResultProviderError(
            "GetSummaryResultsColumn reported/captured result array counts differ"
        )

    rows: list[ConcreteColumnDesignResultRow] = []
    for index in range(number_items):
        values = {name: arrays[position][index] for position, name in enumerate(_RESULT_ARRAY_NAMES)}
        frame_name = _text(values["FrameName"], "FrameName")
        if frame_name != requested_frame_name:
            raise EtabsConcreteColumnDesignResultProviderError(
                "GetSummaryResultsColumn FrameName does not match exact requested canonical UniqueName"
            )
        option = _int(values["MyOption"], "MyOption")
        if option not in (1, 2):
            raise EtabsConcreteColumnDesignResultProviderError("MyOption must be exact CSI Check=1 or Design=2")
        location = _decimal(values["Location"], "Location")
        pmm_area = _decimal(values["PMMArea"], "PMMArea")
        pmm_ratio = _decimal(values["PMMRatio"], "PMMRatio")
        avmajor = _decimal(values["AVMajor"], "AVMajor")
        avminor = _decimal(values["AVMinor"], "AVMinor")
        if location < 0 or pmm_area < 0:
            raise EtabsConcreteColumnDesignResultProviderError("Location and PMMArea must be >= 0")
        pmm_combo = _optional_text(values["PMMCombo"], "PMMCombo")
        vmajor_combo = _optional_text(values["VMajorCombo"], "VMajorCombo")
        vminor_combo = _optional_text(values["VMinorCombo"], "VMinorCombo")
        error_summary = values["ErrorSummary"]
        warning_summary = values["WarningSummary"]
        if not isinstance(error_summary, str) or not isinstance(warning_summary, str):
            raise EtabsConcreteColumnDesignResultProviderError(
                "ErrorSummary/WarningSummary must preserve exact CSI strings"
            )
        payload = {
            "FrameName": frame_name,
            "MyOption": option,
            "Location": _decimal_payload(location),
            "PMMCombo": pmm_combo,
            "PMMArea": _decimal_payload(pmm_area),
            "PMMRatio": _decimal_payload(pmm_ratio),
            "VMajorCombo": vmajor_combo,
            "AVMajor": _decimal_payload(avmajor),
            "VMinorCombo": vminor_combo,
            "AVMinor": _decimal_payload(avminor),
            "ErrorSummary": error_summary,
            "WarningSummary": warning_summary,
        }
        row_id = _source_row_id(frame_name=frame_name, source_index=index, payload=payload)
        rows.append(
            ConcreteColumnDesignResultRow(
                source_row_id=row_id,
                source_index=index,
                frame_name=frame_name,
                my_option=option,
                location_source=location,
                pmm_combo=pmm_combo,
                pmm_area_source=pmm_area,
                pmm_ratio=pmm_ratio,
                vmajor_combo=vmajor_combo,
                avmajor_source=avmajor,
                vminor_combo=vminor_combo,
                avminor_source=avminor,
                error_summary=error_summary,
                warning_summary=warning_summary,
                source_length_unit=source_length_unit,
                source_ref=f"CSI:{SOURCE_API}:{frame_name}:row:{index}:{row_id}",
            )
        )
    return number_items, tuple(rows)


def capture_concrete_column_design_results(
    sap_model: Any,
    *,
    topology: ColumnTopologyEvidenceEnvelope,
    design_sections: ConcreteColumnDesignSectionPopulation,
    session_provenance_ref: str,
) -> ConcreteColumnDesignResultPopulation:
    """Capture every existing column design-result row for canonical topology.

    The only component population is ``topology``.  No call to ``StartDesign``
    or any model/selection mutation is made.  Existing F0 design-section and
    component binders are mandatory dependencies, not recreated locally.
    """
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
            "topology and GetDesignSection population must share model/evidence epoch"
        )

    before = read_etabs_unit_snapshot(sap_model)
    if before.present_units_api != SOURCE_UNIT_API:
        raise EtabsConcreteColumnDesignResultProviderError(
            "GetSummaryResultsColumn requires explicit GetPresentUnits_2 source-unit provenance"
        )
    try:
        source_length_unit = decode_csi_length_unit(before.present_length_unit)
    except EtabsSourceUnitError as exc:
        raise EtabsConcreteColumnDesignResultProviderError(
            "GetSummaryResultsColumn source length unit is unavailable/outside reviewed scope"
        ) from exc

    design_concrete = getattr(sap_model, "DesignConcrete", None)
    getter = getattr(design_concrete, "GetSummaryResultsColumn", None)
    if not callable(getter):
        raise EtabsConcreteColumnDesignResultProviderError(
            "DesignConcrete.GetSummaryResultsColumn is unavailable"
        )

    columns = tuple(sorted(topology.topology.columns, key=lambda item: item.component_id))
    expected_ids = tuple(sorted(item.component_id for item in columns))
    components: list[CapturedConcreteColumnDesignResult] = []
    attempted_count = 0
    reported_total = 0

    for column in columns:
        attempted_count += 1
        section_row = design_sections.by_component_id(column.component_id)
        if section_row.unique_name != column.unique_name:
            raise EtabsConcreteColumnDesignResultProviderError(
                "GetDesignSection population does not bind to the same canonical UniqueName"
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
                f"F0 result/component binding blocked for {column.unique_name}: {binding.status.value}"
            )
        try:
            raw = getter(column.unique_name)
        except Exception as exc:
            raise EtabsConcreteColumnDesignResultProviderError(
                f"GetSummaryResultsColumn({column.unique_name!r}) raised {type(exc).__name__}: {exc}"
            ) from exc
        reported, rows = _parse_summary_results_column(
            raw,
            requested_frame_name=column.unique_name,
            source_length_unit=source_length_unit,
        )
        reported_total += reported
        refs = tuple(
            dict.fromkeys(
                (
                    session_ref,
                    *topology.source_refs,
                    *section_row.source_refs,
                    *binding.source_refs,
                    request_ref,
                    *(row.source_ref for row in rows),
                )
            )
        )
        components.append(
            CapturedConcreteColumnDesignResult(
                component_id=column.component_id,
                unique_name=column.unique_name,
                story=column.story,
                label=column.column_label,
                assigned_section=column.section,
                design_section=section_row.design_section,
                binding=binding,
                row_count_reported=reported,
                rows=rows,
                model_fingerprint=topology.model_fingerprint,
                evidence_epoch_id=topology.evidence_epoch_id,
                source_refs=refs,
            )
        )

    after = read_etabs_unit_snapshot(sap_model)
    if _unit_snapshot_key(after) != _unit_snapshot_key(before):
        raise EtabsConcreteColumnDesignResultProviderError(
            "ETABS present-unit provenance changed during design-result capture"
        )
    try:
        after_length = decode_csi_length_unit(after.present_length_unit)
    except EtabsSourceUnitError as exc:
        raise EtabsConcreteColumnDesignResultProviderError(
            "post-capture source length unit is unavailable/outside reviewed scope"
        ) from exc
    if after_length is not source_length_unit:
        raise EtabsConcreteColumnDesignResultProviderError(
            "source length unit changed during design-result capture"
        )

    captured_total = sum(len(item.rows) for item in components)
    source_refs = tuple(
        dict.fromkeys(
            (
                session_ref,
                *topology.source_refs,
                *design_sections.source_refs,
                f"CSI:{SOURCE_UNIT_API}:length={source_length_unit.value}",
                *(ref for item in components for ref in item.source_refs),
            )
        )
    )
    return ConcreteColumnDesignResultPopulation(
        model_fingerprint=topology.model_fingerprint,
        evidence_epoch_id=topology.evidence_epoch_id,
        source_api=SOURCE_API,
        source_item_type=SOURCE_ITEM_TYPE,
        source_unit_api=SOURCE_UNIT_API,
        source_length_unit=source_length_unit,
        expected_component_ids=expected_ids,
        components=tuple(components),
        expected_component_count=len(expected_ids),
        attempted_component_count=attempted_count,
        captured_component_count=len(components),
        reported_result_row_count=reported_total,
        captured_result_row_count=captured_total,
        session_provenance_ref=session_ref,
        source_refs=source_refs,
    )


__all__ = [
    "SOURCE_API",
    "SOURCE_ITEM_TYPE",
    "SOURCE_UNIT_API",
    "CapturedConcreteColumnDesignResult",
    "ConcreteColumnDesignResultPopulation",
    "ConcreteColumnDesignResultRow",
    "EtabsConcreteColumnDesignResultProviderError",
    "capture_concrete_column_design_results",
]
