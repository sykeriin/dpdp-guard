"""Regex PII extractor + masking. Optional LLM pass for names/addresses (see llm_names)."""
import re
from dataclasses import dataclass, asdict

# kind -> (regex, default purpose, retention_days)
_PATTERNS = {
    "aadhaar": re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)"),
    "pan": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"),
    "upi": re.compile(r"\b[\w.-]{2,}@(?:ok\w+|ybl|paytm|upi|axl|ibl|sbi|hdfcbank|icici)\b", re.I),
    "phone": re.compile(r"(?<!\d)(?:\+?91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?!\d)"),
    "pin": re.compile(r"(?i)\b(?:pin(?:code)?|zip)\D{0,3}([1-9]\d{5})\b|(?<!\d)([1-9]\d{5})(?!\d)"),
}
# order matters: more specific first, so aadhaar/upi/email aren't eaten by phone/pin
_ORDER = ["upi", "email", "aadhaar", "pan", "phone", "pin"]
DEFAULT_RETENTION = {"phone": 90, "email": 90, "pin": 90, "pan": 30, "aadhaar": 7, "upi": 30, "name": 90, "address": 90}


@dataclass
class PIIField:
    kind: str
    value: str
    start: int
    end: int
    purpose: str = "support"
    retention_days: int = 90

    def public(self):
        d = asdict(self)
        d["value"] = mask_value(self.kind, self.value)
        return d


def mask_value(kind: str, v: str) -> str:
    digits = re.sub(r"\D", "", v)
    if kind == "email":
        u, _, d = v.partition("@")
        return u[:1] + "***@" + d
    if kind in ("phone", "aadhaar", "pin") and digits:
        return "*" * max(len(digits) - 2, 0) + digits[-2:]
    if kind == "pan":
        return v[:2] + "*****" + v[-1]
    return v[:1] + "***"


def extract(text: str, purpose: str = "support") -> list[PIIField]:
    taken: list[tuple[int, int]] = []
    out: list[PIIField] = []
    for kind in _ORDER:
        for m in _PATTERNS[kind].finditer(text):
            g = next((i for i in range(1, (m.lastindex or 0) + 1) if m.group(i)), 0)
            s, e = m.span(g)
            if any(s < te and e > ts for ts, te in taken):
                continue
            taken.append((s, e))
            out.append(PIIField(kind, text[s:e], s, e, purpose, DEFAULT_RETENTION[kind]))
    out.sort(key=lambda f: f.start)
    return out


def mask(text: str, fields: list[PIIField] | None = None) -> str:
    fields = extract(text) if fields is None else fields
    for f in sorted(fields, key=lambda f: -f.start):
        text = text[: f.start] + f"[{f.kind.upper()}:{mask_value(f.kind, f.value)}]" + text[f.end:]
    return text


def llm_names(text: str, client=None, model: str = "claude-haiku-5-5") -> list[PIIField]:
    """Optional LLM pass for names/addresses. Returns [] if no client/anthropic installed."""
    if client is None:
        try:
            import anthropic
            client = anthropic.Anthropic()
        except Exception:
            return []
    import json
    try:
        r = client.messages.create(
            model=model, max_tokens=300,
            system='Extract personal names and postal addresses from the user text. Reply ONLY JSON: [{"kind":"name"|"address","value":"<exact substring>"}]. Empty list if none.',
            messages=[{"role": "user", "content": text}])
        items = json.loads(r.content[0].text)
    except Exception:
        return []
    out = []
    for it in items:
        i = text.find(it.get("value", ""))
        if i >= 0 and it.get("kind") in ("name", "address"):
            out.append(PIIField(it["kind"], it["value"], i, i + len(it["value"]), "support", DEFAULT_RETENTION[it["kind"]]))
    return out
