"""PHI / sensitive-identifier guard. The library must never hold patient data (FIN-1413).

This is a tripwire, not a classifier: it rejects text that carries the obvious
shapes of PHI or financial identifiers. Content owners are still responsible
for only loading business documents.
"""

from __future__ import annotations

import re
from typing import List

_PATTERNS = {
    "ssn": re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"),
    "date_of_birth": re.compile(r"\b(?:DOB|D\.O\.B\.|date\s+of\s+birth|birth\s*date)\b\s*[:#]?\s*\S", re.I),
    "medical_record_number": re.compile(r"\b(?:MRN|medical\s+record\s+(?:number|no\.?|#))\b\s*[:#]?\s*\w", re.I),
    "patient_label": re.compile(r"\bpatient\s+(?:name|id|dob|address|phone)\s*[:#]", re.I),
    "medicare_mbi": re.compile(r"\b[1-9][AC-HJKMNP-RT-Y][AC-HJKMNP-RT-Y0-9]\d[AC-HJKMNP-RT-Y][AC-HJKMNP-RT-Y0-9]\d[AC-HJKMNP-RT-Y]{2}\d{2}\b"),
    "diagnosis_code_with_patient": re.compile(r"\b(?:ICD-?10|diagnosis)\b[^\n]{0,40}\bpatient\b", re.I),
}

_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def findings(text: str) -> List[str]:
    """Return the names of every sensitive pattern found (empty list = clean)."""
    hits = [name for name, rx in _PATTERNS.items() if rx.search(text)]
    for m in _CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn(digits):
            hits.append("payment_card_number")
            break
    return hits
