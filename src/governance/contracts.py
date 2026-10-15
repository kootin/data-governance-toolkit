from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Column:
    name: str
    type: str
    classification: str = "internal"
    masking: str | None = None
    checks: list = field(default_factory=list)


@dataclass
class Contract:
    dataset: str
    owner: str
    columns: dict[str, Column]
    freshness: dict | None = None
    steward: str | None = None


def load_contract(path: Path) -> Contract:
    raw = yaml.safe_load(path.read_text())
    cols = {n: Column(name=n, **spec) for n, spec in raw["columns"].items()}
    return Contract(raw["dataset"], raw["owner"], cols, raw.get("freshness"), raw.get("steward"))


def load_all(directory: Path) -> dict[str, Contract]:
    return {
        c.dataset: c
        for c in (load_contract(p) for p in sorted(directory.glob("*.yaml")) if p.name != "access_policy.yaml")
    }


DUCKDB_TYPES = {"string": "VARCHAR", "date": "DATE", "timestamp": "TIMESTAMP", "decimal": "DECIMAL(18,2)",
                "integer": "BIGINT", "boolean": "BOOLEAN"}


def load_csv(con, contract: Contract, path: Path) -> None:
    """Load a CSV into DuckDB using the contract's declared types, not inferred ones.

    Inference would read card numbers as integers and drop leading zeros from ids.
    """
    types = {n: DUCKDB_TYPES[c.type] for n, c in contract.columns.items()}
    con.execute(f"CREATE OR REPLACE TABLE {contract.dataset} AS SELECT * FROM read_csv(?, header=true, types=?)",
                [str(path), types])
