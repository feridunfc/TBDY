"""Neutral factual model-identity contract shared by live integrations.

This module is intentionally import-safe: it has no ETABS COM, integration,
regulatory, product, or runner dependency. It is the single implementation
owner for observed ETABS model-path normalization and the corresponding stable
model fingerprint.
"""
from __future__ import annotations

import hashlib
import json
import ntpath
from collections.abc import Mapping

MODEL_IDENTITY_CONTRACT = "ETABS_MODEL_IDENTITY_V1"
MODEL_FINGERPRINT_PREFIX = "etabs:model-identity:sha256:"
MISSING_MODEL_IDENTITY_STATUS = "BLOCKED_BY_MISSING_LIVE_EPOCH_IDENTITY"


class ModelIdentityError(RuntimeError):
    """The accepted factual model-path source did not yield usable identity."""

    status = MISSING_MODEL_IDENTITY_STATUS


def _canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def normalize_observed_etabs_model_path(model_path: object) -> str:
    """Normalize the observed ETABS model path using the frozen VS1 contract."""
    if not isinstance(model_path, str) or not model_path.strip():
        raise ModelIdentityError(MISSING_MODEL_IDENTITY_STATUS)
    return ntpath.normcase(ntpath.normpath(model_path.strip()))


def model_fingerprint_from_path(model_path: object) -> str:
    """Return the frozen ETABS_MODEL_IDENTITY_V1 path fingerprint byte-for-byte."""
    normalized_path = normalize_observed_etabs_model_path(model_path)
    digest = hashlib.sha256(
        _canonical_json_bytes(
            {
                "contract": MODEL_IDENTITY_CONTRACT,
                "model_path": normalized_path,
            }
        )
    ).hexdigest()
    return f"{MODEL_FINGERPRINT_PREFIX}{digest}"


__all__ = [
    "MODEL_IDENTITY_CONTRACT",
    "MODEL_FINGERPRINT_PREFIX",
    "MISSING_MODEL_IDENTITY_STATUS",
    "ModelIdentityError",
    "normalize_observed_etabs_model_path",
    "model_fingerprint_from_path",
]
