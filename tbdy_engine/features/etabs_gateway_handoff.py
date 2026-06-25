"""Typed ETABS gateway context to FeatureSnapshot handoff.

Dependency direction is strictly one-way: ``tbdy_engine -> etabs_gateway``.
This layer emits observed metadata and traceability evidence only. It never
emits checks, ratios, pass/fail decisions, or TBDY compliance verdicts.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from etabs_gateway.contracts import ETABSGatewayContext
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus

_SOURCE_TABLE = "ETABS_GATEWAY_CONTEXT"
_ACTUAL_SOURCE = "ETABSGatewayContext"
_RESOLVER = "etabs_gateway_context_handoff"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class GatewayContextOrigin(StrEnum):
    LIVE_READ_ONLY = "LIVE_READ_ONLY"
    FIXTURE_REPLAY = "FIXTURE_REPLAY"


@dataclass(frozen=True, slots=True)
class GatewayFeatureSnapshotInput:
    context: ETABSGatewayContext
    origin: GatewayContextOrigin | str
    source_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.context, ETABSGatewayContext):
            raise TypeError(
                "GatewayFeatureSnapshotInput.context must be ETABSGatewayContext."
            )

        normalized_origin = GatewayContextOrigin(str(self.origin))
        object.__setattr__(self, "origin", normalized_origin)

        fingerprint = self.source_fingerprint
        if fingerprint is not None:
            normalized = fingerprint.strip().lower()
            if not _SHA256_PATTERN.fullmatch(normalized):
                raise ValueError(
                    "source_fingerprint must be a 64-character lowercase "
                    "hexadecimal SHA-256 value."
                )
            object.__setattr__(self, "source_fingerprint", normalized)

        if (
            normalized_origin is GatewayContextOrigin.FIXTURE_REPLAY
            and self.source_fingerprint is None
        ):
            raise ValueError(
                "FIXTURE_REPLAY origin requires source_fingerprint."
            )


def build_feature_snapshot_from_gateway_context(
    handoff_input: GatewayFeatureSnapshotInput,
) -> FeatureSnapshot:
    if not isinstance(handoff_input, GatewayFeatureSnapshotInput):
        raise TypeError("handoff_input must be GatewayFeatureSnapshotInput.")

    context = handoff_input.context
    evidence_context = {
        "origin": handoff_input.origin.value,
        "source_fingerprint": handoff_input.source_fingerprint,
        "prog_id": context.attachment.prog_id,
        "attach_mode": context.attachment.attach_mode.value,
        "observed_at_utc": _format_utc(context.observed_at_utc),
    }

    features = {
        "etabs.attachment.prog_id": _resolved_feature(
            "etabs.attachment.prog_id",
            context.attachment.prog_id,
            "SOURCE_SYSTEM_IDENTITY",
            "attachment.prog_id",
            evidence_context,
        ),
        "etabs.attachment.mode": _resolved_feature(
            "etabs.attachment.mode",
            context.attachment.attach_mode.value,
            "SOURCE_CONNECTION_METADATA",
            "attachment.attach_mode",
            evidence_context,
        ),
        "etabs.attachment.worker_thread_id": _resolved_feature(
            "etabs.attachment.worker_thread_id",
            context.attachment.worker_thread_id,
            "SOURCE_CONNECTION_METADATA",
            "attachment.worker_thread_id",
            evidence_context,
        ),
        "etabs.application.version": _resolved_feature(
            "etabs.application.version",
            context.application.version,
            "SOFTWARE_METADATA",
            "application.version",
            evidence_context,
        ),
        "etabs.application.process_id": _optional_feature(
            "etabs.application.process_id",
            context.application.process_id,
            "PROCESS_IDENTITY",
            "application.process_id",
            evidence_context,
            "Gateway context did not expose an application process ID.",
        ),
        "etabs.model.open": _resolved_feature(
            "etabs.model.open",
            context.model.has_open_model,
            "MODEL_METADATA",
            "model.has_open_model",
            evidence_context,
        ),
        "etabs.model.path": _optional_feature(
            "etabs.model.path",
            context.model.model_path,
            "MODEL_IDENTITY",
            "model.model_path",
            evidence_context,
            "No model path was observed in the gateway context.",
        ),
        "etabs.model.locked": _optional_feature(
            "etabs.model.locked",
            context.model.is_locked,
            "MODEL_METADATA",
            "model.is_locked",
            evidence_context,
            "Model lock metadata was unavailable.",
        ),
        "etabs.model.units_code": _optional_feature(
            "etabs.model.units_code",
            None if context.model.units is None else context.model.units.present_units_code,
            "UNIT_METADATA",
            "model.units.present_units_code",
            evidence_context,
            "Present-units metadata was unavailable.",
        ),
        "etabs.model.units_display_name": _optional_feature(
            "etabs.model.units_display_name",
            None if context.model.units is None else context.model.units.display_name,
            "UNIT_METADATA",
            "model.units.display_name",
            evidence_context,
            "The gateway intentionally did not guess a display name for the unit code.",
        ),
    }

    return FeatureSnapshot(
        component_type="ETABS_MODEL_CONTEXT",
        component_id=_component_id(handoff_input),
        identity={
            "source_system": "ETABS",
            "source_contract": _ACTUAL_SOURCE,
            "origin": handoff_input.origin.value,
            "source_fingerprint": handoff_input.source_fingerprint,
            "prog_id": context.attachment.prog_id,
            "attach_mode": context.attachment.attach_mode.value,
            "application_version": context.application.version,
            "model_name": context.model.model_name,
            "model_path": context.model.model_path,
            "observed_at_utc": _format_utc(context.observed_at_utc),
        },
        features=features,
        evidence_by_feature={name: value.evidence for name, value in features.items()},
    )


def _component_id(handoff_input: GatewayFeatureSnapshotInput) -> str:
    context = handoff_input.context
    payload = {
        "prog_id": context.attachment.prog_id,
        "application_version": context.application.version,
        "process_id": context.application.process_id,
        "model_path": context.model.model_path,
        "observed_at_utc": _format_utc(context.observed_at_utc),
        "origin": handoff_input.origin.value,
        "source_fingerprint": handoff_input.source_fingerprint,
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return f"ETABS_CONTEXT:{digest[:20]}"


def _resolved_feature(
    feature_name: str,
    value: Any,
    semantic_role: str,
    source_column: str,
    evidence_context: dict[str, Any],
) -> FeatureValue:
    evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table=_SOURCE_TABLE,
        actual_table_name=_ACTUAL_SOURCE,
        source_column=source_column,
        source_row=evidence_context,
        raw_value=value,
        normalized_value=value,
        resolver=_RESOLVER,
    )
    return FeatureValue(
        feature_name=feature_name,
        value=value,
        semantic_role=semantic_role,
        status=FeatureValueStatus.RESOLVED,
        evidence=(evidence,),
    )


def _optional_feature(
    feature_name: str,
    value: Any,
    semantic_role: str,
    source_column: str,
    evidence_context: dict[str, Any],
    missing_reason: str,
) -> FeatureValue:
    if value is not None:
        return _resolved_feature(
            feature_name,
            value,
            semantic_role,
            source_column,
            evidence_context,
        )

    evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.MISSING,
        source_table=_SOURCE_TABLE,
        actual_table_name=_ACTUAL_SOURCE,
        source_column=source_column,
        source_row=evidence_context,
        raw_value=None,
        normalized_value=None,
        resolver=_RESOLVER,
        reason=missing_reason,
    )
    return FeatureValue(
        feature_name=feature_name,
        value=None,
        semantic_role=semantic_role,
        status=FeatureValueStatus.MISSING,
        evidence=(evidence,),
    )


def _format_utc(value: Any) -> str:
    return value.isoformat().replace("+00:00", "Z")


__all__ = [
    "GatewayContextOrigin",
    "GatewayFeatureSnapshotInput",
    "build_feature_snapshot_from_gateway_context",
]
