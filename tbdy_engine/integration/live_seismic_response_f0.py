"""VS-3 deterministic seismic factual capture -> formal F0 regulatory execution."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from tbdy_engine.etabs.safety import RuntimeCaptureStatus
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.findings import Finding, build_finding_from_check_result, build_finding_from_rule_closure
from tbdy_engine.integration.live_beam_geometry_f0 import live_epoch_id, model_fingerprint_from_path
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table_for_output
from tbdy_engine.regulatory.contracts import (
    AvailabilityState,
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
    AssessmentEngine,
    ExternalDependencyAuthority,
    PopulationCompleteness,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryEngine,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.seismic_response import (
    A1ApplicabilityInput,
    A1_EVIDENCE_TRACE_KEY,
    A1_RATIO_KEY,
    A1_RULE_ID,
    MODAL_EVIDENCE_TRACE_KEY,
    MODAL_RATIO_KEY,
    MODAL_RULE_ID,
    Modal4812ApplicabilityInput,
    VS3_SEISMIC_REGISTRY,
)
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS

SEISMIC_SOURCE_FINGERPRINT_PREFIX = "etabs:seismic-response-source:sha256:"
CAPTURE_CONTRACT = "VS3_SEISMIC_FACTUAL_CAPTURE_V1"
MODAL_TABLE = "Modal Participating Mass Ratios"
STORY_DRIFT_TABLE = "Story Drifts"
A1_TABLE = "Story Max Over Avg Drifts"
BASE_REACTIONS_TABLE = "Base Reactions"
BLOCKED_BY_LIVE_SEISMIC_EVIDENCE_CONFLICT = "BLOCKED_BY_LIVE_SEISMIC_EVIDENCE_CONFLICT"
BLOCKED_BY_MODAL_SOURCE_SEMANTICS = "BLOCKED_BY_MODAL_SOURCE_SEMANTICS"


class LiveSeismicResponseError(RuntimeError):
    pass


class LiveSeismicEvidenceConflictError(LiveSeismicResponseError):
    status = BLOCKED_BY_LIVE_SEISMIC_EVIDENCE_CONFLICT


class ModalSourceSemanticsError(LiveSeismicResponseError):
    status = BLOCKED_BY_MODAL_SOURCE_SEMANTICS


@dataclass(frozen=True, slots=True)
class SeismicCaptureArtifact:
    payload: Mapping[str, Any]
    raw_bytes: bytes
    epoch: EvidenceEpoch


@dataclass(frozen=True, slots=True)
class LiveSeismicPackRun:
    capture: SeismicCaptureArtifact
    modal_4812_applies: bool | None
    modal_case_basis_verified: str
    a1_eccentricity_basis: str
    authorities: tuple[ExternalDependencyAuthority, ...]
    program: object
    store: object
    assessment: object
    check_findings: tuple[Finding, ...]
    closure_findings: tuple[Finding, ...]

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(sorted((*self.check_findings, *self.closure_findings), key=lambda item: item.finding_id))


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            to_jsonable(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _canonical_text(value: object) -> str:
    return json.dumps(
        to_jsonable(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank exact name")
    return value


def _case_tuple(values: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{label} must be a sequence of exact case names")
    names = tuple(_nonblank(item, label) for item in values)
    if not names:
        raise ValueError(f"{label} requires at least one exact case name")
    if len(set(names)) != len(names):
        raise ValueError(f"{label} contains duplicate exact case names")
    return tuple(sorted(names))


def _float_or_none(value: object) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        try:
            result = float(str(value).strip().replace(",", "."))
        except ValueError:
            return None
    return result if math.isfinite(result) else None


def _first(row: Mapping[str, object], aliases: Sequence[str]) -> tuple[str | None, object]:
    direct = {str(key): key for key in row}
    folded = {
        str(key).replace(" ", "").replace("_", "").replace("/", "").casefold(): key
        for key in row
    }
    for alias in aliases:
        if alias in direct:
            key = direct[alias]
            value = row.get(key)
            if value not in (None, ""):
                return str(key), value
        key = folded.get(alias.replace(" ", "").replace("_", "").replace("/", "").casefold())
        if key is not None:
            value = row.get(key)
            if value not in (None, ""):
                return str(key), value
    return None, None


def _normalized_numeric_values(row: Mapping[str, object]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in row.items():
        parsed = _float_or_none(value)
        if parsed is not None:
            out[str(key)] = parsed
    return dict(sorted(out.items()))


def _parser_status(fetched) -> str:
    parsed = fetched.parsed
    if parsed.rows:
        return "PARSED_ROWS"
    debug = dict(parsed.debug or {})
    return str(debug.get("parser_status") or parsed.fetch_status or "EMPTY")


def _capture_status(fetched) -> str:
    value = fetched.capture_status
    return value.value if isinstance(value, RuntimeCaptureStatus) else str(value)


def _selection_summary(fetched) -> dict[str, object]:
    selection = dict(fetched.display_selection or {})
    return {
        "preferred_output_case": selection.get("preferred_output_case"),
        "display_selection_success": bool(selection.get("display_selection_success", False)),
        "display_selection_selected_method": selection.get("display_selection_selected_method"),
        "fetch_after_display_selection": bool(selection.get("fetch_after_display_selection", False)),
        "capture_status": _capture_status(fetched),
        "parser_status": _parser_status(fetched),
        "row_count": len(fetched.parsed.rows),
    }


def _stable_rows(*, fetched, requested_case: str, capture_direction: str | None) -> list[dict[str, object]]:
    raw_rows = [dict(to_jsonable(row)) for row in fetched.parsed.rows]
    raw_rows.sort(key=_canonical_text)
    rows: list[dict[str, object]] = []
    for index, row in enumerate(raw_rows):
        rows.append(
            {
                "source_table": fetched.table_name,
                "actual_table_name": fetched.parsed.actual_table_name,
                "capture_case": requested_case,
                "capture_direction": capture_direction,
                "row_index": index,
                "row_index_basis": "CANONICALIZED_CAPTURE_ORDER",
                "raw_values": row,
                "normalized_numeric_values": _normalized_numeric_values(row),
            }
        )
    return rows


def _fetch_exact(database_tables: object, table_name: str, case_name: str):
    fetched = fetch_display_table_for_output(
        database_tables,
        table_name,
        preferred_output_case=case_name,
        max_rows=None,
    )
    summary = _selection_summary(fetched)
    if not summary["display_selection_success"] or not summary["fetch_after_display_selection"]:
        raise LiveSeismicEvidenceConflictError(
            f"exact ETABS output selection was not verified for {table_name} / {case_name}"
        )
    if summary["capture_status"] != RuntimeCaptureStatus.FULL.value:
        raise LiveSeismicEvidenceConflictError(
            "formal/factual seismic source capture is not FULL: "
            f"{table_name} / {case_name}; capture_status={summary['capture_status']}"
        )
    return fetched, summary


def _modal_final_row(rows: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
    candidates: list[tuple[float, str, Mapping[str, object]]] = []
    for item in rows:
        raw = item.get("raw_values")
        if not isinstance(raw, Mapping):
            continue
        _column, mode = _first(raw, ("Mode", "ModeNum", "Mode Number", "StepNum", "Step"))
        mode_number = _float_or_none(mode)
        if mode_number is not None:
            candidates.append((mode_number, _canonical_text(raw), item))
    if not candidates:
        raise ModalSourceSemanticsError(
            "selected Modal Participating Mass Ratios population has no factual highest-mode identity"
        )
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[-1][2]


def _modal_fact(payload: Mapping[str, object], direction: str) -> dict[str, object]:
    modal = payload.get("modal")
    if not isinstance(modal, Mapping):
        raise ModalSourceSemanticsError("modal factual capture is missing")
    rows = modal.get("rows")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)) or not rows:
        raise ModalSourceSemanticsError("selected modal case has no factual population")
    final = _modal_final_row(tuple(item for item in rows if isinstance(item, Mapping)))
    raw = final.get("raw_values") if isinstance(final, Mapping) else None
    if not isinstance(raw, Mapping):
        raise ModalSourceSemanticsError("final modal row is malformed")
    aliases = ("SumUX", "Sum UX", "Cumulative UX") if direction == "X" else ("SumUY", "Sum UY", "Cumulative UY")
    source_column, raw_value = _first(raw, aliases)
    value = _float_or_none(raw_value)
    return {
        "direction": direction,
        "availability": "RESOLVED" if value is not None else "NO_DATA",
        "value": value,
        "unit": "ratio",
        "source_column": source_column,
        "source_row_index": final.get("row_index"),
        "capture_case": final.get("capture_case"),
    }


def _story(row: Mapping[str, object]) -> str | None:
    raw = row.get("raw_values")
    if not isinstance(raw, Mapping):
        return None
    _column, value = _first(raw, ("Story", "StoryName", "Story Name"))
    return None if value in (None, "") else str(value).strip()


def _eta(row: Mapping[str, object]) -> tuple[str | None, float | None]:
    raw = row.get("raw_values")
    if not isinstance(raw, Mapping):
        return None, None
    column, value = _first(
        raw,
        ("Ratio", "MaxOverAvg", "Max Over Avg", "eta_bi", "EtaBi", "Torsion", "TorsionRatio"),
    )
    return column, _float_or_none(value)


def _row_direction_compatible(row: Mapping[str, object], expected: str) -> bool:
    raw = row.get("raw_values")
    if not isinstance(raw, Mapping):
        return False
    _column, value = _first(raw, ("Direction", "Dir"))
    if value in (None, ""):
        return True
    normalized = str(value).strip().upper()
    aliases = {"X", "U1", "UX"} if expected == "X" else {"Y", "U2", "UY"}
    return normalized in aliases


def _a1_facts(payload: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    a1 = payload.get("a1")
    if not isinstance(a1, Mapping):
        return ()
    by_direction = a1.get("by_direction")
    if not isinstance(by_direction, Mapping):
        return ()

    story_names: set[str] = set()
    direction_rows: dict[str, tuple[Mapping[str, object], ...]] = {}
    for direction in ("X", "Y"):
        item = by_direction.get(direction)
        rows = item.get("rows") if isinstance(item, Mapping) else ()
        selected = tuple(row for row in rows or () if isinstance(row, Mapping))
        direction_rows[direction] = selected
        for row in selected:
            story = _story(row)
            if story:
                story_names.add(story)

    facts: list[dict[str, object]] = []
    for story in sorted(story_names):
        for direction in ("X", "Y"):
            item = by_direction.get(direction)
            cases = tuple(item.get("cases") or ()) if isinstance(item, Mapping) else ()
            rows = direction_rows[direction]
            considered: list[dict[str, object]] = []
            missing_cases: list[str] = []
            for case_name in cases:
                candidates = [
                    row
                    for row in rows
                    if row.get("capture_case") == case_name
                    and _story(row) == story
                    and _row_direction_compatible(row, direction)
                ]
                valid: list[tuple[float, str | None, Mapping[str, object]]] = []
                for row in candidates:
                    source_column, value = _eta(row)
                    if value is not None:
                        valid.append((value, source_column, row))
                if not valid:
                    missing_cases.append(str(case_name))
                    continue
                for value, source_column, row in valid:
                    considered.append(
                        {
                            "case": case_name,
                            "eta_bi": value,
                            "source_column": source_column,
                            "source_row_index": row.get("row_index"),
                        }
                    )
            considered.sort(key=_canonical_text)
            if missing_cases:
                facts.append(
                    {
                        "story": story,
                        "direction": direction,
                        "availability": "NO_DATA",
                        "eta_bi": None,
                        "required_cases": list(cases),
                        "missing_or_unparseable_cases": sorted(missing_cases),
                        "considered_rows": considered,
                        "governing_row": None,
                    }
                )
                continue
            if not considered:
                facts.append(
                    {
                        "story": story,
                        "direction": direction,
                        "availability": "NO_DATA",
                        "eta_bi": None,
                        "required_cases": list(cases),
                        "missing_or_unparseable_cases": list(cases),
                        "considered_rows": [],
                        "governing_row": None,
                    }
                )
                continue
            governing = max(considered, key=lambda item: (float(item["eta_bi"]), _canonical_text(item)))
            facts.append(
                {
                    "story": story,
                    "direction": direction,
                    "availability": "RESOLVED",
                    "eta_bi": governing["eta_bi"],
                    "required_cases": list(cases),
                    "missing_or_unparseable_cases": [],
                    "considered_rows": considered,
                    "governing_row": governing,
                }
            )
    return tuple(facts)


def seismic_source_fingerprint(source_bytes: bytes) -> str:
    if not isinstance(source_bytes, bytes):
        raise TypeError("source_bytes must be bytes")
    return SEISMIC_SOURCE_FINGERPRINT_PREFIX + hashlib.sha256(source_bytes).hexdigest()


def build_seismic_capture_epoch(*, model_path: object, source_bytes: bytes) -> EvidenceEpoch:
    model_fingerprint = model_fingerprint_from_path(model_path)
    source_fingerprint = seismic_source_fingerprint(source_bytes)
    return EvidenceEpoch(
        epoch_id=live_epoch_id(
            model_fingerprint=model_fingerprint,
            source_fingerprint=source_fingerprint,
        ),
        model_fingerprint=model_fingerprint,
        origin=EvidenceEpochOrigin.LIVE_CAPTURE,
        source_fingerprint=source_fingerprint,
        provenance_refs=(model_fingerprint, source_fingerprint),
    )


def capture_seismic_response(
    *,
    database_tables: object,
    model_path: object,
    modal_case: str,
    a1_x_cases: Sequence[str],
    a1_y_cases: Sequence[str],
    unit_provenance: Mapping[str, object] | None = None,
) -> SeismicCaptureArtifact:
    modal_case = _nonblank(modal_case, "modal_case")
    x_cases = _case_tuple(a1_x_cases, "a1_x_cases")
    y_cases = _case_tuple(a1_y_cases, "a1_y_cases")
    model_fingerprint = model_fingerprint_from_path(model_path)

    modal_fetch, modal_diag = _fetch_exact(database_tables, MODAL_TABLE, modal_case)
    modal_rows = _stable_rows(fetched=modal_fetch, requested_case=modal_case, capture_direction=None)

    a1_direction_payload: dict[str, object] = {}
    story_drift_rows: list[dict[str, object]] = []
    base_reaction_rows: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = [
        {"source_table": MODAL_TABLE, "capture_case": modal_case, **modal_diag}
    ]
    for direction, cases in (("X", x_cases), ("Y", y_cases)):
        a1_rows: list[dict[str, object]] = []
        for case_name in cases:
            a1_fetch, a1_diag = _fetch_exact(database_tables, A1_TABLE, case_name)
            drift_fetch, drift_diag = _fetch_exact(database_tables, STORY_DRIFT_TABLE, case_name)
            base_fetch, base_diag = _fetch_exact(database_tables, BASE_REACTIONS_TABLE, case_name)
            a1_rows.extend(_stable_rows(fetched=a1_fetch, requested_case=case_name, capture_direction=direction))
            story_drift_rows.extend(_stable_rows(fetched=drift_fetch, requested_case=case_name, capture_direction=direction))
            base_reaction_rows.extend(_stable_rows(fetched=base_fetch, requested_case=case_name, capture_direction=direction))
            diagnostics.extend(
                (
                    {"source_table": A1_TABLE, "capture_case": case_name, "capture_direction": direction, **a1_diag},
                    {"source_table": STORY_DRIFT_TABLE, "capture_case": case_name, "capture_direction": direction, **drift_diag},
                    {"source_table": BASE_REACTIONS_TABLE, "capture_case": case_name, "capture_direction": direction, **base_diag},
                )
            )
        a1_rows.sort(key=_canonical_text)
        a1_direction_payload[direction] = {"cases": list(cases), "rows": a1_rows}

    story_drift_rows.sort(key=_canonical_text)
    base_reaction_rows.sort(key=_canonical_text)
    diagnostics.sort(key=_canonical_text)
    capture: dict[str, object] = {
        "contract": CAPTURE_CONTRACT,
        "model_identity": {
            "model_fingerprint": model_fingerprint,
            "observed_model_path": str(model_path),
        },
        "capture_selectors": {
            "modal_case": modal_case,
            "a1_x_cases": list(x_cases),
            "a1_y_cases": list(y_cases),
        },
        "source_tables": [MODAL_TABLE, STORY_DRIFT_TABLE, A1_TABLE, BASE_REACTIONS_TABLE],
        "modal": {"case": modal_case, "rows": modal_rows},
        "a1": {"by_direction": a1_direction_payload},
        "story_drift": {"rows": story_drift_rows},
        "base_reactions": {"rows": base_reaction_rows},
        "unit_provenance": dict(to_jsonable(unit_provenance or {})),
        "capture_diagnostics": diagnostics,
        "truncation_applied": False,
    }
    raw_bytes = _canonical_bytes(capture)
    epoch = build_seismic_capture_epoch(model_path=model_path, source_bytes=raw_bytes)
    return SeismicCaptureArtifact(payload=capture, raw_bytes=raw_bytes, epoch=epoch)


def _evidence_ref(*, epoch: EvidenceEpoch, domain: str, scope_ref: str, direction: str, fact: object) -> str:
    digest = hashlib.sha256(_canonical_bytes(fact)).hexdigest()
    return f"seismic:{epoch.epoch_id}:{domain}:{scope_ref}:{direction}:sha256:{digest}"


def _authority_id(*, epoch: EvidenceEpoch, key: str, scope_ref: str, direction: str, availability: str, value: object, evidence_ref: str) -> str:
    digest = hashlib.sha256(
        _canonical_bytes(
            {
                "epoch_id": epoch.epoch_id,
                "key": key,
                "scope_ref": scope_ref,
                "direction": direction,
                "availability": availability,
                "value": value,
                "evidence_ref": evidence_ref,
            }
        )
    ).hexdigest()
    return f"vs3:external:sha256:{digest}"


def _authority(*, epoch: EvidenceEpoch, key, source_kind, semantic_type, grain, scope_ref: str, direction: str, availability: str, value: object, evidence_ref: str) -> ExternalDependencyAuthority:
    state = AvailabilityState.RESOLVED if availability == "RESOLVED" else AvailabilityState.NO_DATA
    return ExternalDependencyAuthority(
        authority_id=_authority_id(
            epoch=epoch,
            key=key.value,
            scope_ref=scope_ref,
            direction=direction,
            availability=availability,
            value=value,
            evidence_ref=evidence_ref,
        ),
        key=key,
        source_kind=source_kind,
        semantic_type=semantic_type,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=grain,
        scope_ref=scope_ref,
        direction=direction,
        unit=UNIT_DIMENSIONLESS,
        availability=state,
        population_completeness=PopulationCompleteness.FULL,
        value=value,
        provenance_refs=(epoch.epoch_id, epoch.source_fingerprint or "", evidence_ref),
    )


def build_seismic_authorities(capture: SeismicCaptureArtifact) -> tuple[ExternalDependencyAuthority, ...]:
    authorities: list[ExternalDependencyAuthority] = []
    for direction in ("X", "Y"):
        fact = _modal_fact(capture.payload, direction)
        availability = str(fact["availability"])
        evidence_ref = _evidence_ref(
            epoch=capture.epoch,
            domain="modal",
            scope_ref="BUILDING",
            direction=direction,
            fact=fact,
        )
        authorities.append(
            _authority(
                epoch=capture.epoch,
                key=MODAL_RATIO_KEY,
                source_kind=DependencySourceKind.FACT,
                semantic_type=SemanticType.MODAL_CUMULATIVE_EFFECTIVE_MASS_RATIO,
                grain=Grain.DIRECTION,
                scope_ref="BUILDING",
                direction=direction,
                availability=availability,
                value=fact["value"],
                evidence_ref=evidence_ref,
            )
        )
        authorities.append(
            _authority(
                epoch=capture.epoch,
                key=MODAL_EVIDENCE_TRACE_KEY,
                source_kind=DependencySourceKind.CONTEXT,
                semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
                grain=Grain.DIRECTION,
                scope_ref="BUILDING",
                direction=direction,
                availability="RESOLVED",
                value=(evidence_ref,),
                evidence_ref=evidence_ref,
            )
        )

    for fact in _a1_facts(capture.payload):
        story = str(fact["story"])
        direction = str(fact["direction"])
        availability = str(fact["availability"])
        evidence_ref = _evidence_ref(
            epoch=capture.epoch,
            domain="a1",
            scope_ref=story,
            direction=direction,
            fact=fact,
        )
        authorities.append(
            _authority(
                epoch=capture.epoch,
                key=A1_RATIO_KEY,
                source_kind=DependencySourceKind.FACT,
                semantic_type=SemanticType.TORSIONAL_IRREGULARITY_COEFFICIENT,
                grain=Grain.STORY,
                scope_ref=story,
                direction=direction,
                availability=availability,
                value=fact["eta_bi"],
                evidence_ref=evidence_ref,
            )
        )
        authorities.append(
            _authority(
                epoch=capture.epoch,
                key=A1_EVIDENCE_TRACE_KEY,
                source_kind=DependencySourceKind.CONTEXT,
                semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
                grain=Grain.STORY,
                scope_ref=story,
                direction=direction,
                availability="RESOLVED",
                value=(evidence_ref,),
                evidence_ref=evidence_ref,
            )
        )
    return tuple(sorted(authorities, key=lambda item: item.sort_key))


def _targets(*, capture: SeismicCaptureArtifact, modal_4812_applies: bool | None, modal_case_basis_verified: str, a1_eccentricity_basis: str) -> tuple[RuleScopeTarget, ...]:
    targets: list[RuleScopeTarget] = [
        RuleScopeTarget(
            rule_id=MODAL_RULE_ID,
            grain=Grain.DIRECTION,
            scope_ref="BUILDING",
            direction=direction,
            applicability_input=Modal4812ApplicabilityInput(
                modal_4812_applies=modal_4812_applies,
                modal_case_basis_verified=modal_case_basis_verified,
            ),
        )
        for direction in ("X", "Y")
    ]
    facts = _a1_facts(capture.payload)
    if not facts:
        raise LiveSeismicEvidenceConflictError("A1 factual capture contains no story population")
    for fact in facts:
        targets.append(
            RuleScopeTarget(
                rule_id=A1_RULE_ID,
                grain=Grain.STORY,
                scope_ref=str(fact["story"]),
                direction=str(fact["direction"]),
                applicability_input=A1ApplicabilityInput(a1_eccentricity_basis),
            )
        )
    return tuple(targets)


def _findings(program, store, assessment) -> tuple[tuple[Finding, ...], tuple[Finding, ...]]:
    results = {item.instance_id: item.result for item in store.formal_results}
    compiled = {item.instance_id: item for item in program.plan.compiled_closure_inventory}
    outcomes = {item.compiled_record_ref: item for item in assessment.closure_outcomes}
    check_findings: list[Finding] = []
    closure_findings: list[Finding] = []
    for instance in program.plan.compiled_rule_instances:
        result = results.get(instance)
        if result is not None:
            finding = build_finding_from_check_result(
                instance_id=instance,
                result=result,
                evidence_refs=tuple(str(item) for item in result.evidence if isinstance(item, str)),
                provenance_refs=(),
            )
            if finding is not None:
                check_findings.append(finding)
        outcome = outcomes[instance]
        finding = build_finding_from_rule_closure(
            compiled_record=compiled[instance],
            outcome=outcome,
            evidence_refs=(),
            provenance_refs=(),
        )
        if finding is not None:
            closure_findings.append(finding)
    return (
        tuple(sorted(check_findings, key=lambda item: item.finding_id)),
        tuple(sorted(closure_findings, key=lambda item: item.finding_id)),
    )


def run_live_seismic_response_f0_pack(
    *,
    capture: SeismicCaptureArtifact,
    modal_4812_applies: bool | None,
    modal_case_basis_verified: str,
    a1_eccentricity_basis: str,
) -> LiveSeismicPackRun:
    if capture.epoch.origin is not EvidenceEpochOrigin.LIVE_CAPTURE:
        raise LiveSeismicEvidenceConflictError("VS-3 requires LIVE_CAPTURE EvidenceEpoch")
    if capture.payload.get("truncation_applied") is not False:
        raise LiveSeismicEvidenceConflictError("seismic factual capture is truncated")
    if capture.epoch.model_fingerprint != capture.payload.get("model_identity", {}).get("model_fingerprint"):
        raise LiveSeismicEvidenceConflictError("seismic capture model identity mismatch")

    authorities = build_seismic_authorities(capture)
    targets = _targets(
        capture=capture,
        modal_4812_applies=modal_4812_applies,
        modal_case_basis_verified=modal_case_basis_verified,
        a1_eccentricity_basis=a1_eccentricity_basis,
    )
    program = RegulatoryCompiler.compile(
        VS3_SEISMIC_REGISTRY,
        RegulatoryCompileInputs(rule_targets=targets, external_authorities=authorities),
    )
    store = RegulatoryEngine.execute(program)
    assessment = AssessmentEngine.reconcile(program, store)
    check_findings, closure_findings = _findings(program, store, assessment)
    return LiveSeismicPackRun(
        capture=capture,
        modal_4812_applies=modal_4812_applies,
        modal_case_basis_verified=modal_case_basis_verified,
        a1_eccentricity_basis=a1_eccentricity_basis,
        authorities=authorities,
        program=program,
        store=store,
        assessment=assessment,
        check_findings=check_findings,
        closure_findings=closure_findings,
    )


def write_seismic_capture(path: Path, capture: SeismicCaptureArtifact) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(capture.raw_bytes)


__all__ = [
    "SEISMIC_SOURCE_FINGERPRINT_PREFIX",
    "CAPTURE_CONTRACT",
    "MODAL_TABLE",
    "STORY_DRIFT_TABLE",
    "A1_TABLE",
    "BASE_REACTIONS_TABLE",
    "BLOCKED_BY_LIVE_SEISMIC_EVIDENCE_CONFLICT",
    "BLOCKED_BY_MODAL_SOURCE_SEMANTICS",
    "LiveSeismicResponseError",
    "LiveSeismicEvidenceConflictError",
    "ModalSourceSemanticsError",
    "SeismicCaptureArtifact",
    "LiveSeismicPackRun",
    "seismic_source_fingerprint",
    "build_seismic_capture_epoch",
    "capture_seismic_response",
    "build_seismic_authorities",
    "run_live_seismic_response_f0_pack",
    "write_seismic_capture",
]
