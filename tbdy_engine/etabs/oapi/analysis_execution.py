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

from tbdy_engine.etabs.safety import EtabsVerifiedSession, _execute_verified_read, read_session_identity

from .contracts import EtabsOAPIError


RUN_CASE_FLAG_SNAPSHOT_CONTRACT = "ETABS_RUN_CASE_FLAG_SNAPSHOT_V1"
RUN_CASE_FLAG_SET_FACT_CONTRACT = "ETABS_RUN_CASE_FLAG_SET_FACT_V1"
CASE_STATUS_POPULATION_CONTRACT = "ETABS_CASE_STATUS_POPULATION_V1"
DEFINED_ANALYSIS_CASE_POPULATION_CONTRACT = "ETABS_DEFINED_ANALYSIS_CASE_POPULATION_V1"
LOAD_CASE_TYPE_RUNTIME_FACT_CONTRACT = "ETABS_LOAD_CASE_TYPE_RUNTIME_FACT_V1"
RESPONSE_SPECTRUM_MODAL_CASE_FACT_CONTRACT = "ETABS_RESPONSE_SPECTRUM_MODAL_CASE_FACT_V1"
ETABS_RUNTIME_VERSION_FACT_CONTRACT = "ETABS_RUNTIME_VERSION_FACT_V1"
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


def _decode_counted_names(
    raw: object,
    *,
    method: str,
) -> tuple[tuple[str, ...], int]:
    """Decode CSI ByRef [count, names, ret] using count as authority."""
    if not isinstance(raw, (tuple, list)) or len(raw) != 3:
        raise EtabsOAPIError(
            f"{method} returned unsupported Python ABI shape: {raw!r}"
        )
    count_raw, names_raw, ret_raw = raw
    if type(count_raw) is not int or count_raw < 0:
        raise EtabsOAPIError(
            f"{method} returned invalid authoritative count: {count_raw!r}"
        )
    if type(ret_raw) is not int:
        raise EtabsOAPIError(
            f"{method} returned invalid return code: {ret_raw!r}"
        )
    if not isinstance(names_raw, (tuple, list)):
        raise EtabsOAPIError(
            f"{method} did not return an indexable name array"
        )

    count = int(count_raw)
    if len(names_raw) < count:
        raise EtabsOAPIError(
            f"{method} returned payload shorter than authoritative count={count}"
        )

    names = tuple(names_raw[:count])
    if any(
        not isinstance(name, str)
        or not name.strip()
        or name != name.strip()
        for name in names
    ):
        raise EtabsOAPIError(
            f"{method} returned invalid case-name prefix"
        )
    if len(set(names)) != len(names):
        raise EtabsOAPIError(
            f"{method} returned duplicate case names"
        )
    return tuple(str(name) for name in names), int(ret_raw)


