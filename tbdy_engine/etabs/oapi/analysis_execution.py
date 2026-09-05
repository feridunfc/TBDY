"""Typed factual ETABS analysis-execution ABI for B5.

This module owns only the exact CSI/OAPI call boundary for analysis run scope,
result clearing, execution, and full case-status observation.  It does not
choose engineering scope, decide result freshness, issue lineage identities,
or expose raw ETABS COM capabilities.

All write/execution calls reuse the already-approved B4T bounded mutation
transport on the gateway-owned STA thread.  Reads reuse the verified safety
bridge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Sequence

from etabs_gateway.mutation_transport import (
    _B4T_MUTATION_TRANSPORT_KEY,
    _execute_bounded_model_mutation,
)

from tbdy_engine.etabs.safety import EtabsVerifiedSession, _execute_verified_read

from .contracts import EtabsOAPIError


RUN_CASE_FLAG_SNAPSHOT_CONTRACT = "ETABS_RUN_CASE_FLAG_SNAPSHOT_V1"
RUN_CASE_FLAG_SET_FACT_CONTRACT = "ETABS_RUN_CASE_FLAG_SET_FACT_V1"
CASE_STATUS_POPULATION_CONTRACT = "ETABS_CASE_STATUS_POPULATION_V1"
DELETE_ANALYSIS_RESULTS_FACT_CONTRACT = "ETABS_DELETE_ANALYSIS_RESULTS_FACT_V1"
RUN_ANALYSIS_FACT_CONTRACT = "ETABS_RUN_ANALYSIS_FACT_V1"
ANALYSIS_EXECUTION_EVIDENCE_PREFIX = "etabs-analysis-execution:sha256:"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsOAPIError(f"{label} must be a nonblank canonical string")
    return value


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return ANALYSIS_EXECUTION_EVIDENCE_PREFIX + hashlib.sha256(encoded).hexdigest()


def _return_code(value: object, *, method: str) -> int:
    if type(value) is int:
        return int(value)
    if isinstance(value, (tuple, list)):
        candidates = tuple(int(item) for item in value if type(item) is int)
        if len(candidates) == 1:
            return candidates[0]
    raise EtabsOAPIError(f"{method} returned unsupported return-code ABI shape: {value!r}")


def _decode_counted_population(
    raw: object,
    *,
    method: str,
    value_kind: str,
) -> tuple[tuple[tuple[str, object], ...], int]:
    """Decode CSI ByRef [count, names, values, ret] using count as authority.

    COM SAFEARRAY payloads may retain capacity beyond the authoritative count;
    only the prefix selected by ``count`` is consumed.  The prefix itself must
    be complete and type-exact.
    """
    if not isinstance(raw, (tuple, list)) or len(raw) != 4:
        raise EtabsOAPIError(
            f"{method} returned unsupported Python ABI shape: {raw!r}"
        )
    count_raw, names_raw, values_raw, ret_raw = raw
    if type(count_raw) is not int or count_raw < 0:
        raise EtabsOAPIError(f"{method} returned invalid authoritative count: {count_raw!r}")
    if type(ret_raw) is not int:
        raise EtabsOAPIError(f"{method} returned invalid return code: {ret_raw!r}")
    if not isinstance(names_raw, (tuple, list)) or not isinstance(values_raw, (tuple, list)):
        raise EtabsOAPIError(f"{method} did not return indexable name/value arrays")
    count = int(count_raw)
    if len(names_raw) < count or len(values_raw) < count:
        raise EtabsOAPIError(
            f"{method} returned payload shorter than authoritative count={count}"
        )

    names = tuple(names_raw[:count])
    values = tuple(values_raw[:count])
    if any(not isinstance(name, str) or not name.strip() or name != name.strip() for name in names):
        raise EtabsOAPIError(f"{method} returned invalid case-name prefix")
    if len(set(names)) != len(names):
        raise EtabsOAPIError(f"{method} returned duplicate case names")

    if value_kind == "bool":
        if any(type(value) is not bool for value in values):
            raise EtabsOAPIError(f"{method} returned non-boolean run flag")
    elif value_kind == "int":
        if any(type(value) is not int for value in values):
            raise EtabsOAPIError(f"{method} returned non-integer case status")
    else:  # pragma: no cover - internal programming guard
        raise AssertionError(value_kind)

    return tuple((str(name), value) for name, value in zip(names, values, strict=True)), int(ret_raw)


@dataclass(frozen=True, slots=True)
class RunCaseFlagSnapshotFact:
    case_flags: tuple[tuple[str, bool], ...]
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = RUN_CASE_FLAG_SNAPSHOT_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != RUN_CASE_FLAG_SNAPSHOT_CONTRACT:
            raise EtabsOAPIError("run-case flag snapshot contract mismatch")
        normalized: list[tuple[str, bool]] = []
        for name, run in self.case_flags:
            normalized.append((_text(name, "case_name"), run))
            if type(run) is not bool:
                raise EtabsOAPIError("run flag must be bool")
        if len({name for name, _ in normalized}) != len(normalized):
            raise EtabsOAPIError("run-case flag snapshot contains duplicate cases")
        if type(self.return_code) is not int:
            raise EtabsOAPIError("return_code must be int")
        ordered = tuple(sorted(normalized, key=lambda item: item[0]))
        object.__setattr__(self, "case_flags", ordered)
        object.__setattr__(
            self,
            "evidence_ref",
            _digest({
                "contract": self.contract,
                "case_flags": [[name, run] for name, run in ordered],
                "return_code": self.return_code,
            }),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0

    @property
    def case_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.case_flags)

    def as_mapping(self) -> dict[str, bool]:
        return dict(self.case_flags)


@dataclass(frozen=True, slots=True)
class CaseStatusPopulationFact:
    case_statuses: tuple[tuple[str, int], ...]
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = CASE_STATUS_POPULATION_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != CASE_STATUS_POPULATION_CONTRACT:
            raise EtabsOAPIError("case-status population contract mismatch")
        normalized: list[tuple[str, int]] = []
        for name, status in self.case_statuses:
            if type(status) is not int:
                raise EtabsOAPIError("case status must be int")
            normalized.append((_text(name, "case_name"), int(status)))
        if len({name for name, _ in normalized}) != len(normalized):
            raise EtabsOAPIError("case-status population contains duplicate cases")
        if type(self.return_code) is not int:
            raise EtabsOAPIError("return_code must be int")
        ordered = tuple(sorted(normalized, key=lambda item: item[0]))
        object.__setattr__(self, "case_statuses", ordered)
        object.__setattr__(
            self,
            "evidence_ref",
            _digest({
                "contract": self.contract,
                "case_statuses": [[name, status] for name, status in ordered],
                "return_code": self.return_code,
            }),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0

    def as_mapping(self) -> dict[str, int]:
        return dict(self.case_statuses)


@dataclass(frozen=True, slots=True)
class RunCaseFlagSetFact:
    case_name: str
    run: bool
    all_cases: bool
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = RUN_CASE_FLAG_SET_FACT_CONTRACT

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_name", _text(self.case_name, "case_name"))
        if type(self.run) is not bool or type(self.all_cases) is not bool:
            raise EtabsOAPIError("run/all_cases must be bool")
        if type(self.return_code) is not int:
            raise EtabsOAPIError("return_code must be int")
        if self.contract != RUN_CASE_FLAG_SET_FACT_CONTRACT:
            raise EtabsOAPIError("run-case flag set contract mismatch")
        object.__setattr__(
            self,
            "evidence_ref",
            _digest({
                "contract": self.contract,
                "case_name": self.case_name,
                "run": self.run,
                "all_cases": self.all_cases,
                "return_code": self.return_code,
            }),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


@dataclass(frozen=True, slots=True)
class DeleteAnalysisResultsFact:
    case_name: str
    all_cases: bool
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = DELETE_ANALYSIS_RESULTS_FACT_CONTRACT

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_name", _text(self.case_name, "case_name"))
        if type(self.all_cases) is not bool:
            raise EtabsOAPIError("all_cases must be bool")
        if type(self.return_code) is not int:
            raise EtabsOAPIError("return_code must be int")
        if self.contract != DELETE_ANALYSIS_RESULTS_FACT_CONTRACT:
            raise EtabsOAPIError("delete-analysis-results contract mismatch")
        object.__setattr__(
            self,
            "evidence_ref",
            _digest({
                "contract": self.contract,
                "case_name": self.case_name,
                "all_cases": self.all_cases,
                "return_code": self.return_code,
            }),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


@dataclass(frozen=True, slots=True)
class RunAnalysisFact:
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = RUN_ANALYSIS_FACT_CONTRACT

    def __post_init__(self) -> None:
        if type(self.return_code) is not int:
            raise EtabsOAPIError("return_code must be int")
        if self.contract != RUN_ANALYSIS_FACT_CONTRACT:
            raise EtabsOAPIError("run-analysis fact contract mismatch")
        object.__setattr__(
            self,
            "evidence_ref",
            _digest({"contract": self.contract, "return_code": self.return_code}),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


def get_run_case_flags_from_session(
    session: EtabsVerifiedSession,
    *,
    timeout_seconds: float = 30.0,
) -> RunCaseFlagSnapshotFact:
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    def acquire(_application: object, model_api: Any) -> RunCaseFlagSnapshotFact:
        raw = model_api.Analyze.GetRunCaseFlag()
        values, return_code = _decode_counted_population(
            raw,
            method="Analyze.GetRunCaseFlag",
            value_kind="bool",
        )
        return RunCaseFlagSnapshotFact(
            case_flags=tuple((name, bool(run)) for name, run in values),
            return_code=return_code,
        )

    return _execute_verified_read(
        session,
        acquire,
        operation="oapi_analyze_get_run_case_flag",
        timeout_seconds=timeout,
    )


def get_case_status_population_from_session(
    session: EtabsVerifiedSession,
    *,
    timeout_seconds: float = 30.0,
) -> CaseStatusPopulationFact:
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    def acquire(_application: object, model_api: Any) -> CaseStatusPopulationFact:
        raw = model_api.Analyze.GetCaseStatus()
        values, return_code = _decode_counted_population(
            raw,
            method="Analyze.GetCaseStatus",
            value_kind="int",
        )
        return CaseStatusPopulationFact(
            case_statuses=tuple((name, int(status)) for name, status in values),
            return_code=return_code,
        )

    return _execute_verified_read(
        session,
        acquire,
        operation="oapi_analyze_get_case_status_population",
        timeout_seconds=timeout,
    )


def set_run_case_flag_from_session(
    session: EtabsVerifiedSession,
    *,
    case_name: str,
    run: bool,
    all_cases: bool = False,
    timeout_seconds: float = 30.0,
) -> RunCaseFlagSetFact:
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    name = _text(case_name, "case_name")
    if type(run) is not bool or type(all_cases) is not bool:
        raise TypeError("run/all_cases must be bool")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    def mutate(model_api: Any) -> RunCaseFlagSetFact:
        raw = model_api.Analyze.SetRunCaseFlag(name, run, all_cases)
        return RunCaseFlagSetFact(
            case_name=name,
            run=run,
            all_cases=all_cases,
            return_code=_return_code(raw, method="Analyze.SetRunCaseFlag"),
        )

    return _execute_bounded_model_mutation(
        session._gateway_session,  # noqa: SLF001 - trusted OAPI -> B4T boundary
        mutate,
        operation="oapi_analyze_set_run_case_flag",
        timeout_seconds=timeout,
        _transport_key=_B4T_MUTATION_TRANSPORT_KEY,
    )


def delete_analysis_results_from_session(
    session: EtabsVerifiedSession,
    *,
    case_name: str,
    all_cases: bool = False,
    timeout_seconds: float = 30.0,
) -> DeleteAnalysisResultsFact:
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    name = _text(case_name, "case_name")
    if type(all_cases) is not bool:
        raise TypeError("all_cases must be bool")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    def mutate(model_api: Any) -> DeleteAnalysisResultsFact:
        raw = model_api.Analyze.DeleteResults(name, all_cases)
        return DeleteAnalysisResultsFact(
            case_name=name,
            all_cases=all_cases,
            return_code=_return_code(raw, method="Analyze.DeleteResults"),
        )

    return _execute_bounded_model_mutation(
        session._gateway_session,  # noqa: SLF001 - trusted OAPI -> B4T boundary
        mutate,
        operation="oapi_analyze_delete_results",
        timeout_seconds=timeout,
        _transport_key=_B4T_MUTATION_TRANSPORT_KEY,
    )


def run_analysis_from_session(
    session: EtabsVerifiedSession,
    *,
    timeout_seconds: float = 300.0,
) -> RunAnalysisFact:
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    def execute(model_api: Any) -> RunAnalysisFact:
        raw = model_api.Analyze.RunAnalysis()
        return RunAnalysisFact(
            return_code=_return_code(raw, method="Analyze.RunAnalysis"),
        )

    return _execute_bounded_model_mutation(
        session._gateway_session,  # noqa: SLF001 - trusted OAPI -> B4T boundary
        execute,
        operation="oapi_analyze_run_analysis",
        timeout_seconds=timeout,
        _transport_key=_B4T_MUTATION_TRANSPORT_KEY,
    )


__all__ = [
    "ANALYSIS_EXECUTION_EVIDENCE_PREFIX",
    "CASE_STATUS_POPULATION_CONTRACT",
    "DELETE_ANALYSIS_RESULTS_FACT_CONTRACT",
    "RUN_ANALYSIS_FACT_CONTRACT",
    "RUN_CASE_FLAG_SET_FACT_CONTRACT",
    "RUN_CASE_FLAG_SNAPSHOT_CONTRACT",
    "CaseStatusPopulationFact",
    "DeleteAnalysisResultsFact",
    "RunAnalysisFact",
    "RunCaseFlagSetFact",
    "RunCaseFlagSnapshotFact",
    "delete_analysis_results_from_session",
    "get_case_status_population_from_session",
    "get_run_case_flags_from_session",
    "run_analysis_from_session",
    "set_run_case_flag_from_session",
]
