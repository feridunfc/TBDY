"""Immutable factual evidence-capture lifecycle identity for F0 integration."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class EvidenceEpochOrigin(StrEnum):
    LIVE_CAPTURE = "LIVE_CAPTURE"
    FIXTURE_REPLAY = "FIXTURE_REPLAY"
    REACQUIRE = "REACQUIRE"


def _canonical_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonblank string")
    if value != value.strip():
        raise ValueError(f"{label} must not contain leading or trailing whitespace")
    return value


def _optional_text(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    return _canonical_text(value, label)


@dataclass(frozen=True, slots=True)
class EvidenceEpoch:
    """One immutable evidence capture generation; never regulatory truth."""

    epoch_id: str
    model_fingerprint: str
    origin: EvidenceEpochOrigin | str
    source_fingerprint: str | None = None
    predecessor_epoch_ref: str | None = None
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _canonical_text(self.epoch_id, "epoch_id")
        _canonical_text(self.model_fingerprint, "model_fingerprint")
        try:
            origin = EvidenceEpochOrigin(str(self.origin))
        except ValueError as exc:
            raise ValueError("origin must be a bounded EvidenceEpochOrigin") from exc
        object.__setattr__(self, "origin", origin)
        object.__setattr__(
            self,
            "source_fingerprint",
            _optional_text(self.source_fingerprint, "source_fingerprint"),
        )
        object.__setattr__(
            self,
            "predecessor_epoch_ref",
            _optional_text(self.predecessor_epoch_ref, "predecessor_epoch_ref"),
        )
        if type(self.provenance_refs) is not tuple:
            raise TypeError("provenance_refs must be a tuple of strings")
        refs = self.provenance_refs
        if any(not isinstance(item, str) for item in refs):
            raise TypeError("provenance_refs must contain strings only")
        object.__setattr__(
            self,
            "provenance_refs",
            tuple(_canonical_text(item, "provenance_ref") for item in refs),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "epoch_id": self.epoch_id,
            "model_fingerprint": self.model_fingerprint,
            "origin": self.origin.value,
            "source_fingerprint": self.source_fingerprint,
            "predecessor_epoch_ref": self.predecessor_epoch_ref,
            "provenance_refs": list(self.provenance_refs),
        }


__all__ = ["EvidenceEpoch", "EvidenceEpochOrigin"]
