from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CheckResult:
    id: str
    component: str
    check_type: str
    status: str
    demand: float | None
    capacity: float | None
    ratio: float | None
    evidence: Mapping[str, object]
    messages: tuple[str, ...]
    story: str | None = None
    section: str | None = None
    unit: str | None = None
    code_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CheckAdapter:
    def __init__(self, *_: object, **__: object) -> None:
        pass

    def adapt(self, package: object) -> list[CheckResult]:
        component = _required_str(_read(package, "component"), "package.component")
        story = _optional_str(_read(package, "story"))
        section = _optional_str(_read(package, "section"))
        evidence = _mapping_or_empty(_read(package, "evidence"))
        package_messages = _tuple_of_strings(_read(package, "messages"))
        checks = _read(package, "checks")

        if checks is None:
            raise ValueError("package.checks is required")

        return [
            self._map_check(
                component=component,
                story=story,
                section=section,
                evidence=evidence,
                package_messages=package_messages,
                check=check,
            )
            for check in _sequence(checks, "package.checks")
        ]

    def adapt_all(self, evaluation_results: Mapping[str, object]) -> list[CheckResult]:
        packages = evaluation_results.get("packages") or evaluation_results.get("results") or []
        if isinstance(packages, Mapping):
            packages = packages.values()
        return [result for package in _sequence(packages, "evaluation packages") for result in self.adapt(package)]

    def _map_check(
        self,
        *,
        component: str,
        story: str | None,
        section: str | None,
        evidence: Mapping[str, object],
        package_messages: tuple[str, ...],
        check: object,
    ) -> CheckResult:
        check_type = _required_str(_read(check, "check_type"), "check.check_type")
        check_messages = _tuple_of_strings(_read(check, "messages"))
        return CheckResult(
            id=_result_id(component, story, check_type),
            component=component,
            check_type=check_type,
            status=_required_str(_read(check, "status"), "check.status"),
            demand=_float_or_none(_read(check, "demand")),
            capacity=_float_or_none(_read(check, "capacity")),
            ratio=_float_or_none(_read(check, "ratio")),
            evidence=evidence,
            messages=package_messages + check_messages,
            story=story,
            section=section,
            unit=_optional_str(_read(check, "unit")),
            code_ref=_optional_str(_read(check, "code_ref")),
        )


def _read(obj: object, name: str) -> object:
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def _required_str(value: object, field_name: str) -> str:
    if value is None or str(value) == "":
        raise ValueError(f"{field_name} is required")
    return str(value)


def _optional_str(value: object) -> str | None:
    if value is None or str(value) == "":
        return None
    return str(value)


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("boolean values are not valid numeric check values")
    return float(value)


def _mapping_or_empty(value: object) -> Mapping[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("package.evidence must be a mapping")
    return value


def _tuple_of_strings(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, Sequence):
        raise ValueError("messages must be a sequence of strings")
    return tuple(str(item) for item in value)


def _sequence(value: object, field_name: str) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    raise ValueError(f"{field_name} must be a sequence")


def _result_id(component: str, story: str | None, check_type: str) -> str:
    parts = [component]
    if story:
        parts.append(story)
    parts.append(check_type)
    return ":".join(parts)
