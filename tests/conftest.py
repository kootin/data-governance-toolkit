from datetime import datetime
from pathlib import Path

import duckdb
import pytest

from governance.contracts import load_all, load_csv
from governance.sample import make

ROOT = Path(__file__).parents[1]
AS_OF = datetime(2026, 10, 14, 12)


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    make(d)
    return d


@pytest.fixture(scope="session")
def contracts():
    return load_all(ROOT / "contracts")


@pytest.fixture
def con(data_dir, contracts):
    c = duckdb.connect()
    for name, contract in contracts.items():
        load_csv(c, contract, data_dir / f"{name}.csv")
    yield c
    c.close()
