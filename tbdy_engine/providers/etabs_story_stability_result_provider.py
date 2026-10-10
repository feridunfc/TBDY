"""Factual ETABS result acquisition for TS500 story-stability composition.

The provider reads one already-existing ETABS output combination after the sole
B5 analysis generation. It captures global story shear, raw StoryDrifts rows and
the full column-force population and binds those facts to the exact B5 result
identity/proof supplied by the application composer.

It deliberately does *not* promote CSI ``StoryDrifts.Drift`` to TS500 Eq.7.13
``Delta_i``. The CSI API contract documents drift rows, but the current approved
sources do not prove the aggregation/units required to equate a maximum point
Drift row with the TS500 relative-storey displacement. That mapping therefore
stays explicit and fail-closed until a separate source-bound resolver proves it.

No TS500 load-basis matching, sway classification, effective-length math or
moment magnification is performed here.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

from tbdy_engine.etabs.oapi import fetch_display_table_for_output_from_session
from tbdy_engine.etabs.oapi.story_drift_results import (
    StoryDriftResultRow,
    read_story_drifts_from_session,
)
from tbdy_engine.etabs.safety import EtabsVerifiedSession, RuntimeCaptureStatus
from tbdy_engine.features.column_shear_topology import (
    ColumnTopologyEvidence,
    StrictColumnTopologyBundle,
    ColumnPhysicalEndpointsEvidence,
)
from tbdy_engine.etabs.oapi.eq713_response_results import FrameForceResponseFact, FrameForceResponseRow
from tbdy_engine.etabs.oapi.joint_displacement_results import JointDisplacementResultFact, JointDisplacementResultRow
from tbdy_engine.etabs.oapi.database_tables import TableFieldMetadataFetchResult
from tbdy_engine.analysis_basis.eq713_response_mechanics import NativeModalAmplitude, NativeModalScalarResponse
from tbdy_engine.providers.etabs_column_force_result_population_provider import (
    ColumnForcePopulationExpectation,
    capture_column_force_result_population_from_session,
)


TABLE_STORY_FORCES = "Story Forces"
STORY_STABILITY_FACT_AUTHORITY = "ETABS_B5_STORY_STABILITY_FACTS"
TS500_DELTA_D_MAPPING_NOT_PROVEN = "NOT_PROVEN_CSI_STORYDRIFTS_TO_TS500_DELTA_I"


class StoryStabilityResultProviderError(RuntimeError):
    """Raised when exact post-B5 story-stability facts cannot be established."""


class NativeModalBottomBindingError(StoryStabilityResultProviderError):
    def __init__(self, code: str, column: str, raw_response_ref: str, detail: str):
        self.code, self.column, self.raw_response_ref = code, column, raw_response_ref
        super().__init__(f"{code}: Column={column}; raw={raw_response_ref}; {detail}")


def qualify_native_modal_physical_bottom_rows(
    column: ColumnPhysicalEndpointsEvidence, fact: FrameForceResponseFact, *,
    modal_case: str, expected_modes: Sequence[int], raw_response_ref: str,
    force_unit: str, length_unit: str,
) -> tuple[FrameForceResponseRow, ...]:
    """Exact native object endpoint, retaining the uniquely matching element.

    ObjSta is measured from object I; ElmSta remains the factual element grain.
    Unlike the old display-table min/max selector, a truncated station universe
    cannot masquerade as a physical endpoint. No nearest-station tolerance or
    element orientation is inferred. This factual selector issues no B5 epoch.
    """
    if not isinstance(column, ColumnPhysicalEndpointsEvidence) or not isinstance(fact, FrameForceResponseFact):
        raise TypeError("typed physical Column and native FrameForce fact required")
    def fail(code, detail):
        raise NativeModalBottomBindingError(code, column.unique_name, raw_response_ref, detail)
    if not isinstance(raw_response_ref, str) or not raw_response_ref.strip() or raw_response_ref != raw_response_ref.strip():
        fail("MODAL_BOTTOM_RAW_REF_MISSING", "exact raw property/result binding required")
    if force_unit != "kN" or length_unit != "m":
        fail("MODAL_BOTTOM_UNIT_SCOPE", "current factual Column slice requires kN/m")
    modes = tuple(expected_modes)
    if not modes or any(type(n) is not int or n <= 0 for n in modes) or len(set(modes)) != len(modes):
        fail("MODAL_BOTTOM_MODE_AUTHORITY", "nonempty unique exact mode population required")
    if (fact.return_code != 0 or fact.source_api != "Results.FrameForce"
            or fact.frame_name != column.unique_name or fact.case_name != modal_case):
        fail("MODAL_BOTTOM_SOURCE_IDENTITY", "successful exact object/modal case source required")
    target = 0.0 if column.bottom.unique_name == column.point_i.unique_name else column.object_length_m
    grains, selected = {}, {}
    for row in fact.rows:
        if row.object_name != column.unique_name or row.load_case != modal_case or row.step_type != "Mode":
            fail("MODAL_BOTTOM_ROW_IDENTITY", "object/case/Mode mismatch")
        if (type(row.step_number) not in (int, float) or not math.isfinite(row.step_number)
                or int(row.step_number) != row.step_number or int(row.step_number) not in modes):
            fail("MODAL_BOTTOM_MODE_POPULATION", "invalid/extra mode")
        if (not isinstance(row.element_name, str) or not row.element_name.strip() or row.element_name != row.element_name.strip()
                or any(type(v) not in (int, float) or not math.isfinite(v)
                       for v in (row.object_station, row.element_station, row.p))
                or min(row.object_station, row.element_station) < 0):
            fail("MODAL_BOTTOM_ROW_VALUES", "finite signed P and native element/stations required")
        n = int(row.step_number)
        grain = (row.element_name, row.object_station, row.element_station)
        population = grains.setdefault(grain, set())
        if n in population:
            fail("MODAL_BOTTOM_DUPLICATE_MODE", f"duplicate mode={n}; grain={grain}")
        population.add(n)
        if row.object_station == target:
            if n in selected:
                fail("MODAL_BOTTOM_AMBIGUOUS_STATION", f"mode={n}; target={target}; multiple native element rows")
            selected[n] = row
    if not grains or any(values != set(modes) for values in grains.values()):
        fail("MODAL_BOTTOM_MODE_POPULATION", "missing mode in a native physical grain")
    if set(selected) != set(modes):
        fail("MODAL_BOTTOM_ENDPOINT_NOT_EXACT", f"target ObjSta={target}; no exact physical endpoint per mode")
    if len({(r.element_name, r.element_station) for r in selected.values()}) != 1:
        fail("MODAL_BOTTOM_ELEMENT_GRAIN_DRIFT", "endpoint element identity/station differs between modes")
    return tuple(selected[n] for n in sorted(modes))


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise StoryStabilityResultProviderError(f"{label} must be a nonblank canonical string")
    return value


def qualify_native_modal_endpoint_rows(
    point: str, fact: JointDisplacementResultFact, *, modal_case: str,
    expected_modes: Sequence[int], length_unit: str, raw_response_ref: str,
) -> tuple[JointDisplacementResultRow, ...]:
    """Preserve point-LOCAL endpoint responses; never relabel them global.

    CSI API ETABS v1 (2024), JointDispl pp.147-150 defines U1/U2/U3 in
    point-element local axes. Physical coordinates do not prove those axes.
    An independently captured local-to-global transformation is still needed.
    """
    _text(point, "physical endpoint")
    _text(raw_response_ref, "endpoint raw response")
    modes = tuple(expected_modes)
    if (not modes or any(type(n) is not int or n <= 0 for n in modes)
            or len(set(modes)) != len(modes)):
        raise StoryStabilityResultProviderError("exact complete endpoint mode authority required")
    if (not isinstance(fact, JointDisplacementResultFact) or fact.return_code != 0
            or fact.source_api != "Results.JointDispl" or fact.item_type_elm != 0
            or fact.point_object != point or fact.output_name != modal_case or fact.output_kind != "case"
            or length_unit != "m"):
        raise StoryStabilityResultProviderError("successful exact native endpoint/case/metre source required")
    by_mode, elements = {}, set()
    for row in fact.rows:
        if (row.point_object != point or row.load_case != modal_case or row.step_type != "Mode"
                or type(row.step_number) not in (int, float) or not math.isfinite(row.step_number)
                or int(row.step_number) != row.step_number or int(row.step_number) not in modes):
            raise StoryStabilityResultProviderError("endpoint object/case/Mode population mismatch")
        n = int(row.step_number)
        if n in by_mode:
            raise StoryStabilityResultProviderError("duplicate/ambiguous physical endpoint mode")
        _text(row.element_name, "physical endpoint element")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (row.u1, row.u2, row.u3)):
            raise StoryStabilityResultProviderError("finite signed native endpoint translations required")
        elements.add(row.element_name)
        by_mode[n] = row
    if set(by_mode) != set(modes) or len(elements) != 1:
        raise StoryStabilityResultProviderError("incomplete endpoint modes or element-grain drift")
    return tuple(by_mode[n] for n in modes)


def qualify_native_modal_story_shear(
    rows: Sequence[Mapping[str, Any]], *, story: str,
    amplitudes: Sequence[NativeModalAmplitude], expected_modes: Sequence[int],
    metadata: TableFieldMetadataFetchResult, raw_response_ref: str,
) -> tuple[NativeModalScalarResponse, ...]:
    """Exact global signed bottom-cut modes, before native Amp multiplication.

    Unrelated stories/cases/top cuts are excluded, not modal alternatives.
    VX/VY direction and kN units must be established by native metadata.
    The case's Global/zero-angle load mapping belongs to the source adapter.
    This selector cannot issue a B5 epoch or a statistical stability state.
    """
    _text(story, "physical story")
    _text(raw_response_ref, "story shear raw response")
    modes, amps = tuple(expected_modes), tuple(amplitudes)
    if (not modes or any(type(n) is not int or n <= 0 for n in modes)
            or len(set(modes)) != len(modes) or any(not isinstance(a, NativeModalAmplitude) for a in amps)
            or tuple(a.mode for a in amps) != modes):
        raise StoryStabilityResultProviderError("complete matching amplitude/mode authority required")
    binding = amps[0].binding
    if any(a.binding != binding for a in amps) or binding.database_force_unit != "kN":
        raise StoryStabilityResultProviderError("story shear amplitude source/case/unit drift")
    field = {"U1": "VX", "U2": "VY"}.get(binding.source_direction)
    if field is None or not isinstance(metadata, TableFieldMetadataFetchResult):
        raise StoryStabilityResultProviderError("qualified X/Y shear field metadata required")
    if metadata.table_name != "Story Forces" or metadata.return_code != 0 or len(set(metadata.field_keys)) != len(metadata.field_keys):
        raise StoryStabilityResultProviderError("successful exact unique Story Forces metadata required")
    definition = metadata.field_metadata(field)
    direction = {"VX": "X", "VY": "Y"}[field]
    if (definition["UnitsString"] != "kN"
            or definition["Description"] != f"The shear force in the global {direction}-direction."):
        raise StoryStabilityResultProviderError("native global shear direction/unit metadata mismatch")
    selected = {}
    for row in rows:
        if (row.get("Story"), row.get("OutputCase"), row.get("Location")) != (story, binding.modal_case, "Bottom"):
            continue
        if row.get("StepType") != "Mode" or row.get("CaseType") not in {"LinModRitz", "LinModEigen"}:
            raise StoryStabilityResultProviderError("bottom modal row must be a native Mode, not an extremum")
        if isinstance(row.get("StepNumber"), bool):
            raise StoryStabilityResultProviderError("exact modal index required")
        number = _finite(row.get("StepNumber"), "shear mode")
        if int(number) != number or int(number) not in modes:
            raise StoryStabilityResultProviderError("extra/fractional shear mode")
        n = int(number)
        if n in selected:
            raise StoryStabilityResultProviderError("duplicate bottom modal shear mode")
        if isinstance(row.get(field), bool):
            raise StoryStabilityResultProviderError("signed shear must be factual numeric")
        selected[n] = NativeModalScalarResponse(n, _finite(row.get(field), field), binding,
            "STORY_BOTTOM_SHEAR", "kN", f"Story Forces|{story}|Bottom|{binding.modal_case}|Mode:{n}|{field}",
            (raw_response_ref, metadata.raw_response_ref))
    if set(selected) != set(modes):
        raise StoryStabilityResultProviderError("incomplete exact bottom modal shear population")
    return tuple(selected[n] for n in modes)


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            result = float(value)  # ETABS table parser may preserve numeric strings.
        except (TypeError, ValueError) as exc:
            raise StoryStabilityResultProviderError(f"{label} must be numeric") from exc
    else:
        result = float(value)
    if not math.isfinite(result):
        raise StoryStabilityResultProviderError(f"{label} must be finite")
    return result


def _require_full(fetch, label: str) -> tuple[Mapping[str, Any], ...]:
    if fetch.capture_status is not RuntimeCaptureStatus.FULL:
        raise StoryStabilityResultProviderError(
            f"{label} requires FULL runtime capture; got {fetch.capture_status.value}"
        )
    rows = tuple(dict(row) for row in fetch.parsed.rows)
    reported = fetch.parsed.row_count_reported
    if reported is not None and len(rows) != int(reported):
        raise StoryStabilityResultProviderError(
            f"{label} FULL row mismatch: captured={len(rows)} reported={reported}"
        )
    if not rows:
        raise StoryStabilityResultProviderError(f"{label} returned no rows")
    return rows


def _restore_verified(fetch) -> bool:
    return any(
        item.get("phase") == "restore_verify" and item.get("success") is True
        for item in fetch.state_diagnostics
    )


def _field(row: Mapping[str, Any], names: Sequence[str], label: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    raise StoryStabilityResultProviderError(
        f"{label} missing required field; accepted aliases={tuple(names)}"
    )


def _story_height_mm(topology: StrictColumnTopologyBundle, story: str) -> tuple[float, tuple[str, ...]]:
    columns = tuple(item for item in topology.columns if item.story == story)
    if not columns:
        raise StoryStabilityResultProviderError(f"strict topology has no columns in story {story!r}")
    heights = tuple(abs(item.top_coord_m[2] - item.bottom_coord_m[2]) for item in columns)
    if any(value <= 0.0 or not math.isfinite(value) for value in heights):
        raise StoryStabilityResultProviderError(f"story {story!r} contains nonpositive column height")
    reference = heights[0]
    if any(not math.isclose(value, reference, rel_tol=1e-9, abs_tol=1e-6) for value in heights[1:]):
        raise StoryStabilityResultProviderError(
            f"story {story!r} column elevations do not prove one exact story height: {heights!r}"
        )
    refs = tuple(
        f"strict-topology:{item.unique_name}:z={item.bottom_coord_m[2]:.12g}->{item.top_coord_m[2]:.12g}"
        for item in columns
    )
    return reference * 1000.0, refs


def _bottom_station_row(
    column: ColumnTopologyEvidence,
    rows: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    exact = tuple(row for row in rows if row.get("UniqueName") == column.unique_name)
    if not exact:
        raise StoryStabilityResultProviderError(
            f"combo column-force population lacks {column.unique_name!r}"
        )
    stations = tuple(_finite(row.get("Station"), f"{column.unique_name}.Station") for row in exact)
    point_i = column.connectivity_row.get("UniquePtI")
    point_j = column.connectivity_row.get("UniquePtJ")
    if point_i == column.joint_bottom and point_j == column.joint_top:
        target = min(stations)
    elif point_j == column.joint_bottom and point_i == column.joint_top:
        target = max(stations)
    else:
        raise StoryStabilityResultProviderError(
            f"column {column.unique_name!r} bottom/top joint identity is inconsistent with connectivity row"
        )
    matches = tuple(
        row for row in exact
        if math.isclose(_finite(row.get("Station"), "Station"), target, rel_tol=1e-9, abs_tol=1e-9)
    )
    if len(matches) != 1:
        raise StoryStabilityResultProviderError(
            f"column {column.unique_name!r} requires exactly one physical-bottom force row; got {len(matches)}"
        )
    return matches[0]


def _sum_story_axial_compression_n(
    topology: StrictColumnTopologyBundle,
    *,
    story: str,
    force_rows: Sequence[Mapping[str, Any]],
    force_unit: str,
) -> tuple[float, tuple[str, ...]]:
    if force_unit != "kN":
        raise StoryStabilityResultProviderError(
            "COLUMN-R1 current result-unit contract requires reviewed force_unit='kN'"
        )
    columns = tuple(item for item in topology.columns if item.story == story)
    if not columns:
        raise StoryStabilityResultProviderError(f"story {story!r} has no strict-topology columns")
    total_n = 0.0
    refs: list[str] = []
    for column in columns:
        row = _bottom_station_row(column, force_rows)
        # Existing Column demand normalization contract is factual ETABS
        # negative-compression P. Preserve signed summation so a tensile
        # column reduces the storey compression rather than being clipped.
        p_kn = _finite(row.get("P"), f"{column.unique_name}.P")
        total_n += -p_kn * 1000.0
        refs.append(
            f"ETABS:Element Forces - Columns:{column.unique_name}:physical-bottom:P={p_kn:.12g}kN"
        )
    if not math.isfinite(total_n) or total_n <= 0.0:
        raise StoryStabilityResultProviderError(
            f"story {story!r} summed design axial compression must be >0; got {total_n} N"
        )
    return total_n, tuple(refs)


def _story_shear_row(
    rows: Sequence[Mapping[str, Any]],
    *,
    output_name: str,
    story: str,
) -> Mapping[str, Any]:
    exact = []
    for row in rows:
        if row.get("Story") != story:
            continue
        output = row.get("OutputCase", row.get("Output Case"))
        if output != output_name:
            continue
        # TS500 V_fi is the storey total shear at the storey cut. Do not accept
        # a different table location or silently use a row whose location is
        # absent/unresolved.
        location = str(row.get("Location", "")).strip().casefold()
        if location != "bottom":
            continue
        exact.append(row)
    if len(exact) != 1:
        raise StoryStabilityResultProviderError(
            f"{TABLE_STORY_FORCES}@{output_name}/{story} requires exactly one Bottom row; got {len(exact)}"
        )
    return exact[0]


def _story_shear_for_direction_n(row: Mapping[str, Any], direction: str) -> float:
    direction_name = _text(direction, "global_direction")
    if direction_name not in {"X", "Y"}:
        raise StoryStabilityResultProviderError("global_direction must be X or Y")
    field = ("VX", "Vx") if direction_name == "X" else ("VY", "Vy")
    value_kn = _finite(_field(row, field, "Story Forces"), f"Story Forces.V{direction_name}")
    if abs(value_kn) <= 1e-12:
        raise StoryStabilityResultProviderError(
            f"story shear in required global {direction_name} direction is zero"
        )
    return abs(value_kn) * 1000.0


@dataclass(frozen=True, slots=True)
class EtabsStoryStabilityComboFact:
    output_name: str
    output_kind: str
    story: str
    global_direction: str
    story_height_mm: float
    story_drift_rows: tuple[StoryDriftResultRow, ...]
    ts500_delta_d_mapping_status: str
    story_shear_n: float
    sum_column_axial_design_force_n: float
    analysis_result_ref: str
    execution_proof_ref: str
    source_refs: tuple[str, ...]
    authority: str = STORY_STABILITY_FACT_AUTHORITY


def capture_story_stability_combo_fact_from_session(
    session: EtabsVerifiedSession,
    *,
    output_name: str,
    story: str,
    global_direction: str,
    direction_source_refs: Sequence[str],
    topology: StrictColumnTopologyBundle,
    analysis_result_ref: str,
    execution_proof_ref: str,
    reviewed_force_unit: str,
    timeout_seconds: float = 30.0,
) -> EtabsStoryStabilityComboFact:
    """Capture one existing combo's exact post-B5 story-stability factual operands.

    ``global_direction`` must already be proven by the existing load-definition /
    direction-binding path. Story response magnitudes are not allowed to create
    direction authority here.
    """
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    name = _text(output_name, "output_name")
    story_name = _text(story, "story")
    direction = _text(global_direction, "global_direction")
    if direction not in {"X", "Y"}:
        raise StoryStabilityResultProviderError("global_direction must be X or Y")
    direction_refs = tuple(_text(ref, "direction_source_ref") for ref in direction_source_refs)
    if not direction_refs or len(set(direction_refs)) != len(direction_refs):
        raise StoryStabilityResultProviderError(
            "direction_source_refs must be nonempty and unique"
        )
    analysis_ref = _text(analysis_result_ref, "analysis_result_ref")
    proof_ref = _text(execution_proof_ref, "execution_proof_ref")
    if not isinstance(topology, StrictColumnTopologyBundle):
        raise TypeError("topology must be StrictColumnTopologyBundle")

    height_mm, height_refs = _story_height_mm(topology, story_name)

    story_forces = fetch_display_table_for_output_from_session(
        session,
        TABLE_STORY_FORCES,
        preferred_output_case=name,
        max_rows=None,
        timeout_seconds=timeout_seconds,
    )
    force_rows = _require_full(story_forces, f"{TABLE_STORY_FORCES}@{name}")
    if not _restore_verified(story_forces):
        raise StoryStabilityResultProviderError(
            f"{TABLE_STORY_FORCES}@{name} output-selection restoration did not verify"
        )
    shear_row = _story_shear_row(force_rows, output_name=name, story=story_name)
    shear_n = _story_shear_for_direction_n(shear_row, direction)

    drift_fact = read_story_drifts_from_session(
        session,
        output_name=name,
        output_kind="combo",
        timeout_seconds=timeout_seconds,
    )
    drift_rows = tuple(
        row for row in drift_fact.rows
        if row.story == story_name and row.direction == direction
    )
    if not drift_rows:
        raise StoryStabilityResultProviderError(
            f"Results.StoryDrifts@{name}/{story_name}/{direction} returned no exact rows"
        )

    expectation = ColumnForcePopulationExpectation(
        expected_unique_names=tuple(item.unique_name for item in topology.columns),
        source_row_count=len(topology.columns),
    )
    column_forces = capture_column_force_result_population_from_session(
        session,
        case_name=name,
        expectation=expectation,
        timeout_seconds=timeout_seconds,
    )
    story_rows = tuple(row for row in column_forces.rows if row.get("Story") == story_name)
    sum_nd_n, axial_refs = _sum_story_axial_compression_n(
        topology,
        story=story_name,
        force_rows=story_rows,
        force_unit=reviewed_force_unit,
    )

    refs = tuple(
        dict.fromkeys(
            (
                analysis_ref,
                proof_ref,
                *direction_refs,
                *height_refs,
                f"ETABS:{TABLE_STORY_FORCES}:{name}:{story_name}:Bottom:V{direction}",
                drift_fact.evidence_ref,
                *(f"ETABS:Results.StoryDrifts:{name}:{story_name}:{direction}:{row.point_label}" for row in drift_rows),
                column_forces.evidence_ref,
                *axial_refs,
                TS500_DELTA_D_MAPPING_NOT_PROVEN,
            )
        )
    )
    return EtabsStoryStabilityComboFact(
        output_name=name,
        output_kind="combo",
        story=story_name,
        global_direction=direction,
        story_height_mm=height_mm,
        story_drift_rows=drift_rows,
        ts500_delta_d_mapping_status=TS500_DELTA_D_MAPPING_NOT_PROVEN,
        story_shear_n=shear_n,
        sum_column_axial_design_force_n=sum_nd_n,
        analysis_result_ref=analysis_ref,
        execution_proof_ref=proof_ref,
        source_refs=refs,
    )


__all__ = [
    "EtabsStoryStabilityComboFact",
    "STORY_STABILITY_FACT_AUTHORITY",
    "StoryStabilityResultProviderError",
    "TABLE_STORY_FORCES",
    "TS500_DELTA_D_MAPPING_NOT_PROVEN",
    "capture_story_stability_combo_fact_from_session",
]
