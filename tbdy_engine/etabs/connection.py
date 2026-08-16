# app/etabs/connection.py

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

logger = logging.getLogger("etabs-connection")

_connection: Optional["ETABSConnection"] = None
_etabs_object = None
_sap = None
_helper = None


def _parse_available_tables_raw(raw) -> List[str]:
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, (list, tuple)) and item:
                return [str(x) for x in item]

        if len(raw) >= 2 and isinstance(raw[1], (list, tuple)):
            return [str(x) for x in raw[1]]

    return []


class ETABSConnection:
    def __init__(self):
        self._etabs_object = None
        self._sap = None
        self._helper = None

    def connect(self) -> Tuple[bool, str]:
        global _etabs_object, _sap, _helper

        try:
            import comtypes.client

            helper = None
            try:
                helper = comtypes.client.CreateObject("ETABSv1.Helper")
                try:
                    import comtypes.gen.ETABSv1
                    helper = helper.QueryInterface(comtypes.gen.ETABSv1.cHelper)
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"ETABS helper could not be created: {e}")

            etabs_object = None
            errors = []

            if helper is not None:
                try:
                    etabs_object = helper.GetObject("CSI.ETABS.API.ETABSObject")
                except Exception as e:
                    errors.append(f"helper.GetObject CSI: {e}")

            if etabs_object is None:
                try:
                    etabs_object = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
                except Exception as e:
                    errors.append(f"GetActiveObject CSI: {e}")

            if etabs_object is None:
                try:
                    etabs_object = comtypes.client.GetActiveObject("ETABSv1.ETABSObject")
                except Exception as e:
                    errors.append(f"GetActiveObject ETABSv1: {e}")

            if etabs_object is None and helper is not None:
                try:
                    etabs_object = helper.GetObject("ETABSv1.ETABSObject")
                except Exception as e:
                    errors.append(f"helper.GetObject ETABSv1: {e}")

            if etabs_object is None:
                return False, (
                    "No running ETABS instance found. Open ETABS and load/create a model. "
                    "Make sure ETABS and Python/PyCharm run with the same admin privilege. "
                    f"Attempts: {' | '.join(errors)}"
                )

            sap = etabs_object.SapModel
            if sap is None:
                return False, "SapModel is null. Restart ETABS and open/create a model."

            try:
                version_raw = sap.GetVersion()
            except Exception as e:
                return False, f"SapModel.GetVersion failed: {e}"

            try:
                model_raw = sap.GetModelFilename()
            except Exception:
                model_raw = "unknown"

            # Read-only compatibility connection: do not normalize ETABS present
            # units by mutating the live session. Unit provenance is handled by
            # tbdy_engine.etabs.safety / engine.unit_context.
            try:
                tables_raw = sap.DatabaseTables.GetAvailableTables()
            except Exception as e:
                return False, (
                    f"GetAvailableTables failed after read-only attach: {e}. "
                    "ETABS is connected but DatabaseTables API is not usable."
                )

            tables = _parse_available_tables_raw(tables_raw)
            if not tables:
                return False, "Connected to ETABS but available table list is empty."

            _helper = helper
            _etabs_object = etabs_object
            _sap = sap

            self._helper = helper
            self._etabs_object = etabs_object
            self._sap = sap

            version = self._string_from_etabs_return(version_raw)
            model = self._string_from_etabs_return(model_raw)

            return True, (
                f"Connected to ETABS. Version: {version}. "
                f"Model: {model}. Tables: {len(tables)}. Present units preserved."
            )

        except ImportError:
            return False, "comtypes not installed. Run: pip install comtypes"
        except Exception as e:
            logger.exception("ETABS connection failed")
            return False, f"Connection failed: {e}"

    def _string_from_etabs_return(self, ret) -> str:
        if isinstance(ret, str):
            return ret.strip() or "unknown"

        if isinstance(ret, (list, tuple)):
            for item in ret:
                if isinstance(item, str) and item.strip():
                    return item.strip()
            return str(ret)

        return str(ret) if ret is not None else "unknown"

    def get_sap(self):
        global _sap

        if _sap is None:
            ok, msg = self.connect()
            if not ok:
                raise RuntimeError(msg)

        sap = _sap or self._sap
        if sap is None:
            raise RuntimeError("SapModel is not available after connection.")

        # Do not call SetPresentUnits here. Canonical acquisition is read-only
        # with explicit source-unit provenance.
        return sap

    def get_version(self) -> str:
        sap = _sap or self._sap
        if sap is None:
            return "unknown"

        try:
            return self._string_from_etabs_return(sap.GetVersion())
        except Exception as e:
            logger.warning(f"get_version: {e}")
            return "unknown"

    def get_model_filename(self) -> str:
        sap = _sap or self._sap
        if sap is None:
            return "unknown"

        try:
            return self._string_from_etabs_return(sap.GetModelFilename())
        except Exception as e:
            logger.warning(f"get_model_filename: {e}")
            return "unknown"

    def disconnect(self):
        global _etabs_object, _sap, _helper

        _etabs_object = None
        _sap = None
        _helper = None

        self._etabs_object = None
        self._sap = None
        self._helper = None


def get_connection() -> ETABSConnection:
    global _connection
    if _connection is None:
        _connection = ETABSConnection()
    return _connection


def get_sap():
    return get_connection().get_sap()


def check_etabs_connection() -> Tuple[bool, str]:
    return get_connection().connect()


def get_available_tables(sap) -> List[str]:
    try:
        raw = sap.DatabaseTables.GetAvailableTables()
        return _parse_available_tables_raw(raw)
    except Exception as e:
        logger.error(f"get_available_tables: {e}")
        return []


if __name__ == "__main__":
    ok, msg = check_etabs_connection()
    print("OK:", ok)
    print("MSG:", msg)

    if ok:
        sap = get_sap()
        tables = get_available_tables(sap)
        print("TABLE COUNT:", len(tables))
        print("FIRST 20 TABLES:")
        for t in tables[:20]:
            print(" -", t)
