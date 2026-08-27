from pathlib import Path
import subprocess
import sys


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _fresh_python(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=_repo_root(),
        text=True,
        capture_output=True,
        check=False,
    )


def test_legacy_public_minimal_check_engine_import_remains_valid():
    from tbdy_engine.checks import MinimalCheckEngine as public_engine
    from tbdy_engine.checks.engine import MinimalCheckEngine as direct_engine

    assert public_engine is direct_engine


def test_fresh_interpreter_authority_import_then_legacy_public_engine_has_no_cycle():
    result = _fresh_python(
        "import tbdy_engine.regulatory.fnd_col_2_authority\n"
        "from tbdy_engine.checks import MinimalCheckEngine\n"
        "from tbdy_engine.checks.engine import MinimalCheckEngine as Direct\n"
        "assert MinimalCheckEngine is Direct\n"
    )
    assert result.returncode == 0, result.stderr


def test_fresh_interpreter_legacy_public_engine_then_authority_has_no_cycle():
    result = _fresh_python(
        "from tbdy_engine.checks import MinimalCheckEngine\n"
        "import tbdy_engine.regulatory.fnd_col_2_authority\n"
        "from tbdy_engine.checks.engine import MinimalCheckEngine as Direct\n"
        "assert MinimalCheckEngine is Direct\n"
    )
    assert result.returncode == 0, result.stderr
