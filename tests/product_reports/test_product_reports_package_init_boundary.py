from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_INIT = ROOT / "tbdy_engine/product_reports/__init__.py"
FORBIDDEN_EAGER_MODULES = (
    "tools.render_product_report",
    "tbdy_engine.product_reports.c13_1_report",
    "tbdy_engine.product_reports.check_results",
    "tbdy_engine.product_reports.combined_verdict",
)
LEGACY_ROOT_EXPORTS = (
    "build_c13_1_product_report",
    "write_c13_1_product_report",
)


def _fresh_import(module_name: str) -> dict[str, bool]:
    code = "\n".join(
        (
            "import json, sys",
            f"import {module_name}",
            f"names = {FORBIDDEN_EAGER_MODULES!r}",
            "print(json.dumps({name: name in sys.modules for name in names}, sort_keys=True))",
        )
    )
    env = os.environ.copy()
    pythonpath = [
        str(ROOT),
        str(ROOT / "packages/etabs_gateway/src"),
    ]
    existing = env.get("PYTHONPATH")
    if existing:
        pythonpath.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    import json

    return json.loads(completed.stdout.strip())


def _fresh_tools_modules(module_name: str) -> list[str]:
    code = "\n".join(
        (
            "import json, sys",
            f"import {module_name}",
            "print(json.dumps(sorted(name for name in sys.modules if name == 'tools' or name.startswith('tools.'))))",
        )
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "packages/etabs_gateway/src")))
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    import json

    return json.loads(completed.stdout.strip())


def test_supported_unified_report_import_is_dependency_light_in_fresh_process():
    loaded = _fresh_import("tbdy_engine.product_reports.unified_building_report")
    assert loaded == {name: False for name in FORBIDDEN_EAGER_MODULES}


def test_supported_application_import_is_dependency_light_in_fresh_process():
    loaded = _fresh_import("tbdy_engine.application.project_execution")
    assert loaded == {name: False for name in FORBIDDEN_EAGER_MODULES}


def test_product_reports_package_root_has_no_legacy_c13_reexports():
    code = "\n".join(
        (
            "import json",
            "import tbdy_engine.product_reports as package",
            f"names = {LEGACY_ROOT_EXPORTS!r}",
            "print(json.dumps({name: hasattr(package, name) for name in names}, sort_keys=True))",
        )
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "packages/etabs_gateway/src")))
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    import json

    assert json.loads(completed.stdout.strip()) == {name: False for name in LEGACY_ROOT_EXPORTS}


def test_legacy_c13_module_remains_directly_importable_without_root_reexport():
    code = "\n".join(
        (
            "from tbdy_engine.product_reports.c13_1_report import build_c13_1_product_report, write_c13_1_product_report",
            "print(callable(build_c13_1_product_report) and callable(write_c13_1_product_report))",
        )
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "packages/etabs_gateway/src")))
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert completed.stdout.strip() == "True"


def test_package_init_contains_no_legacy_c13_import_edge():
    tree = ast.parse(PACKAGE_INIT.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    assert not any("c13_1_report" in name for name in imports)
    assert not any(name.startswith("tools") for name in imports)


def test_supported_imports_load_no_tools_modules_in_fresh_process():
    assert _fresh_tools_modules("tbdy_engine.product_reports.unified_building_report") == []
    assert _fresh_tools_modules("tbdy_engine.application.project_execution") == []
