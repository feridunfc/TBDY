from __future__ import annotations
from typing import Any, Dict, List

REQUIRED_DESIGN_BASIS_KEYS = ["R", "D", "I", "SDS", "SD1", "fck_mpa", "fyk_mpa"]
TRUSTED_SOURCE_HINTS = ("etabs", "user", "project", "input", "excel", "model", "api")
UNTRUSTED_SOURCE_HINTS = ("template", "default", "fallback", "assumption", "unknown")


def _source_for(basis: Dict[str, Any], key: str) -> str:
    sources = basis.get("sources") or {}
    return str(sources.get(key) or sources.get(key.upper()) or "").strip()


def _is_missing(value: Any) -> bool:
    return value in (None, "", 0, 0.0)


def classify_design_basis_source(source: str) -> str:
    s = str(source or "").lower()
    if not s:
        return "UNKNOWN"
    if any(x in s for x in TRUSTED_SOURCE_HINTS) and not any(x in s for x in ("template", "default")):
        return "VERIFIED"
    if any(x in s for x in UNTRUSTED_SOURCE_HINTS):
        return "ASSUMED"
    return "UNKNOWN"


def audit_design_basis(ctx: Any) -> Dict[str, Any]:
    basis = dict(getattr(ctx, "design_basis", {}) or {})
    spectrum = dict(getattr(ctx, "spectrum", {}) or {})
    issues: List[Dict[str, Any]] = []
    parameters: Dict[str, Dict[str, Any]] = {}

    for key in REQUIRED_DESIGN_BASIS_KEYS:
        value = basis.get(key, spectrum.get(key))
        source = _source_for(basis, key) or _source_for(spectrum, key)
        source_class = classify_design_basis_source(source)
        if _is_missing(value):
            severity = "CRITICAL"
            code = "DESIGN_BASIS_MISSING"
            message = f"{key} bulunamadı; bu parametreye bağlı design-level kontroller güvenilir değildir."
        elif source_class != "VERIFIED":
            severity = "WARNING"
            code = "DESIGN_BASIS_UNVERIFIED_SOURCE"
            message = f"{key} kaynağı doğrulanmış ETABS/user verisi değil ({source or 'UNKNOWN'}); sonuç varsayım içerir."
        else:
            severity = "OK"
            code = "DESIGN_BASIS_VERIFIED"
            message = f"{key} doğrulanmış kaynaktan geliyor."
        parameters[key] = {"value": value, "source": source or "UNKNOWN", "source_class": source_class, "severity": severity, "code": code, "message": message}
        if severity != "OK":
            issues.append({"severity": severity, "code": code, "parameter": key, "message": message})

    overall = "CRITICAL" if any(i["severity"] == "CRITICAL" for i in issues) else "WARNING" if issues else "OK"
    verified = [k for k, v in parameters.items() if v["source_class"] == "VERIFIED" and v["severity"] == "OK"]
    assumed = [k for k, v in parameters.items() if v["source_class"] != "VERIFIED" and v["severity"] != "CRITICAL"]
    missing = [k for k, v in parameters.items() if v["severity"] == "CRITICAL"]
    return {"overall_severity": overall, "is_design_level_basis_verified": overall == "OK", "parameters": parameters, "verified_parameters": verified, "assumed_parameters": assumed, "missing_parameters": missing, "issues": issues, "policy": "DESIGN_LEVEL checks require R/D/I/SDS/SD1/fck/fyk from ETABS/user/project input. Template/default values are allowed only as ASSUMED basis and must downgrade confidence or raise warnings."}


def design_basis_verified(ctx: Any) -> bool:
    return bool(audit_design_basis(ctx).get("is_design_level_basis_verified"))
