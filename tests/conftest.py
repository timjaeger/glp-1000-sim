import copy
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from glpsim import schemas  # noqa: E402
from glpsim.common import Paths, load_json  # noqa: E402


@pytest.fixture
def repo(tmp_path) -> Paths:
    """A throwaway copy of the spec files (config, schema, prompts, data) with empty world/ and runs/."""
    for d in ("config", "schema", "prompts", "data"):
        shutil.copytree(ROOT / d, tmp_path / d)
    schemas.clear_cache()
    yield Paths(tmp_path)
    schemas.clear_cache()


@pytest.fixture
def baseline() -> dict:
    return load_json(ROOT / "data" / "step0_baseline.json")


@pytest.fixture
def fake_world(baseline):
    """Factory: a schema-valid fictional world for a given year, derived from the baseline."""
    def make(year=2028, **overrides):
        w = copy.deepcopy(baseline)
        w["year"] = year
        w["fictional"] = True
        for k, v in overrides.items():
            w[k] = v
        return w
    return make
