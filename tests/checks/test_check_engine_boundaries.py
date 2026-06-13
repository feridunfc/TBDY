import ast
from pathlib import Path


FORBIDDEN = [
    "providers",
    "resolver",
    "runner_v2",
    "runtime",
    "archx",
    "table_registry",
    "load_combo_policy",
    "design_combo_matrix",
    "section_state_policy",
    "etabs",
    "beam_checks_patch",
    "full_engineering",
    "registry",
]


def _imports(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_check_engine_does_not_import_forbidden_layers():
    imports = _imports("tbdy_engine/checks/engine.py")
    text = "\n".join(imports)
    for forbidden in FORBIDDEN:
        assert forbidden not in text


def test_check_package_init_does_not_import_forbidden_layers():
    imports = _imports("tbdy_engine/checks/__init__.py")
    text = "\n".join(imports)
    for forbidden in FORBIDDEN:
        assert forbidden not in text


def test_check_engine_source_does_not_read_forbidden_contracts():
    text = Path("tbdy_engine/checks/engine.py").read_text(encoding="utf-8")
    for forbidden in ["table_registry", "load_combo_policy", "design_combo_matrix", "section_state_policy", "GetTableForDisplayArray"]:
        assert forbidden not in text
