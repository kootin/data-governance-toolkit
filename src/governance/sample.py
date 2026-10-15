"""Generate sample customer/account data and access-control records with known problems."""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

FIRST = ["Ava", "Liam", "Noah", "Mia", "Zoe", "Ethan", "Ivy", "Omar", "Priya", "Chen"]
LAST = ["Smith", "Garcia", "Patel", "Nguyen", "Kim", "Okafor", "Rossi", "Silva"]


def luhn_complete(prefix: str) -> str:
    digits = [int(d) for d in prefix]
    for i in range(len(digits) - 1, -1, -2):
        digits[i] = digits[i] * 2 - 9 if digits[i] * 2 > 9 else digits[i] * 2
    return prefix + str((10 - sum(digits) % 10) % 10)


def make(out: Path, n: int = 500, seed: int = 11) -> None:
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    customers = []
    for i in range(n):
        fn, ln = rng.choice(FIRST), rng.choice(LAST)
        customers.append({
            "customer_id": f"C{i:05d}",
            "full_name": f"{fn} {ln}",
            "email": f"{fn.lower()}.{ln.lower()}{i}@example.com",
            "ssn": f"{rng.randint(100, 899):03d}-{rng.randint(10, 99):02d}-{rng.randint(1000, 9999):04d}",
            "date_of_birth": (date(1950, 1, 1) + timedelta(days=rng.randrange(20000))).isoformat(),
            "segment": rng.choice(["RETAIL", "PRIVATE", "BUSINESS"]),
            "kyc_status": rng.choice(["VERIFIED"] * 9 + ["PENDING"]),
            "updated_at": (datetime(2026, 10, 14) - timedelta(hours=rng.randrange(48))).isoformat(),
            # Free-text notes column that nobody classified, and that sometimes holds a phone number.
            "notes": rng.choice(["", "prefers email", f"call back on (212) 555-{rng.randint(1000, 9999)}", "VIP"]),
        })
    # Planted quality problems
    customers[5]["email"] = "not-an-email"
    customers.append(dict(customers[7], email="dup.delivery@example.com"))  # duplicate key
    customers[8]["segment"] = "UNKNOWN"
    customers[9]["kyc_status"] = None
    pd.DataFrame(customers).to_csv(out / "customers.csv", index=False)

    accounts = [{
        "account_id": f"A{i:06d}",
        "customer_id": f"C{rng.randrange(n):05d}",
        "card_number": luhn_complete("4" + "".join(str(rng.randrange(10)) for _ in range(14))),
        "balance": round(rng.uniform(-500, 250_000), 2),
        "opened_on": (date(2015, 1, 1) + timedelta(days=rng.randrange(3800))).isoformat(),
    } for i in range(n * 2)]
    accounts[0]["customer_id"] = "C99999"                                # orphan foreign key
    accounts[1]["balance"] = -2_000_000.0                                 # out of range
    pd.DataFrame(accounts).to_csv(out / "accounts.csv", index=False)

    users = ["alice", "bob", "carol", "dan", "erin", "frank", "grace"]
    grants = [
        ("alice", "analyst", "customers", "2025-01-10", "jsmith"),
        ("bob", "analyst", "customers", "2025-03-02", "jsmith"),
        ("carol", "pii_reader", "customers", "2025-02-14", "mlopez"),
        ("dan", "data_engineer", "customers", "2024-06-01", "mlopez"),
        ("dan", "data_engineer", "accounts", "2024-06-01", "mlopez"),
        ("dan", "approver", "access_requests", "2024-06-01", "dan"),     # self-approved + SoD conflict
        ("erin", "pii_reader", "accounts", "2023-11-20", "jsmith"),        # dormant
        ("frank", "admin", "customers", "2026-09-30", None),               # no approver recorded
        ("grace", "analyst", "accounts", "2025-07-07", "jsmith"),          # grace left the firm
    ]
    pd.DataFrame(grants, columns=["user", "role", "dataset", "granted_on", "approved_by"]).to_csv(out / "grants.csv", index=False)
    pd.DataFrame([{"user": u, "active": u != "grace"} for u in users]).to_csv(out / "hr_roster.csv", index=False)

    log = []
    now = datetime(2026, 10, 14)
    for _ in range(400):
        u, role, ds, *_ = rng.choice([g for g in grants if g[0] != "erin" and g[2] != "access_requests"])
        log.append({"ts": (now - timedelta(minutes=rng.randrange(60 * 24 * 60))).isoformat(), "user": u,
                    "dataset": ds, "columns": rng.choice(["customer_id,segment", "email,full_name", "*"])})
    log.append({"ts": (now - timedelta(days=200)).isoformat(), "user": "erin", "dataset": "accounts", "columns": "*"})
    pd.DataFrame(log).to_csv(out / "access_log.csv", index=False)


if __name__ == "__main__":
    make(Path("sample_data"))
    print("wrote sample_data/")
