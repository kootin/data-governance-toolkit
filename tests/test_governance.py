import pandas as pd
import yaml

from conftest import AS_OF, ROOT
from governance import access_review, lineage, masking, pii, quality
from governance.cli import build_report


def failures(results):
    return {(r.column, r.check): r.failed_rows for r in results if not r.passed}


def test_quality_checks_catch_planted_issues(con, contracts):
    cust = failures(quality.run_checks(con, contracts["customers"], now=AS_OF))
    assert cust == {("customer_id", "unique"): 2, ("email", "regex"): 1,
                    ("segment", "allowed_values"): 1, ("kyc_status", "not_null"): 1}
    acct = failures(quality.run_checks(con, contracts["accounts"], now=AS_OF))
    assert acct == {("customer_id", "references"): 1, ("balance", "range"): 1}


def test_luhn_check_rejects_bad_card(con, contracts):
    con.execute("UPDATE accounts SET card_number = '4111111111111112' WHERE account_id = 'A000002'")
    acct = failures(quality.run_checks(con, contracts["accounts"], now=AS_OF))
    assert acct[("card_number", "luhn")] == 1


def test_freshness_fails_when_stale(con, contracts):
    from datetime import timedelta
    res = quality.run_checks(con, contracts["customers"], now=AS_OF + timedelta(days=3))
    assert any(r.check.startswith("freshness") and not r.passed for r in res)


def test_pii_scan_finds_unclassified_phone_numbers(con, contracts):
    found = {(f.column, f.pii_type): f for c in contracts.values() for f in pii.scan(con, c)}
    assert found[("notes", "phone")].under_classified
    assert not found[("email", "email")].under_classified
    assert not found[("card_number", "card_number")].under_classified
    assert not found[("ssn", "ssn")].under_classified


def test_masking_views_respect_role(con, contracts):
    masking.create_secure_views(con, contracts, ROOT / "contracts/access_policy.yaml")
    analyst = con.execute("SELECT email, ssn, date_of_birth, segment FROM secure.customers__analyst LIMIT 1").fetchone()
    raw = con.execute("SELECT email, segment FROM customers LIMIT 1").fetchone()
    assert analyst[0] != raw[0] and len(analyst[0]) == 64          # sha256 hash
    assert analyst[1] == "***REDACTED***" and len(analyst[2]) == 4
    assert analyst[3] == raw[1]                                     # internal column stays clear
    pii_reader = con.execute("SELECT email, ssn FROM secure.customers__pii_reader LIMIT 1").fetchone()
    assert pii_reader[0] == raw[0] and pii_reader[1] == "***REDACTED***"
    card = con.execute("SELECT card_number FROM secure.accounts__data_engineer LIMIT 1").fetchone()[0]
    assert card.startswith("************") and card[-4:].isdigit()


def test_lineage_resolves_transitive_upstreams():
    edges = lineage.lineage_graph(ROOT / "sql")
    assert ("accounts", "analytics.customer_360") in edges
    assert lineage.upstream(edges, "reporting.kyc_exceptions") == {"analytics.customer_360", "customers", "accounts"}
    assert all(s != "acct" for s, _ in edges)                       # CTEs are not tables


def test_access_review_findings(data_dir):
    policy = yaml.safe_load((ROOT / "contracts/access_policy.yaml").read_text())
    grants = pd.read_csv(data_dir / "grants.csv")
    f = access_review.review(grants, pd.read_csv(data_dir / "access_log.csv"),
                             pd.read_csv(data_dir / "hr_roster.csv"), policy, AS_OF)
    got = {(x.control, x.user) for x in f}
    assert {("leaver_access", "grace"), ("missing_approval", "frank"), ("self_approval", "dan"),
            ("segregation_of_duties", "dan"), ("dormant_grant", "erin")} <= got
    assert ("pii_read_via_masked_role", "alice") in got
    assert ("pii_read_via_masked_role", "carol") not in got        # carol is a pii_reader
    assert access_review.effectiveness(grants, f) == round(100 * 4 / 9, 1)   # grace, frank and dan's 3 grants are flagged


def test_full_report_builds(data_dir):
    md, summary = build_report(data_dir, ROOT / "contracts", ROOT / "sql", AS_OF)
    assert "## 5. Access control review" in md and "```mermaid" in md
    assert summary["under_classified"] == ["customers.notes"]
