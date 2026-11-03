"""guard(message, user_id, channel) - runs before the agent.

Flow per message:
  1. rights intent (always honoured, even before consent)
  2. likely-minor -> parental consent flow (Rules 10-12), blocked
  3. no consent decision yet -> itemised notice, per-purpose opt-in
  4. notice pending -> parse reply, record per-purpose consent
  5. required purposes not granted -> block; else forward (raw message for the agent, masked copy for logs)
"""
import re
from dataclasses import dataclass, field

from . import intent as intent_mod, minors, notices, pii as pii_mod
from .chain import hash_principal
from .store import LocalStore

_YES = re.compile(r"(?i)^\s*(y|yes|yep|ok|okay|haan|han|ha|hanji|ji|sure|agree|i agree|हाँ|हां|जी)\s*[.!]*\s*$")
# Messages that look privacy-related but matched no rights intent: queued for a human instead of silently passing.
# Deliberately broad (some benign hits, e.g. "data plans"); a missed erasure request is worse than a skimmed ticket.
_REVIEW = re.compile(r"(?i)\b(?:data|personal (?:info|information|details)|privacy|consent|permission|gdpr|dpdp|delete|erase|erasure|forget me|unsubscribe|opt[- ]?out|"
                     r"stored|saved|records?|hatao|hata|mita|jaankari|sahmati)\b|डेटा|जानकारी|सहमति|गोपनीयता|हटा|मिटा")
_NO = re.compile(r"(?i)^\s*(n|no|nope|none|nahi|nahin|na|decline|disagree|नहीं|नही)\s*[.!]*\s*$")


@dataclass
class GuardResult:
    action: str                      # forward | reply | block
    message: str = ""                # original message (what the agent should see) - only meaningful when action == forward
    masked_message: str = ""         # safe for logs/transcripts
    reply_text: str = ""             # send this to the user when action != forward
    intent: str | None = None
    pii: list = field(default_factory=list)
    granted: list = field(default_factory=list)
    rights_ref: str | None = None
    notify: list = field(default_factory=list)   # [{'to': <raw id>, 'text': ...}] extra messages YOU must deliver (e.g. guardian invite)
    review_ref: str | None = None    # privacy-looking message with no recognised intent: a 'review' ticket was opened for a human
    error: str | None = None         # set when the guard failed (fail_mode decides forward vs block)


