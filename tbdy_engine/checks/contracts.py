# app/checks/contracts.py
"""
Check result contract validation and status semantics.

Faz 0 değişiklikleri:
  - EvaluationLevel enum: ETABS_DESIGN_RESULT, DESIGN_LEVEL, APPROXIMATE,
    SCREENING, METADATA_ONLY, NO_DATA  (DESIGN_LEVEL != ETABS_DESIGN_RESULT)
  - ExecutionStatus enum: EVALUATED, SKIPPED, NOT_EVALUATED
  - NOT_EVALUATED ALLOWED_STATUSES'a eklendi (check function dönemez ama
    runner normalize eder; validation tanımalıdır)
  - validate_check_results() semantik çelişkileri yakalar:
      * NOT_EVALUATED + execution_status=EVALUATED → çelişki
      * ETABS_DESIGN_RESULT + missing design table → çelişki
      * METADATA_ONLY check'in OK/FAIL/WARNING taşıması → çelişki
  - Backward compat: CheckLevel ve DependencyStatus importları aynen durur
    (contracts'tan import eden modüller kırılmaz).
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Iterable, List

from tbdy_engine.engine.validation import ValidationIssue, ValidationReport

# ---------------------------------------------------------------------------
# Temel durum kümeleri
# ---------------------------------------------------------------------------

ALLOWED_STATUSES = {
    "OK", "WARNING", "FAIL",
    "NO_DATA", "ERROR", "UNKNOWN_CHECK", "PARTIAL",
    "NOT_EVALUATED",          # Faz 0: bağımsız dep modeli olmayan check
}
BLOCKING_STATUSES = {"ERROR", "UNKNOWN_CHECK"}
INCOMPLETE_STATUSES = {"NO_DATA", "NOT_EVALUATED"}

# OK/FAIL/WARNING sayılacak gerçek mühendislik statüleri
REAL_ENGINEERING_STATUSES = {"OK", "FAIL", "WARNING", "PARTIAL"}


# ---------------------------------------------------------------------------
# EvaluationLevel  — ETABS_DESIGN_RESULT artık DESIGN_LEVEL'den ayrı
# ---------------------------------------------------------------------------

class EvaluationLevel(str, Enum):
    """
    Check'in değerlendirme güven seviyesi.

    ETABS_DESIGN_RESULT : ETABS design result tablosundan okunan sonuç.
    DESIGN_LEVEL        : Manuel TBDY formülü + doğrulanmış malzeme/kesit verisi.
    APPROXIMATE         : Eksik tasarım tablosu, fallback hesap.
    SCREENING           : Yalnızca geometri/kuvvet; donatı/malzeme yok.
    METADATA_ONLY       : Bağımsız dep modeli tanımlı değil; check içi kontrol.
    NO_DATA             : Minimum veri bile eksik; check çalıştırılamadı.
    """
    ETABS_DESIGN_RESULT = "ETABS_DESIGN_RESULT"
    DESIGN_LEVEL        = "DESIGN_LEVEL"
    APPROXIMATE         = "APPROXIMATE"
    SCREENING           = "SCREENING"
    METADATA_ONLY       = "METADATA_ONLY"
    NO_DATA             = "NO_DATA"


ALLOWED_EVALUATION_LEVELS = {e.value for e in EvaluationLevel}


# ---------------------------------------------------------------------------
# ExecutionStatus  — çalışıp çalışmadığı
# ---------------------------------------------------------------------------

class ExecutionStatus(str, Enum):
    """
    Check'in runner tarafından nasıl ele alındığı.

    EVALUATED     : Fonksiyon çalıştı (bağımsız dep modeli doğruladı).
    SKIPPED       : Veri eksikliği nedeniyle atlandı (SKIP_NO_DATA).
    NOT_EVALUATED : Bağımsız dep modeli yok; check içi kontrol kullanıldı.
    """
    EVALUATED     = "EVALUATED"
    SKIPPED       = "SKIPPED"
    NOT_EVALUATED = "NOT_EVALUATED"


ALLOWED_EXECUTION_STATUSES = {e.value for e in ExecutionStatus}


# ---------------------------------------------------------------------------
# Backward-compat: eski CheckLevel importları kırılmasın
# ---------------------------------------------------------------------------

class CheckLevel(str, Enum):
    DESIGN_LEVEL = "DESIGN_LEVEL"
    ETABS_DESIGN_RESULT = "ETABS_DESIGN_RESULT"
    APPROXIMATE  = "APPROXIMATE"
    SCREENING    = "SCREENING"
    NO_DATA      = "NO_DATA"


class DependencyStatus(str, Enum):
    RUN_DESIGN_LEVEL      = "RUN_DESIGN_LEVEL"
    RUN_APPROXIMATE       = "RUN_APPROXIMATE"
    RUN_SCREENING         = "RUN_SCREENING"
    SKIP_NO_DATA          = "SKIP_NO_DATA"
    FAIL_MISSING_CRITICAL = "FAIL_MISSING_CRITICAL"
    NOT_EVALUATED         = "NOT_EVALUATED"


# ---------------------------------------------------------------------------
# Status öncelik tablosu
# NOT_EVALUATED: no_data ile aynı ağırlıkta; OK/FAIL/WARNING sayılmaz
# ---------------------------------------------------------------------------

STATUS_PRIORITY = {
    "ERROR":         0,
    "UNKNOWN_CHECK": 0,
    "FAIL":          1,
    "NO_DATA":       2,
    "PARTIAL":       2,
    "NOT_EVALUATED": 2,   # Faz 0: no_data ile aynı ağırlık
    "WARNING":       3,
    "OK":            4,
}


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def summarize_statuses(checks: Dict[str, Any]) -> Dict[str, int]:
    statuses = [
        str(c.get("status", "ERROR")).upper()
        if isinstance(c, dict) else "ERROR"
        for c in checks.values()
    ]
    return {
        "total":         len(checks),
        "ok":            sum(1 for s in statuses if s == "OK"),
        "fail":          sum(1 for s in statuses if s == "FAIL"),
        "warning":       sum(1 for s in statuses if s == "WARNING"),
        "no_data":       sum(1 for s in statuses if s == "NO_DATA"),
        "error":         sum(1 for s in statuses if s == "ERROR"),
        "unknown_check": sum(1 for s in statuses if s == "UNKNOWN_CHECK"),
        "partial":       sum(1 for s in statuses if s == "PARTIAL"),
        "not_evaluated": sum(1 for s in statuses if s == "NOT_EVALUATED"),
    }


def overall_status_from_summary(summary: Dict[str, int]) -> str:
    """
    NOT_EVALUATED check'ler PARTIAL gibi davranır: overall'ı OK'tan düşürür
    ama kendi başına FAIL veya ERROR üretmez.
    """
    if summary.get("error", 0) or summary.get("unknown_check", 0):
        return "ERROR"
    if summary.get("fail", 0):
        return "FAIL"
    if summary.get("no_data", 0) or summary.get("partial", 0) or summary.get("not_evaluated", 0):
        return "PARTIAL"
    if summary.get("warning", 0):
        return "WARNING"
    return "OK"


# ---------------------------------------------------------------------------
# Payload field validation helpers
# ---------------------------------------------------------------------------

def _check_semantic_contradictions(
    name: str,
    check: Dict[str, Any],
    issues: List[ValidationIssue],
) -> None:
    """
    Semantik çelişki tespiti.

    1. NOT_EVALUATED + execution_status=EVALUATED → çelişki.
    2. METADATA_ONLY evaluation_level + real engineering status → çelişki.
    3. ETABS_DESIGN_RESULT evaluation_level ama hiç design table verisi yok
       (missing_data içinde design tablo adı varsa) → uyarı.
    4. execution_status=NOT_EVALUATED + status=OK/FAIL/WARNING → kritik.
    """
    status         = str(check.get("status", "")).upper()
    exec_status    = str(check.get("execution_status", "")).upper()
    eval_level     = str(check.get("evaluation_level", "")).upper()
    missing_data   = check.get("missing_data") or []
    selected_meth  = str(check.get("selected_method", "")).upper()

    # Kural 1: NOT_EVALUATED statüsü + EVALUATED execution
    if status == "NOT_EVALUATED" and exec_status == ExecutionStatus.EVALUATED.value:
        issues.append(ValidationIssue(
            "WARNING",
            "SEMANTIC_NOT_EVALUATED_BUT_EXECUTED",
            f"Check '{name}' status=NOT_EVALUATED ama execution_status=EVALUATED. "
            f"Bu, runner normalizasyonunun gözden kaçırdığı bir çelişkidir.",
            f"checks.{name}",
        ))

    # Kural 2: METADATA_ONLY + gerçek mühendislik statüsü
    if eval_level == EvaluationLevel.METADATA_ONLY.value and status in REAL_ENGINEERING_STATUSES:
        issues.append(ValidationIssue(
            "ERROR",
            "SEMANTIC_METADATA_ONLY_REAL_STATUS",
            f"Check '{name}' evaluation_level=METADATA_ONLY ama status={status}. "
            f"Bağımsız dep modeli olmayan check gerçek mühendislik statüsü taşıyamaz. "
            f"Runner normalizasyonu başarısız olmuştur.",
            f"checks.{name}.status",
        ))

    # Kural 3: execution_status=NOT_EVALUATED + OK/FAIL/WARNING
    if exec_status == ExecutionStatus.NOT_EVALUATED.value and status in REAL_ENGINEERING_STATUSES:
        issues.append(ValidationIssue(
            "ERROR",
            "SEMANTIC_NOT_EVALUATED_REAL_STATUS",
            f"Check '{name}' execution_status=NOT_EVALUATED ama status={status}. "
            f"NOT_EVALUATED check mühendislik sonucu veremez.",
            f"checks.{name}.status",
        ))

    # Kural 4: ETABS_DESIGN_RESULT + design tablosu missing_data listesinde
    if eval_level == EvaluationLevel.ETABS_DESIGN_RESULT.value and missing_data:
        # design tablo adları: column_design_summary, beam_design_summary, scwb_design vb.
        design_table_patterns = ("design_summary", "scwb_design", "joint_shear_design")
        suspicious = [
            t for t in missing_data
            if any(p in str(t).lower() for p in design_table_patterns)
        ]
        if suspicious:
            issues.append(ValidationIssue(
                "WARNING",
                "SEMANTIC_ETABS_DESIGN_RESULT_BUT_TABLE_MISSING",
                f"Check '{name}' evaluation_level=ETABS_DESIGN_RESULT ama "
                f"missing_data içinde design tablosu var: {suspicious}. "
                f"selected_method={selected_meth!r} ile doğrulayın.",
                f"checks.{name}.evaluation_level",
            ))


# ---------------------------------------------------------------------------
# Ana validation
# ---------------------------------------------------------------------------

def validate_check_results(
    result: Dict[str, Any],
    selected: Iterable[str] | None = None,
) -> ValidationReport:
    issues: List[ValidationIssue] = []

    if not isinstance(result, dict):
        return ValidationReport(
            "check_results", False,
            [ValidationIssue("ERROR", "CHECK_RESULT_NOT_DICT", "Check result must be a dict.")],
        )

    checks = result.get("checks")
    if not isinstance(checks, dict):
        return ValidationReport(
            "check_results", False,
            [ValidationIssue("ERROR", "CHECKS_NOT_DICT", "result['checks'] must be a dict.", "checks")],
        )

    # Seçili check'ler çalışmış mı?
    selected_set = set(selected or [])
    if selected_set:
        missing = selected_set - set(checks.keys())
        for name in sorted(missing):
            issues.append(ValidationIssue(
                "ERROR", "SELECTED_CHECK_MISSING",
                f"Selected check did not run: {name}.",
                f"checks.{name}",
            ))

    for name, check in checks.items():
        if not isinstance(check, dict):
            issues.append(ValidationIssue(
                "ERROR", "CHECK_NOT_DICT",
                f"Check '{name}' did not return a dict.",
                f"checks.{name}",
            ))
            continue

        # --- status ---
        status = str(check.get("status", "")).upper()
        if not status:
            issues.append(ValidationIssue(
                "ERROR", "CHECK_STATUS_MISSING",
                f"Check '{name}' has no status.",
                f"checks.{name}.status",
            ))
        elif status not in ALLOWED_STATUSES:
            issues.append(ValidationIssue(
                "ERROR", "CHECK_STATUS_UNKNOWN",
                f"Check '{name}' returned unknown status '{status}'.",
                f"checks.{name}.status",
            ))

        # --- check name consistency ---
        if check.get("check") and check.get("check") != name:
            issues.append(ValidationIssue(
                "WARNING", "CHECK_NAME_MISMATCH",
                f"Check key '{name}' differs from result check='{check.get('check')}'.",
                f"checks.{name}.check",
            ))

        # --- ERROR must have message ---
        if status == "ERROR" and not check.get("error"):
            issues.append(ValidationIssue(
                "WARNING", "CHECK_ERROR_WITHOUT_MESSAGE",
                f"Check '{name}' is ERROR but has no error message.",
                f"checks.{name}.error",
            ))

        # --- NO_DATA must explain ---
        if status == "NO_DATA" and not (
            check.get("message") or check.get("reason") or check.get("missing_tables")
        ):
            issues.append(ValidationIssue(
                "WARNING", "NO_DATA_WITHOUT_REASON",
                f"Check '{name}' is NO_DATA but does not explain missing data.",
                f"checks.{name}",
            ))

        # --- run_level ---
        run_level = str(check.get("run_level", "")).upper()
        if not run_level:
            issues.append(ValidationIssue(
                "WARNING", "CHECK_LEVEL_MISSING",
                f"Check '{name}' has no run_level.",
                f"checks.{name}.run_level",
            ))
        elif run_level not in {x.value for x in CheckLevel}:
            issues.append(ValidationIssue(
                "WARNING", "CHECK_LEVEL_UNKNOWN",
                f"Check '{name}' has unknown run_level '{run_level}'.",
                f"checks.{name}.run_level",
            ))

        # --- evaluation_level (Faz 0 yeni alan) ---
        eval_level = str(check.get("evaluation_level", "")).upper()
        if eval_level and eval_level not in ALLOWED_EVALUATION_LEVELS:
            issues.append(ValidationIssue(
                "WARNING", "EVALUATION_LEVEL_UNKNOWN",
                f"Check '{name}' has unknown evaluation_level '{eval_level}'.",
                f"checks.{name}.evaluation_level",
            ))

        # --- execution_status (Faz 0 yeni alan) ---
        exec_status = str(check.get("execution_status", "")).upper()
        if exec_status and exec_status not in ALLOWED_EXECUTION_STATUSES:
            issues.append(ValidationIssue(
                "WARNING", "EXECUTION_STATUS_UNKNOWN",
                f"Check '{name}' has unknown execution_status '{exec_status}'.",
                f"checks.{name}.execution_status",
            ))

        # --- dependency_status ---
        if not check.get("dependency_status"):
            issues.append(ValidationIssue(
                "WARNING", "DEPENDENCY_STATUS_MISSING",
                f"Check '{name}' has no dependency_status.",
                f"checks.{name}.dependency_status",
            ))

        # --- missing_data_impact ---
        if run_level in {"SCREENING", "APPROXIMATE", "NO_DATA"} and not check.get("missing_data_impact"):
            issues.append(ValidationIssue(
                "WARNING", "MISSING_IMPACT_TEXT",
                f"Check '{name}' is {run_level} but has no missing_data_impact.",
                f"checks.{name}.missing_data_impact",
            ))

        # --- requires_engineer_review ---
        if "requires_engineer_review" not in check:
            issues.append(ValidationIssue(
                "WARNING", "REQUIRES_REVIEW_MISSING",
                f"Check '{name}' has no requires_engineer_review field.",
                f"checks.{name}.requires_engineer_review",
            ))

        # --- Semantik çelişki kontrolleri ---
        _check_semantic_contradictions(name, check, issues)

    # --- Summary tutarlılığı ---
    computed = summarize_statuses(checks)
    reported_summary = result.get("summary") or {}
    for key, val in computed.items():
        if key in reported_summary and int(reported_summary.get(key) or 0) != val:
            issues.append(ValidationIssue(
                "WARNING", "SUMMARY_COUNT_MISMATCH",
                f"Summary '{key}' is {reported_summary.get(key)}, computed {val}.",
                f"summary.{key}",
            ))

    # --- overall_status tutarlılığı ---
    expected_overall = overall_status_from_summary(computed)
    if str(result.get("overall_status", expected_overall)).upper() != expected_overall:
        issues.append(ValidationIssue(
            "WARNING", "OVERALL_STATUS_MISMATCH",
            f"overall_status is {result.get('overall_status')}, expected {expected_overall}.",
            "overall_status",
        ))

    return ValidationReport(
        name="check_results",
        valid=not any(i.severity == "ERROR" for i in issues),
        issues=issues,
    )
