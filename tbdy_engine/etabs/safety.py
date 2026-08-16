"""Minimal factual ETABS session and acquisition safety boundary.

This module intentionally contains no engineering interpretation. It provides
session identity, capability facts, unit provenance, factual analysis status,
and reversible output-selection transactions for the ETABS APIs currently
consumed by the repository.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import Enum
import ntpath
import threading
from typing import Any, Mapping, Sequence

from tbdy_engine.features.etabs_com_attach import (
    ATTACH_STATUS_ATTACHED,
    STRATEGY_COMTYPES_HELPER_GET_OBJECT_PROCESS,
    EtabsAttachResult,
    attach_to_running_etabs,
)


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


class EtabsSafetyError(RuntimeError):
    """Base error for a fail-closed ETABS safety operation."""


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


@dataclass(frozen=True, slots=True)
class EtabsCapabilitySnapshot:
    pid_attach: CapabilityState = CapabilityState.UNKNOWN
    present_units_2: CapabilityState = CapabilityState.UNKNOWN
    database_units_2: CapabilityState = CapabilityState.UNKNOWN
    case_status: CapabilityState = CapabilityState.UNKNOWN
    results_case_selection: CapabilityState = CapabilityState.UNKNOWN
    results_combo_selection: CapabilityState = CapabilityState.UNKNOWN
    database_case_selection: CapabilityState = CapabilityState.UNKNOWN
    database_combo_selection: CapabilityState = CapabilityState.UNKNOWN
    database_pattern_selection: CapabilityState = CapabilityState.UNKNOWN
    database_output_options: CapabilityState = CapabilityState.UNKNOWN

    def as_dict(self) -> dict[str, str]:
        return {name: getattr(self, name).value for name in self.__dataclass_fields__}


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
class EtabsVerifiedSession:
    attach_result: EtabsAttachResult
    identity: EtabsSessionIdentity
    capabilities: EtabsCapabilitySnapshot


@dataclass(frozen=True, slots=True)
class AnalysisCaseReadiness:
    case_name: str
    readiness: AnalysisReadiness
    etabs_status_code: int | None
    return_code: int | None
    source_api: str = "Analyze.GetCaseStatus"


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
    states = (_method_state(obj, get_name), _method_state(obj, set_name))
    if all(state is CapabilityState.SUPPORTED for state in states):
        return CapabilityState.SUPPORTED
    if any(state is CapabilityState.UNKNOWN for state in states):
        return CapabilityState.UNKNOWN
    return CapabilityState.UNSUPPORTED


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
        if len(values) >= 4 and _return_code(raw) is not None:
            values = values[:-1]
        if len(values) >= 3:
            return values[0], values[1], values[2], _return_code(raw)
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
            diagnostics.append({"api": "GetPresentUnits_2", "return_code": ret, "status": "NONZERO_RETURN"})
            present_triplet = None

    database_triplet = _read_triplet_method(sap_model, "GetDatabaseUnits_2")
    if database_triplet is not None:
        df, dl, dt, ret = database_triplet
        if ret not in (None, 0):
            diagnostics.append({"api": "GetDatabaseUnits_2", "return_code": ret, "status": "NONZERO_RETURN"})
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
        diagnostics.append({"api": "present_units", "status": "UNAVAILABLE"})
    if database_api is None:
        diagnostics.append({"api": "database_units", "status": "UNAVAILABLE"})

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
        internal = None
        for item in raw:
            if isinstance(item, float):
                internal = item
                break
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
    strings = _string_items(raw)
    strings = [item.strip() for item in strings if item.strip()]
    padded = strings[:3] + [None] * max(0, 3 - len(strings))
    return padded[0], padded[1], padded[2]


def _read_model_full_path(sap_model: Any) -> str:
    filename: str | None = None
    method = _safe_attr(sap_model, "GetModelFilename")
    if callable(method):
        try:
            filename = _first_nonempty_string(method(True))
        except TypeError:
            try:
                filename = _first_nonempty_string(method())
            except Exception:
                filename = None
        except Exception:
            filename = None

    filepath = _first_nonempty_string(_read_scalar_method(sap_model, "GetModelFilepath"))
    if filename and (ntpath.isabs(filename) or ntpath.dirname(filename)):
        return ntpath.normpath(filename)
    if filename and filepath:
        return ntpath.normpath(ntpath.join(filepath, filename))
    raise EtabsCapabilityError("Exact ETABS model full path could not be retrieved.")


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
        units=read_etabs_unit_snapshot(sap_model),
    )


def _normalize_windows_path(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(str(path).strip().strip('"')))


def verify_target_model(identity: EtabsSessionIdentity, expected_model_full_path: str) -> None:
    expected = str(expected_model_full_path or "").strip()
    if not expected or not (ntpath.isabs(expected) or expected.startswith("\\\\")):
        raise EtabsIdentityMismatchError("Expected ETABS target must be an exact full model path.")
    if _normalize_windows_path(identity.model_full_path) != _normalize_windows_path(expected):
        raise EtabsIdentityMismatchError(
            f"Wrong ETABS model attached: expected {expected!r}, got {identity.model_full_path!r}."
        )


def _pid_capability_from_attach(attach_result: EtabsAttachResult | None) -> CapabilityState:
    if attach_result is None:
        return CapabilityState.UNKNOWN
    if attach_result.strategy == STRATEGY_COMTYPES_HELPER_GET_OBJECT_PROCESS:
        return CapabilityState.SUPPORTED
    pid_attempts = [
        attempt
        for attempt in attach_result.attempts
        if attempt.strategy == STRATEGY_COMTYPES_HELPER_GET_OBJECT_PROCESS
    ]
    if not pid_attempts:
        return CapabilityState.UNKNOWN
    if any(attempt.status == "SUCCESS" for attempt in pid_attempts):
        return CapabilityState.SUPPORTED
    if any(
        attempt.exception_type == "AttributeError" or "GetObjectProcess" in attempt.message and "not accessible" in attempt.message
        for attempt in pid_attempts
    ):
        return CapabilityState.UNSUPPORTED
    return CapabilityState.UNKNOWN


def read_capability_snapshot(
    sap_model: Any,
    *,
    attach_result: EtabsAttachResult | None = None,
) -> EtabsCapabilitySnapshot:
    analyze = _safe_attr(sap_model, "Analyze")
    results = _safe_attr(sap_model, "Results")
    setup = _safe_attr(results, "Setup")
    db = _safe_attr(sap_model, "DatabaseTables")

    return EtabsCapabilitySnapshot(
        pid_attach=_pid_capability_from_attach(attach_result),
        present_units_2=_method_state(sap_model, "GetPresentUnits_2"),
        database_units_2=_method_state(sap_model, "GetDatabaseUnits_2"),
        case_status=_method_state(analyze, "GetCaseStatus"),
        results_case_selection=_pair_state(setup, "GetCaseSelectedForOutput", "SetCaseSelectedForOutput"),
        results_combo_selection=_pair_state(setup, "GetComboSelectedForOutput", "SetComboSelectedForOutput"),
        database_case_selection=_pair_state(db, "GetLoadCasesSelectedForDisplay", "SetLoadCasesSelectedForDisplay"),
        database_combo_selection=_pair_state(db, "GetLoadCombinationsSelectedForDisplay", "SetLoadCombinationsSelectedForDisplay"),
        database_pattern_selection=_pair_state(db, "GetLoadPatternsSelectedForDisplay", "SetLoadPatternsSelectedForDisplay"),
        database_output_options=_pair_state(db, "GetOutputOptionsForDisplay", "SetOutputOptionsForDisplay"),
    )


def attach_verified_to_running_etabs(
    expected_model_full_path: str,
    *,
    pid: int | None = None,
    comtypes_client: Any | None = None,
    win32com_client: Any | None = None,
) -> EtabsVerifiedSession:
    """Attach using bounded strategies, then hard-verify the exact target model."""
    attach_result = attach_to_running_etabs(
        pid=pid,
        comtypes_client=comtypes_client,
        win32com_client=win32com_client,
    )
    if attach_result.status != ATTACH_STATUS_ATTACHED:
        raise EtabsSafetyError(f"ETABS attach failed: {attach_result.as_diagnostic_dict()}")

    actual_pid = pid if attach_result.strategy == STRATEGY_COMTYPES_HELPER_GET_OBJECT_PROCESS else None
    identity = read_session_identity(
        attach_result.etabs_object,
        attach_result.sap_model,
        process_id=actual_pid,
        attach_strategy=attach_result.strategy,
    )
    verify_target_model(identity, expected_model_full_path)
    capabilities = read_capability_snapshot(attach_result.sap_model, attach_result=attach_result)
    return EtabsVerifiedSession(attach_result=attach_result, identity=identity, capabilities=capabilities)


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


def _read_selected_names(obj: Any, getter_name: str) -> tuple[str, ...]:
    getter = _safe_attr(obj, getter_name)
    if not callable(getter):
        raise EtabsCapabilityError(f"{getter_name} is required before selection mutation.")
    try:
        raw = getter()
    except Exception as exc:
        raise EtabsCapabilityError(f"{getter_name} failed before mutation: {exc}") from exc
    code = _return_code(raw)
    if code not in (None, 0):
        raise EtabsCapabilityError(f"{getter_name} returned {code} before mutation.")
    values = _extract_string_sequence(raw)
    if values is None:
        raise EtabsCapabilityError(f"{getter_name} did not expose an exact selected-name list.")
    return values


def _set_selected_names(obj: Any, setter_name: str, names: Sequence[str]) -> tuple[Any, int | None]:
    setter = _safe_attr(obj, setter_name)
    if not callable(setter):
        raise EtabsCapabilityError(f"{setter_name} is required for reversible selection mutation.")
    raw = setter(list(names))
    code = _return_code(raw)
    if code not in (None, 0):
        raise EtabsStateVerificationError(f"{setter_name} returned {code}.")
    return raw, code


def _selection_equal(left: Sequence[str], right: Sequence[str]) -> bool:
    return tuple(sorted(str(item) for item in left)) == tuple(sorted(str(item) for item in right))


def _optional_selected_names(obj: Any, getter_name: str, setter_name: str) -> tuple[str, ...] | None:
    if _pair_state(obj, getter_name, setter_name) is not CapabilityState.SUPPORTED:
        return None
    return _read_selected_names(obj, getter_name)


def _read_output_options_if_supported(database_tables: Any) -> tuple[Any, ...] | None:
    if _pair_state(database_tables, "GetOutputOptionsForDisplay", "SetOutputOptionsForDisplay") is not CapabilityState.SUPPORTED:
        return None
    getter = database_tables.GetOutputOptionsForDisplay
    try:
        raw = getter()
    except Exception:
        return None
    code = _return_code(raw)
    if code not in (None, 0):
        return None
    if not isinstance(raw, (tuple, list)):
        return None
    values = list(raw)
    if code is not None and values:
        values = values[:-1]
    return tuple(values)


class DatabaseTablesReadTransaction(AbstractContextManager["DatabaseTablesReadTransaction"]):
    """Reversible DatabaseTables case/combo display-selection transaction."""

    mutation_kind = EtabsStateMutationKind.READ_WITH_OUTPUT_SELECTION_STATE_CHANGE

    def __init__(self, database_tables: Any) -> None:
        self.database_tables = database_tables
        self.snapshot: DatabaseTablesSelectionSnapshot | None = None
        self.diagnostics: list[dict[str, Any]] = []
        self._entered = False

    def __enter__(self) -> "DatabaseTablesReadTransaction":
        _PROCESS_LOCAL_ACQUISITION_LOCK.acquire()
        self._entered = True
        try:
            cases = _read_selected_names(self.database_tables, "GetLoadCasesSelectedForDisplay")
            combos = _read_selected_names(self.database_tables, "GetLoadCombinationsSelectedForDisplay")
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
                "mutation_kind": self.mutation_kind.value,
                "cases": list(cases),
                "combos": list(combos),
                "patterns": None if patterns is None else list(patterns),
                "output_options_captured": output_options is not None,
            })
            return self
        except Exception:
            self._entered = False
            _PROCESS_LOCAL_ACQUISITION_LOCK.release()
            raise

    def select_output(self, preferred_output_case: str) -> dict[str, Any]:
        if not self._entered or self.snapshot is None:
            raise EtabsSafetyError("DatabaseTablesReadTransaction must be entered before selection.")
        case_name = str(preferred_output_case or "").strip()
        if not case_name:
            raise EtabsSafetyError("preferred_output_case is required for display selection.")

        attempts: list[dict[str, Any]] = []
        selected_method: str | None = None
        attempted_case_fallback = False
        skipped_case = False

        try:
            _, code = _set_selected_names(
                self.database_tables,
                "SetLoadCombinationsSelectedForDisplay",
                [case_name],
            )
            current = _read_selected_names(self.database_tables, "GetLoadCombinationsSelectedForDisplay")
            verified = case_name in current
            attempts.append({
                "method": "SetLoadCombinationsSelectedForDisplay",
                "return_code": code,
                "verified": verified,
                "selected_names_after": list(current),
                "mutation_kind": self.mutation_kind.value,
            })
            if verified:
                selected_method = "SetLoadCombinationsSelectedForDisplay"
                skipped_case = True
        except Exception as exc:
            attempts.append({
                "method": "SetLoadCombinationsSelectedForDisplay",
                "verified": False,
                "exception_type": type(exc).__name__,
                "exception": str(exc),
                "mutation_kind": self.mutation_kind.value,
            })

        if selected_method is None:
            attempted_case_fallback = True
            try:
                _, code = _set_selected_names(
                    self.database_tables,
                    "SetLoadCasesSelectedForDisplay",
                    [case_name],
                )
                current = _read_selected_names(self.database_tables, "GetLoadCasesSelectedForDisplay")
                verified = case_name in current
                attempts.append({
                    "method": "SetLoadCasesSelectedForDisplay",
                    "return_code": code,
                    "verified": verified,
                    "selected_names_after": list(current),
                    "mutation_kind": self.mutation_kind.value,
                })
                if verified:
                    selected_method = "SetLoadCasesSelectedForDisplay"
            except Exception as exc:
                attempts.append({
                    "method": "SetLoadCasesSelectedForDisplay",
                    "verified": False,
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "mutation_kind": self.mutation_kind.value,
                })

        diagnostic = {
            "preferred_output_case": case_name,
            "preferred_output_kind_detected": "combo" if selected_method and "Combination" in selected_method else (
                "case" if selected_method else "unknown"
            ),
            "display_selection_attempted": True,
            "display_selection_attempts": attempts,
            "display_selection_selected_method": selected_method,
            "display_selection_success": selected_method is not None,
            "fetch_after_display_selection": selected_method is not None,
            "attempted_case_fallback": attempted_case_fallback,
            "skipped_case_selection_because_combo_succeeded": skipped_case,
            "mutation_kind": self.mutation_kind.value,
        }
        self.diagnostics.append({"phase": "temporary_selection", **diagnostic})
        if selected_method is None:
            raise EtabsStateVerificationError("Could not establish and verify ETABS display output selection.")
        return diagnostic

    def _restore_and_verify(self) -> None:
        if self.snapshot is None:
            raise EtabsStateRestoreError("DatabaseTables selection snapshot was not captured.")
        restore_errors: list[str] = []
        for setter_name, names in (
            ("SetLoadCasesSelectedForDisplay", self.snapshot.cases),
            ("SetLoadCombinationsSelectedForDisplay", self.snapshot.combos),
        ):
            try:
                _set_selected_names(self.database_tables, setter_name, names)
            except Exception as exc:
                restore_errors.append(f"{setter_name}: {type(exc).__name__}: {exc}")

        if restore_errors:
            self.diagnostics.append({"phase": "restore", "success": False, "errors": restore_errors})
            raise EtabsStateRestoreError("; ".join(restore_errors))

        restored_cases = _read_selected_names(self.database_tables, "GetLoadCasesSelectedForDisplay")
        restored_combos = _read_selected_names(self.database_tables, "GetLoadCombinationsSelectedForDisplay")
        verified = _selection_equal(restored_cases, self.snapshot.cases) and _selection_equal(restored_combos, self.snapshot.combos)

        optional_changes: list[str] = []
        if self.snapshot.patterns is not None:
            current_patterns = _read_selected_names(self.database_tables, "GetLoadPatternsSelectedForDisplay")
            if not _selection_equal(current_patterns, self.snapshot.patterns):
                optional_changes.append("load_patterns_changed_during_transaction")
        if self.snapshot.output_options is not None:
            current_options = _read_output_options_if_supported(self.database_tables)
            if current_options != self.snapshot.output_options:
                optional_changes.append("output_options_changed_during_transaction")

        self.diagnostics.append({
            "phase": "restore_verify",
            "success": verified and not optional_changes,
            "restored_cases": list(restored_cases),
            "restored_combos": list(restored_combos),
            "unexpected_external_state_changes": optional_changes,
        })
        if not verified:
            raise EtabsStateRestoreError("DatabaseTables case/combo selection did not restore exactly.")
        if optional_changes:
            raise EtabsStateVerificationError(
                "DatabaseTables state changed outside the transaction: " + ", ".join(optional_changes)
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
            raise EtabsStateRestoreError(str(restore_error)) from exc
        return False


def _get_name_list(container: Any, label: str) -> tuple[str, ...]:
    method = _safe_attr(container, "GetNameList")
    if not callable(method):
        raise EtabsCapabilityError(f"{label}.GetNameList is required for reversible Results.Setup mutation.")
    try:
        raw = method()
    except Exception as exc:
        raise EtabsCapabilityError(f"{label}.GetNameList failed: {exc}") from exc
    if not _call_succeeded(raw):
        raise EtabsCapabilityError(f"{label}.GetNameList returned {_return_code(raw)}.")
    names = _extract_string_sequence(raw)
    if names is None:
        raise EtabsCapabilityError(f"{label}.GetNameList did not expose the exact name list.")
    return names


def _read_selected_flag(setup: Any, method_name: str, name: str) -> bool:
    method = _safe_attr(setup, method_name)
    if not callable(method):
        raise EtabsCapabilityError(f"{method_name} is required before Results.Setup mutation.")
    raw = method(name)
    code = _return_code(raw)
    if code not in (None, 0):
        raise EtabsCapabilityError(f"{method_name}({name!r}) returned {code}.")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (tuple, list)):
        for item in raw:
            if isinstance(item, bool):
                return item
    raise EtabsCapabilityError(f"{method_name}({name!r}) did not return a selected flag.")


def _set_selected_flag(setup: Any, method_name: str, name: str, selected: bool) -> None:
    method = _safe_attr(setup, method_name)
    if not callable(method):
        raise EtabsCapabilityError(f"{method_name} is required for reversible Results.Setup mutation.")
    raw = method(name, bool(selected))
    code = _return_code(raw)
    if code not in (None, 0):
        raise EtabsStateVerificationError(f"{method_name}({name!r}) returned {code}.")


class ResultsSetupReadTransaction(AbstractContextManager["ResultsSetupReadTransaction"]):
    """Reversible Results.Setup case/combo selection transaction."""

    mutation_kind = EtabsStateMutationKind.READ_WITH_OUTPUT_SELECTION_STATE_CHANGE

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
                raise EtabsCapabilityError("SapModel.Results.Setup is unavailable.")
            self._case_names = _get_name_list(_safe_attr(self.sap_model, "LoadCases"), "LoadCases")
            self._combo_names = _get_name_list(_safe_attr(self.sap_model, "RespCombo"), "RespCombo")
            case_flags = tuple(
                (name, _read_selected_flag(self.setup, "GetCaseSelectedForOutput", name))
                for name in self._case_names
            )
            combo_flags = tuple(
                (name, _read_selected_flag(self.setup, "GetComboSelectedForOutput", name))
                for name in self._combo_names
            )
            self.snapshot = ResultsSetupSelectionSnapshot(case_flags=case_flags, combo_flags=combo_flags)
            self.diagnostics.append({
                "phase": "snapshot",
                "mutation_kind": self.mutation_kind.value,
                "case_flags": list(case_flags),
                "combo_flags": list(combo_flags),
            })
            return self
        except Exception:
            self._entered = False
            _PROCESS_LOCAL_ACQUISITION_LOCK.release()
            raise

    def _deselect_all(self) -> None:
        method = _safe_attr(self.setup, "DeselectAllCasesAndCombosForOutput")
        if not callable(method):
            raise EtabsCapabilityError("DeselectAllCasesAndCombosForOutput is required for exact temporary Results.Setup state.")
        raw = method()
        code = _return_code(raw)
        if code not in (None, 0):
            raise EtabsStateVerificationError(f"DeselectAllCasesAndCombosForOutput returned {code}.")

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
            raise EtabsStateVerificationError(f"Unknown ETABS load case {name!r}.")
        self._deselect_all()
        _set_selected_flag(self.setup, "SetCaseSelectedForOutput", name, True)
        current = self._current_flags()
        expected = ResultsSetupSelectionSnapshot(
            case_flags=tuple((case, case == name) for case in self._case_names),
            combo_flags=tuple((combo, False) for combo in self._combo_names),
        )
        if current != expected:
            raise EtabsStateVerificationError("Temporary Results.Setup case selection did not verify exactly.")
        self.diagnostics.append({"phase": "temporary_selection", "kind": "case", "name": name, "verified": True})

    def select_combo(self, name: str) -> None:
        if name not in self._combo_names:
            raise EtabsStateVerificationError(f"Unknown ETABS load combination {name!r}.")
        self._deselect_all()
        _set_selected_flag(self.setup, "SetComboSelectedForOutput", name, True)
        current = self._current_flags()
        expected = ResultsSetupSelectionSnapshot(
            case_flags=tuple((case, False) for case in self._case_names),
            combo_flags=tuple((combo, combo == name) for combo in self._combo_names),
        )
        if current != expected:
            raise EtabsStateVerificationError("Temporary Results.Setup combo selection did not verify exactly.")
        self.diagnostics.append({"phase": "temporary_selection", "kind": "combo", "name": name, "verified": True})

    def _restore_and_verify(self) -> None:
        if self.snapshot is None:
            raise EtabsStateRestoreError("Results.Setup selection snapshot was not captured.")
        self._deselect_all()
        for name, selected in self.snapshot.case_flags:
            if selected:
                _set_selected_flag(self.setup, "SetCaseSelectedForOutput", name, True)
        for name, selected in self.snapshot.combo_flags:
            if selected:
                _set_selected_flag(self.setup, "SetComboSelectedForOutput", name, True)
        current = self._current_flags()
        self.diagnostics.append({"phase": "restore_verify", "success": current == self.snapshot})
        if current != self.snapshot:
            raise EtabsStateRestoreError("Results.Setup case/combo selection did not restore exactly.")

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
            raise EtabsStateRestoreError(str(restore_error)) from exc
        return False


def _status_sequence(raw: Any, expected_len: int) -> tuple[int | None, ...] | None:
    if not isinstance(raw, (tuple, list)):
        return None
    for item in raw:
        if isinstance(item, (tuple, list)) and len(item) == expected_len and not all(isinstance(value, str) for value in item):
            values = tuple(_coerce_int(value) for value in item)
            if any(value is not None for value in values):
                return values
    return None


def read_analysis_readiness(sap_model: Any, case_name: str) -> AnalysisCaseReadiness:
    analyze = _safe_attr(sap_model, "Analyze")
    method = _safe_attr(analyze, "GetCaseStatus")
    if not callable(method):
        raise EtabsCapabilityError("Analyze.GetCaseStatus is required for factual analysis readiness.")
    try:
        raw = method()
    except Exception as exc:
        raise EtabsCapabilityError(f"Analyze.GetCaseStatus failed: {exc}") from exc
    return_code = _return_code(raw)
    if return_code not in (None, 0):
        raise EtabsCapabilityError(f"Analyze.GetCaseStatus returned {return_code}.")
    names = _extract_string_sequence(raw)
    if names is None:
        raise EtabsCapabilityError("Analyze.GetCaseStatus did not return case names.")
    statuses = _status_sequence(raw, len(names))
    if statuses is None:
        raise EtabsCapabilityError("Analyze.GetCaseStatus did not return aligned case statuses.")
    try:
        index = names.index(case_name)
    except ValueError as exc:
        raise EtabsCapabilityError(f"Analyze.GetCaseStatus did not report case {case_name!r}.") from exc
    code = statuses[index]
    mapping = {
        1: AnalysisReadiness.ANALYSIS_NOT_RUN,
        2: AnalysisReadiness.ANALYSIS_COULD_NOT_START,
        3: AnalysisReadiness.ANALYSIS_INCOMPLETE,
        4: AnalysisReadiness.ANALYSIS_FINISHED,
    }
    return AnalysisCaseReadiness(
        case_name=case_name,
        readiness=mapping.get(code, AnalysisReadiness.ANALYSIS_UNKNOWN),
        etabs_status_code=code,
        return_code=return_code,
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
    if max_rows is not None and max_rows >= 0 and row_count_reported is not None and row_count_reported > row_count_captured:
        return RuntimeCaptureStatus.SAMPLED
    if return_code not in (None, 0):
        return RuntimeCaptureStatus.PARTIAL if row_count_captured > 0 else RuntimeCaptureStatus.UNKNOWN
    if row_count_reported is None or flat_payload_length is None or header_count < 0:
        return RuntimeCaptureStatus.PARTIAL if row_count_captured > 0 else RuntimeCaptureStatus.UNKNOWN
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
    "EtabsSessionIdentity",
    "EtabsStateMutationKind",
    "EtabsStateRestoreError",
    "EtabsStateVerificationError",
    "EtabsUnitSnapshot",
    "EtabsVerifiedSession",
    "ResultsSetupReadTransaction",
    "ResultsSetupSelectionSnapshot",
    "RuntimeCaptureStatus",
    "attach_verified_to_running_etabs",
    "classify_capture_status",
    "process_local_acquisition_lock",
    "read_analysis_readiness",
    "read_capability_snapshot",
    "read_etabs_unit_snapshot",
    "read_session_identity",
    "verify_target_model",
]