class Guard:
    def __init__(self, tenant: str, business: str, required_purposes: list[str], optional_purposes: list[str] | None = None,
                 store=None, privacy_url: str = "https://example.com/privacy", notice_cfg: dict | None = None,
                 use_llm: bool = False, llm_client=None, salt: str = "", default_lang: str = "en", log_transcripts: bool = True,
                 fail_mode: str = "closed"):
        self.tenant, self.business = tenant, business
        self.required = list(required_purposes)
        self.optional = list(optional_purposes or [])
        self.purposes = self.required + self.optional
        self.store = store or LocalStore()
        self.privacy_url = privacy_url
        self.cfg = notice_cfg or notices.load()
        self.use_llm, self.llm_client, self.salt, self.default_lang = use_llm, llm_client, salt, default_lang
        self.log_transcripts = log_transcripts
        assert fail_mode in ("closed", "open"), "fail_mode must be 'closed' or 'open'"
        self.fail_mode = fail_mode

    # -- helpers
    @staticmethod
    def _norm(user_id: str) -> str:
        """+91 98765 43210, 919876543210 and 9876543210 are the same person."""
        if re.fullmatch(r"\+?[\d ()-]{10,16}", user_id):
            return re.sub(r"\D", "", user_id)[-10:]
        return user_id

    def _pid(self, user_id):
        return hash_principal(self.tenant, self._norm(user_id), self.salt)

    def pid(self, user_id):
        """Principal hash. Tag records in your own stores (CRM, vector DB) with this so erasure can find them."""
        return self._pid(user_id)

    def _lang(self, pid, text):
        l = notices.lang_of(text, self.store.get_state(self.tenant, pid, "lang", self.default_lang))
        self.store.set_state(self.tenant, pid, "lang", l)
        return l

    def _notice(self, lang):
        return notices.notice(self.purposes, self.business, self.privacy_url, lang, self.cfg)

    def _parse_consent(self, text: str):
        """Return dict purpose->bool or None if unparseable. Never infers consent from silence or unrelated text."""
        t = text.strip()
        n = len(self.purposes)
        if _NO.match(t):
            return {p: False for p in self.purposes}
        if _YES.match(t):
            # a bare "yes" to a multi-purpose notice is NOT specific consent; ask again
            return {self.purposes[0]: True} if n == 1 else None
        nums = re.findall(r"\d+", t)
        if nums and re.fullmatch(r"[\d\s,&andऔर+]*", t, re.I):
            chosen = {int(x) for x in nums if 1 <= int(x) <= n}
            if not chosen:
                return None
            return {p: (i + 1) in chosen for i, p in enumerate(self.purposes)}
        # "yes to order updates" style
        named = {}
        for p in self.purposes:
            label = p.replace("_", " ")
            if re.search(rf"(?i)\b(yes|haan|agree)\b.{{0,15}}\b{re.escape(label)}\b", t):
                named[p] = True
        if named:
            return {p: named.get(p, False) for p in self.purposes}
        return None

    # -- main
    def __call__(self, message: str, user_id: str, channel: str = "web") -> GuardResult:
        return self.process(message, user_id, channel)

    def process(self, message: str, user_id: str, channel: str = "web") -> GuardResult:
        try:
            res = self._process(message, user_id, channel)
            if res.intent is None and _REVIEW.search(message):
                res.review_ref = self.store.create_rights_request(self.tenant, self._pid(user_id), "review", res.masked_message)
            if self.log_transcripts and hasattr(self.store, "log_transcript"):
                pid = self._pid(user_id)
                self.store.log_transcript(self.tenant, pid, "user", res.masked_message)   # masked only: raw PII never reaches logs
                if res.action != "forward" and res.reply_text:
                    self.store.log_transcript(self.tenant, pid, "bot", res.reply_text)
            return res
        except Exception as e:  # store/ledger unreachable or buggy
            if self.fail_mode == "open":
                # explicit opt-in: the agent sees the message UNLOGGED and without a consent check
                return GuardResult("forward", message=message, masked_message=pii_mod.mask(message), error=repr(e))
            return GuardResult("block", masked_message=pii_mod.mask(message), error=repr(e),
                               reply_text="Sorry, we can't process your message right now. Please try again in a few minutes.")

    def _process(self, message: str, user_id: str, channel: str = "web") -> GuardResult:
        s, t = self.store, self.tenant
        pid = self._pid(user_id)
        lang = self._lang(pid, message)
        fields = pii_mod.extract(message)
        masked = pii_mod.mask(message, fields)

        # 1. rights
        it = intent_mod.classify(message, self.use_llm, self.llm_client)
        if it:
            ref = s.create_rights_request(t, pid, it, masked)
            key = {"erasure": "erasure_ack", "access": "access_ack", "correction": "correction_ack",
                   "grievance": "grievance_ack", "withdraw": "withdraw_ack", "stop": "withdraw_ack"}[it]
            if it in ("withdraw", "stop", "erasure"):
                targets = self.optional if it == "stop" and self.optional else self.purposes
                for p in targets:
                    if s.consent_state(t, pid).get(p):
                        s.record_consent(t, pid, p, False, channel, self.cfg["version"])
            return GuardResult("reply", masked_message=masked, reply_text=notices.render(key, lang, self.cfg, ref=ref), intent=it, rights_ref=ref)

        # 2a. this sender is a guardian answering a pending request
        minor_pid = s.get_state(t, pid, "guardian_for", None)
        if minor_pid:
            return self._guardian_reply(message, pid, minor_pid, lang, masked, channel)

        # 2b. minors (Rules 10-12): detection -> guardian consent -> only then the normal flow
        stage = s.get_state(t, pid, "guardian_stage", None)
        if not s.get_state(t, pid, "parental_ok", False):
            if stage == "declined":
                return GuardResult("block", masked_message=masked, reply_text=notices.render("guardian_declined_minor", lang, self.cfg))
            if stage == "awaiting_guardian":
                return GuardResult("block", masked_message=masked, reply_text=notices.render("guardian_waiting", lang, self.cfg))
            if stage == "awaiting_number" or minors.likely_minor(message):
                return self._guardian_request(message, pid, stage, lang, masked, channel)

        state = s.consent_state(t, pid)

        # 3. first contact -> notice
        if not state and not s.get_state(t, pid, "notice_pending", False):
            s.set_state(t, pid, "notice_pending", True)
            s.append_event(t, "notice_shown", pid, {"channel": channel, "notice_version": self.cfg["version"], "purposes": self.purposes})
            return GuardResult("reply", masked_message=masked, reply_text=self._notice(lang))

        # 4. reply to notice
        if s.get_state(t, pid, "notice_pending", False):
            parsed = self._parse_consent(message)
            if parsed is None:
                return GuardResult("reply", masked_message=masked, reply_text=self._notice(lang))
            for p, g in parsed.items():
                s.record_consent(t, pid, p, g, channel, self.cfg["version"])
            s.set_state(t, pid, "notice_pending", False)
            granted = [p for p, g in parsed.items() if g]
            if all(r in granted for r in self.required):
                txt = notices.render("consent_recorded", lang, self.cfg, granted=", ".join(granted))
            else:
                txt = notices.render("consent_declined", lang, self.cfg)
            return GuardResult("reply", masked_message=masked, reply_text=txt, granted=granted)

        # 5. required purposes
        if not all(state.get(r) for r in self.required):
            return GuardResult("block", masked_message=masked, reply_text=notices.render("consent_declined", lang, self.cfg))

        # forward: register PII under the primary required purpose
        purpose = self.required[0]
        for f in fields:
            f.purpose = purpose
            s.record_pii(t, pid, f.kind, purpose, pii_mod.mask_value(f.kind, f.value), self._retention(purpose, f.retention_days))
        s.append_event(t, "message_forwarded", pid, {"channel": channel, "masked": masked})
        return GuardResult("forward", message=message, masked_message=masked, pii=[f.public() for f in fields],
                           granted=[p for p, g in state.items() if g])

    def _guardian_request(self, message, pid, stage, lang, masked, channel):
        s, t = self.store, self.tenant
        if stage != "awaiting_number":
            s.append_event(t, "minor_signal", pid, {"channel": channel})
            s.set_state(t, pid, "guardian_stage", "awaiting_number")
            return GuardResult("block", masked_message=masked, reply_text=notices.render("guardian_ask_number", lang, self.cfg))
        phones = [f for f in pii_mod.extract(message) if f.kind == "phone"]
        if not phones:
            return GuardResult("block", masked_message=masked, reply_text=notices.render("guardian_ask_number", lang, self.cfg))
        raw = phones[0].value
        gpid = self._pid(raw)
        if gpid == pid:
            return GuardResult("block", masked_message=masked, reply_text=notices.render("guardian_need_other", lang, self.cfg))
        s.set_state(t, gpid, "guardian_for", pid)
        s.set_state(t, pid, "guardian_stage", "awaiting_guardian")
        s.append_event(t, "guardian_requested", pid, {"guardian": gpid, "channel": channel})   # hashes only; raw number is not stored
        invite = notices.render("guardian_invite", lang, self.cfg, business=self.business,
                                purpose_lines=notices.purpose_lines(self.purposes, lang, self.cfg), privacy_url=self.privacy_url)
        return GuardResult("block", masked_message=masked, reply_text=notices.render("guardian_waiting", lang, self.cfg),
                           notify=[{"to": re.sub(r"\D", "", raw), "text": invite}])

    def _guardian_reply(self, message, gpid, minor_pid, lang, masked, channel):
        s, t = self.store, self.tenant
        parsed = self._parse_consent(message)
        if parsed is None:
            invite = notices.render("guardian_invite", lang, self.cfg, business=self.business,
                                    purpose_lines=notices.purpose_lines(self.purposes, lang, self.cfg), privacy_url=self.privacy_url)
            return GuardResult("reply", masked_message=masked, reply_text=invite)
        for p, g in parsed.items():
            s.record_consent(t, minor_pid, p, g, "guardian", self.cfg["version"])     # recorded against the CHILD's principal
        granted = [p for p, g in parsed.items() if g]
        ok = all(r in granted for r in self.required)
        s.append_event(t, "parental_consent_granted" if ok else "parental_consent_declined", minor_pid,
                       {"guardian": gpid, "purposes": granted, "verification": "self-asserted-number"})
        s.set_state(t, minor_pid, "parental_ok", ok)
        s.set_state(t, minor_pid, "guardian_stage", "approved" if ok else "declined")
        s.set_state(t, gpid, "guardian_for", None)
        return GuardResult("reply", masked_message=masked, granted=granted,
                           reply_text=notices.render("guardian_recorded", lang, self.cfg, granted=", ".join(granted) or "none"))

    def _retention(self, purpose, default):
        return min(default, self.cfg["purposes"].get(purpose, {}).get("retention_days", default))
