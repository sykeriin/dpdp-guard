"""Rights-intent classifier: access / correction / erasure / withdraw / grievance / stop.
Rule layer first (EN, Hindi, Hinglish); optional LLM fallback for unmatched text."""
import re
import unicodedata

INTENTS = ["erasure", "withdraw", "access", "correction", "grievance", "stop"]

_RULES = {
    "erasure": [
        r"\b(delete|erase|remove|wipe)\b.{0,25}\b(my|meri|mera)?\s*(data|details|info|information|account|number|record)",
        r"\b(my|meri|mera)\b.{0,15}\b(data|details|info|number)\b.{0,20}\b(delete|erase|remove|hata|hatao|mita|mitao)",
        r"\b(hata|hatao|hatado|hata do|mita|mitao|mita do|delete kar|delete karo|delete kardo|delete kar do)\b",
        r"right to (be forgotten|erasure)", r"forget me", r"\b(delete|erase|remove|wipe)\b.{0,30}\b(everything|all)\b.{0,25}\bon me\b",
        r"(डेटा|जानकारी|डिटेल).{0,15}(हटा|मिटा|डिलीट)", r"(हटा|मिटा|डिलीट).{0,15}(डेटा|जानकारी|डिटेल)", r"मुझे भूल जाओ",
    ],
    "withdraw": [
        r"\b(withdraw|revoke|take back|cancel)\b.{0,20}\b(consent|permission)", r"\bconsent\b.{0,15}\b(withdraw|wapas|vapas|cancel)",
        r"\b(sahmati|permission)\b.{0,15}\b(wapas|vapas|le lo|cancel)", r"(सहमति|अनुमति).{0,12}(वापस|रद्द)",
        r"\bi do(n't| not) (agree|consent)\b", r"\bno longer consent\b",
    ],
    "access": [
        r"\bwhat (data|details|info|information)\b.{0,30}\b(do you|have you|you have)\b", r"\b(show|give|send|share)\b.{0,15}\b(me )?(my )?(data|details|information)\b",
        r"\bcopy of my (data|details)", r"\bkya (data|details|jaankari|information)\b.{0,25}\b(hai|rakha|store|stored|save)",
        r"\b(meri|mera) (details|data|jaankari)\b.{0,20}\b(batao|dikhao|bhejo|do)\b", r"मेरा डेटा.{0,12}(दिखाओ|बताओ|भेजो)", r"क्या डेटा.{0,15}(है|रखा)",
    ],
    "correction": [
        r"\b(correct|update|change|fix|edit)\b.{0,20}\b(my )?(name|number|phone|email|address|details)\b", r"\b(galat|wrong)\b.{0,20}\b(name|number|email|address|details|naam|pata)\b",
        r"\b(naam|number|address|pata|email)\b.{0,15}\b(badlo|badal|theek|sahi|update)", r"\b(name|number|phone|email|address)\b.{0,12}\b(is|hai)\b.{0,3}\b(wrong|galat|incorrect)\b", r"(नाम|पता|नंबर).{0,10}(बदल|सही|ठीक)",
    ],
    "grievance": [
        r"\b(complain|complaint|grievance|report)\b.{0,20}\b(privacy|data|misuse)", r"\bdata (misuse|leak|breach)\b",
        r"\bgrievance officer\b", r"\bprivacy complaint\b", r"\bgrievance about\b.{0,30}\bdata\b", r"\b(shikayat|shikayat karni)\b", r"शिकायत",
    ],
    "stop": [
        r"^\s*(stop|unsubscribe|opt[ -]?out|stop messages?)\s*[.!]*\s*$", r"\b(stop|band)\b.{0,15}\b(messages?|msgs?|texts?|calling|calls?|marketing|promotions?)\b",
        r"\b(messages?|msgs?|calls?)\b.{0,15}\b(band|stop)\b", r"\bdon'?t (message|text|call|contact) me\b", r"\bunsubscribe\b", r"मैसेज.{0,10}बंद",
    ],
}
_COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in _RULES.items()}
# priority when several match: erasure beats withdraw beats the rest
_PRIORITY = ["erasure", "withdraw", "access", "correction", "grievance", "stop"]


def _norm(t: str) -> str:
    return unicodedata.normalize("NFC", t).strip()


def classify_rules(text: str) -> str | None:
    t = _norm(text)
    hits = [k for k in _PRIORITY if any(p.search(t) for p in _COMPILED[k])]
    return hits[0] if hits else None


def classify_llm(text: str, client=None, model: str = "claude-haiku-5-5") -> str | None:
    if client is None:
        try:
            import anthropic
            client = anthropic.Anthropic()
        except Exception:
            return None
    try:
        r = client.messages.create(
            model=model, max_tokens=10,
            system=("Classify a chat message sent to a business bot (English, Hindi or Hinglish) into one data-rights intent: "
                    "erasure (delete my data), withdraw (withdraw consent), access (what data do you have), correction (fix my details), "
                    "grievance (privacy complaint), stop (stop messaging me), none. Reply with one word only."),
            messages=[{"role": "user", "content": text}])
        out = r.content[0].text.strip().lower()
    except Exception:
        return None
    return out if out in INTENTS else None


def classify(text: str, use_llm: bool = False, client=None) -> str | None:
    r = classify_rules(text)
    if r or not use_llm:
        return r
    return classify_llm(text, client)
