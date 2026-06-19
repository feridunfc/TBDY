"""C13.5-P4 read-only live ETABS geometry table discovery sidecar."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import json

from tbdy_engine.features.etabs_com_attach import EtabsAttachFailure, EtabsAttachResult, attach_to_running_etabs

DISCOVERY_STATUS_OK = "OK"
DISCOVERY_STATUS_PARTIAL = "PARTIAL"
DISCOVERY_STATUS_FAIL = "FAIL"
FETCH_STATUS_NOT_FETCHED = "NOT_FETCHED"
FETCH_STATUS_FETCHED = "FETCHED"
FETCH_STATUS_EMPTY = "EMPTY"
FETCH_STATUS_FAILED = "FAILED"
FETCH_STATUS_SKIPPED_BY_CAP = "SKIPPED_BY_CAP"

GEOMETRY_TABLE_KEYWORDS: tuple[str, ...] = (
    "frame",
    "section",
    "property",
    "assignment",
    "assign",
    "column",
    "beam",
    "dimension",
    "object",
)
POSSIBLE_GEOMETRY_COLUMNS: tuple[str, ...] = (
    "Story",
    "Label",
    "UniqueName",
    "Object",
    "Frame",
    "Section",
    "SectionName",
    "PropName",
    "Width",
    "Depth",
    "t3",
    "t2",
)
_REQUIRED_MAPPING_FIELDS = ("Width", "Depth")
_WIDTH_COLUMN_ALIASES = ("width", "t2")
_DEPTH_COLUMN_ALIASES = ("depth", "t3")
_IDENTITY_COLUMN_NAMES = frozenset({"story", "label", "uniquename", "object", "frame", "section", "sectionname", "propname"})
_ALLOWED_DISCOVERY_STATUSES = frozenset({DISCOVERY_STATUS_OK, DISCOVERY_STATUS_PARTIAL, DISCOVERY_STATUS_FAIL})
_ALLOWED_FETCH_STATUSES = frozenset(
    {
        FETCH_STATUS_NOT_FETCHED,
        FETCH_STATUS_FETCHED,
        FETCH_STATUS_EMPTY,
        FETCH_STATUS_FAILED,
        FETCH_STATUS_SKIPPED_BY_CAP,
    }
)
_SCOPE = "LIVE_ETABS_GEOMETRY_TABLE_DISCOVERY"
_RUNNER = "C13.5-P4 Live ETABS Geometry Table Discovery"
_REQUIRED_OUTPUT_FILES = (
    "live_geometry_table_discovery_summary.json",
    "live_geometry_table_inventory.json",
    "live_geometry_table_candidates.json",
    "live_geometry_table_rejections.json",
    "live_geometry_table_discovery_diagnostics.json",
    "live_geometry_table_discovery_manifest.json",
)
_OPTIONAL_ACCEPTED_MAPPING_FILE = "accepted_geometry_table_mapping.json"
_DEFAULT_CANDIDATE_FETCH_CAP = 5


class EtabsTableDiscoverySource(Protocol):
    def list_table_descriptors(self) -> Sequence["EtabsTableDescriptor"]:
        """Return read-only ETABS table descriptors."""

    def fetch_table_columns(self, table_key: str) -> "EtabsTableFetchResult":
        """Return read-only table columns for a single table key."""


@dataclass(frozen=True, slots=True)
class EtabsTableDescriptor:
    table_key: str
    display_name: str | None
    import_type: str | None
    is_empty: bool | None
    source: str

    def __post_init__(self) -> None:
        if not self.table_key:
            raise ValueError("EtabsTableDescriptor.table_key is required")
        if not self.source:
            raise ValueError("EtabsTableDescriptor.source is required")

    def as_dict(self) -> dict[str, object]:
        return {
            "display_name": self.display_name,
            "import_type": self.import_type,
            "is_empty": self.is_empty,
            "source": self.source,
            "table_key": self.table_key,
        }


@dataclass(frozen=True, slots=True)
class GeometryTableCandidate:
    table_key: str
    score: int
    reasons: tuple[str, ...]
    matched_keywords: tuple[str, ...]
    available_columns: tuple[str, ...]
    missing_expected_columns: tuple[str, ...]
    fetch_status: str

    def __post_init__(self) -> None:
        if not self.table_key:
            raise ValueError("GeometryTableCandidate.table_key is required")
        if self.score < 0:
            raise ValueError("GeometryTableCandidate.score cannot be negative")
        if self.fetch_status not in _ALLOWED_FETCH_STATUSES:
            raise ValueError("Unsupported geometry table candidate fetch status")
        object.__setattr__(self, "reasons", tuple(str(item) for item in self.reasons))
        object.__setattr__(self, "matched_keywords", tuple(str(item) for item in self.matched_keywords))
        object.__setattr__(self, "available_columns", tuple(str(item) for item in self.available_columns))
        object.__setattr__(self, "missing_expected_columns", tuple(str(item) for item in self.missing_expected_columns))

    def as_dict(self) -> dict[str, object]:
        return {
            "available_columns": list(self.available_columns),
            "fetch_status": self.fetch_status,
            "matched_keywords": list(self.matched_keywords),
            "missing_expected_columns": list(self.missing_expected_columns),
            "reasons": list(self.reasons),
            "score": self.score,
            "table_key": self.table_key,
        }


@dataclass(frozen=True, slots=True)
class GeometryTableDiscoveryResult:
    status: str
    table_count: int
    candidate_count: int
    rejected_count: int
    candidates: tuple[GeometryTableCandidate, ...]
    diagnostics: tuple[dict[str, object], ...]

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_DISCOVERY_STATUSES:
            raise ValueError("Unsupported geometry table discovery status")
        if self.table_count < 0 or self.candidate_count < 0 or self.rejected_count < 0:
            raise ValueError("Geometry table discovery counts cannot be negative")
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "diagnostics", tuple(dict(item) for item in self.diagnostics))


@dataclass(frozen=True, slots=True)
class EtabsTableFetchResult:
    status: str
    available_columns: tuple[str, ...]
    row_count: int | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_FETCH_STATUSES:
            raise ValueError("Unsupported ETABS table fetch status")
        object.__setattr__(self, "available_columns", tuple(str(item) for item in self.available_columns))


@dataclass(frozen=True, slots=True)
class MappingEtabsTableDiscoverySource:
    descriptors: tuple[EtabsTableDescriptor, ...]
    columns_by_table_key: Mapping[str, tuple[str, ...]]
    failed_table_keys: frozenset[str]

    def __init__(
        self,
        *,
        descriptors: Sequence[EtabsTableDescriptor],
        columns_by_table_key: Mapping[str, Sequence[str]],
        failed_table_keys: Sequence[str] = (),
    ) -> None:
        object.__setattr__(self, "descriptors", tuple(descriptors))
        object.__setattr__(
            self,
            "columns_by_table_key",
            {str(key): tuple(str(item) for item in value) for key, value in columns_by_table_key.items()},
        )
        object.__setattr__(self, "failed_table_keys", frozenset(str(item) for item in failed_table_keys))

    def list_table_descriptors(self) -> Sequence[EtabsTableDescriptor]:
        return self.descriptors

    def fetch_table_columns(self, table_key: str) -> EtabsTableFetchResult:
        if table_key in self.failed_table_keys:
            return EtabsTableFetchResult(
                status=FETCH_STATUS_FAILED,
                available_columns=(),
                message="Fake table fetch failure",
            )
        columns = self.columns_by_table_key.get(table_key, ())
        if not columns:
            return EtabsTableFetchResult(status=FETCH_STATUS_EMPTY, available_columns=(), row_count=0)
        return EtabsTableFetchResult(status=FETCH_STATUS_FETCHED, available_columns=tuple(columns), row_count=None)


def run_live_geometry_table_discovery(
    *,
    source: EtabsTableDiscoverySource,
    output_dir: Path,
    candidate_fetch_cap: int = _DEFAULT_CANDIDATE_FETCH_CAP,
) -> GeometryTableDiscoveryResult:
    if candidate_fetch_cap < 0:
        raise ValueError("candidate_fetch_cap cannot be negative")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    accepted_mapping_path = out_dir / _OPTIONAL_ACCEPTED_MAPPING_FILE
    if accepted_mapping_path.exists():
        accepted_mapping_path.unlink()

    descriptors = tuple(source.list_table_descriptors())
    candidate_descriptors, rejections = _split_candidate_descriptors(descriptors)
    candidates = _build_candidates(
        source=source,
        descriptors=candidate_descriptors,
        candidate_fetch_cap=candidate_fetch_cap,
    )
    diagnostics = _build_diagnostics(
        table_count=len(descriptors),
        candidates=candidates,
    )
    accepted_mapping = _accepted_mapping(candidates)
    if accepted_mapping is not None:
        _write_json(accepted_mapping_path, accepted_mapping)

    status = _result_status(table_count=len(descriptors), candidates=candidates)
    fetched_candidate_count = sum(1 for candidate in candidates if candidate.fetch_status != FETCH_STATUS_SKIPPED_BY_CAP)
    result = GeometryTableDiscoveryResult(
        status=status,
        table_count=len(descriptors),
        candidate_count=len(candidates),
        rejected_count=len(rejections),
        candidates=tuple(candidates),
        diagnostics=tuple(diagnostics),
    )

    _write_json(out_dir / "live_geometry_table_inventory.json", [descriptor.as_dict() for descriptor in descriptors])
    _write_json(out_dir / "live_geometry_table_candidates.json", [candidate.as_dict() for candidate in candidates])
    _write_json(out_dir / "live_geometry_table_rejections.json", rejections)
    _write_json(out_dir / "live_geometry_table_discovery_diagnostics.json", diagnostics)
    _write_json(
        out_dir / "live_geometry_table_discovery_summary.json",
        {
            "accepted_mapping_written": accepted_mapping is not None,
            "candidate_count": result.candidate_count,
            "candidate_fetch_cap": candidate_fetch_cap,
            "fetched_candidate_count": fetched_candidate_count,
            "rejected_count": result.rejected_count,
            "status": result.status,
            "table_count": result.table_count,
        },
    )
    _write_json(
        out_dir / "live_geometry_table_discovery_manifest.json",
        {
            "accepted_mapping_policy": "explicit_width_depth_columns_only",
            "candidate_fetch_cap": candidate_fetch_cap,
            "geometry_table_keywords": list(GEOMETRY_TABLE_KEYWORDS),
            "live_etabs_required_for_ci": False,
            "output_files": list(_REQUIRED_OUTPUT_FILES),
            "possible_geometry_columns": list(POSSIBLE_GEOMETRY_COLUMNS),
            "runner": _RUNNER,
            "scope": _SCOPE,
            "sidecar_only": True,
        },
    )
    return result


def write_table_discovery_attach_failure_outputs(*, output_dir: Path, attach_result: EtabsAttachResult) -> GeometryTableDiscoveryResult:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    accepted_mapping_path = out_dir / _OPTIONAL_ACCEPTED_MAPPING_FILE
    if accepted_mapping_path.exists():
        accepted_mapping_path.unlink()
    attempts = [attempt.as_dict() for attempt in attach_result.attempts]
    diagnostics = [
        {
            "attempts": attempts,
            "code": "ETABS_COM_ATTACH_FAILED",
            "message": "No attach strategy succeeded; table discovery was not attempted.",
            "status": "BLOCKED",
        }
    ]
    _write_json(
        out_dir / "live_geometry_table_discovery_summary.json",
        {
            "accepted_mapping_written": False,
            "candidate_count": 0,
            "failure_stage": "COM_ATTACH",
            "rejected_count": 0,
            "status": DISCOVERY_STATUS_FAIL,
            "table_count": 0,
        },
    )
    _write_json(out_dir / "live_geometry_table_discovery_diagnostics.json", diagnostics)
    _write_json(
        out_dir / "live_geometry_table_discovery_manifest.json",
        {
            "failure_stage": "COM_ATTACH",
            "live_etabs_required_for_ci": False,
            "output_files": [
                "live_geometry_table_discovery_summary.json",
                "live_geometry_table_discovery_diagnostics.json",
                "live_geometry_table_discovery_manifest.json",
            ],
            "runner": _RUNNER,
            "scope": _SCOPE,
            "sidecar_only": True,
        },
    )
    return GeometryTableDiscoveryResult(
        status=DISCOVERY_STATUS_FAIL,
        table_count=0,
        candidate_count=0,
        rejected_count=0,
        candidates=(),
        diagnostics=tuple(diagnostics),
    )


def create_live_etabs_table_discovery_source(*, attach_result: EtabsAttachResult | None = None) -> EtabsTableDiscoverySource:
    resolved_attach_result = attach_result or attach_to_running_etabs()
    if resolved_attach_result.status != "ATTACHED":
        raise EtabsAttachFailure(resolved_attach_result)
    if resolved_attach_result.sap_model is None:
        raise RuntimeError("ETABS attach succeeded without SapModel; table discovery cannot continue")
    return SapModelEtabsTableDiscoverySource(resolved_attach_result.sap_model)


@dataclass(frozen=True, slots=True)
class SapModelEtabsTableDiscoverySource:
    sap_model: object

    def list_table_descriptors(self) -> Sequence[EtabsTableDescriptor]:
        database_tables = getattr(self.sap_model, "DatabaseTables")
        try:
            raw_tables = database_tables.GetAvailableTables()
        except Exception as exc:  # pragma: no cover - live ETABS boundary.
            raise RuntimeError(f"ETABS GetAvailableTables failed: {exc}") from exc
        return _table_descriptors_from_raw_available_tables(raw_tables)

    def fetch_table_columns(self, table_key: str) -> EtabsTableFetchResult:
        database_tables = getattr(self.sap_model, "DatabaseTables")
        try:  # pragma: no cover - live ETABS boundary.
            raw_table = database_tables.GetTableForDisplayArray(table_key, [], "", 0, [], 0, [])
        except Exception as exc:
            return EtabsTableFetchResult(
                status=FETCH_STATUS_FAILED,
                available_columns=(),
                message=str(exc) or repr(exc),
            )
        columns, row_count = _columns_and_row_count_from_display_array(raw_table)
        if not columns:
            return EtabsTableFetchResult(status=FETCH_STATUS_EMPTY, available_columns=(), row_count=0)
        return EtabsTableFetchResult(status=FETCH_STATUS_FETCHED, available_columns=columns, row_count=row_count)


def load_mapping_table_discovery_source_from_json(path: Path) -> MappingEtabsTableDiscoverySource:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    tables = payload.get("tables") if isinstance(payload, Mapping) else payload
    if not isinstance(tables, Sequence) or isinstance(tables, (str, bytes, bytearray)):
        raise ValueError("Fake ETABS table inventory fixture must contain a tables list")
    descriptors: list[EtabsTableDescriptor] = []
    columns_by_table_key: dict[str, tuple[str, ...]] = {}
    failed_table_keys: list[str] = []
    for index, item in enumerate(tables):
        if not isinstance(item, Mapping):
            raise ValueError(f"Fake ETABS table inventory item at index {index} must be an object")
        table_key = _required_text(item.get("table_key"), field_name="table_key")
        descriptors.append(
            EtabsTableDescriptor(
                table_key=table_key,
                display_name=_optional_text(item.get("display_name")),
                import_type=_optional_text(item.get("import_type")),
                is_empty=_optional_bool(item.get("is_empty")),
                source="fake_fixture",
            )
        )
        columns = item.get("columns", ())
        if not isinstance(columns, Sequence) or isinstance(columns, (str, bytes, bytearray)):
            raise ValueError(f"Fake ETABS table inventory columns for {table_key} must be a list")
        columns_by_table_key[table_key] = tuple(str(column) for column in columns)
        if bool(item.get("fetch_failure", False)):
            failed_table_keys.append(table_key)
    return MappingEtabsTableDiscoverySource(
        descriptors=tuple(descriptors),
        columns_by_table_key=columns_by_table_key,
        failed_table_keys=tuple(failed_table_keys),
    )


def _split_candidate_descriptors(
    descriptors: Sequence[EtabsTableDescriptor],
) -> tuple[tuple[EtabsTableDescriptor, ...], list[dict[str, object]]]:
    candidates: list[tuple[int, EtabsTableDescriptor]] = []
    rejections: list[dict[str, object]] = []
    for descriptor in descriptors:
        matched_keywords = _matched_keywords(descriptor)
        if matched_keywords:
            candidates.append((_keyword_score(matched_keywords), descriptor))
        else:
            rejections.append(
                {
                    "display_name": descriptor.display_name,
                    "reasons": ["no bounded geometry keyword match"],
                    "table_key": descriptor.table_key,
                }
            )
    candidates.sort(key=lambda item: (-item[0], item[1].table_key.casefold()))
    return tuple(descriptor for _score, descriptor in candidates), rejections


def _build_candidates(
    *,
    source: EtabsTableDiscoverySource,
    descriptors: Sequence[EtabsTableDescriptor],
    candidate_fetch_cap: int,
) -> list[GeometryTableCandidate]:
    candidates: list[GeometryTableCandidate] = []
    for index, descriptor in enumerate(descriptors):
        matched_keywords = _matched_keywords(descriptor)
        reasons = tuple(f"matched keyword: {keyword}" for keyword in matched_keywords)
        if index >= candidate_fetch_cap:
            candidates.append(
                GeometryTableCandidate(
                    table_key=descriptor.table_key,
                    score=_keyword_score(matched_keywords),
                    reasons=reasons + ("candidate fetch skipped by cap",),
                    matched_keywords=matched_keywords,
                    available_columns=(),
                    missing_expected_columns=_missing_expected_columns(()),
                    fetch_status=FETCH_STATUS_SKIPPED_BY_CAP,
                )
            )
            continue
        fetch_result = source.fetch_table_columns(descriptor.table_key)
        columns = tuple(fetch_result.available_columns)
        candidates.append(
            GeometryTableCandidate(
                table_key=descriptor.table_key,
                score=_keyword_score(matched_keywords) + _column_score(columns),
                reasons=reasons + _column_reasons(columns, fetch_result),
                matched_keywords=matched_keywords,
                available_columns=columns,
                missing_expected_columns=_missing_expected_columns(columns),
                fetch_status=fetch_result.status,
            )
        )
    candidates.sort(key=lambda item: (-item.score, item.table_key.casefold()))
    return candidates


def _build_diagnostics(*, table_count: int, candidates: Sequence[GeometryTableCandidate]) -> list[dict[str, object]]:
    diagnostics: list[dict[str, object]] = []
    if table_count == 0:
        diagnostics.append(
            {
                "code": "NO_VISIBLE_ETABS_TABLES",
                "message": "No ETABS database tables were visible from the read-only discovery source.",
                "status": "NO_DATA",
            }
        )
    if not candidates and table_count > 0:
        diagnostics.append(
            {
                "code": "NO_CANDIDATE_GEOMETRY_TABLES",
                "message": "Visible ETABS tables did not match the bounded geometry table keywords.",
                "status": "NO_DATA",
            }
        )
    failed = [candidate.table_key for candidate in candidates if candidate.fetch_status == FETCH_STATUS_FAILED]
    if failed:
        diagnostics.append(
            {
                "code": "CANDIDATE_TABLE_FETCH_FAILED",
                "message": "One or more candidate table schemas could not be fetched.",
                "status": "WARNING",
                "table_keys": failed,
            }
        )
    if candidates and _accepted_mapping(candidates) is None:
        diagnostics.append(
            {
                "code": "NO_ACCEPTED_GEOMETRY_TABLE_MAPPING",
                "message": "Candidate tables were found, but no candidate exposed explicit width/depth geometry columns. This explains why the C13.5-P3 FeatureSnapshot probe may produce zero snapshots.",
                "status": "NO_DATA",
            }
        )
    return diagnostics


def _result_status(*, table_count: int, candidates: Sequence[GeometryTableCandidate]) -> str:
    if table_count == 0:
        return DISCOVERY_STATUS_FAIL
    if any(candidate.fetch_status == FETCH_STATUS_FAILED for candidate in candidates):
        return DISCOVERY_STATUS_PARTIAL
    return DISCOVERY_STATUS_OK


def _accepted_mapping(candidates: Sequence[GeometryTableCandidate]) -> dict[str, object] | None:
    for candidate in candidates:
        width_column = _first_matching_column(candidate.available_columns, _WIDTH_COLUMN_ALIASES)
        depth_column = _first_matching_column(candidate.available_columns, _DEPTH_COLUMN_ALIASES)
        if candidate.fetch_status == FETCH_STATUS_FETCHED and width_column and depth_column:
            return {
                "depth_column": depth_column,
                "mapping_basis": "explicit_columns_only",
                "table_key": candidate.table_key,
                "width_column": width_column,
            }
    return None


def _matched_keywords(descriptor: EtabsTableDescriptor) -> tuple[str, ...]:
    haystack = f"{descriptor.table_key} {descriptor.display_name or ''}".casefold()
    return tuple(keyword for keyword in GEOMETRY_TABLE_KEYWORDS if keyword in haystack)


def _keyword_score(matched_keywords: Sequence[str]) -> int:
    return len(tuple(matched_keywords)) * 5


def _column_score(columns: Sequence[str]) -> int:
    normalized = {_normalize_column(column) for column in columns}
    score = 0
    if any(alias in normalized for alias in _WIDTH_COLUMN_ALIASES):
        score += 4
    if any(alias in normalized for alias in _DEPTH_COLUMN_ALIASES):
        score += 4
    score += sum(1 for column in normalized if column in _IDENTITY_COLUMN_NAMES)
    return score


def _column_reasons(columns: Sequence[str], fetch_result: EtabsTableFetchResult) -> tuple[str, ...]:
    reasons: list[str] = [f"fetch status: {fetch_result.status}"]
    if _first_matching_column(columns, _WIDTH_COLUMN_ALIASES):
        reasons.append("explicit width column present")
    if _first_matching_column(columns, _DEPTH_COLUMN_ALIASES):
        reasons.append("explicit depth column present")
    return tuple(reasons)


def _missing_expected_columns(columns: Sequence[str]) -> tuple[str, ...]:
    missing: list[str] = []
    if not _first_matching_column(columns, _WIDTH_COLUMN_ALIASES):
        missing.append("Width")
    if not _first_matching_column(columns, _DEPTH_COLUMN_ALIASES):
        missing.append("Depth")
    return tuple(missing)


def _first_matching_column(columns: Sequence[str], aliases: Sequence[str]) -> str | None:
    normalized_aliases = set(aliases)
    for column in columns:
        if _normalize_column(column) in normalized_aliases:
            return str(column)
    return None


def _normalize_column(column: str) -> str:
    return str(column).strip().casefold()


def _table_descriptors_from_raw_available_tables(raw_tables: object) -> tuple[EtabsTableDescriptor, ...]:
    if isinstance(raw_tables, Mapping):
        tables = raw_tables.get("tables", ())
        if isinstance(tables, Sequence) and not isinstance(tables, (str, bytes, bytearray)):
            return tuple(_descriptor_from_mapping(item, source="live_sap_model") for item in tables if isinstance(item, Mapping))
    if not isinstance(raw_tables, Sequence) or isinstance(raw_tables, (str, bytes, bytearray)):
        return ()
    sequences = [tuple(item) for item in raw_tables if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray))]
    string_sequences = [sequence for sequence in sequences if sequence and all(isinstance(item, str) for item in sequence)]
    if not string_sequences:
        return ()
    table_keys = string_sequences[0]
    display_names = string_sequences[1] if len(string_sequences) > 1 and len(string_sequences[1]) == len(table_keys) else tuple(None for _ in table_keys)
    import_types = _matching_length_sequence(sequences, len(table_keys), exclude=(table_keys, display_names))
    empty_flags = _matching_bool_sequence(sequences, len(table_keys))
    descriptors: list[EtabsTableDescriptor] = []
    for index, table_key in enumerate(table_keys):
        descriptors.append(
            EtabsTableDescriptor(
                table_key=str(table_key),
                display_name=_sequence_value(display_names, index),
                import_type=_sequence_value(import_types, index),
                is_empty=_sequence_bool_value(empty_flags, index),
                source="live_sap_model",
            )
        )
    return tuple(descriptors)


def _descriptor_from_mapping(item: Mapping[object, object], *, source: str) -> EtabsTableDescriptor:
    return EtabsTableDescriptor(
        table_key=_required_text(item.get("table_key"), field_name="table_key"),
        display_name=_optional_text(item.get("display_name")),
        import_type=_optional_text(item.get("import_type")),
        is_empty=_optional_bool(item.get("is_empty")),
        source=source,
    )


def _columns_and_row_count_from_display_array(raw_table: object) -> tuple[tuple[str, ...], int | None]:
    if not isinstance(raw_table, Sequence) or isinstance(raw_table, (str, bytes, bytearray)):
        return (), None
    fields = next(
        (
            tuple(str(item) for item in value)
            for value in raw_table
            if isinstance(value, Sequence)
            and not isinstance(value, (str, bytes, bytearray))
            and value
            and all(isinstance(item, str) for item in value)
        ),
        (),
    )
    if not fields:
        return (), None
    flat_data = next(
        (
            tuple(value)
            for value in reversed(tuple(raw_table))
            if isinstance(value, Sequence)
            and not isinstance(value, (str, bytes, bytearray))
            and value
            and not all(isinstance(item, str) for item in value)
        ),
        (),
    )
    if not flat_data:
        return fields, 0
    return fields, len(flat_data) // len(fields)


def _matching_length_sequence(
    sequences: Sequence[tuple[object, ...]],
    length: int,
    *,
    exclude: Sequence[tuple[object, ...]],
) -> tuple[object, ...]:
    excluded = {id(sequence) for sequence in exclude}
    for sequence in sequences:
        if id(sequence) not in excluded and len(sequence) == length:
            return sequence
    return tuple(None for _ in range(length))


def _matching_bool_sequence(sequences: Sequence[tuple[object, ...]], length: int) -> tuple[object, ...]:
    for sequence in sequences:
        if len(sequence) == length and all(isinstance(item, bool) for item in sequence):
            return sequence
    return tuple(None for _ in range(length))


def _sequence_value(sequence: Sequence[object], index: int) -> str | None:
    if index >= len(sequence):
        return None
    return _optional_text(sequence[index])


def _sequence_bool_value(sequence: Sequence[object], index: int) -> bool | None:
    if index >= len(sequence):
        return None
    return _optional_bool(sequence[index])


def _required_text(value: object, *, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _optional_text(value: object) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    return bool(value)


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(nested) for key, nested in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    return str(value)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


__all__ = [
    "EtabsTableDescriptor",
    "EtabsTableDiscoverySource",
    "EtabsTableFetchResult",
    "GeometryTableCandidate",
    "GeometryTableDiscoveryResult",
    "GEOMETRY_TABLE_KEYWORDS",
    "MappingEtabsTableDiscoverySource",
    "POSSIBLE_GEOMETRY_COLUMNS",
    "create_live_etabs_table_discovery_source",
    "load_mapping_table_discovery_source_from_json",
    "run_live_geometry_table_discovery",
    "write_table_discovery_attach_failure_outputs",
]
