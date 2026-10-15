"""Periodic user-access review: evaluates how well access controls are working."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd


@dataclass
class Finding:
    severity: str
    control: str
    user: str
    detail: str


def review(grants: pd.DataFrame, access_log: pd.DataFrame, roster: pd.DataFrame, policy: dict,
           as_of: datetime) -> list[Finding]:
    f: list[Finding] = []
    active = set(roster.loc[roster["active"], "user"])
    log = access_log.assign(ts=pd.to_datetime(access_log["ts"]))
    last_use = log.groupby(["user", "dataset"])["ts"].max()
    dormant_cutoff = as_of - timedelta(days=policy["review"]["dormant_after_days"])

    for g in grants.itertuples():
        if g.user not in active:
            f.append(Finding("HIGH", "leaver_access", g.user, f"{g.role} on {g.dataset} still granted after termination"))
        if pd.isna(g.approved_by):
            f.append(Finding("HIGH", "missing_approval", g.user, f"{g.role} on {g.dataset} has no recorded approver"))
        elif g.approved_by == g.user:
            f.append(Finding("HIGH", "self_approval", g.user, f"{g.role} on {g.dataset} approved by the grantee"))
        used = last_use.get((g.user, g.dataset))
        if g.dataset != "access_requests" and (used is None or used < dormant_cutoff):
            sev = "MEDIUM" if g.role in policy["review"]["privileged_roles"] else "LOW"
            when = "never used" if used is None else f"last used {used:%Y-%m-%d}"
            f.append(Finding(sev, "dormant_grant", g.user, f"{g.role} on {g.dataset} {when}"))

    roles_by_user = grants.groupby("user")["role"].apply(set)
    for user, roles in roles_by_user.items():
        for a, b in policy["sod_conflicts"]:
            if {a, b} <= roles:
                f.append(Finding("HIGH", "segregation_of_duties", user, f"holds both {a} and {b}"))

    # Who read PII columns without a role that may see PII unmasked?
    pii_roles = {r for r, spec in policy["roles"].items() if "pii" in spec["unmasked"]}
    roles = grants[["user", "dataset", "role"]]
    reads = log[log["columns"].str.contains("email|full_name|ssn|\\*", regex=True)].merge(roles, on=["user", "dataset"])
    for (user, dataset), grp in reads.groupby(["user", "dataset"]):
        if not set(grp["role"]) & pii_roles:
            f.append(Finding("MEDIUM", "pii_read_via_masked_role", user,
                             f"{len(grp)} queries touched PII columns of {dataset}; served masked, confirm need"))
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return sorted(f, key=lambda x: (order[x.severity], x.control, x.user))


def effectiveness(grants: pd.DataFrame, findings: list[Finding]) -> float:
    """Percent of grants with no HIGH finding against them."""
    flagged = {(x.user) for x in findings if x.severity == "HIGH"}
    return round(100 * (1 - float(grants["user"].isin(flagged).mean())), 1)
