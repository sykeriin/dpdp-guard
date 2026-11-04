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

# ---- generalising rules: verb/noun proximity instead of fixed phrases (added after held-out first-run = 58.9%) ----
def _near(a: str, b: str, w: int = 45) -> str:
    return rf"(?:{a}).{{0,{w}}}(?:{b})|(?:{b}).{{0,{w}}}(?:{a})"

_DEL = r"\b(?:delet\w*|eras\w*|remov\w*|wip\w*|purg\w*|get rid of|destroy\w*|forget|nikal\w*|hat[ae]\w*|mit[ae]\w*)\b|हटा|मिटा|डिलीट|निकाल"
_DATA = r"\b(?:data|details?|information|info|records?|numbers?|accounts?|profile|history|jaankari|personal|database|systems?)\b|डेटा|जानकारी|डिटेल|नंबर|रिकॉर्ड|खाता"
_ME = r"\b(?:me|my|mine|mera|meri|mere|mujhe|mujh|main|mai|apna|apni|apne|personal)\b|मेरा|मेरी|मेरे|मुझे|अपना|अपनी|अपने"
_EDIT = r"\b(?:correct\w*|updat\w*|chang\w*|fix\w*|edit\w*|modif\w*|badal\w*|badl\w*|sudhar\w*|theek|sahi)\b|बदल|सुधार|ठीक|सही"
_FIELD = r"\b(?:name|phone|mobile|number|e-?mail|email id|address|details|naam|pata)\b|नाम|पता|नंबर|ईमेल"
_WRONG = r"\b(?:wrong|incorrect|galat|mistake|error|misspelt)\b|गलत"
_ORDERCTX = re.compile(r"(?i)\b(?:order|delivery|parcel|shipment|shipping|cart|booking|appointment|slot|courier)\b|ऑर्डर|डिलीवरी")
_PROFILECTX = re.compile(r"(?i)\b(?:profile|records?|saved|registered|contact details|your (?:system|database)|you have for me)\b")
_HOLD = r"\b(?:hold|have|has|store[sd]?|collect\w*|keep|kept|know|saved?|rakha|rakhi)\b|पास|रखा"

_GENERAL = {
    "erasure": [
        _near(_DEL, _DATA) + "|" + _near(_DEL, r"\beverything\b|\ball\b", 25),   # gated by _ME below
    ],
    "withdraw": [
        _near(r"\b(?:revok\w*|withdraw\w*|take back|taking back|cancel\w*)\b|वापस", r"\b(?:consent|permission|sahmati)\b|सहमति|अनुमति", 40),
        r"\bno longer (?:agree|consent)\b", r"\b(?:do not|don'?t|dont) (?:consent|agree)\b", r"\bconsent\b.{0,15}\b(?:wapas|vapas)\b",
    ],
    "access": [
        r"\bwhat\b.{0,40}\b(?:you|aap\w*)\b.{0,20}(?:" + _HOLD + r").{0,25}\b(?:about|on)\s+me\b",
        r"\b(?:see|view|show|tell|give|send|share|export|list|provide|copy)\b.{0,45}(?:\bpersonal data\b|\bmy (?:data|details|information|info|records)\b|\b(?:data|details|information|info) (?:that )?(?:you|aap)\b.{0,15}(?:" + _HOLD + r")|\b(?:data|details|information) (?:about|on) me\b)",
        r"\bcopy of (?:the |my )?(?:information|data|details)\b.{0,30}\b(?:hold|have|store)\b",
        r"\b(?:mere|meri|mera|mujhe)\b.{0,30}\b(?:baare|bare|details|data|jaankari|information|info)\b.{0,30}\b(?:kya|copy|dikha\w*|bata\w*|bhej\w*|chahiye)\b",
        r"मेरे बारे में.{0,25}(?:जानकारी|डेटा|क्या)", r"(?:मेरा|मेरी|मुझे).{0,15}(?:डेटा|जानकारी|डिटेल).{0,15}(?:दिखा|बता|भेज|कॉपी)",
    ],
    "correction": [
        _near(_EDIT, _FIELD, 30), _near(_WRONG, _FIELD, 35),
    ],
    "grievance": [
        _near(r"\b(?:complain\w*|grievance|escalat\w*|dpo|shikayat|data protection officer)\b|शिकायत", r"\b(?:data|privacy|information|personal|misuse|leak\w*)\b|डेटा|जानकारी|दुरुपयोग", 50),
        r"\bleak\w*\b.{0,25}\b(?:my|our)\b.{0,15}\b(?:information|data|details)\b", r"\bdata protection officer\b",
    ],
    "stop": [
        _near(r"\b(?:stop|don'?t|dont|no more|any more|mat|band|unsubscribe|remove me from|nahi chahiye)\b", r"\b(?:messages?|msgs?|texts?|promo\w*|marketing|offers?|mailing list|whatsapp\w*|calls?)\b|मैसेज|प्रमोशनल", 28),
        r"^\s*stop all\s*[.!]*\s*$", r"मैसेज.{0,10}(?:मत|बंद)",
    ],
}
_GENERAL_C = {k: [re.compile(p, re.I) for p in v] for k, v in _GENERAL.items()}
_ME_C, _ERASE_EXPLICIT = re.compile(_ME, re.I), re.compile(r"(?i)\bunder dpdp\b|\bpersonal data\b|\bme\b")


def _general_hit(intent_name: str, t: str) -> bool:
    if not any(p.search(t) for p in _GENERAL_C[intent_name]):
        return False
    if intent_name == "erasure":
        return bool(_ME_C.search(t))                      # must be about the speaker's own data
    return True


_COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in _RULES.items()}
# priority when several match: erasure beats withdraw beats the rest
_PRIORITY = ["erasure", "withdraw", "access", "correction", "grievance", "stop"]


def _norm(t: str) -> str:
    return unicodedata.normalize("NFC", t).strip()


def classify_rules(text: str) -> str | None:
    t = _norm(text)
    hits = [k for k in _PRIORITY if any(p.search(t) for p in _COMPILED[k]) or _general_hit(k, t)]
    # editing an order / delivery / booking is service work, not a data-correction right, unless the text points at the stored profile
    if "correction" in hits and _ORDERCTX.search(t) and not _PROFILECTX.search(t):
        hits.remove("correction")
    return hits[0] if hits else None


def classify_llm(text: str, client=None, model: str = "claude-haiku-5-5") -> str | None:
    from ._llm import call_text, make_client
    client = client or make_client()
    if client is None:
        return None
    try:
        out = call_text(client, (
            "Classify a chat message sent to a business bot (English, Hindi or Hinglish) into one data-rights intent: "
            "erasure (delete my data), withdraw (withdraw consent), access (what data do you have), correction (fix my stored details), "
            "grievance (privacy complaint), stop (stop messaging me), none. Ordinary service requests about an order, delivery, "
            "booking or product are none. Reply with one word only."), text, max_tokens=16, model=model)
    except Exception:
        return None
    out = (out or "").strip().lower()
    return out if out in INTENTS else None


def classify(text: str, use_llm: bool = False, client=None) -> str | None:
    r = classify_rules(text)
    if r or not use_llm:
        return r
    return classify_llm(text, client)
