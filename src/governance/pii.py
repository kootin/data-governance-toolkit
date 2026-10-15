"""Scan column values for PII and flag columns whose contract classification understates it."""
from __future__ import annotations

import re
from dataclasses import dataclass

import duckdb

from governance.contracts import Contract

PATTERNS = {
    "email": re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.I),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\(?\b\d{3}\)?[ .-]?\d{3}[ .-]\d{4}\b"),
    "card_number": re.compile(r"\b\d{13,19}\b"),
}
SENSITIVITY = {"public": 0, "internal": 1, "confidential": 2, "pii": 3, "restricted": 4}
DETECTED_LEVEL = {"email": "pii", "phone": "pii", "ssn": "restricted", "card_number": "restricted"}


def luhn_ok(number: str) -> bool:
    digits = [int(d) for d in number][::-1]
    total = sum(d if i % 2 == 0 else (d * 2 - 9 if d * 2 > 9 else d * 2) for i, d in enumerate(digits))
    return total % 10 == 0


@dataclass
class PiiFinding:
    dataset: str
    column: str
    pii_type: str
    match_rate: float
    declared: str
    required: str

    @property
    def under_classified(self) -> bool:
        return SENSITIVITY[self.declared] < SENSITIVITY[self.required]


def scan(con: duckdb.DuckDBPyConnection, contract: Contract, sample: int = 1000, threshold: float = 0.02) -> list[PiiFinding]:
    findings = []
    for col in contract.columns.values():
        values = [r[0] for r in con.execute(
            f'SELECT CAST("{col.name}" AS VARCHAR) FROM {contract.dataset} '
            f'WHERE "{col.name}" IS NOT NULL USING SAMPLE {sample} ROWS (reservoir, 42)'
        ).fetchall()]
        if not values:
            continue
        for pii_type, rx in PATTERNS.items():
            hits = [v for v in values if rx.search(v)]
            if pii_type == "card_number":
                hits = [v for v in hits if luhn_ok(rx.search(v).group())]
            rate = len(hits) / len(values)
            if rate >= threshold:
                findings.append(PiiFinding(contract.dataset, col.name, pii_type, round(rate, 3),
                                           col.classification, DETECTED_LEVEL[pii_type]))
    return findings
