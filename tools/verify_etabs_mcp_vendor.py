#!/usr/bin/env python3
"""Verify the immutable ETABS-MCP vendor snapshot and Phase-0 boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

INVENTORY_RELATIVE_PATH = Path("provenance/ETABS_MCP_UPSTREAM_SHA256.json")
MANIFEST_RELATIVE_PATH = Path("provenance/SOURCE_MANIFEST.json")
SENTINEL_RELATIVE_PATH = Path("vendor/.etabs-mcp-managed.json")
VENDOR_RELATIVE_PATH = Path("vendor/etabs-mcp")
GATEWAY_RELATIVE_PATH = Path("packages/etabs_gateway")

IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "node_modules",
}

CODE_ROOTS = (
    Path("tbdy_engine"),
    Path("packages"),
    Path("apps"),
    Path("contracts"),
)

ROOT_CONFIG_FILES = (
    Path("pyproject.toml"),
    Path("setup.py"),
    Path("setup.cfg"),
    Path("tox.ini"),
)

CODE_EXTENSIONS = {".py", ".toml", ".ini", ".cfg", ".yaml", ".yml"}

IMPORT_PATTERNS = (
    re.compile(r"(?m)^\s*from\s+etabs_mcp(?:\.|\s+import\b)"),
    re.compile(r"(?m)^\s*import\s+[^\n#]*\betabs_mcp\b"),
    re.compile(r"vendor[\\/]etabs[-_]mcp", re.IGNORECASE),
)


@dataclass(frozen=True)
class FileRecord:
    path: str
    size_bytes: int
    sha256: str


@dataclass
class VerificationResult:
    result: str
    generated_at_utc: str
    repository_root: str
    checks: dict[str, Any]
    errors: list[str]
    warnings: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that vendor/etabs-mcp still matches the recorded upstream "
            "snapshot and remains outside the active runtime."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="TBDY repository root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--write-report",
        type=Path,
        default=None,
        help=(
            "Optional report path. Relative paths are resolved from --repo-root. "
            "Normal verification does not modify the repository."
        ),
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Required JSON file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_code_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRECTORY_NAMES for part in path.parts):
            continue
        yield path


def iter_vendor_files_exact(vendor_root: Path) -> Iterable[Path]:
    """Yield every vendor file so generated cache files become invariant violations."""
    for path in sorted(vendor_root.rglob("*")):
        if not path.is_file():
            continue
        if ".git" in path.relative_to(vendor_root).parts:
            continue
        yield path


def inventory_vendor(vendor_root: Path) -> list[FileRecord]:
    records: list[FileRecord] = []
    for path in iter_vendor_files_exact(vendor_root):
        records.append(
            FileRecord(
                path=path.relative_to(vendor_root).as_posix(),
                size_bytes=path.stat().st_size,
                sha256=sha256_file(path),
            )
        )
    return records


def parse_expected_inventory(document: dict[str, Any]) -> list[FileRecord]:
    raw_files = document.get("files")
    if not isinstance(raw_files, list):
        raise ValueError("Inventory document must contain a 'files' array.")

    records: list[FileRecord] = []
    for index, item in enumerate(raw_files):
        if not isinstance(item, dict):
            raise ValueError(f"Inventory item {index} is not an object.")
        try:
            records.append(
                FileRecord(
                    path=str(item["path"]),
                    size_bytes=int(item["size_bytes"]),
                    sha256=str(item["sha256"]).lower(),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid inventory item at index {index}: {item}") from exc

    records.sort(key=lambda record: record.path)
    return records


def compare_inventories(
    expected: list[FileRecord], actual: list[FileRecord]
) -> tuple[list[str], list[str], list[str]]:
    expected_by_path = {record.path: record for record in expected}
    actual_by_path = {record.path: record for record in actual}

    missing = sorted(set(expected_by_path) - set(actual_by_path))
    extra = sorted(set(actual_by_path) - set(expected_by_path))

    changed: list[str] = []
    for path in sorted(set(expected_by_path) & set(actual_by_path)):
        expected_record = expected_by_path[path]
        actual_record = actual_by_path[path]
        if (
            expected_record.size_bytes != actual_record.size_bytes
            or expected_record.sha256 != actual_record.sha256
        ):
            changed.append(path)

    return missing, extra, changed


def find_nested_git_entries(vendor_root: Path) -> list[str]:
    findings: list[str] = []
    for path in vendor_root.rglob(".git"):
        findings.append(path.relative_to(vendor_root).as_posix())
    return sorted(findings)


def candidate_code_files(repo_root: Path) -> Iterable[Path]:
    yielded: set[Path] = set()

    for relative_root in CODE_ROOTS:
        root = repo_root / relative_root
        if not root.exists():
            continue
        for path in iter_code_files(root):
            if VENDOR_RELATIVE_PATH in path.relative_to(repo_root).parents:
                continue
            if path.suffix.lower() not in CODE_EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved not in yielded:
                yielded.add(resolved)
                yield path

    for relative_path in ROOT_CONFIG_FILES:
        path = repo_root / relative_path
        if path.is_file():
            resolved = path.resolve()
            if resolved not in yielded:
                yielded.add(resolved)
                yield path


def find_forbidden_runtime_references(repo_root: Path) -> list[str]:
    findings: list[str] = []
    for path in candidate_code_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(
                f"{path.relative_to(repo_root).as_posix()}: non-UTF-8 active code/config file"
            )
            continue

        for pattern in IMPORT_PATTERNS:
            match = pattern.search(text)
            if match:
                line_number = text.count("\n", 0, match.start()) + 1
                findings.append(
                    f"{path.relative_to(repo_root).as_posix()}:{line_number}: "
                    f"forbidden reference '{match.group(0).strip()}'"
                )
                break

    return sorted(findings)


def resolve_report_path(repo_root: Path, requested: Path | None) -> Path | None:
    if requested is None:
        return None
    if requested.is_absolute():
        return requested
    return repo_root / requested


def write_report(path: Path, result: VerificationResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def verify(repo_root: Path) -> VerificationResult:
    repo_root = repo_root.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}

    if not (repo_root / ".git").exists():
        errors.append(f"Not a Git repository root: {repo_root}")

    inventory_path = repo_root / INVENTORY_RELATIVE_PATH
    manifest_path = repo_root / MANIFEST_RELATIVE_PATH
    sentinel_path = repo_root / SENTINEL_RELATIVE_PATH
    vendor_root = repo_root / VENDOR_RELATIVE_PATH
    gateway_root = repo_root / GATEWAY_RELATIVE_PATH

    try:
        inventory_document = load_json(inventory_path)
        expected_inventory = parse_expected_inventory(inventory_document)
    except ValueError as exc:
        errors.append(str(exc))
        expected_inventory = []
        inventory_document = {}

    try:
        manifest = load_json(manifest_path)
    except ValueError as exc:
        errors.append(str(exc))
        manifest = {}

    try:
        sentinel = load_json(sentinel_path)
    except ValueError as exc:
        errors.append(str(exc))
        sentinel = {}

    checks["vendor_directory_exists"] = vendor_root.is_dir()
    if not vendor_root.is_dir():
        errors.append(f"Vendor directory is missing: {vendor_root}")
        actual_inventory: list[FileRecord] = []
    else:
        actual_inventory = inventory_vendor(vendor_root)

    missing, extra, changed = compare_inventories(expected_inventory, actual_inventory)
    checks["expected_file_count"] = len(expected_inventory)
    checks["actual_file_count"] = len(actual_inventory)
    checks["missing_files"] = missing
    checks["extra_files"] = extra
    checks["changed_files"] = changed
    checks["hash_inventory_matches"] = not (missing or extra or changed)

    if missing:
        errors.append(f"Vendor snapshot has {len(missing)} missing file(s).")
    if extra:
        errors.append(f"Vendor snapshot has {len(extra)} unrecorded extra file(s).")
    if changed:
        errors.append(f"Vendor snapshot has {len(changed)} changed file(s).")

    nested_git_entries = find_nested_git_entries(vendor_root) if vendor_root.exists() else []
    checks["nested_git_entries"] = nested_git_entries
    if nested_git_entries:
        errors.append("Nested .git content exists inside vendor/etabs-mcp.")

    checks["sentinel_managed_by"] = sentinel.get("managed_by")
    checks["sentinel_target"] = sentinel.get("managed_target")
    if sentinel.get("managed_by") != "tbdy-next-phase0-genesis-v3":
        errors.append("Vendor management sentinel has an unexpected managed_by value.")
    if sentinel.get("managed_target") != "vendor/etabs-mcp":
        errors.append("Vendor management sentinel has an unexpected managed_target value.")

    inventory_sha = inventory_document.get("upstream_commit_sha")
    sentinel_sha = sentinel.get("upstream_commit_sha")
    manifest_sha = (
        manifest.get("etabs_mcp_upstream", {}).get("resolved_commit_sha")
        if isinstance(manifest.get("etabs_mcp_upstream"), dict)
        else None
    )
    checks["inventory_upstream_sha"] = inventory_sha
    checks["sentinel_upstream_sha"] = sentinel_sha
    checks["manifest_upstream_sha"] = manifest_sha
    checks["upstream_sha_consistent"] = bool(inventory_sha) and (
        inventory_sha == sentinel_sha == manifest_sha
    )
    if not checks["upstream_sha_consistent"]:
        errors.append("Upstream commit SHA is inconsistent across provenance files.")

    integration_status = manifest.get("integration_status")
    checks["integration_status"] = integration_status
    if integration_status == "NONE":
        gateway_python_files = (
            sorted(path.relative_to(repo_root).as_posix() for path in gateway_root.rglob("*.py"))
            if gateway_root.exists()
            else []
        )
        checks["gateway_python_files"] = gateway_python_files
        if gateway_python_files:
            errors.append(
                "Phase-0 integration_status is NONE but Python implementation exists "
                "under packages/etabs_gateway."
            )

    forbidden_references = find_forbidden_runtime_references(repo_root)
    checks["forbidden_runtime_references"] = forbidden_references
    if forbidden_references:
        errors.append(
            "Active code or package configuration references the vendored ETABS-MCP runtime."
        )

    expected_count_field = inventory_document.get("file_count")
    if expected_count_field is not None and int(expected_count_field) != len(expected_inventory):
        errors.append("Inventory file_count does not match the number of file records.")

    snapshot_policy = inventory_document.get("snapshot_policy")
    checks["snapshot_policy"] = snapshot_policy
    if snapshot_policy != "TRACKED_SOURCE_WITH_EXPLICIT_GENERATED_ARTIFACT_EXCLUSIONS":
        errors.append("Inventory snapshot_policy is missing or unexpected.")

    excluded_files = inventory_document.get("excluded_files", [])
    excluded_count = inventory_document.get("excluded_file_count", 0)
    checks["excluded_file_count"] = excluded_count
    if not isinstance(excluded_files, list) or int(excluded_count) != len(excluded_files):
        errors.append("Inventory excluded_file_count does not match excluded_files.")

    result_name = "PASS" if not errors else "FAIL"
    return VerificationResult(
        result=result_name,
        generated_at_utc=utc_now(),
        repository_root=".",
        checks=checks,
        errors=errors,
        warnings=warnings,
    )


def main() -> int:
    args = parse_args()
    result = verify(args.repo_root)

    report_path = resolve_report_path(args.repo_root.resolve(), args.write_report)
    if report_path is not None:
        write_report(report_path, result)

    if result.result == "PASS":
        print("ETABS-MCP vendor verification: PASS")
        print(f"Verified files: {result.checks.get('actual_file_count', 0)}")
        return 0

    print("ETABS-MCP vendor verification: FAIL", file=sys.stderr)
    for error in result.errors:
        print(f"- {error}", file=sys.stderr)

    for key in ("missing_files", "extra_files", "changed_files", "forbidden_runtime_references"):
        values = result.checks.get(key) or []
        for value in values:
            print(f"  {key}: {value}", file=sys.stderr)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
