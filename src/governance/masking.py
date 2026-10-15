"""Generate role-specific secure views that mask columns the role may not see in clear."""
from __future__ import annotations

import duckdb
import yaml

from governance.contracts import Contract

MASKS = {
    "hash": "sha256(CAST({c} AS VARCHAR))",
    "redact": "'***REDACTED***'",
    "partial": "left(CAST({c} AS VARCHAR), 1) || repeat('*', greatest(length(CAST({c} AS VARCHAR)) - 1, 0))",
    "last4": "repeat('*', greatest(length(CAST({c} AS VARCHAR)) - 4, 0)) || right(CAST({c} AS VARCHAR), 4)",
    "year_only": "CAST(year(CAST({c} AS DATE)) AS VARCHAR)",
}


def view_sql(contract: Contract, role: str, policy: dict) -> str:
    allowed = set(policy["roles"][role]["unmasked"])
    exprs = []
    for col in contract.columns.values():
        c = f'"{col.name}"'
        if col.classification in allowed:
            exprs.append(c)
        else:
            exprs.append(f"{MASKS[col.masking or 'redact'].format(c=c)} AS {c}")
    return f"CREATE OR REPLACE VIEW secure.{contract.dataset}__{role} AS SELECT {', '.join(exprs)} FROM main.{contract.dataset}"


def create_secure_views(con: duckdb.DuckDBPyConnection, contracts: dict[str, Contract], policy_path) -> list[str]:
    policy = yaml.safe_load(open(policy_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS secure")
    created = []
    for contract in contracts.values():
        for role in policy["roles"]:
            con.execute(view_sql(contract, role, policy))
            created.append(f"secure.{contract.dataset}__{role}")
    return created
