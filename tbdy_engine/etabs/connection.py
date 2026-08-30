"""Legacy ETABS connection compatibility facade.

The gateway is the sole production COM/STA/session/attach owner. This module no
longer attaches directly and never returns SapModel. Its legacy status probe may
use gateway factual context, then closes the gateway session immediately.
Supported acquisition code must use ``tbdy_engine.etabs.safety`` and
``tbdy_engine.etabs.oapi``.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from etabs_gateway import ETABSGatewaySession
from etabs_gateway.errors import ETABSGatewayError

logger = logging.getLogger("etabs-connection")

_connection: Optional["ETABSConnection"] = None
LEGACY_COMPATIBILITY_ONLY = True


class ETABSConnection:
    def __init__(self):
        self._version = "unknown"
        self._model_filename = "unknown"
        self._last_message = "not connected"

    def connect(self) -> Tuple[bool, str]:
        """Compatibility-only running-instance probe through the gateway owner."""
        session = ETABSGatewaySession()
        try:
            context = session.start()
            self._version = context.application.version
            self._model_filename = context.model.model_path or "unknown"
            self._last_message = (
                f"ETABS gateway probe succeeded. Version: {self._version}. "
                f"Model: {self._model_filename}. Raw SapModel export is retired."
            )
            return True, self._last_message
        except ETABSGatewayError as exc:
            self._last_message = f"ETABS gateway probe failed: {exc}"
            return False, self._last_message
        except Exception as exc:
            logger.exception("ETABS gateway compatibility probe failed")
            self._last_message = f"ETABS gateway probe failed: {exc}"
            return False, self._last_message
        finally:
            try:
                session.close()
            except Exception:
                pass

    def get_sap(self):
        raise RuntimeError(
            "Legacy get_sap() raw capability export is retired. Use "
            "tbdy_engine.etabs.safety + tbdy_engine.etabs.oapi."
        )

    def get_version(self) -> str:
        return self._version

    def get_model_filename(self) -> str:
        return self._model_filename

    def disconnect(self) -> None:
        self._version = "unknown"
        self._model_filename = "unknown"
        self._last_message = "disconnected"


def get_connection() -> ETABSConnection:
    global _connection
    if _connection is None:
        _connection = ETABSConnection()
    return _connection


def get_sap():
    return get_connection().get_sap()


def check_etabs_connection() -> Tuple[bool, str]:
    return get_connection().connect()


def get_available_tables(sap=None) -> List[str]:
    del sap
    raise RuntimeError(
        "Legacy get_available_tables() raw OAPI helper is retired. Use the "
        "canonical tbdy_engine.etabs.oapi DatabaseTables boundary."
    )


__all__ = [
    "ETABSConnection",
    "LEGACY_COMPATIBILITY_ONLY",
    "check_etabs_connection",
    "get_available_tables",
    "get_connection",
    "get_sap",
]
