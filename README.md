# data-governance-toolkit

Governance controls you can run, driven by YAML data contracts. Each run produces one report covering data quality, PII discovery, role-based masking, SQL lineage and a user-access review.

## Posting skills this demonstrates

From JPMorgan Chase's **Lead Data Engineer** posting:

| Posting asks for | Where it shows up here |
| --- | --- |
| Recommendations and insight on data management and governance procedures | Data contracts with an owner, a steward, a classification and checks per column (`contracts/*.yaml`) |
| Data governance and ensuring data quality and integrity | `quality.py`: not-null, unique, regex, allowed values, range, Luhn, referential integrity and freshness checks, compiled to SQL |
| Evaluates and reports on access control processes to determine the effectiveness of data asset security | `access_review.py`: leaver access, missing or self approval, segregation of duties, dormant privileged grants and PII reads through masked roles, plus an effectiveness score |
| Secure data access | `masking.py` generates one secure view per role and dataset. It hashes, partially masks, redacts or reduces to last-4 / year-only based on classification |
| Data lifecycle | Lineage parsed from SQL with sqlglot answers "what feeds this report?" |
| Communicating complex technical concepts to non-technical audiences | The output is a plain Markdown report a risk or audit partner can read ([sample](docs/sample_report.md)) |

## What the sample run finds

The sample data has known problems planted in it, and the tests assert each one is caught.

* **Quality.** A duplicate customer key, a malformed email, an unknown segment, a missing KYC status, an orphaned account and an out-of-range balance.
* **PII.** A free-text `notes` column labeled `internal` that contains phone numbers in 34% of rows. It is flagged **UNDER-CLASSIFIED**.
* **Access.** A leaver who still has access, an admin grant with no approver, a self-approved grant, a segregation-of-duties conflict, and a dormant privileged grant.

```
| HIGH   | leaver_access          | grace | analyst on accounts still granted after termination |
| HIGH   | missing_approval       | frank | admin on customers has no recorded approver |
| HIGH   | segregation_of_duties  | dan   | holds both data_engineer and approver |
| HIGH   | self_approval          | dan   | approver on access_requests approved by the grantee |
| MEDIUM | dormant_grant          | erin  | pii_reader on accounts last used 2026-03-28 |
```

## Run it

```bash
pip install -e ".[dev]"
make report     # generates sample data and writes governance_report.md
make test
```

CI builds the report on every push and uploads it as a build artifact.

## Design notes

* **Contracts are the single source of truth.** Column types in the contract drive loading, so card numbers are never inferred as integers. Classifications drive masking, and checks drive quality. Adding a dataset means adding one YAML file.
* **Checks compile to SQL.** Each check becomes a predicate that is true for failing rows. The same rules can run in DuckDB, Trino or Spark SQL, and failing rows are easy to pull for triage.
* **Detect, don't trust.** PII discovery samples real values and compares what it finds with what the contract declares. That catches mislabeled columns before they reach a downstream masked view.
