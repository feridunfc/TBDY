from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum


class DatasetStatus(str, Enum):
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    EMPTY = "EMPTY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DatasetCheck:
    dataset: str
    status: DatasetStatus
    required_by: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class DatasetValidationResult:
    checks: tuple[DatasetCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.status is DatasetStatus.PRESENT for check in self.checks)

    @property
    def missing(self) -> tuple[DatasetCheck, ...]:
        return tuple(check for check in self.checks if check.status is DatasetStatus.MISSING)

    @property
    def empty(self) -> tuple[DatasetCheck, ...]:
        return tuple(check for check in self.checks if check.status is DatasetStatus.EMPTY)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "checks": [
                {
                    "dataset": check.dataset,
                    "status": check.status.value,
                    "required_by": list(check.required_by),
                    "message": check.message,
                }
                for check in self.checks
            ],
            "missing": [check.dataset for check in self.missing],
            "empty": [check.dataset for check in self.empty],
        }


@dataclass(frozen=True)
class DatasetValidator:
    required_datasets: tuple[str, ...]
    _required_by: tuple[tuple[str, tuple[str, ...]], ...] = field(default_factory=tuple, repr=False)

    @classmethod
    def from_catalog(cls, catalog: object, *, enabled_only: bool = True) -> "DatasetValidator":
        checks_obj = _member(catalog, "checks")
        required_by: dict[str, set[str]] = {}

        for fallback_check_id, check in _iter_named_objects(checks_obj):
            if enabled_only and not _runner_enabled(check):
                continue

            check_id = _string_member(check, "id", fallback_check_id)
            for dataset in _string_sequence_member(check, "required_datasets"):
                required_by.setdefault(dataset, set()).add(check_id)

        required_datasets = tuple(sorted(required_by))
        required_by_items = tuple(
            (dataset, tuple(sorted(check_ids)))
            for dataset, check_ids in sorted(required_by.items())
        )
        return cls(required_datasets=required_datasets, _required_by=required_by_items)

    def validate(self, context: object) -> DatasetValidationResult:
        required_by = dict(self._required_by)
        checks = tuple(
            DatasetCheck(
                dataset=dataset,
                status=_dataset_status(context, dataset),
                required_by=required_by.get(dataset, ()),
                message=_message(dataset, _dataset_status(context, dataset)),
            )
            for dataset in self.required_datasets
        )
        return DatasetValidationResult(checks=checks)


def _member(obj: object, name: str) -> object:
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def _string_member(obj: object, name: str, default: str) -> str:
    value = _member(obj, name)
    if value in (None, ""):
        return default
    return str(value)


def _runner_enabled(check: object) -> bool:
    value = _member(check, "runner_enabled")
    if value is None:
        return True
    return bool(value)


def _iter_named_objects(obj: object) -> tuple[tuple[str, object], ...]:
    if isinstance(obj, Mapping):
        return tuple((str(key), value) for key, value in obj.items())
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        return tuple((str(index), value) for index, value in enumerate(obj))
    return ()


def _string_sequence_member(obj: object, name: str) -> tuple[str, ...]:
    value = _member(obj, name)
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if str(item))
    return ()


def _context_lookup(context: object, dataset: str) -> tuple[bool, object]:
    if isinstance(context, Mapping) and dataset in context:
        return True, context[dataset]
    if hasattr(context, dataset):
        return True, getattr(context, dataset)
    return False, None


def _is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (str, dict, list, tuple, set)):
        return len(value) == 0
    return False


def _dataset_status(context: object, dataset: str) -> DatasetStatus:
    exists, value = _context_lookup(context, dataset)
    if not exists:
        return DatasetStatus.MISSING
    if _is_empty(value):
        return DatasetStatus.EMPTY
    return DatasetStatus.PRESENT


def _message(dataset: str, status: DatasetStatus) -> str:
    if status is DatasetStatus.PRESENT:
        return f"Dataset '{dataset}' is present."
    if status is DatasetStatus.MISSING:
        return f"Dataset '{dataset}' is missing."
    if status is DatasetStatus.EMPTY:
        return f"Dataset '{dataset}' is empty."
    return f"Dataset '{dataset}' status is unknown."