@dataclass(frozen=True, slots=True)
class DefinedAnalysisCasePopulationFact:
    case_names: tuple[str, ...]
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = DEFINED_ANALYSIS_CASE_POPULATION_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != DEFINED_ANALYSIS_CASE_POPULATION_CONTRACT:
            raise EtabsOAPIError(
                "defined-analysis-case population contract mismatch"
            )
        names = tuple(sorted(_text(name, "case_name") for name in self.case_names))
        if len(set(names)) != len(names):
            raise EtabsOAPIError(
                "defined-analysis-case population contains duplicate cases"
            )
        if type(self.return_code) is not int:
            raise EtabsOAPIError("return_code must be int")
        object.__setattr__(self, "case_names", names)
        object.__setattr__(
            self,
            "evidence_ref",
            _digest({
                "contract": self.contract,
                "case_names": list(names),
                "return_code": self.return_code,
            }),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


@dataclass(frozen=True, slots=True)
class EtabsRuntimeVersionFact:
    """Exact factual SapModel.GetVersion runtime observation."""

    program_version: str
    internal_version_number: float
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = ETABS_RUNTIME_VERSION_FACT_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != ETABS_RUNTIME_VERSION_FACT_CONTRACT:
            raise EtabsOAPIError(
                "ETABS runtime-version fact contract mismatch"
            )

        object.__setattr__(
            self,
            "program_version",
            _text(self.program_version, "program_version"),
        )

        if type(self.internal_version_number) is not float:
            raise EtabsOAPIError(
                "internal_version_number must be exact float"
            )
        if type(self.return_code) is not int:
            raise EtabsOAPIError(
                "return_code must be exact int"
            )

        object.__setattr__(
            self,
            "evidence_ref",
            _digest({
                "contract": self.contract,
                "program_version": self.program_version,
                "internal_version_number": self.internal_version_number,
                "return_code": self.return_code,
            }),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


@dataclass(frozen=True, slots=True)
class LoadCaseTypeRuntimeFact:
    """Exact observed GetTypeOAPI_1 Python projection.

    CSI documents the ByRef fields as CaseType, SubType, DesignType,
    DesignTypeOption and Auto. ETABS v23.2 live observation returned runtime
    Auto-slot values beyond the documented 0/1 domain. Preserve the integer
    fact exactly; semantic compatibility policy belongs above this ABI layer.
    """

    case_name: str
    case_type: int
    sub_type: int
    design_type: int
    design_type_option: int
    runtime_auto_slot_value: int
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = LOAD_CASE_TYPE_RUNTIME_FACT_CONTRACT

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "case_name",
            _text(self.case_name, "case_name"),
        )
        if self.contract != LOAD_CASE_TYPE_RUNTIME_FACT_CONTRACT:
            raise EtabsOAPIError(
                "load-case type runtime fact contract mismatch"
            )
        for name in (
            "case_type",
            "sub_type",
            "design_type",
            "design_type_option",
            "runtime_auto_slot_value",
            "return_code",
        ):
            if type(getattr(self, name)) is not int:
                raise EtabsOAPIError(
                    f"{name} must be an exact integer"
                )

        object.__setattr__(
            self,
            "evidence_ref",
            _digest({
                "contract": self.contract,
                "case_name": self.case_name,
                "case_type": self.case_type,
                "sub_type": self.sub_type,
                "design_type": self.design_type,
                "design_type_option": self.design_type_option,
                "runtime_auto_slot_value": self.runtime_auto_slot_value,
                "return_code": self.return_code,
            }),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


@dataclass(frozen=True, slots=True)
class ResponseSpectrumModalCaseFact:
    """Exact factual ResponseSpectrum.GetModalCase Python projection."""

    response_spectrum_case_name: str
    modal_case_name: str
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = RESPONSE_SPECTRUM_MODAL_CASE_FACT_CONTRACT

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "response_spectrum_case_name",
            _text(self.response_spectrum_case_name, "response_spectrum_case_name"),
        )
        object.__setattr__(
            self,
            "modal_case_name",
            _text(self.modal_case_name, "modal_case_name"),
        )
        if self.contract != RESPONSE_SPECTRUM_MODAL_CASE_FACT_CONTRACT:
            raise EtabsOAPIError("response-spectrum modal-case fact contract mismatch")
        if type(self.return_code) is not int:
            raise EtabsOAPIError("return_code must be exact int")
        object.__setattr__(
            self,
            "evidence_ref",
            _digest({
                "contract": self.contract,
                "response_spectrum_case_name": self.response_spectrum_case_name,
                "modal_case_name": self.modal_case_name,
                "return_code": self.return_code,
            }),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


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


def get_defined_analysis_cases_from_session(
    session: EtabsVerifiedSession,
    *,
    timeout_seconds: float = 30.0,
) -> DefinedAnalysisCasePopulationFact:
    """Retrieve the exact currently-defined LoadCases.GetNameList population."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    def acquire(
        _application: object,
        model_api: Any,
    ) -> DefinedAnalysisCasePopulationFact:
        raw = model_api.LoadCases.GetNameList()
        names, return_code = _decode_counted_names(
            raw,
            method="LoadCases.GetNameList",
        )
        return DefinedAnalysisCasePopulationFact(
            case_names=names,
            return_code=return_code,
        )

    return _execute_verified_read(
        session,
        acquire,
        operation="oapi_load_cases_get_name_list",
        timeout_seconds=timeout,
    )


def get_etabs_runtime_version_fact_from_session(
    session: EtabsVerifiedSession,
    *,
    timeout_seconds: float = 30.0,
) -> EtabsRuntimeVersionFact:
    """Read the exact SapModel.GetVersion runtime projection.

    Live ETABS 23.2.0 acceptance established the Python projection:
    [program_version: str, internal_version_number: float, ret: int].
    """
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")

    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    def acquire(
        _application: object,
        model_api: Any,
    ) -> EtabsRuntimeVersionFact:
        raw = model_api.GetVersion()

        if not isinstance(raw, (tuple, list)) or len(raw) != 3:
            raise EtabsOAPIError(
                "SapModel.GetVersion returned unsupported "
                f"Python ABI shape: {raw!r}"
            )

        program_version, internal_version_number, return_code = raw

        if (
            not isinstance(program_version, str)
            or not program_version.strip()
            or program_version != program_version.strip()
        ):
            raise EtabsOAPIError(
                "SapModel.GetVersion returned invalid program version"
            )
        if type(internal_version_number) is not float:
            raise EtabsOAPIError(
                "SapModel.GetVersion returned invalid internal "
                f"version-number type: {raw!r}"
            )
        if type(return_code) is not int:
            raise EtabsOAPIError(
                "SapModel.GetVersion returned invalid return-code "
                f"type: {raw!r}"
            )

        return EtabsRuntimeVersionFact(
            program_version=program_version,
            internal_version_number=internal_version_number,
            return_code=return_code,
        )

    return _execute_verified_read(
        session,
        acquire,
        operation="oapi_sap_model_get_version",
        timeout_seconds=timeout,
    )


def get_load_case_type_runtime_fact_from_session(
    session: EtabsVerifiedSession,
    *,
    case_name: str,
    timeout_seconds: float = 30.0,
) -> LoadCaseTypeRuntimeFact:
    """Read one exact GetTypeOAPI_1 runtime projection.

    The six-item Python projection is acceptance-gated runtime ABI:
    [CaseType, SubType, DesignType, DesignTypeOption, Auto, ret].
    The OAPI layer preserves the integer Auto slot without interpreting
    undocumented ETABS v23.2 values.
    """
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")

    name = _text(case_name, "case_name")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    def acquire(
        _application: object,
        model_api: Any,
    ) -> LoadCaseTypeRuntimeFact:
        raw = model_api.LoadCases.GetTypeOAPI_1(name)

        if not isinstance(raw, (tuple, list)) or len(raw) != 6:
            raise EtabsOAPIError(
                "LoadCases.GetTypeOAPI_1 returned unsupported "
                f"Python ABI shape: {raw!r}"
            )

        if any(type(value) is not int for value in raw):
            raise EtabsOAPIError(
                "LoadCases.GetTypeOAPI_1 returned non-integer "
                f"runtime projection: {raw!r}"
            )

        (
            case_type,
            sub_type,
            design_type,
            design_type_option,
            runtime_auto_slot_value,
            return_code,
        ) = raw

        return LoadCaseTypeRuntimeFact(
            case_name=name,
            case_type=case_type,
            sub_type=sub_type,
            design_type=design_type,
            design_type_option=design_type_option,
            runtime_auto_slot_value=runtime_auto_slot_value,
            return_code=return_code,
        )

    return _execute_verified_read(
        session,
        acquire,
        operation="oapi_load_cases_get_type_oapi_1",
        timeout_seconds=timeout,
    )


def get_response_spectrum_modal_case_from_session(
    session: EtabsVerifiedSession,
    *,
    response_spectrum_case_name: str,
    timeout_seconds: float = 30.0,
) -> ResponseSpectrumModalCaseFact:
    """Read exact ResponseSpectrum.GetModalCase factual dependency."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    name = _text(response_spectrum_case_name, "response_spectrum_case_name")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    def acquire(_application: object, model_api: Any) -> ResponseSpectrumModalCaseFact:
        load_cases = getattr(model_api, "LoadCases", None)
        response_spectrum = getattr(load_cases, "ResponseSpectrum", None)
        method = getattr(response_spectrum, "GetModalCase", None)
        if method is None:
            raise EtabsOAPIError("SapModel.LoadCases.ResponseSpectrum.GetModalCase is unavailable")
        raw = method(name)
        if not isinstance(raw, (tuple, list)) or len(raw) != 2:
            raise EtabsOAPIError(
                "LoadCases.ResponseSpectrum.GetModalCase returned unsupported "
                f"Python ABI shape: {raw!r}"
            )
        modal_case_name, return_code = raw
        if (
            not isinstance(modal_case_name, str)
            or not modal_case_name.strip()
            or modal_case_name != modal_case_name.strip()
        ):
            raise EtabsOAPIError(
                "LoadCases.ResponseSpectrum.GetModalCase returned invalid "
                f"modal-case identity: {raw!r}"
            )
        if type(return_code) is not int:
            raise EtabsOAPIError(
                "LoadCases.ResponseSpectrum.GetModalCase returned invalid "
                f"return-code type: {raw!r}"
            )
        return ResponseSpectrumModalCaseFact(
            response_spectrum_case_name=name,
            modal_case_name=modal_case_name,
            return_code=return_code,
        )

    return _execute_verified_read(
        session,
        acquire,
        operation="oapi_load_cases_response_spectrum_get_modal_case",
        timeout_seconds=timeout,
    )


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
    "DEFINED_ANALYSIS_CASE_POPULATION_CONTRACT",
    "LOAD_CASE_TYPE_RUNTIME_FACT_CONTRACT",
    "RESPONSE_SPECTRUM_MODAL_CASE_FACT_CONTRACT",
    "ETABS_RUNTIME_VERSION_FACT_CONTRACT",
    "RUN_ANALYSIS_FACT_CONTRACT",
    "RUN_CASE_FLAG_SET_FACT_CONTRACT",
    "RUN_CASE_FLAG_SNAPSHOT_CONTRACT",
    "CaseStatusPopulationFact",
    "DefinedAnalysisCasePopulationFact",
    "EtabsRuntimeVersionFact",
    "LoadCaseTypeRuntimeFact",
    "ResponseSpectrumModalCaseFact",
    "DeleteAnalysisResultsFact",
    "RunAnalysisFact",
    "RunCaseFlagSetFact",
    "RunCaseFlagSnapshotFact",
    "delete_analysis_results_from_session",
    "get_case_status_population_from_session",
    "get_defined_analysis_cases_from_session",
    "get_etabs_runtime_version_fact_from_session",
    "get_load_case_type_runtime_fact_from_session",
    "get_response_spectrum_modal_case_from_session",
    "get_run_case_flags_from_session",
    "run_analysis_from_session",
    "set_run_case_flag_from_session",
]


# CSI API ETABS v1 (2024), pages 675–698. These are ByRef output names,
# not an interpretation of undocumented integer enumerations. No setter is
# reachable through this bounded acquisition owner.
RESPONSE_SPECTRUM_SETTINGS_SOURCE = (
    "CSI_API_ETABS_v1_2024:sha256:"
    "6ee860c75d37215d6d6c44251e94788709439e155b68a7939e893a66f01dda27#675-698"
)
_RS_SETTING_OUTPUTS = {
    "GetModalCase": ("ModalCase",),
    "GetLoads": ("NumberLoads", "LoadName", "Func", "SF", "CSys", "Ang"),
    "GetModalComb_1": ("MyType", "F1", "F2", "PeriodicRigidCombType", "Td"),
    "GetDirComb": ("MyType", "SF"),
    "GetDampType": ("DampType",),
    "GetDampConstant": ("Damp",),
    "GetDampInterpolated": ("DampType", "NumberItems", "Time", "Damp"),
    "GetDampProportional": ("DampType", "DampA", "DampB", "DampF1", "DampF2", "DampD1", "DampD2"),
    "GetDampOverrides": ("NumberItems", "Mode", "Damp"),
    "GetEccentricity": ("Eccen",),
    "GetDiaphragmEccentricityOverride": ("Num", "Diaph", "Eccen"),
}


@dataclass(frozen=True, slots=True)
class ResponseSpectrumSettingReadFact:
    method: str
    outputs: tuple[tuple[str, object], ...]
    raw_response: tuple[object, ...]
    return_code: int
    source_ref: str = RESPONSE_SPECTRUM_SETTINGS_SOURCE

    @property
    def success(self) -> bool:
        return self.return_code == 0


@dataclass(frozen=True, slots=True)
class ResponseSpectrumSettingsFact:
    case_name: str
    settings: tuple[ResponseSpectrumSettingReadFact, ...]
    source_model_ref: str
    session_ref: str
    capture_ref: str
    observation_before: str
    observation_after: str
    # Factual settings are not an analysis generation or a design state.
    analysis_result_qualified: bool = field(default=False, init=False)

    @property
    def evidence_ref(self) -> str:
        return _digest({"case": self.case_name, "source": self.source_model_ref,
                        "session": self.session_ref, "capture": self.capture_ref,
                        "before": self.observation_before, "after": self.observation_after,
                        "raw": [(s.method, s.raw_response) for s in self.settings]})


def _decode_response_spectrum_setting(method: str, raw: object) -> ResponseSpectrumSettingReadFact:
    """Decode reviewed output order; retain nonzero results without promotion.

    Inactive damping getters may return nonzero. Their outputs remain raw and
    unqualified; a successful unrelated getter cannot qualify them.
    """
    import math
    from copy import deepcopy
    keys = _RS_SETTING_OUTPUTS[method]
    if not isinstance(raw, (tuple, list)) or len(raw) != len(keys) + 1 or type(raw[-1]) is not int:
        raise EtabsOAPIError(f"ResponseSpectrum.{method}: unsupported ABI shape")
    frozen = tuple(deepcopy(raw))
    if raw[-1] != 0:
        return ResponseSpectrumSettingReadFact(method, (), frozen, raw[-1])
    outputs = tuple(zip(keys, frozen[:-1]))
    array_fields = {
        "GetLoads": ("LoadName", "Func", "SF", "CSys", "Ang"),
        "GetDampInterpolated": ("Time", "Damp"),
        "GetDampOverrides": ("Mode", "Damp"),
        "GetDiaphragmEccentricityOverride": ("Diaph", "Eccen"),
    }
    values = dict(outputs)
    count_key = next((key for key in ("NumberLoads", "NumberItems", "Num") if key in values), None)
    for key, value in outputs:
        if key in {"NumberLoads", "NumberItems", "Num", "MyType", "PeriodicRigidCombType", "DampType"}:
            if type(value) is not int or value < 0:
                raise EtabsOAPIError(f"ResponseSpectrum.{method}.{key}: invalid integer")
        elif key == "ModalCase":
            _text(value, key)
        elif key in array_fields.get(method, ()) and (isinstance(value, (list, tuple)) or
                (value is None and count_key is not None and values[count_key] == 0)):
            continue  # Counted prefix validated below; preserve unused capacity.
        elif type(value) not in (int, float) or not math.isfinite(value):
            raise EtabsOAPIError(f"ResponseSpectrum.{method}.{key}: invalid scalar")
    if count_key:
        count = values[count_key]
        array_keys = array_fields[method]
        for key in array_keys:
            array = values[key]
            if count == 0 and array is None:
                continue
            if not isinstance(array, (tuple, list)) or len(array) < count:
                raise EtabsOAPIError(f"ResponseSpectrum.{method}.{key}: incomplete counted population")
            for value in array[:count]:
                if key in {"LoadName", "Func", "CSys", "Diaph"}:
                    _text(value, key)
                elif key == "Mode":
                    if type(value) is not int or value <= 0:
                        raise EtabsOAPIError(f"ResponseSpectrum.{method}.Mode: invalid mode")
                elif type(value) not in (int, float) or not math.isfinite(value):
                    raise EtabsOAPIError(f"ResponseSpectrum.{method}.{key}: invalid numeric array")
    return ResponseSpectrumSettingReadFact(method, outputs, frozen, raw[-1])


def get_response_spectrum_settings_from_session(
    session: EtabsVerifiedSession, *, case_name: str, timeout_seconds: float = 30.0,
) -> ResponseSpectrumSettingsFact:
    """One fresh before/after bounded factual settings capture on verified STA.

    Numeric method codes are retained, never guessed from case names. This
    protected-source reader does not issue scratch/B5 lineage.
    """
    import math
    import uuid
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    name = _text(case_name, "case_name")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be finite and positive")
    expected = session.identity
    if expected.program_version != "23.2.0" or expected.program_api_version != 2.014:
        raise EtabsOAPIError("ResponseSpectrum settings: unsupported ETABS/API version")
    gateway = session._gateway_session
    capture = f"response-spectrum-settings-capture:{uuid.uuid4().hex}"

    def acquire(application: object, model_api: Any) -> ResponseSpectrumSettingsFact:
        def observe():
            if session.identity != expected or session._gateway_session is not gateway:
                raise EtabsOAPIError("ResponseSpectrum settings: session drift")
            observed = read_session_identity(application, model_api,
                process_id=expected.process_id, attach_strategy=expected.attach_strategy)
            if observed != expected:
                raise EtabsOAPIError("ResponseSpectrum settings: source/session/unit drift")
            if (observed.units.present_observation_status != "OBSERVED_CONSISTENT"
                    or observed.units.database_observation_status != "OBSERVED_CONSISTENT"):
                raise EtabsOAPIError("ResponseSpectrum settings: independent unit observations missing")
            return json.dumps(observed.as_dict(), sort_keys=True)
        before = observe()
        owner = model_api.LoadCases.ResponseSpectrum
        facts = []
        for method in _RS_SETTING_OUTPUTS:
            getter = getattr(owner, method, None)
            if not callable(getter):
                raise EtabsOAPIError(f"ResponseSpectrum.{method}: getter unavailable")
            try:
                raw = getter(name)
            except Exception as exc:
                raise EtabsOAPIError(f"ResponseSpectrum.{method}: getter failed: {exc}") from exc
            facts.append(_decode_response_spectrum_setting(method, raw))
        after = observe()
        return ResponseSpectrumSettingsFact(name, tuple(facts), expected.model_full_path,
            f"etabs-session:pid:{expected.process_id}", capture, before, after)
    return _execute_verified_read(session, acquire,
        operation="oapi_response_spectrum_settings_read", timeout_seconds=timeout_seconds)
