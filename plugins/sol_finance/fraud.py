"""Fraud guard: inbound messages that look like payment fraud trigger an alert, never action."""

from __future__ import annotations

import re
from typing import List

_PATTERNS = [
    ("bank_change", re.compile(
        r"(?i)\b(change|update|new|replace|switch)\w*\b.{0,40}\b(bank|wire|routing|account|ach|payment)\b.{0,20}\b(details?|instructions?|info\w*|number)\b")),
    ("bank_change", re.compile(r"(?i)\b(our|my)\s+(bank|banking)\s+(details|information|account)\s+(has|have|changed|are changing)")),
    ("urgent_pay", re.compile(r"(?i)\b(urgent(ly)?|immediately|asap|today only|right away|same[- ]day)\b.{0,60}\b(pay|payment|wire|transfer|send)\b")),
    ("urgent_pay", re.compile(r"(?i)\b(pay|wire|transfer|send)\b.{0,60}\b(urgent(ly)?|immediately|asap|right away)\b")),
    ("claims_approval", re.compile(r"(?i)\b(rick|nancy|ceo|chairman)\b.{0,30}\b(approved|authorized|signed off|okayed)\b")),
    ("claims_approval", re.compile(r"(?i)\bapproved by (rick|nancy)\b")),
]


def scan(text: str) -> List[str]:
    signals: List[str] = []
    for name, pat in _PATTERNS:
        if pat.search(text or "") and name not in signals:
            signals.append(name)
    return signals
