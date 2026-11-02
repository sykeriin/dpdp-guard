"""Free DPDP bot checker: static gap report from a pasted transcript or bot flow. Heuristic, not legal advice."""
import re

from dpdp_guard import intent, pii

_NOTICE = re.compile(r"(?i)(personal data|your data|privacy (policy|notice)|data protection|process your|collect your|डेटा|गोपनीयता)")
_CONSENT_ASK = re.compile(r"(?i)(do you (agree|consent)|reply (yes|1)|i agree|opt[- ]in|consent|agree to|सहमत)")
_BUNDLED = re.compile(r"(?i)(by (continuing|using|chatting|replying).{0,60}(agree|consent|accept)|terms (and|&) conditions.{0,40}(agree|accept)|you (agree|consent) to (our )?(terms|privacy))")
_MARKETING = re.compile(r"(?i)(offers?|promotions?|newsletter|marketing|deals?|discount)")
_ERASE_PATH = re.compile(r"(?i)(delete (my )?data|erase|withdraw|stop|unsubscribe|opt[- ]?out|data (request|rights)|grievance|हटा)")
_PURPOSE = re.compile(r"(?i)(we (will )?use (it|this|your)|in order to|only for|to send you|purpose)")
_RETENTION = re.compile(r"(?i)(retain|keep (it|your data)|for \d+ (days|months|years)|deleted after|retention)")
_AI = re.compile(r"(?i)(ai assistant|ai bot|automated|virtual assistant|chatbot|i am a bot)")


def check(text: str) -> dict:
    findings = []

    def add(code, severity, title, why, fix):
        findings.append({"code": code, "severity": severity, "title": title, "why": why, "fix": fix})

    fields = pii.extract(text)
    has_notice = bool(_NOTICE.search(text)); has_ask = bool(_CONSENT_ASK.search(text)); bundled = bool(_BUNDLED.search(text))
    if not has_notice:
        add("NO_NOTICE", "high", "No privacy notice before data collection", "Rule 3 requires an itemised notice before consent.", "Show what data, for which purposes, how to withdraw, before the bot asks anything.")
    if not has_ask or bundled:
        add("NO_EXPLICIT_CONSENT" if not has_ask else "BUNDLED_CONSENT", "high",
            "No explicit opt-in" if not has_ask else "Consent bundled into terms / implied by continuing",
            "Consent must be a clear affirmative action, specific per purpose (s.6).", "Ask a separate yes/no per purpose (e.g. order updates vs marketing) and store the answer.")
    if _MARKETING.search(text) and not re.search(r"(?i)marketing.{0,80}(separate|optional|agree|opt)", text) and has_ask:
        add("MARKETING_NOT_SEPARATE", "medium", "Marketing not clearly separated from service consent", "Bundling marketing with transactional consent is a common violation.", "Make marketing a separate, optional opt-in.")
    if not _ERASE_PATH.search(text):
        add("NO_ERASURE_PATH", "high", "No way to withdraw consent or request erasure", "Rule 14 / s.6(4): withdrawing must be as easy as giving consent.", "Tell users they can say 'stop' or 'delete my data' and handle it.")
    if fields:
        kinds = sorted({f.kind for f in fields})
        add("UNMASKED_PII", "medium", f"Raw personal data appears in the transcript ({', '.join(kinds)})", "Rule 6 expects masking/access control on stored logs.", "Mask PII before transcripts reach logs; restrict who can read them.")
    if any(f.kind in ("aadhaar", "pan") for f in fields):
        add("GOVT_ID", "high", "Government ID numbers collected in chat", "High-risk data; collect only if essential.", "Avoid collecting Aadhaar/PAN in chat; redirect to a secure form.")
    if not _PURPOSE.search(text):
        add("NO_PURPOSE", "medium", "Purpose of collection not stated", "Data must be tied to a stated purpose (purpose limitation).", "State why each field is collected.")
    if not _RETENTION.search(text):
        add("NO_RETENTION", "low", "No retention period mentioned", "Data must be erased once the purpose is served (Rule 8).", "Set expiries per field and tell users.")
    if re.search(r"(?i)\b(class|grade|std)\s*\d|school|student|exam|under 18|\bage\b", text):
        add("MINOR_SIGNALS", "medium", "Conversation suggests minors may use this bot", "Rules 10-12 need verifiable parental consent under 18.", "Detect likely minors and route to a parental-consent flow.")
    if not _AI.search(text):
        add("NO_AI_DISCLOSURE", "info", "Bot does not say it is automated", "Not a DPDP requirement, but good practice and required in some jurisdictions.", "Disclose that users are talking to an AI.")
    sev = {"high": 3, "medium": 2, "low": 1, "info": 0}
    score = max(0, 100 - sum({3: 20, 2: 10, 1: 5, 0: 0}[sev[f["severity"]]] for f in findings))
    return {"score": score, "findings": sorted(findings, key=lambda f: -sev[f["severity"]]),
            "disclaimer": "Heuristic checker, not legal advice. Absence of a finding does not mean compliance."}
