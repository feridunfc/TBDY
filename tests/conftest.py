from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = Path(__file__).resolve().parent
GATEWAY_SRC = ROOT / "packages" / "etabs_gateway" / "src"

for path in (ROOT, GATEWAY_SRC):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

# Some repository tests reuse sibling test harnesses through ``tests.*``
# imports.  Keep ``tests`` a namespace in the test process instead of making
# the repository test tree a Python package: the latter collides with the
# independent ``packages/etabs_gateway/tests`` tree during broad collection.
repo_tests = types.ModuleType("tests")
repo_tests.__path__ = [str(TEST_ROOT)]
sys.modules["tests"] = repo_tests
