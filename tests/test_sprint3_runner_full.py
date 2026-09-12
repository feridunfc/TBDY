from __future__ import annotations

import importlib.util

from tbdy_engine.application.column_execution import execute_column_domain
from tbdy_engine.application.project_execution import execute_project


def test_retired_legacy_runner_remains_absent_after_contract_first_cutover():
    assert importlib.util.find_spec("tbdy_engine.runner") is None
    assert importlib.util.find_spec("tbdy_engine.runner_v2") is None


def test_current_project_execution_is_the_public_product_root():
    assert callable(execute_project)
    assert execute_project.__module__ == "tbdy_engine.application.project_execution"


def test_current_column_execution_is_the_column_application_composer():
    assert callable(execute_column_domain)
    assert execute_column_domain.__module__ == "tbdy_engine.application.column_execution"


def test_legacy_runner_is_not_restored_as_a_compatibility_shim():
    for module_name in (
        "tbdy_engine.runner",
        "tbdy_engine.runner_v2",
        "tbdy_engine.runtime.runner",
    ):
        assert importlib.util.find_spec(module_name) is None
