import ast
import importlib
import inspect


def test_etabs_table_probe_import_safe_without_etabs():
    module = importlib.import_module("tools.probe_etabs_table_headers")
    assert hasattr(module, "parse_etabs_display_table_result")


def test_etabs_table_probe_has_no_forbidden_architecture_imports():
    module = importlib.import_module("tools.probe_etabs_table_headers")
    tree = ast.parse(inspect.getsource(module))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for forbidden in ("CheckEngine", "runner_v2", "runtime", "archx"):
        assert not any(forbidden in name for name in imported)
