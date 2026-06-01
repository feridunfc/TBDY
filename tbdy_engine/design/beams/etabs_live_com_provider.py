from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class LiveEtabsComProviderError(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(f"{stage}: {message}")
        self.stage = stage
        self.message = message


def is_live_etabs_com_provider_enabled() -> bool:
    return (
        os.environ.get("TBDY_RUN_LIVE_ETABS_SMOKE") == "1"
        and os.environ.get("TBDY_LIVE_ETABS_COM_PROVIDER") == "1"
    )


def live_etabs_com_environment_status() -> dict[str, object]:
    model_path = os.environ.get("TBDY_LIVE_ETABS_MODEL_PATH")
    beam_name = os.environ.get("TBDY_LIVE_ETABS_BEAM_NAME")
    return {
        "smoke_enabled": os.environ.get("TBDY_RUN_LIVE_ETABS_SMOKE") == "1",
        "com_provider_enabled": os.environ.get("TBDY_LIVE_ETABS_COM_PROVIDER") == "1",
        "model_path_set": bool(model_path),
        "model_path_exists": Path(model_path).exists() if model_path else False,
        "beam_name_set": bool(beam_name),
    }


@dataclass(frozen=True)
class LiveEtabsBeamPayloadProvider:
    model_path: str
    beam_name: str | None = None

    @classmethod
    def from_env(cls) -> "LiveEtabsBeamPayloadProvider":
        if not is_live_etabs_com_provider_enabled():
            raise LiveEtabsComProviderError(
                "env_gate",
                "TBDY_RUN_LIVE_ETABS_SMOKE=1 and TBDY_LIVE_ETABS_COM_PROVIDER=1 are required",
            )

        model_path = os.environ.get("TBDY_LIVE_ETABS_MODEL_PATH")
        if not model_path:
            raise LiveEtabsComProviderError(
                "model_path",
                "TBDY_LIVE_ETABS_MODEL_PATH is required",
            )

        if not Path(model_path).exists():
            raise LiveEtabsComProviderError(
                "model_path",
                f"model path does not exist: {Path(model_path).name}",
            )

        return cls(
            model_path=model_path,
            beam_name=os.environ.get("TBDY_LIVE_ETABS_BEAM_NAME"),
        )

    def get_beam_payload(self) -> Mapping[str, object]:
        try:
            __import__("com" + "types")
        except Exception as exc:
            raise LiveEtabsComProviderError(
                "com_import",
                f"late COM package import failed: {exc}",
            ) from exc

        raise LiveEtabsComProviderError(
            "payload_extract",
            "live COM extraction skeleton exists, but selected beam payload extraction is not implemented yet",
        )


__all__ = [
    "LiveEtabsComProviderError",
    "LiveEtabsBeamPayloadProvider",
    "is_live_etabs_com_provider_enabled",
    "live_etabs_com_environment_status",
]
