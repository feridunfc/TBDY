"""Deterministic offline fixture and replay support.

Fixtures contain immutable ``ETABSGatewayContext`` values only. They never
contain raw COM references and never invoke ETABS, Windows COM, analysis,
design, table extraction, or model mutation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final, Mapping

from .contracts import (
    AttachMode,
    ETABSApplicationInfo,
    ETABSAttachment,
    ETABSGatewayContext,
    ETABSModelContext,
    ETABSUnitContext,
)
from .errors import ETABSFixtureValidationError

FIXTURE_SCHEMA_VERSION: Final[str] = "1.0"
FIXTURE_TYPE: Final[str] = "ETABS_GATEWAY_CONTEXT"

_ENVELOPE_KEYS = frozenset(
    {"schema_version", "fixture_type", "context", "sha256"}
)
_SIGNED_PAYLOAD_KEYS = frozenset(
    {"schema_version", "fixture_type", "context"}
)
_CONTEXT_KEYS = frozenset(
    {"attachment", "application", "model", "observed_at_utc"}
)
_ATTACHMENT_KEYS = frozenset(
    {
        "prog_id",
        "attach_mode",
        "attached_at_utc",
        "worker_thread_id",
    }
)
_APPLICATION_KEYS = frozenset(
    {"version", "process_id", "attached_at_utc"}
)
_MODEL_KEYS = frozenset(
    {"has_open_model", "model_path", "is_locked", "units"}
)
_UNIT_KEYS = frozenset(
    {"present_units_code", "display_name", "source_contract"}
)


@dataclass(frozen=True, slots=True)
class ETABSGatewayFixture:
    """Validated fixture envelope and immutable replay value."""

    context: ETABSGatewayContext
    sha256: str
    schema_version: str = FIXTURE_SCHEMA_VERSION
    fixture_type: str = FIXTURE_TYPE

    def __post_init__(self) -> None:
        if self.schema_version != FIXTURE_SCHEMA_VERSION:
            raise ValueError("Unsupported fixture schema version.")
        if self.fixture_type != FIXTURE_TYPE:
            raise ValueError("Unsupported fixture type.")
        if len(self.sha256) != 64:
            raise ValueError("sha256 must contain 64 hexadecimal characters.")
        try:
            int(self.sha256, 16)
        except ValueError as exc:
            raise ValueError("sha256 must be hexadecimal.") from exc


class FixtureReplayProvider:
    """Read-only provider that replays one validated immutable context."""

    def __init__(self, fixture: ETABSGatewayFixture) -> None:
        self._fixture = fixture

    @classmethod
    def from_json(cls, text: str) -> FixtureReplayProvider:
        return cls(parse_gateway_context_fixture(text))

    @classmethod
    def from_path(
        cls,
        path: str | Path,
    ) -> FixtureReplayProvider:
        return cls(load_gateway_context_fixture(path))

    @property
    def fingerprint(self) -> str:
        return self._fixture.sha256

    @property
    def fixture(self) -> ETABSGatewayFixture:
        return self._fixture

    def read_context(self) -> ETABSGatewayContext:
        return self._fixture.context


def context_to_payload(
    context: ETABSGatewayContext,
) -> dict[str, Any]:
    units = context.model.units

    return {
        "attachment": {
            "prog_id": context.attachment.prog_id,
            "attach_mode": context.attachment.attach_mode.value,
            "attached_at_utc": _format_utc(
                context.attachment.attached_at_utc
            ),
            "worker_thread_id": context.attachment.worker_thread_id,
        },
        "application": {
            "version": context.application.version,
            "process_id": context.application.process_id,
            "attached_at_utc": _format_utc(
                context.application.attached_at_utc
            ),
        },
        "model": {
            "has_open_model": context.model.has_open_model,
            "model_path": context.model.model_path,
            "is_locked": context.model.is_locked,
            "units": (
                None
                if units is None
                else {
                    "present_units_code": units.present_units_code,
                    "display_name": units.display_name,
                    "source_contract": units.source_contract,
                }
            ),
        },
        "observed_at_utc": _format_utc(context.observed_at_utc),
    }


def context_from_payload(
    raw_payload: object,
) -> ETABSGatewayContext:
    payload = _require_mapping(
        raw_payload,
        field_path="context",
    )
    _require_exact_keys(payload, _CONTEXT_KEYS, "context")

    attachment_payload = _require_mapping(
        payload["attachment"],
        field_path="context.attachment",
    )
    _require_exact_keys(
        attachment_payload,
        _ATTACHMENT_KEYS,
        "context.attachment",
    )

    application_payload = _require_mapping(
        payload["application"],
        field_path="context.application",
    )
    _require_exact_keys(
        application_payload,
        _APPLICATION_KEYS,
        "context.application",
    )

    model_payload = _require_mapping(
        payload["model"],
        field_path="context.model",
    )
    _require_exact_keys(
        model_payload,
        _MODEL_KEYS,
        "context.model",
    )

    try:
        attach_mode = AttachMode(
            _require_string(
                attachment_payload["attach_mode"],
                "context.attachment.attach_mode",
            )
        )
    except ValueError as exc:
        raise _validation_error(
            "Invalid attachment mode.",
            "context.attachment.attach_mode",
            value=attachment_payload["attach_mode"],
        ) from exc

    attachment = ETABSAttachment(
        prog_id=_require_string(
            attachment_payload["prog_id"],
            "context.attachment.prog_id",
        ),
        attach_mode=attach_mode,
        attached_at_utc=_parse_utc(
            attachment_payload["attached_at_utc"],
            "context.attachment.attached_at_utc",
        ),
        worker_thread_id=_require_int(
            attachment_payload["worker_thread_id"],
            "context.attachment.worker_thread_id",
            minimum=1,
        ),
    )

    process_id_raw = application_payload["process_id"]
    process_id = (
        None
        if process_id_raw is None
        else _require_int(
            process_id_raw,
            "context.application.process_id",
            minimum=1,
        )
    )

    application = ETABSApplicationInfo(
        version=_require_string(
            application_payload["version"],
            "context.application.version",
        ),
        process_id=process_id,
        attached_at_utc=_parse_utc(
            application_payload["attached_at_utc"],
            "context.application.attached_at_utc",
        ),
    )

    units_raw = model_payload["units"]
    units: ETABSUnitContext | None
    if units_raw is None:
        units = None
    else:
        unit_payload = _require_mapping(
            units_raw,
            field_path="context.model.units",
        )
        _require_exact_keys(
            unit_payload,
            _UNIT_KEYS,
            "context.model.units",
        )
        display_name_raw = unit_payload["display_name"]
        display_name = (
            None
            if display_name_raw is None
            else _require_string(
                display_name_raw,
                "context.model.units.display_name",
            )
        )
        units = ETABSUnitContext(
            present_units_code=_require_int(
                unit_payload["present_units_code"],
                "context.model.units.present_units_code",
                minimum=0,
            ),
            display_name=display_name,
            source_contract=_require_string(
                unit_payload["source_contract"],
                "context.model.units.source_contract",
            ),
        )

    model_path_raw = model_payload["model_path"]
    model_path = (
        None
        if model_path_raw is None
        else _require_string(
            model_path_raw,
            "context.model.model_path",
        )
    )

    is_locked_raw = model_payload["is_locked"]
    is_locked = (
        None
        if is_locked_raw is None
        else _require_bool(
            is_locked_raw,
            "context.model.is_locked",
        )
    )

    try:
        model = ETABSModelContext(
            has_open_model=_require_bool(
                model_payload["has_open_model"],
                "context.model.has_open_model",
            ),
            model_path=model_path,
            is_locked=is_locked,
            units=units,
        )

        return ETABSGatewayContext(
            attachment=attachment,
            application=application,
            model=model,
            observed_at_utc=_parse_utc(
                payload["observed_at_utc"],
                "context.observed_at_utc",
            ),
        )
    except ValueError as exc:
        raise ETABSFixtureValidationError(
            "Fixture context violates gateway contract invariants.",
            operation="fixture_context_build",
            details={
                "stage": "contract_validation",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc


def build_gateway_context_fixture(
    context: ETABSGatewayContext,
) -> ETABSGatewayFixture:
    signed_payload = _signed_payload(context)
    fingerprint = _fingerprint_signed_payload(signed_payload)
    return ETABSGatewayFixture(
        context=context,
        sha256=fingerprint,
    )


def canonical_gateway_context_fixture_json(
    fixture_or_context: ETABSGatewayFixture | ETABSGatewayContext,
) -> str:
    fixture = (
        fixture_or_context
        if isinstance(fixture_or_context, ETABSGatewayFixture)
        else build_gateway_context_fixture(fixture_or_context)
    )
    envelope = {
        "schema_version": fixture.schema_version,
        "fixture_type": fixture.fixture_type,
        "context": context_to_payload(fixture.context),
        "sha256": fixture.sha256,
    }
    return _canonical_json(envelope)


def parse_gateway_context_fixture(
    text: str,
) -> ETABSGatewayFixture:
    if not isinstance(text, str) or not text.strip():
        raise _validation_error(
            "Fixture JSON must be a non-empty string.",
            "$",
        )

    try:
        raw_envelope = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ETABSFixtureValidationError(
            "Fixture is not valid JSON.",
            operation="fixture_parse",
            details={
                "stage": "json_decode",
                "line": exc.lineno,
                "column": exc.colno,
                "message": exc.msg,
            },
        ) from exc

    envelope = _require_mapping(raw_envelope, field_path="$")
    _require_exact_keys(envelope, _ENVELOPE_KEYS, "$")

    schema_version = _require_string(
        envelope["schema_version"],
        "$.schema_version",
    )
    if schema_version != FIXTURE_SCHEMA_VERSION:
        raise _validation_error(
            "Unsupported fixture schema version.",
            "$.schema_version",
            expected=FIXTURE_SCHEMA_VERSION,
            value=schema_version,
        )

    fixture_type = _require_string(
        envelope["fixture_type"],
        "$.fixture_type",
    )
    if fixture_type != FIXTURE_TYPE:
        raise _validation_error(
            "Unsupported fixture type.",
            "$.fixture_type",
            expected=FIXTURE_TYPE,
            value=fixture_type,
        )

    declared_sha256 = _require_string(
        envelope["sha256"],
        "$.sha256",
    ).lower()
    if len(declared_sha256) != 64:
        raise _validation_error(
            "Fixture fingerprint must have 64 characters.",
            "$.sha256",
            value=declared_sha256,
        )
    try:
        int(declared_sha256, 16)
    except ValueError as exc:
        raise _validation_error(
            "Fixture fingerprint must be hexadecimal.",
            "$.sha256",
            value=declared_sha256,
        ) from exc

    signed_payload = {
        "schema_version": schema_version,
        "fixture_type": fixture_type,
        "context": envelope["context"],
    }
    _require_exact_keys(
        signed_payload,
        _SIGNED_PAYLOAD_KEYS,
        "$signed",
    )
    observed_sha256 = _fingerprint_signed_payload(signed_payload)
    if observed_sha256 != declared_sha256:
        raise ETABSFixtureValidationError(
            "Fixture fingerprint verification failed.",
            operation="fixture_verify",
            details={
                "stage": "sha256_mismatch",
                "declared_sha256": declared_sha256,
                "observed_sha256": observed_sha256,
            },
        )

    context = context_from_payload(envelope["context"])
    return ETABSGatewayFixture(
        context=context,
        sha256=declared_sha256,
        schema_version=schema_version,
        fixture_type=fixture_type,
    )


def dump_gateway_context_fixture(
    context: ETABSGatewayContext,
    path: str | Path,
) -> ETABSGatewayFixture:
    fixture = build_gateway_context_fixture(context)
    destination = Path(path)
    destination.write_text(
        canonical_gateway_context_fixture_json(fixture) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return fixture


def load_gateway_context_fixture(
    path: str | Path,
) -> ETABSGatewayFixture:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ETABSFixtureValidationError(
            "Fixture file could not be read.",
            operation="fixture_load",
            details={
                "stage": "file_read",
                "path": str(source),
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc
    return parse_gateway_context_fixture(text)


def _signed_payload(
    context: ETABSGatewayContext,
) -> dict[str, Any]:
    return {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "fixture_type": FIXTURE_TYPE,
        "context": context_to_payload(context),
    }


def _fingerprint_signed_payload(
    signed_payload: Mapping[str, Any],
) -> str:
    return hashlib.sha256(
        _canonical_json(signed_payload).encode("utf-8")
    ).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ETABSFixtureValidationError(
            "Datetime must be timezone-aware.",
            operation="fixture_serialize",
            details={"stage": "datetime_validation"},
        )
    normalized = value.astimezone(timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")


def _parse_utc(raw_value: object, field_path: str) -> datetime:
    value = _require_string(raw_value, field_path)
    if not value.endswith("Z"):
        raise _validation_error(
            "UTC datetime must use the Z suffix.",
            field_path,
            value=value,
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _validation_error(
            "Invalid UTC datetime.",
            field_path,
            value=value,
        ) from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise _validation_error(
            "Datetime must be expressed in UTC.",
            field_path,
            value=value,
        )
    return parsed


def _require_mapping(
    raw_value: object,
    *,
    field_path: str,
) -> Mapping[str, Any]:
    if not isinstance(raw_value, dict):
        raise _validation_error(
            "Expected a JSON object.",
            field_path,
            value_type=type(raw_value).__name__,
        )
    return raw_value


def _require_exact_keys(
    mapping: Mapping[str, Any],
    expected: frozenset[str],
    field_path: str,
) -> None:
    observed = frozenset(mapping)
    if observed == expected:
        return
    raise _validation_error(
        "Object keys do not match the fixture schema.",
        field_path,
        missing=sorted(expected - observed),
        unexpected=sorted(observed - expected),
    )


def _require_string(raw_value: object, field_path: str) -> str:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise _validation_error(
            "Expected a non-empty string.",
            field_path,
            value_type=type(raw_value).__name__,
        )
    return raw_value


def _require_bool(raw_value: object, field_path: str) -> bool:
    if not isinstance(raw_value, bool):
        raise _validation_error(
            "Expected a boolean.",
            field_path,
            value_type=type(raw_value).__name__,
        )
    return raw_value


def _require_int(
    raw_value: object,
    field_path: str,
    *,
    minimum: int,
) -> int:
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise _validation_error(
            "Expected an integer.",
            field_path,
            value_type=type(raw_value).__name__,
        )
    if raw_value < minimum:
        raise _validation_error(
            "Integer is below the permitted minimum.",
            field_path,
            minimum=minimum,
            value=raw_value,
        )
    return raw_value


def _validation_error(
    message: str,
    field_path: str,
    **details: object,
) -> ETABSFixtureValidationError:
    return ETABSFixtureValidationError(
        message,
        operation="fixture_validate",
        details={
            "stage": "schema_validation",
            "field_path": field_path,
            **details,
        },
    )


__all__ = [
    "ETABSGatewayFixture",
    "FIXTURE_SCHEMA_VERSION",
    "FIXTURE_TYPE",
    "FixtureReplayProvider",
    "build_gateway_context_fixture",
    "canonical_gateway_context_fixture_json",
    "context_from_payload",
    "context_to_payload",
    "dump_gateway_context_fixture",
    "load_gateway_context_fixture",
    "parse_gateway_context_fixture",
]
