"""Private reusable factual/state mechanics for the ETABS safety boundary.

This module intentionally contains no COM attachment, verified-session
construction, engineering interpretation, or public raw-capability ownership.
Gateway-owned bounded execution may pass raw ETABS objects into these helpers
internally; only factual/state results are returned through the public safety
facade.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import Enum
import ntpath
import threading
from typing import Any, Mapping, Sequence


class CapabilityState(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class RuntimeCaptureStatus(str, Enum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    SAMPLED = "SAMPLED"
    TRUNCATED = "TRUNCATED"
    UNKNOWN = "UNKNOWN"


class AnalysisReadiness(str, Enum):
    ANALYSIS_NOT_RUN = "ANALYSIS_NOT_RUN"
    ANALYSIS_COULD_NOT_START = "ANALYSIS_COULD_NOT_START"
    ANALYSIS_INCOMPLETE = "ANALYSIS_INCOMPLETE"
    ANALYSIS_FINISHED = "ANALYSIS_FINISHED"
    ANALYSIS_UNKNOWN = "ANALYSIS_UNKNOWN"


class EtabsStateMutationKind(str, Enum):
    PURE_READ = "PURE_READ"
    READ_WITH_OUTPUT_SELECTION_STATE_CHANGE = "READ_WITH_OUTPUT_SELECTION_STATE_CHANGE"
    MODEL_OR_SESSION_MUTATION = "MODEL_OR_SESSION_MUTATION"


class EtabsSafetyErrorCode(str, Enum):
    """Small, machine-stable safety failure contract."""

    ATTACH_FAILED = "ATTACH_FAILED"
    PID_ATTACH_UNSUPPORTED = "PID_ATTACH_UNSUPPORTED"
    PID_ATTACH_FAILED = "PID_ATTACH_FAILED"
    ATTACHED_MODEL_MISMATCH = "ATTACHED_MODEL_MISMATCH"
    SESSION_IDENTITY_UNAVAILABLE = "SESSION_IDENTITY_UNAVAILABLE"
    STATE_SNAPSHOT_UNSUPPORTED = "STATE_SNAPSHOT_UNSUPPORTED"
    TEMPORARY_STATE_SET_FAILED = "TEMPORARY_STATE_SET_FAILED"
    TEMPORARY_STATE_VERIFY_FAILED = "TEMPORARY_STATE_VERIFY_FAILED"
    FETCH_FAILED = "FETCH_FAILED"
    STATE_RESTORE_FAILED = "STATE_RESTORE_FAILED"
    STATE_RESTORE_VERIFY_FAILED = "STATE_RESTORE_VERIFY_FAILED"
    UNIT_PROVENANCE_UNAVAILABLE = "UNIT_PROVENANCE_UNAVAILABLE"
    ANALYSIS_STATUS_UNKNOWN = "ANALYSIS_STATUS_UNKNOWN"
    CAPTURE_INTEGRITY_FAILED = "CAPTURE_INTEGRITY_FAILED"


class EtabsSafetyError(RuntimeError):
    """Base error for a fail-closed ETABS safety operation."""

    def __init__(
        self,
        message: str,
        *,
        code: EtabsSafetyErrorCode,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = EtabsSafetyErrorCode(code)
        self.details = dict(details or {})

    def as_diagnostic_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": str(self),
            "details": dict(self.details),
        }


class EtabsIdentityMismatchError(EtabsSafetyError):
    """Attached ETABS model is not the exact requested target."""


class EtabsCapabilityError(EtabsSafetyError):
    """A required factual ETABS capability is unavailable or unusable."""


class EtabsStateRestoreError(EtabsSafetyError):
    """Temporary ETABS acquisition state could not be restored exactly."""


class EtabsStateVerificationError(EtabsSafetyError):
    """Temporary or restored ETABS state did not verify."""


@dataclass(frozen=True, slots=True)
class EtabsUnitSnapshot:
    present_units: Any = None
    database_units: Any = None
    present_force_unit: Any = None
    present_length_unit: Any = None
    present_temperature_unit: Any = None
    database_force_unit: Any = None
    database_length_unit: Any = None
    database_temperature_unit: Any = None
    present_units_api: str | None = None
    database_units_api: str | None = None
    diagnostics: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "present_units": self.present_units,
            "database_units": self.database_units,
            "present_force_unit": self.present_force_unit,
            "present_length_unit": self.present_length_unit,
            "present_temperature_unit": self.present_temperature_unit,
            "database_force_unit": self.database_force_unit,
            "database_length_unit": self.database_length_unit,
            "database_temperature_unit": self.database_temperature_unit,
            "present_units_api": self.present_units_api,
            "database_units_api": self.database_units_api,
            "diagnostics": [dict(item) for item in self.diagnostics],
        }


def _combined_capability(getter: CapabilityState, setter: CapabilityState) -> CapabilityState:
    if getter is CapabilityState.SUPPORTED and setter is CapabilityState.SUPPORTED:
        return CapabilityState.SUPPORTED
    if getter is CapabilityState.UNKNOWN or setter is CapabilityState.UNKNOWN:
        return CapabilityState.UNKNOWN
    return CapabilityState.UNSUPPORTED


@dataclass(frozen=True, slots=True)
class EtabsCapabilitySnapshot:
    pid_attach: CapabilityState = CapabilityState.UNKNOWN
    present_units_2: CapabilityState = CapabilityState.UNKNOWN
    database_units_2: CapabilityState = CapabilityState.UNKNOWN
    case_status: CapabilityState = CapabilityState.UNKNOWN

    results_case_selection_get: CapabilityState = CapabilityState.UNKNOWN
    results_case_selection_set: CapabilityState = CapabilityState.UNKNOWN
    results_combo_selection_get: CapabilityState = CapabilityState.UNKNOWN
    results_combo_selection_set: CapabilityState = CapabilityState.UNKNOWN

    database_case_selection_get: CapabilityState = CapabilityState.UNKNOWN
    database_case_selection_set: CapabilityState = CapabilityState.UNKNOWN
    database_combo_selection_get: CapabilityState = CapabilityState.UNKNOWN
    database_combo_selection_set: CapabilityState = CapabilityState.UNKNOWN

    database_pattern_selection: CapabilityState = CapabilityState.UNKNOWN
    database_output_options: CapabilityState = CapabilityState.UNKNOWN

    @property
    def results_case_selection(self) -> CapabilityState:
        return _combined_capability(self.results_case_selection_get, self.results_case_selection_set)

    @property
    def results_combo_selection(self) -> CapabilityState:
        return _combined_capability(self.results_combo_selection_get, self.results_combo_selection_set)

    @property
    def database_case_selection(self) -> CapabilityState:
        return _combined_capability(self.database_case_selection_get, self.database_case_selection_set)

    @property
    def database_combo_selection(self) -> CapabilityState:
        return _combined_capability(self.database_combo_selection_get, self.database_combo_selection_set)

    def as_dict(self) -> dict[str, str]:
        payload = {name: getattr(self, name).value for name in self.__dataclass_fields__}
        payload.update({
            "results_case_selection": self.results_case_selection.value,
            "results_combo_selection": self.results_combo_selection.value,
            "database_case_selection": self.database_case_selection.value,
            "database_combo_selection": self.database_combo_selection.value,
        })
        return payload


@dataclass(frozen=True, slots=True)
class EtabsSessionIdentity:
    process_id: int | None
    attach_strategy: str | None
    program_api_version: Any
    program_name: str | None
    program_version: str | None
    program_level: str | None
    internal_program_version: Any
    model_full_path: str
    model_fingerprint: str | None
    model_fingerprint_source: str
    model_locked: bool | None
    units: EtabsUnitSnapshot

    def as_dict(self) -> dict[str, Any]:
        return {
            "process_id": self.process_id,
            "attach_strategy": self.attach_strategy,
            "program_api_version": self.program_api_version,
            "program_name": self.program_name,
            "program_version": self.program_version,
            "program_level": self.program_level,
            "internal_program_version": self.internal_program_version,
            "model_full_path": self.model_full_path,
            "model_fingerprint": self.model_fingerprint,
            "model_fingerprint_source": self.model_fingerprint_source,
            "model_locked": self.model_locked,
            "units": self.units.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class AnalysisCaseReadiness:
    case_name: str
    readiness: AnalysisReadiness
    etabs_status_code: int | None
    return_code: int | None
    source_api: str = "Analyze.GetCaseStatus"
    error_code: EtabsSafetyErrorCode | None = None


@dataclass(frozen=True, slots=True)
class DatabaseTablesSelectionSnapshot:
    cases: tuple[str, ...]
    combos: tuple[str, ...]
    patterns: tuple[str, ...] | None = None
    output_options: tuple[Any, ...] | None = None


@dataclass(frozen=True, slots=True)
class ResultsSetupSelectionSnapshot:
    case_flags: tuple[tuple[str, bool], ...]
    combo_flags: tuple[tuple[str, bool], ...]


_PROCESS_LOCAL_ACQUISITION_LOCK = threading.RLock()


def process_local_acquisition_lock() -> threading.RLock:
    """Return the repository's process-local ETABS acquisition lock.

    This is deliberately not described as a machine-wide or cross-process lock.
    """
    return _PROCESS_LOCAL_ACQUISITION_LOCK


def _method_state(obj: Any, method_name: str) -> CapabilityState:
    if obj is None:
        return CapabilityState.UNSUPPORTED
    try:
        value = getattr(obj, method_name)
    except AttributeError:
        return CapabilityState.UNSUPPORTED
    except Exception:
        return CapabilityState.UNKNOWN
    return CapabilityState.SUPPORTED if callable(value) else CapabilityState.UNSUPPORTED


def _pair_state(obj: Any, get_name: str, set_name: str) -> CapabilityState:
    return _combined_capability(_method_state(obj, get_name), _method_state(obj, set_name))


def _safe_attr(obj: Any, name: str) -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return None


def _return_code(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return int(raw)
    if isinstance(raw, (tuple, list)) and raw:
        last = raw[-1]
        if isinstance(last, int) and not isinstance(last, bool):
            return int(last)
    return None


def _call_succeeded(raw: Any) -> bool:
    code = _return_code(raw)
    return code in (None, 0)


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    candidate = getattr(value, "value", None)
    if isinstance(candidate, int) and not isinstance(candidate, bool):
        return int(candidate)
    try:
        return int(value)
    except Exception:
        return None


def _first_nonempty_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (tuple, list)):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def _string_items(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (tuple, list)):
        return [str(item) for item in raw if isinstance(item, str)]
    return []


def _read_triplet_method(sap_model: Any, method_name: str) -> tuple[Any, Any, Any, int | None] | None:
    method = _safe_attr(sap_model, method_name)
    if not callable(method):
        return None
    try:
        raw = method()
    except Exception:
        return None
    if isinstance(raw, Mapping):
        keys = list(raw)
        if len(keys) >= 3:
            values = [raw[key] for key in keys[:3]]
            return values[0], values[1], values[2], _return_code(raw)
    if isinstance(raw, (tuple, list)):
        values = list(raw)
        code = _return_code(raw)
        if len(values) >= 4 and code is not None:
            values = values[:-1]
        if len(values) >= 3:
            return values[0], values[1], values[2], code
    return None


def _read_scalar_method(sap_model: Any, method_name: str) -> Any:
    method = _safe_attr(sap_model, method_name)
    if not callable(method):
        return None
    try:
        raw = method()
    except Exception:
        return None
    if isinstance(raw, (tuple, list)):
        values = list(raw)
        if len(values) >= 2 and _return_code(raw) is not None:
            values = values[:-1]
        return values[0] if values else None
    return raw


def read_etabs_unit_snapshot(sap_model: Any) -> EtabsUnitSnapshot:
    """Read ETABS unit provenance without changing present units."""
    diagnostics: list[dict[str, Any]] = []

    present_triplet = _read_triplet_method(sap_model, "GetPresentUnits_2")
    if present_triplet is not None:
        pf, pl, pt, ret = present_triplet
        if ret not in (None, 0):
            diagnostics.append({
                "api": "GetPresentUnits_2",
                "return_code": ret,
                "status": "NONZERO_RETURN",
                "error_code": EtabsSafetyErrorCode.UNIT_PROVENANCE_UNAVAILABLE.value,
            })
            present_triplet = None

    database_triplet = _read_triplet_method(sap_model, "GetDatabaseUnits_2")
    if database_triplet is not None:
        df, dl, dt, ret = database_triplet
        if ret not in (None, 0):
            diagnostics.append({
                "api": "GetDatabaseUnits_2",
                "return_code": ret,
                "status": "NONZERO_RETURN",
                "error_code": EtabsSafetyErrorCode.UNIT_PROVENANCE_UNAVAILABLE.value,
            })
            database_triplet = None

    present_units = _read_scalar_method(sap_model, "GetPresentUnits")
    database_units = _read_scalar_method(sap_model, "GetDatabaseUnits")

    if present_triplet is not None:
        pf, pl, pt, _ = present_triplet
        present_api = "GetPresentUnits_2"
    else:
        pf = pl = pt = None
        present_api = "GetPresentUnits" if present_units is not None else None

    if database_triplet is not None:
        df, dl, dt, _ = database_triplet
        database_api = "GetDatabaseUnits_2"
    else:
        df = dl = dt = None
        database_api = "GetDatabaseUnits" if database_units is not None else None

    if present_api is None:
        diagnostics.append({
            "api": "present_units",
            "status": "UNAVAILABLE",
            "error_code": EtabsSafetyErrorCode.UNIT_PROVENANCE_UNAVAILABLE.value,
        })
    if database_api is None:
        diagnostics.append({
            "api": "database_units",
            "status": "UNAVAILABLE",
            "error_code": EtabsSafetyErrorCode.UNIT_PROVENANCE_UNAVAILABLE.value,
        })

    return EtabsUnitSnapshot(
        present_units=present_units,
        database_units=database_units,
        present_force_unit=pf,
        present_length_unit=pl,
        present_temperature_unit=pt,
        database_force_unit=df,
        database_length_unit=dl,
        database_temperature_unit=dt,
        present_units_api=present_api,
        database_units_api=database_api,
        diagnostics=tuple(diagnostics),
    )


def _read_program_version(sap_model: Any) -> tuple[str | None, Any]:
    method = _safe_attr(sap_model, "GetVersion")
    if not callable(method):
        return None, None
    try:
        raw = method()
    except Exception:
        return None, None
    if isinstance(raw, str):
        return raw.strip() or None, None
    if isinstance(raw, (tuple, list)):
        version = next((item.strip() for item in raw if isinstance(item, str) and item.strip()), None)
        internal = next((item for item in raw if isinstance(item, float)), None)
        return version, internal
    return str(raw), None


def _read_program_info(sap_model: Any) -> tuple[str | None, str | None, str | None]:
    method = _safe_attr(sap_model, "GetProgramInfo")
    if not callable(method):
        return None, None, None
    try:
        raw = method()
    except Exception:
        return None, None, None
    strings = [item.strip() for item in _string_items(raw) if item.strip()]
    padded = strings[:3] + [None] * max(0, 3 - len(strings))
    return padded[0], padded[1], padded[2]


def _read_model_full_path(sap_model: Any) -> str:
    """Reconstruct the exact ETABS model reference from bounded filename/path facts.

    This compatibility boundary deliberately uses ``GetModelFilename(False)``
    together with ``GetModelFilepath()``. It accepts only an unqualified
    filename leaf plus an absolute Windows directory.

    It does not infer original-file provenance, map file extensions, or treat
    another ETABS file representation as identity-equivalent.
    """
    filename: str | None = None
    method = _safe_attr(sap_model, "GetModelFilename")
    if callable(method):
        try:
            filename = _first_nonempty_string(method(False))
        except Exception:
            filename = None

    filepath = _first_nonempty_string(_read_scalar_method(sap_model, "GetModelFilepath"))
    filename_has_path = bool(
        filename and (ntpath.isabs(filename) or bool(ntpath.dirname(filename)))
    )
    filepath_is_absolute = bool(
        filepath and (ntpath.isabs(filepath) or filepath.startswith("\\\\"))
    )
    if (
        filename
        and filepath
        and not filename_has_path
        and filename not in {".", ".."}
        and filepath_is_absolute
    ):
        model_reference = ntpath.normpath(ntpath.join(filepath, filename))
        if ntpath.isabs(model_reference) or model_reference.startswith("\\\\"):
            return model_reference

    raise EtabsCapabilityError(
        "Exact ETABS model reference could not be reconstructed from "
        "GetModelFilename(False) and GetModelFilepath().",
        code=EtabsSafetyErrorCode.SESSION_IDENTITY_UNAVAILABLE,
    )

def read_session_identity(
    etabs_object: Any,
    sap_model: Any,
    *,
    process_id: int | None = None,
    attach_strategy: str | None = None,
) -> EtabsSessionIdentity:
    program_api_version = None
    method = _safe_attr(etabs_object, "GetOAPIVersionNumber")
    if callable(method):
        try:
            program_api_version = method()
        except Exception:
            program_api_version = None

    program_name, info_version, program_level = _read_program_info(sap_model)
    program_version, internal_version = _read_program_version(sap_model)
    if program_version is None:
        program_version = info_version

    locked: bool | None = None
    lock_method = _safe_attr(sap_model, "GetModelIsLocked")
    if callable(lock_method):
        try:
            raw_locked = lock_method()
            if isinstance(raw_locked, bool):
                locked = raw_locked
            elif isinstance(raw_locked, (tuple, list)):
                locked = next((item for item in raw_locked if isinstance(item, bool)), None)
        except Exception:
            locked = None

    units = read_etabs_unit_snapshot(sap_model)
    if units.present_units_api is None or units.database_units_api is None:
        raise EtabsCapabilityError(
            "ETABS present/database unit provenance is unavailable.",
            code=EtabsSafetyErrorCode.UNIT_PROVENANCE_UNAVAILABLE,
            details={"unit_diagnostics": [dict(item) for item in units.diagnostics]},
        )

    return EtabsSessionIdentity(
        process_id=process_id,
        attach_strategy=attach_strategy,
        program_api_version=program_api_version,
        program_name=program_name,
        program_version=program_version,
        program_level=program_level,
        internal_program_version=internal_version,
        model_full_path=_read_model_full_path(sap_model),
        model_fingerprint=None,
        model_fingerprint_source="UNAVAILABLE_FROM_CONSUMED_API",
        model_locked=locked,
        units=units,
    )


def _normalize_windows_path(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(str(path).strip().strip('"')))


def verify_target_model(identity: EtabsSessionIdentity, expected_model_full_path: str) -> None:
    expected = str(expected_model_full_path or "").strip()
    if not expected or not (ntpath.isabs(expected) or expected.startswith("\\\\")):
        raise EtabsIdentityMismatchError(
            "Expected ETABS target must be an exact full model path.",
            code=EtabsSafetyErrorCode.ATTACHED_MODEL_MISMATCH,
        )
    if _normalize_windows_path(identity.model_full_path) != _normalize_windows_path(expected):
        raise EtabsIdentityMismatchError(
            f"Wrong ETABS model attached: expected {expected!r}, got {identity.model_full_path!r}.",
            code=EtabsSafetyErrorCode.ATTACHED_MODEL_MISMATCH,
            details={"expected_model_full_path": expected, "actual_model_full_path": identity.model_full_path},
        )


def read_capability_snapshot(sap_model: Any) -> EtabsCapabilitySnapshot:
    analyze = _safe_attr(sap_model, "Analyze")
    results = _safe_attr(sap_model, "Results")
    setup = _safe_attr(results, "Setup")
    db = _safe_attr(sap_model, "DatabaseTables")

    return EtabsCapabilitySnapshot(
        pid_attach=CapabilityState.UNKNOWN,
        present_units_2=_method_state(sap_model, "GetPresentUnits_2"),
        database_units_2=_method_state(sap_model, "GetDatabaseUnits_2"),
        case_status=_method_state(analyze, "GetCaseStatus"),
        results_case_selection_get=_method_state(setup, "GetCaseSelectedForOutput"),
        results_case_selection_set=_method_state(setup, "SetCaseSelectedForOutput"),
        results_combo_selection_get=_method_state(setup, "GetComboSelectedForOutput"),
        results_combo_selection_set=_method_state(setup, "SetComboSelectedForOutput"),
        database_case_selection_get=_method_state(db, "GetLoadCasesSelectedForDisplay"),
        database_case_selection_set=_method_state(db, "SetLoadCasesSelectedForDisplay"),
        database_combo_selection_get=_method_state(db, "GetLoadCombinationsSelectedForDisplay"),
        database_combo_selection_set=_method_state(db, "SetLoadCombinationsSelectedForDisplay"),
        database_pattern_selection=_pair_state(
            db, "GetLoadPatternsSelectedForDisplay", "SetLoadPatternsSelectedForDisplay"
        ),
        database_output_options=_pair_state(
            db, "GetOutputOptionsForDisplay", "SetOutputOptionsForDisplay"
        ),
    )


def _extract_string_sequence(raw: Any) -> tuple[str, ...] | None:
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return tuple(raw)
    if isinstance(raw, tuple) and raw and all(isinstance(item, str) for item in raw):
        return tuple(raw)
    if isinstance(raw, (tuple, list)):
        candidates: list[tuple[str, ...]] = []
        for item in raw:
            if isinstance(item, (tuple, list)) and all(isinstance(value, str) for value in item):
                candidates.append(tuple(str(value) for value in item))
        if candidates:
            return max(candidates, key=len)
    return None


def _require_methods(
    obj: Any,
    method_names: Sequence[str],
    *,
    code: EtabsSafetyErrorCode = EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
) -> None:
    missing = [name for name in method_names if _method_state(obj, name) is not CapabilityState.SUPPORTED]
    if missing:
        raise EtabsCapabilityError(
            "Required reversible ETABS state APIs are unavailable: " + ", ".join(missing),
            code=code,
            details={"missing_methods": missing},
        )


def _decode_database_selected_names(
    raw: Any,
    getter_name: str,
    *,
    error_code: EtabsSafetyErrorCode,
) -> tuple[str, ...]:
    """Decode ETABS DatabaseTables selected-name getters by authoritative count.

    ETABS/comtypes may return a SAFEARRAY whose tail retains old capacity and is
    padded with ``None`` after a singleton selection. Only ``payload[:count]``
    is authoritative. The padded tail is never inferred as selected state.
    """
    if not isinstance(raw, (tuple, list)) or len(raw) < 3:
        raise EtabsCapabilityError(
            f"{getter_name} did not return [count, payload, return_code].",
            code=error_code,
            details={"raw_type": type(raw).__name__},
        )

    code = _return_code(raw)
    if code != 0:
        raise EtabsCapabilityError(
            f"{getter_name} returned {code}.",
            code=error_code,
            details={"api_return_code": code},
        )

    raw_count = raw[0]
    if isinstance(raw_count, bool):
        count = None
    elif isinstance(raw_count, int):
        count = int(raw_count)
    else:
        candidate = getattr(raw_count, "value", None)
        count = (
            int(candidate)
            if isinstance(candidate, int) and not isinstance(candidate, bool)
            else None
        )
    if count is None or count < 0:
        raise EtabsCapabilityError(
            f"{getter_name} returned an invalid selected-name count.",
            code=error_code,
            details={"selected_count": raw[0]},
        )

    payload = raw[1]
    if not isinstance(payload, (tuple, list)):
        raise EtabsCapabilityError(
            f"{getter_name} did not return an indexable selected-name payload.",
            code=error_code,
            details={"selected_count": count, "payload_type": type(payload).__name__},
        )
    if len(payload) < count:
        raise EtabsCapabilityError(
            f"{getter_name} selected-name payload is shorter than its authoritative count.",
            code=error_code,
            details={"selected_count": count, "payload_length": len(payload)},
        )

    prefix = payload[:count]
    invalid_positions = [
        index
        for index, value in enumerate(prefix)
        if not isinstance(value, str) or not value.strip()
    ]
    if invalid_positions:
        raise EtabsCapabilityError(
            f"{getter_name} authoritative selected-name prefix is invalid.",
            code=error_code,
            details={
                "selected_count": count,
                "invalid_prefix_positions": invalid_positions,
            },
        )
    return tuple(prefix)


def _read_selected_names(
    obj: Any,
    getter_name: str,
    *,
    error_code: EtabsSafetyErrorCode = EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
) -> tuple[str, ...]:
    getter = _safe_attr(obj, getter_name)
    if not callable(getter):
        raise EtabsCapabilityError(
            f"{getter_name} is required before selection mutation.",
            code=error_code,
        )
    try:
        raw = getter()
    except Exception as exc:
        raise EtabsCapabilityError(
            f"{getter_name} failed before mutation: {exc}",
            code=error_code,
        ) from exc
    return _decode_database_selected_names(raw, getter_name, error_code=error_code)


def _set_selected_names(
    obj: Any,
    setter_name: str,
    names: Sequence[str],
    *,
    error_code: EtabsSafetyErrorCode,
) -> int | None:
    setter = _safe_attr(obj, setter_name)
    if not callable(setter):
        raise EtabsCapabilityError(
            f"{setter_name} is required for reversible selection mutation.",
            code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
        )
    try:
        raw = setter(list(names))
    except Exception as exc:
        raise EtabsStateVerificationError(
            f"{setter_name} raised {type(exc).__name__}: {exc}",
            code=error_code,
        ) from exc
    code = _return_code(raw)
    if code not in (None, 0):
        raise EtabsStateVerificationError(
            f"{setter_name} returned {code}.",
            code=error_code,
            details={"api_return_code": code, "requested_names": list(names)},
        )
    return code


def _selection_equal_exact(left: Sequence[str], right: Sequence[str]) -> bool:
    return tuple(str(item) for item in left) == tuple(str(item) for item in right)


def _optional_selected_names(obj: Any, getter_name: str, setter_name: str) -> tuple[str, ...] | None:
    if _pair_state(obj, getter_name, setter_name) is not CapabilityState.SUPPORTED:
        return None
    return _read_selected_names(obj, getter_name)


def _read_output_options_if_supported(database_tables: Any) -> tuple[Any, ...] | None:
    if _pair_state(
        database_tables,
        "GetOutputOptionsForDisplay",
        "SetOutputOptionsForDisplay",
    ) is not CapabilityState.SUPPORTED:
        return None
    getter = database_tables.GetOutputOptionsForDisplay
    try:
        raw = getter()
    except Exception:
        return None
    code = _return_code(raw)
    if code not in (None, 0) or not isinstance(raw, (tuple, list)):
        return None
    values = list(raw)
    if code is not None and values:
        values = values[:-1]
    return tuple(values)


class DatabaseTablesReadTransaction(AbstractContextManager["DatabaseTablesReadTransaction"]):
    """Reversible DatabaseTables case/combo display-selection transaction."""

    mutation_kind = EtabsStateMutationKind.READ_WITH_OUTPUT_SELECTION_STATE_CHANGE

    _CORE_METHODS = (
        "GetLoadCasesSelectedForDisplay",
        "SetLoadCasesSelectedForDisplay",
        "GetLoadCombinationsSelectedForDisplay",
        "SetLoadCombinationsSelectedForDisplay",
    )

    def __init__(self, database_tables: Any) -> None:
        self.database_tables = database_tables
        self.snapshot: DatabaseTablesSelectionSnapshot | None = None
        self.diagnostics: list[dict[str, Any]] = []
        self._entered = False

    def __enter__(self) -> "DatabaseTablesReadTransaction":
        _PROCESS_LOCAL_ACQUISITION_LOCK.acquire()
        self._entered = True
        try:
            _require_methods(self.database_tables, self._CORE_METHODS)
            cases = _read_selected_names(self.database_tables, "GetLoadCasesSelectedForDisplay")
            combos = _read_selected_names(
                self.database_tables, "GetLoadCombinationsSelectedForDisplay"
            )
            patterns = _optional_selected_names(
                self.database_tables,
                "GetLoadPatternsSelectedForDisplay",
                "SetLoadPatternsSelectedForDisplay",
            )
            output_options = _read_output_options_if_supported(self.database_tables)
            self.snapshot = DatabaseTablesSelectionSnapshot(
                cases=cases,
                combos=combos,
                patterns=patterns,
                output_options=output_options,
            )
            self.diagnostics.append({
                "phase": "snapshot",
                "error_code": None,
                "mutation_kind": self.mutation_kind.value,
                "cases": list(cases),
                "combos": list(combos),
                "patterns": None if patterns is None else list(patterns),
                "output_options_captured": output_options is not None,
            })
            return self
        except Exception as exc:
            if isinstance(exc, EtabsSafetyError):
                self.diagnostics.append({
                    "phase": "snapshot",
                    "success": False,
                    "error_code": exc.code.value,
                    "message": str(exc),
                })
            self._entered = False
            _PROCESS_LOCAL_ACQUISITION_LOCK.release()
            raise

    def _current_core_selection(
        self,
        *,
        error_code: EtabsSafetyErrorCode,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        cases = _read_selected_names(
            self.database_tables,
            "GetLoadCasesSelectedForDisplay",
            error_code=error_code,
        )
        combos = _read_selected_names(
            self.database_tables,
            "GetLoadCombinationsSelectedForDisplay",
            error_code=error_code,
        )
        return cases, combos

    def _set_core_exact(
        self,
        *,
        target_kind: str,
        cases: Sequence[str],
        combos: Sequence[str],
        set_error_code: EtabsSafetyErrorCode,
        verify_error_code: EtabsSafetyErrorCode,
        phase: str,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        if target_kind == "case":
            _set_selected_names(
                self.database_tables,
                "SetLoadCasesSelectedForDisplay",
                cases,
                error_code=set_error_code,
            )
        elif target_kind == "combo":
            _set_selected_names(
                self.database_tables,
                "SetLoadCombinationsSelectedForDisplay",
                combos,
                error_code=set_error_code,
            )
        else:
            raise EtabsStateVerificationError(
                f"Unsupported DatabaseTables target kind {target_kind!r}.",
                code=set_error_code,
            )

        current_cases, current_combos = self._current_core_selection(
            error_code=verify_error_code
        )
        cases_verified = _selection_equal_exact(current_cases, cases)
        combos_verified = _selection_equal_exact(current_combos, combos)
        verified = cases_verified and combos_verified
        self.diagnostics.append({
            "phase": phase,
            "target_kind": target_kind,
            "requested_cases": list(cases),
            "requested_combos": list(combos),
            "actual_cases": list(current_cases),
            "actual_combos": list(current_combos),
            "temporary_cases_verified_exact": cases_verified,
            "temporary_combos_verified_exact": combos_verified,
            "verified_exact": verified,
            "opposite_domain_preserved": (
                combos_verified if target_kind == "case" else cases_verified
            ),
            "selection_scope": "VERIFIED_SUPERSET_SELECTION",
            "error_code": None if verified else verify_error_code.value,
            "mutation_kind": self.mutation_kind.value,
        })
        if not verified:
            raise EtabsStateVerificationError(
                "ETABS DatabaseTables temporary selection did not verify exactly.",
                code=verify_error_code,
                details={
                    "target_kind": target_kind,
                    "requested_cases": list(cases),
                    "requested_combos": list(combos),
                    "actual_cases": list(current_cases),
                    "actual_combos": list(current_combos),
                    "temporary_cases_verified_exact": cases_verified,
                    "temporary_combos_verified_exact": combos_verified,
                },
            )
        return current_cases, current_combos

    def _restore_core_and_verify(self, *, phase: str = "restore_verify") -> None:
        if self.snapshot is None:
            raise EtabsStateRestoreError(
                "DatabaseTables selection snapshot was not captured.",
                code=EtabsSafetyErrorCode.STATE_RESTORE_FAILED,
            )

        try:
            _set_selected_names(
                self.database_tables,
                "SetLoadCasesSelectedForDisplay",
                self.snapshot.cases,
                error_code=EtabsSafetyErrorCode.STATE_RESTORE_FAILED,
            )
            _set_selected_names(
                self.database_tables,
                "SetLoadCombinationsSelectedForDisplay",
                self.snapshot.combos,
                error_code=EtabsSafetyErrorCode.STATE_RESTORE_FAILED,
            )
        except EtabsSafetyError as exc:
            self.diagnostics.append({
                "phase": phase,
                "success": False,
                "error_code": EtabsSafetyErrorCode.STATE_RESTORE_FAILED.value,
                "message": str(exc),
            })
            raise EtabsStateRestoreError(
                str(exc),
                code=EtabsSafetyErrorCode.STATE_RESTORE_FAILED,
                details=exc.details,
            ) from exc

        try:
            restored_cases, restored_combos = self._current_core_selection(
                error_code=EtabsSafetyErrorCode.STATE_RESTORE_VERIFY_FAILED
            )
        except EtabsSafetyError as exc:
            self.diagnostics.append({
                "phase": phase,
                "success": False,
                "error_code": EtabsSafetyErrorCode.STATE_RESTORE_VERIFY_FAILED.value,
                "message": str(exc),
            })
            raise EtabsStateRestoreError(
                "DatabaseTables restored state could not be re-read.",
                code=EtabsSafetyErrorCode.STATE_RESTORE_VERIFY_FAILED,
            ) from exc

        verified = (
            _selection_equal_exact(restored_cases, self.snapshot.cases)
            and _selection_equal_exact(restored_combos, self.snapshot.combos)
        )
        self.diagnostics.append({
            "phase": phase,
            "success": verified,
            "error_code": None if verified else EtabsSafetyErrorCode.STATE_RESTORE_VERIFY_FAILED.value,
            "restored_cases": list(restored_cases),
            "restored_combos": list(restored_combos),
        })
        if not verified:
            raise EtabsStateRestoreError(
                "DatabaseTables case/combo selection did not restore exactly.",
                code=EtabsSafetyErrorCode.STATE_RESTORE_VERIFY_FAILED,
                details={
                    "expected_cases": list(self.snapshot.cases),
                    "expected_combos": list(self.snapshot.combos),
                    "actual_cases": list(restored_cases),
                    "actual_combos": list(restored_combos),
                },
            )

    def select_output(self, preferred_output_case: str) -> dict[str, Any]:
        if not self._entered or self.snapshot is None:
            raise EtabsSafetyError(
                "DatabaseTablesReadTransaction must be entered before selection.",
                code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
            )
        name = str(preferred_output_case or "").strip()
        if not name:
            raise EtabsSafetyError(
                "preferred_output_case is required for display selection.",
                code=EtabsSafetyErrorCode.TEMPORARY_STATE_SET_FAILED,
            )

        attempts: list[dict[str, Any]] = []

        def attempt(kind: str) -> tuple[bool, EtabsSafetyError | None]:
            cases = self.snapshot.cases if kind == "combo" else (name,)
            combos = (name,) if kind == "combo" else self.snapshot.combos
            setter_name = (
                "SetLoadCombinationsSelectedForDisplay"
                if kind == "combo"
                else "SetLoadCasesSelectedForDisplay"
            )
            try:
                current_cases, current_combos = self._set_core_exact(
                    target_kind=kind,
                    cases=cases,
                    combos=combos,
                    set_error_code=EtabsSafetyErrorCode.TEMPORARY_STATE_SET_FAILED,
                    verify_error_code=EtabsSafetyErrorCode.TEMPORARY_STATE_VERIFY_FAILED,
                    phase=f"temporary_selection_{kind}",
                )
                attempts.append({
                    "kind": kind,
                    "target_name": name,
                    "method": setter_name,
                    "verified": True,
                    "selected_cases_after": list(current_cases),
                    "selected_combos_after": list(current_combos),
                    "temporary_cases_exact": list(cases),
                    "temporary_combos_exact": list(combos),
                    "opposite_domain_preserved": True,
                    "temporary_state_verified_exact": True,
                    "selection_scope": "VERIFIED_SUPERSET_SELECTION",
                    "error_code": None,
                    "mutation_kind": self.mutation_kind.value,
                })
                return True, None
            except EtabsSafetyError as exc:
                attempts.append({
                    "kind": kind,
                    "target_name": name,
                    "method": setter_name,
                    "verified": False,
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "error_code": exc.code.value,
                    "mutation_kind": self.mutation_kind.value,
                })
                return False, exc

        combo_ok, combo_error = attempt("combo")
        selected_kind: str | None = "combo" if combo_ok else None

        if not combo_ok:
            self._restore_core_and_verify(phase="candidate_combo_rollback_verify")
            case_ok, case_error = attempt("case")
            if case_ok:
                selected_kind = "case"
            else:
                self._restore_core_and_verify(phase="candidate_case_rollback_verify")
                terminal = case_error or combo_error
                if terminal is None:
                    terminal = EtabsStateVerificationError(
                        "Could not establish exact DatabaseTables temporary selection.",
                        code=EtabsSafetyErrorCode.TEMPORARY_STATE_VERIFY_FAILED,
                    )
                raise terminal

        selected_method = (
            "SetLoadCombinationsSelectedForDisplay"
            if selected_kind == "combo"
            else "SetLoadCasesSelectedForDisplay"
        )
        temporary_cases = self.snapshot.cases if selected_kind == "combo" else (name,)
        temporary_combos = (name,) if selected_kind == "combo" else self.snapshot.combos
        diagnostic = {
            "preferred_output_case": name,
            "preferred_output_kind_detected": selected_kind,
            "target_kind": selected_kind,
            "target_name": name,
            "display_selection_attempted": True,
            "display_selection_attempts": attempts,
            "display_selection_selected_method": selected_method,
            "display_selection_success": True,
            "fetch_after_display_selection": True,
            "attempted_case_fallback": selected_kind == "case",
            "skipped_case_selection_because_combo_succeeded": selected_kind == "combo",
            "temporary_cases_exact": list(temporary_cases),
            "temporary_combos_exact": list(temporary_combos),
            "opposite_domain_preserved": True,
            "temporary_state_verified_exact": True,
            "selection_scope": "VERIFIED_SUPERSET_SELECTION",
            "target_only_capture_claimed": False,
            "error_code": None,
            "mutation_kind": self.mutation_kind.value,
        }
        self.diagnostics.append({"phase": "temporary_selection_accepted", **diagnostic})
        return diagnostic

    def _restore_and_verify(self) -> None:
        self._restore_core_and_verify()

        optional_changes: list[str] = []
        assert self.snapshot is not None
        if self.snapshot.patterns is not None:
            current_patterns = _read_selected_names(
                self.database_tables, "GetLoadPatternsSelectedForDisplay"
            )
            if not _selection_equal_exact(current_patterns, self.snapshot.patterns):
                optional_changes.append("load_patterns_changed_during_transaction")
        if self.snapshot.output_options is not None:
            current_options = _read_output_options_if_supported(self.database_tables)
            if current_options != self.snapshot.output_options:
                optional_changes.append("output_options_changed_during_transaction")

        if optional_changes:
            self.diagnostics.append({
                "phase": "restore_verify_optional",
                "success": False,
                "error_code": EtabsSafetyErrorCode.STATE_RESTORE_VERIFY_FAILED.value,
                "unexpected_external_state_changes": optional_changes,
            })
            raise EtabsStateRestoreError(
                "DatabaseTables state changed outside the transaction: "
                + ", ".join(optional_changes),
                code=EtabsSafetyErrorCode.STATE_RESTORE_VERIFY_FAILED,
            )

    def __exit__(self, exc_type, exc, tb) -> bool:
        restore_error: Exception | None = None
        try:
            self._restore_and_verify()
        except Exception as restore_exc:
            restore_error = restore_exc
        finally:
            if self._entered:
                self._entered = False
                _PROCESS_LOCAL_ACQUISITION_LOCK.release()
        if restore_error is not None:
            if isinstance(restore_error, EtabsStateRestoreError):
                raise restore_error from exc
            if isinstance(restore_error, EtabsSafetyError):
                raise EtabsStateRestoreError(
                    str(restore_error),
                    code=EtabsSafetyErrorCode.STATE_RESTORE_FAILED,
                ) from exc
            raise EtabsStateRestoreError(
                str(restore_error),
                code=EtabsSafetyErrorCode.STATE_RESTORE_FAILED,
            ) from exc
        return False


def _get_name_list(container: Any, label: str) -> tuple[str, ...]:
    method = _safe_attr(container, "GetNameList")
    if not callable(method):
        raise EtabsCapabilityError(
            f"{label}.GetNameList is required for reversible Results.Setup mutation.",
            code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
        )
    try:
        raw = method()
    except Exception as exc:
        raise EtabsCapabilityError(
            f"{label}.GetNameList failed: {exc}",
            code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
        ) from exc
    if not _call_succeeded(raw):
        raise EtabsCapabilityError(
            f"{label}.GetNameList returned {_return_code(raw)}.",
            code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
        )
    names = _extract_string_sequence(raw)
    if names is None:
        raise EtabsCapabilityError(
            f"{label}.GetNameList did not expose the exact name list.",
            code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
        )
    return names


def _read_selected_flag(setup: Any, method_name: str, name: str) -> bool:
    method = _safe_attr(setup, method_name)
    if not callable(method):
        raise EtabsCapabilityError(
            f"{method_name} is required before Results.Setup mutation.",
            code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
        )
    try:
        raw = method(name)
    except Exception as exc:
        raise EtabsCapabilityError(
            f"{method_name}({name!r}) failed: {exc}",
            code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
        ) from exc
    code = _return_code(raw)
    if code not in (None, 0):
        raise EtabsCapabilityError(
            f"{method_name}({name!r}) returned {code}.",
            code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
        )
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (tuple, list)):
        for item in raw:
            if isinstance(item, bool):
                return item
    raise EtabsCapabilityError(
        f"{method_name}({name!r}) did not return a selected flag.",
        code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
    )


def _set_selected_flag(
    setup: Any,
    method_name: str,
    name: str,
    selected: bool,
    *,
    error_code: EtabsSafetyErrorCode,
) -> None:
    method = _safe_attr(setup, method_name)
    if not callable(method):
        raise EtabsCapabilityError(
            f"{method_name} is required for reversible Results.Setup mutation.",
            code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
        )
    try:
        raw = method(name, bool(selected))
    except Exception as exc:
        raise EtabsStateVerificationError(
            f"{method_name}({name!r}) raised {type(exc).__name__}: {exc}",
            code=error_code,
        ) from exc
    code = _return_code(raw)
    if code not in (None, 0):
        raise EtabsStateVerificationError(
            f"{method_name}({name!r}) returned {code}.",
            code=error_code,
        )


class ResultsSetupReadTransaction(AbstractContextManager["ResultsSetupReadTransaction"]):
    """Reversible Results.Setup case/combo selection transaction."""

    mutation_kind = EtabsStateMutationKind.READ_WITH_OUTPUT_SELECTION_STATE_CHANGE

    _SELECTION_METHODS = (
        "GetCaseSelectedForOutput",
        "SetCaseSelectedForOutput",
        "GetComboSelectedForOutput",
        "SetComboSelectedForOutput",
    )

    def __init__(self, sap_model: Any) -> None:
        self.sap_model = sap_model
        self.setup = _safe_attr(_safe_attr(sap_model, "Results"), "Setup")
        self.snapshot: ResultsSetupSelectionSnapshot | None = None
        self._case_names: tuple[str, ...] = ()
        self._combo_names: tuple[str, ...] = ()
        self.diagnostics: list[dict[str, Any]] = []
        self._entered = False

    def __enter__(self) -> "ResultsSetupReadTransaction":
        _PROCESS_LOCAL_ACQUISITION_LOCK.acquire()
        self._entered = True
        try:
            if self.setup is None:
                raise EtabsCapabilityError(
                    "SapModel.Results.Setup is unavailable.",
                    code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
                )
            _require_methods(self.setup, self._SELECTION_METHODS)
            _require_methods(
                self.setup,
                ("DeselectAllCasesAndCombosForOutput",),
                code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
            )
            self._case_names = _get_name_list(
                _safe_attr(self.sap_model, "LoadCases"), "LoadCases"
            )
            self._combo_names = _get_name_list(
                _safe_attr(self.sap_model, "RespCombo"), "RespCombo"
            )
            case_flags = tuple(
                (name, _read_selected_flag(self.setup, "GetCaseSelectedForOutput", name))
                for name in self._case_names
            )
            combo_flags = tuple(
                (name, _read_selected_flag(self.setup, "GetComboSelectedForOutput", name))
                for name in self._combo_names
            )
            self.snapshot = ResultsSetupSelectionSnapshot(
                case_flags=case_flags, combo_flags=combo_flags
            )
            self.diagnostics.append({
                "phase": "snapshot",
                "error_code": None,
                "mutation_kind": self.mutation_kind.value,
                "case_flags": list(case_flags),
                "combo_flags": list(combo_flags),
            })
            return self
        except Exception as exc:
            if isinstance(exc, EtabsSafetyError):
                self.diagnostics.append({
                    "phase": "snapshot",
                    "success": False,
                    "error_code": exc.code.value,
                    "message": str(exc),
                })
            self._entered = False
            _PROCESS_LOCAL_ACQUISITION_LOCK.release()
            raise

    def _deselect_all(self, *, error_code: EtabsSafetyErrorCode) -> None:
        method = _safe_attr(self.setup, "DeselectAllCasesAndCombosForOutput")
        if not callable(method):
            raise EtabsCapabilityError(
                "DeselectAllCasesAndCombosForOutput is required for exact temporary Results.Setup state.",
                code=EtabsSafetyErrorCode.STATE_SNAPSHOT_UNSUPPORTED,
            )
        try:
            raw = method()
        except Exception as exc:
            raise EtabsStateVerificationError(
                f"DeselectAllCasesAndCombosForOutput raised {type(exc).__name__}: {exc}",
                code=error_code,
            ) from exc
        code = _return_code(raw)
        if code not in (None, 0):
            raise EtabsStateVerificationError(
                f"DeselectAllCasesAndCombosForOutput returned {code}.",
                code=error_code,
            )

    def _current_flags(self) -> ResultsSetupSelectionSnapshot:
        return ResultsSetupSelectionSnapshot(
            case_flags=tuple(
                (name, _read_selected_flag(self.setup, "GetCaseSelectedForOutput", name))
                for name in self._case_names
            ),
            combo_flags=tuple(
                (name, _read_selected_flag(self.setup, "GetComboSelectedForOutput", name))
                for name in self._combo_names
            ),
        )

    def select_case(self, name: str) -> None:
        if name not in self._case_names:
            raise EtabsStateVerificationError(
                f"Unknown ETABS load case {name!r}.",
                code=EtabsSafetyErrorCode.TEMPORARY_STATE_SET_FAILED,
            )
        self._deselect_all(error_code=EtabsSafetyErrorCode.TEMPORARY_STATE_SET_FAILED)
        _set_selected_flag(
            self.setup,
            "SetCaseSelectedForOutput",
            name,
            True,
            error_code=EtabsSafetyErrorCode.TEMPORARY_STATE_SET_FAILED,
        )
        current = self._current_flags()
        expected = ResultsSetupSelectionSnapshot(
            case_flags=tuple((case, case == name) for case in self._case_names),
            combo_flags=tuple((combo, False) for combo in self._combo_names),
        )
        if current != expected:
            raise EtabsStateVerificationError(
                "Temporary Results.Setup case selection did not verify exactly.",
                code=EtabsSafetyErrorCode.TEMPORARY_STATE_VERIFY_FAILED,
            )
        self.diagnostics.append({
            "phase": "temporary_selection",
            "kind": "case",
            "name": name,
            "verified": True,
            "error_code": None,
        })

    def select_combo(self, name: str) -> None:
        if name not in self._combo_names:
            raise EtabsStateVerificationError(
                f"Unknown ETABS load combination {name!r}.",
                code=EtabsSafetyErrorCode.TEMPORARY_STATE_SET_FAILED,
            )
        self._deselect_all(error_code=EtabsSafetyErrorCode.TEMPORARY_STATE_SET_FAILED)
        _set_selected_flag(
            self.setup,
            "SetComboSelectedForOutput",
            name,
            True,
            error_code=EtabsSafetyErrorCode.TEMPORARY_STATE_SET_FAILED,
        )
        current = self._current_flags()
        expected = ResultsSetupSelectionSnapshot(
            case_flags=tuple((case, False) for case in self._case_names),
            combo_flags=tuple((combo, combo == name) for combo in self._combo_names),
        )
        if current != expected:
            raise EtabsStateVerificationError(
                "Temporary Results.Setup combo selection did not verify exactly.",
                code=EtabsSafetyErrorCode.TEMPORARY_STATE_VERIFY_FAILED,
            )
        self.diagnostics.append({
            "phase": "temporary_selection",
            "kind": "combo",
            "name": name,
            "verified": True,
            "error_code": None,
        })

    def _restore_and_verify(self) -> None:
        if self.snapshot is None:
            raise EtabsStateRestoreError(
                "Results.Setup selection snapshot was not captured.",
                code=EtabsSafetyErrorCode.STATE_RESTORE_FAILED,
            )
        try:
            self._deselect_all(error_code=EtabsSafetyErrorCode.STATE_RESTORE_FAILED)
            for name, selected in self.snapshot.case_flags:
                if selected:
                    _set_selected_flag(
                        self.setup,
                        "SetCaseSelectedForOutput",
                        name,
                        True,
                        error_code=EtabsSafetyErrorCode.STATE_RESTORE_FAILED,
                    )
            for name, selected in self.snapshot.combo_flags:
                if selected:
                    _set_selected_flag(
                        self.setup,
                        "SetComboSelectedForOutput",
                        name,
                        True,
                        error_code=EtabsSafetyErrorCode.STATE_RESTORE_FAILED,
                    )
        except EtabsSafetyError as exc:
            self.diagnostics.append({
                "phase": "restore",
                "success": False,
                "error_code": EtabsSafetyErrorCode.STATE_RESTORE_FAILED.value,
                "message": str(exc),
            })
            raise EtabsStateRestoreError(
                str(exc),
                code=EtabsSafetyErrorCode.STATE_RESTORE_FAILED,
            ) from exc

        try:
            current = self._current_flags()
        except EtabsSafetyError as exc:
            raise EtabsStateRestoreError(
                "Results.Setup restored state could not be re-read.",
                code=EtabsSafetyErrorCode.STATE_RESTORE_VERIFY_FAILED,
            ) from exc

        self.diagnostics.append({
            "phase": "restore_verify",
            "success": current == self.snapshot,
            "error_code": (
                None
                if current == self.snapshot
                else EtabsSafetyErrorCode.STATE_RESTORE_VERIFY_FAILED.value
            ),
        })
        if current != self.snapshot:
            raise EtabsStateRestoreError(
                "Results.Setup case/combo selection did not restore exactly.",
                code=EtabsSafetyErrorCode.STATE_RESTORE_VERIFY_FAILED,
            )

    def __exit__(self, exc_type, exc, tb) -> bool:
        restore_error: Exception | None = None
        try:
            self._restore_and_verify()
        except Exception as restore_exc:
            restore_error = restore_exc
        finally:
            if self._entered:
                self._entered = False
                _PROCESS_LOCAL_ACQUISITION_LOCK.release()
        if restore_error is not None:
            if isinstance(restore_error, EtabsStateRestoreError):
                raise restore_error from exc
            raise EtabsStateRestoreError(
                str(restore_error),
                code=EtabsSafetyErrorCode.STATE_RESTORE_FAILED,
            ) from exc
        return False


def _status_sequence(raw: Any, expected_len: int) -> tuple[int | None, ...] | None:
    if not isinstance(raw, (tuple, list)):
        return None
    for item in raw:
        if (
            isinstance(item, (tuple, list))
            and len(item) == expected_len
            and not all(isinstance(value, str) for value in item)
        ):
            values = tuple(_coerce_int(value) for value in item)
            if any(value is not None for value in values):
                return values
    return None


def read_analysis_readiness(sap_model: Any, case_name: str) -> AnalysisCaseReadiness:
    analyze = _safe_attr(sap_model, "Analyze")
    method = _safe_attr(analyze, "GetCaseStatus")
    if not callable(method):
        raise EtabsCapabilityError(
            "Analyze.GetCaseStatus is required for factual analysis readiness.",
            code=EtabsSafetyErrorCode.ANALYSIS_STATUS_UNKNOWN,
        )
    try:
        raw = method()
    except Exception as exc:
        raise EtabsCapabilityError(
            f"Analyze.GetCaseStatus failed: {exc}",
            code=EtabsSafetyErrorCode.ANALYSIS_STATUS_UNKNOWN,
        ) from exc
    return_code = _return_code(raw)
    if return_code not in (None, 0):
        raise EtabsCapabilityError(
            f"Analyze.GetCaseStatus returned {return_code}.",
            code=EtabsSafetyErrorCode.ANALYSIS_STATUS_UNKNOWN,
        )
    names = _extract_string_sequence(raw)
    if names is None:
        raise EtabsCapabilityError(
            "Analyze.GetCaseStatus did not return case names.",
            code=EtabsSafetyErrorCode.ANALYSIS_STATUS_UNKNOWN,
        )
    statuses = _status_sequence(raw, len(names))
    if statuses is None:
        raise EtabsCapabilityError(
            "Analyze.GetCaseStatus did not return aligned case statuses.",
            code=EtabsSafetyErrorCode.ANALYSIS_STATUS_UNKNOWN,
        )
    try:
        index = names.index(case_name)
    except ValueError as exc:
        raise EtabsCapabilityError(
            f"Analyze.GetCaseStatus did not report case {case_name!r}.",
            code=EtabsSafetyErrorCode.ANALYSIS_STATUS_UNKNOWN,
        ) from exc

    code = statuses[index]
    mapping = {
        1: AnalysisReadiness.ANALYSIS_NOT_RUN,
        2: AnalysisReadiness.ANALYSIS_COULD_NOT_START,
        3: AnalysisReadiness.ANALYSIS_INCOMPLETE,
        4: AnalysisReadiness.ANALYSIS_FINISHED,
    }
    readiness = mapping.get(code, AnalysisReadiness.ANALYSIS_UNKNOWN)
    return AnalysisCaseReadiness(
        case_name=case_name,
        readiness=readiness,
        etabs_status_code=code,
        return_code=return_code,
        error_code=(
            EtabsSafetyErrorCode.ANALYSIS_STATUS_UNKNOWN
            if readiness is AnalysisReadiness.ANALYSIS_UNKNOWN
            else None
        ),
    )


def classify_capture_status(
    *,
    return_code: int | None,
    row_count_reported: int | None,
    row_count_captured: int,
    header_count: int,
    flat_payload_length: int | None,
    max_rows: int | None = None,
    parser_has_error: bool = False,
    explicitly_truncated: bool = False,
) -> RuntimeCaptureStatus:
    """Classify factual runtime capture completeness without engineering meaning."""
    if explicitly_truncated:
        return RuntimeCaptureStatus.TRUNCATED
    if (
        max_rows is not None
        and max_rows >= 0
        and row_count_reported is not None
        and row_count_reported > row_count_captured
    ):
        return RuntimeCaptureStatus.SAMPLED

    if return_code != 0:
        return (
            RuntimeCaptureStatus.PARTIAL
            if row_count_captured > 0
            else RuntimeCaptureStatus.UNKNOWN
        )
    if header_count <= 0:
        return (
            RuntimeCaptureStatus.PARTIAL
            if row_count_captured > 0 or (row_count_reported or 0) > 0
            else RuntimeCaptureStatus.UNKNOWN
        )
    if row_count_reported is None or flat_payload_length is None:
        return (
            RuntimeCaptureStatus.PARTIAL
            if row_count_captured > 0
            else RuntimeCaptureStatus.UNKNOWN
        )

    expected_flat = row_count_reported * header_count
    structurally_full = (
        row_count_captured == row_count_reported
        and flat_payload_length == expected_flat
        and not parser_has_error
    )
    if structurally_full:
        return RuntimeCaptureStatus.FULL
    if row_count_captured > 0 or row_count_reported > 0:
        return RuntimeCaptureStatus.PARTIAL
    return RuntimeCaptureStatus.UNKNOWN


__all__ = [
    "AnalysisCaseReadiness",
    "AnalysisReadiness",
    "CapabilityState",
    "DatabaseTablesReadTransaction",
    "DatabaseTablesSelectionSnapshot",
    "EtabsCapabilityError",
    "EtabsCapabilitySnapshot",
    "EtabsIdentityMismatchError",
    "EtabsSafetyError",
    "EtabsSafetyErrorCode",
    "EtabsSessionIdentity",
    "EtabsStateMutationKind",
    "EtabsStateRestoreError",
    "EtabsStateVerificationError",
    "EtabsUnitSnapshot",
    "ResultsSetupReadTransaction",
    "ResultsSetupSelectionSnapshot",
    "RuntimeCaptureStatus",
    "classify_capture_status",
    "process_local_acquisition_lock",
    "read_analysis_readiness",
    "read_capability_snapshot",
    "read_etabs_unit_snapshot",
    "read_session_identity",
    "verify_target_model",
]
