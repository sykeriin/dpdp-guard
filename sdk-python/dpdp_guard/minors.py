"""Heuristics for likely minors (Rules 10-12). Signals only; the customer must still verify."""
import re

_AGE = re.compile(r"(?i)\b(?:i am|i'm|im|main|meri umar|age|umar)\s*(?:is\s*)?(\d{1,2})\s*(?:years?|yrs?|saal|sal|वर्ष|साल)?\b")
_CLASS = re.compile(r"(?i)\b(?:class|grade|std|standard|कक्षा)\s*(\d{1,2})(?:th|st|nd|rd)?\b")
_WORDS = re.compile(r"(?i)\b(?:my school|school mein|mere papa ne|mummy ne bola|i'm a kid|under 18|minor|board exam|jee prep|neet prep)\b")


def likely_minor(text: str) -> bool:
    for m in _AGE.finditer(text):
        if 5 <= int(m.group(1)) < 18:
            return True
    for m in _CLASS.finditer(text):
        if 1 <= int(m.group(1)) <= 12:
            return True
    return bool(_WORDS.search(text))
