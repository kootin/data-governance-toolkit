"""Run the checks declared in a data contract against a DuckDB table."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import duckdb

from governance.contracts import Contract


@dataclass
class CheckResult:
    dataset: str
    column: str
    check: str
    failed_rows: int
    total_rows: int

    @property
    def passed(self) -> bool:
        return self.failed_rows == 0


def _luhn_sql(col: str) -> str:
    # Luhn checksum in SQL: double every second digit from the right.
    return f"""(
      SELECT sum(CASE WHEN (len({col}) - i) % 2 = 1
                      THEN (CAST(substr({col}, i, 1) AS INT) * 2) - CASE WHEN CAST(substr({col}, i, 1) AS INT) * 2 > 9 THEN 9 ELSE 0 END
                      ELSE CAST(substr({col}, i, 1) AS INT) END) % 10 = 0
      FROM range(1, len({col}) + 1) t(i))"""


def failing_predicate(column: str, check) -> tuple[str, str]:
    """Return (check_name, SQL predicate that is TRUE for a failing row)."""
    c = f'"{column}"'
    if check == "not_null":
        return "not_null", f"{c} IS NULL"
    if check == "luhn":
        return "luhn", f"{c} IS NOT NULL AND NOT {_luhn_sql(c)}"
    if isinstance(check, dict):
        (name, arg), = check.items()
        if name == "regex":
            return f"regex", f"{c} IS NOT NULL AND NOT regexp_full_match({c}, '{arg}')"
        if name == "allowed_values":
            vals = ", ".join(f"'{v}'" for v in arg)
            return "allowed_values", f"{c} IS NOT NULL AND {c} NOT IN ({vals})"
        if name == "range":
            return "range", f"{c} < {arg['min']} OR {c} > {arg['max']}"
    raise ValueError(f"unsupported check {check!r}")


def run_checks(con: duckdb.DuckDBPyConnection, contract: Contract, now: datetime | None = None) -> list[CheckResult]:
    t = contract.dataset
    total = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    results = []
    actual_cols = {r[0] for r in con.execute(f"DESCRIBE {t}").fetchall()}
    for missing in sorted(set(contract.columns) - actual_cols):
        results.append(CheckResult(t, missing, "column_exists", total, total))
    for col in contract.columns.values():
        if col.name not in actual_cols:
            continue
        for check in col.checks:
            if check == "unique":
                failed = con.execute(
                    f'SELECT coalesce(sum(n), 0) FROM (SELECT count(*) n FROM {t} GROUP BY "{col.name}" HAVING n > 1)'
                ).fetchone()[0]
                results.append(CheckResult(t, col.name, "unique", int(failed), total))
            elif isinstance(check, dict) and "references" in check:
                ref_t, ref_c = check["references"].split(".")
                failed = con.execute(
                    f'SELECT count(*) FROM {t} x WHERE "{col.name}" IS NOT NULL AND NOT EXISTS '
                    f'(SELECT 1 FROM {ref_t} r WHERE r."{ref_c}" = x."{col.name}")'
                ).fetchone()[0]
                results.append(CheckResult(t, col.name, "references", failed, total))
            else:
                name, pred = failing_predicate(col.name, check)
                failed = con.execute(f"SELECT count(*) FROM {t} WHERE {pred}").fetchone()[0]
                results.append(CheckResult(t, col.name, name, failed, total))
    if contract.freshness:
        col, max_age = contract.freshness["column"], contract.freshness["max_age_hours"]
        now = now or datetime.now()
        newest = con.execute(f'SELECT max(CAST("{col}" AS TIMESTAMP)) FROM {t}').fetchone()[0]
        stale = newest is None or (now - newest).total_seconds() > max_age * 3600
        results.append(CheckResult(t, col, f"freshness<={max_age}h", total if stale else 0, total))
    return results


def score(results: list[CheckResult]) -> float:
    """Share of check-row evaluations that passed, 0-100."""
    evals = sum(r.total_rows for r in results)
    failed = sum(min(r.failed_rows, r.total_rows) for r in results)
    return round(100 * (1 - failed / evals), 2) if evals else 100.0
