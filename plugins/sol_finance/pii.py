"""PII scrubber: card numbers, bank/routing numbers, SSNs, passwords, API keys.

Applied to logs, memory writes, tool results and every outgoing message.
Card and account numbers keep the last four digits only.
"""

from __future__ import annotations

import logging
import re

_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD = re.compile(r"(?<![\d-])(?:\d[ -]?){13,19}(?![\d-])")
_ACCT = re.compile(
    r"(?i)\b(account|acct|routing|aba|iban|swift)(?:\s*(?:number|no\.?|#))?\s*[:#=]?\s*(\d[\d -]{5,32}\d)")
_PASSWORD = re.compile(r"(?i)\b(password|passwd|pwd|passcode|pin)\s*[:=]\s*\S+")
_KEYS = re.compile(
    r"\b(sk_(?:live|test)_[A-Za-z0-9]{8,}|rk_(?:live|test)_[A-Za-z0-9]{8,}|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,})\b")


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


def _card_sub(m: "re.Match[str]") -> str:
    digits = re.sub(r"\D", "", m.group(0))
    if 13 <= len(digits) <= 19 and _luhn(digits):
        return f"[CARD ****{digits[-4:]}]"
    return m.group(0)


def scrub(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    text = _KEYS.sub("[SECRET REDACTED]", text)
    text = _PASSWORD.sub(lambda m: f"{m.group(1)}: [REDACTED]", text)
    text = _SSN.sub("[SSN REDACTED]", text)
    text = _ACCT.sub(lambda m: f"{m.group(1)} ****{re.sub(chr(92)+'D','',m.group(2))[-4:]}", text)
    text = _CARD.sub(_card_sub, text)
    return text


def contains_pii(text: str) -> bool:
    return isinstance(text, str) and scrub(text) != text


def scrub_obj(obj):
    if isinstance(obj, str):
        return scrub(obj)
    if isinstance(obj, dict):
        return {k: scrub_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [scrub_obj(v) for v in obj]
    return obj


class ScrubFilter(logging.Filter):
    """Logging filter: scrub every record's message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = scrub(record.getMessage())
            record.args = ()
        except Exception:
            pass
        return True


def install_log_filter() -> None:
    root = logging.getLogger()
    if not any(isinstance(f, ScrubFilter) for f in root.filters):
        root.addFilter(ScrubFilter())
        for h in root.handlers:
            h.addFilter(ScrubFilter())
