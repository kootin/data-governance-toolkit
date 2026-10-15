"""Table-level lineage extracted from SQL transformations with sqlglot."""
from __future__ import annotations

from pathlib import Path

import sqlglot
from sqlglot import exp


def edges_for_sql(sql: str, dialect: str = "duckdb") -> list[tuple[str, str]]:
    edges = []
    for stmt in sqlglot.parse(sql, read=dialect):
        if stmt is None:
            continue
        target = None
        if isinstance(stmt, (exp.Create, exp.Insert)):
            t = stmt.this.find(exp.Table) if not isinstance(stmt.this, exp.Table) else stmt.this
            target = t.sql(dialect=dialect) if t is not None else None
        if not target:
            continue
        ctes = {c.alias for c in stmt.find_all(exp.CTE)}
        for src in stmt.find_all(exp.Table):
            name = src.sql(dialect=dialect).split(" AS ")[0]
            if name != target and src.name not in ctes:
                edges.append((name, target))
    return sorted(set(edges))


def lineage_graph(sql_dir: Path) -> list[tuple[str, str]]:
    edges = []
    for f in sorted(sql_dir.glob("*.sql")):
        edges += edges_for_sql(f.read_text())
    return sorted(set(edges))


def upstream(edges: list[tuple[str, str]], node: str) -> set[str]:
    parents = {s for s, t in edges if t == node}
    return parents | {a for p in parents for a in upstream(edges, p)}


def to_mermaid(edges: list[tuple[str, str]]) -> str:
    lines = ["graph LR"] + [f"    {s.replace('.', '_')}[{s}] --> {t.replace('.', '_')}[{t}]" for s, t in edges]
    return "\n".join(lines)
