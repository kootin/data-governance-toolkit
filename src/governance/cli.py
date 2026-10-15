"""Run every governance control over the sample data and write a Markdown report."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from governance import access_review, lineage, masking, pii, quality
from governance.contracts import load_all, load_csv


def build_report(data: Path, contracts_dir: Path, sql_dir: Path, as_of: datetime) -> tuple[str, dict]:
    con = duckdb.connect()
    contracts = load_all(contracts_dir)
    for name, contract in contracts.items():
        load_csv(con, contract, data / f"{name}.csv")
    policy = yaml.safe_load((contracts_dir / "access_policy.yaml").read_text())

    out = [f"# Data governance report\n\nAs of {as_of:%Y-%m-%d %H:%M}\n"]
    summary = {}

    out.append("## 1. Data quality\n\n| Dataset | Column | Check | Failed rows | Status |\n|---|---|---|---|---|")
    all_results = []
    for c in contracts.values():
        res = quality.run_checks(con, c, now=as_of)
        all_results += res
        for r in res:
            out.append(f"| {r.dataset} | {r.column} | {r.check} | {r.failed_rows} / {r.total_rows} | {'PASS' if r.passed else 'FAIL'} |")
    summary["quality_score"] = quality.score(all_results)
    summary["failed_checks"] = sum(not r.passed for r in all_results)
    out.append(f"\n**Quality score: {summary['quality_score']}%** ({summary['failed_checks']} failing checks)\n")

    out.append("## 2. PII discovery\n\n| Dataset | Column | Detected | Match rate | Declared | Required | Status |\n|---|---|---|---|---|---|---|")
    findings = [f for c in contracts.values() for f in pii.scan(con, c)]
    for f in findings:
        out.append(f"| {f.dataset} | {f.column} | {f.pii_type} | {f.match_rate:.1%} | {f.declared} | {f.required} | "
                   f"{'UNDER-CLASSIFIED' if f.under_classified else 'ok'} |")
    summary["under_classified"] = [f"{f.dataset}.{f.column}" for f in findings if f.under_classified]

    views = masking.create_secure_views(con, contracts, contracts_dir / "access_policy.yaml")
    out.append(f"\n## 3. Masking\n\nCreated {len(views)} role-specific secure views. What an `analyst` sees:\n")
    cur = con.execute("SELECT customer_id, full_name, email, ssn, date_of_birth FROM secure.customers__analyst LIMIT 3")
    cols = [d[0] for d in cur.description]
    out.append("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols))
    out += ["| " + " | ".join(str(v) for v in row) + " |" for row in cur.fetchall()]

    edges = lineage.lineage_graph(sql_dir)
    out.append("\n\n## 4. Lineage\n\n```mermaid\n" + lineage.to_mermaid(edges) + "\n```\n")
    out.append(f"`reporting.kyc_exceptions` depends on: {', '.join(sorted(lineage.upstream(edges, 'reporting.kyc_exceptions')))}\n")

    grants = pd.read_csv(data / "grants.csv")
    review = access_review.review(grants, pd.read_csv(data / "access_log.csv"), pd.read_csv(data / "hr_roster.csv"), policy, as_of)
    summary["access_effectiveness"] = access_review.effectiveness(grants, review)
    summary["access_findings"] = len(review)
    out.append("## 5. Access control review\n\n| Severity | Control | User | Detail |\n|---|---|---|---|")
    out += [f"| {f.severity} | {f.control} | {f.user} | {f.detail} |" for f in review]
    out.append(f"\n**Grants free of high-severity findings: {summary['access_effectiveness']}%**\n")
    return "\n".join(out), summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", default="sample_data")
    p.add_argument("--contracts", default="contracts")
    p.add_argument("--sql", default="sql")
    p.add_argument("--out", default="governance_report.md")
    p.add_argument("--as-of", type=datetime.fromisoformat, default=datetime(2026, 10, 14, 12))
    a = p.parse_args()
    md, summary = build_report(Path(a.data), Path(a.contracts), Path(a.sql), a.as_of)
    Path(a.out).write_text(md)
    print(summary)
    print(f"report written to {a.out}")


if __name__ == "__main__":
    main()
