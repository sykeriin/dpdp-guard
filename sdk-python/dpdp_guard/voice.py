"""Voice channel adapter (call bots). Spoken / keypad consent, one purpose at a time, then hands off to Guard.

Scope and limits (read before relying on it):
  * It maps ASR text + DTMF digits onto the same consent/rights/PII logic as chat. It has been tested ONLY with simulated inputs,
    never with a telephony provider, a real ASR, or a real call.
  * Spoken consent is only as good as your ASR: if you can't prove a caller said "yes", press-1 (DTMF) is the stronger evidence.
  * Call RECORDINGS and raw transcripts are personal data too (audio contains voice, names, numbers). This adapter never stores
    audio; if your telephony stack records, that recording needs its own notice, retention and erasure. Not solved here.
  * Guardian/minor flow is text-based (the invite goes out via GuardResult.notify); no voice version.
"""
import re
from dataclasses import dataclass, field

from . import intent as intent_mod, notices
from .guard import Guard

_YES_EN = re.compile(r"(?i)\b(yes|yeah|yep|yup|ok|okay|sure|agree|i agree|haan|han|ha|hanji|ji haan)\b")
_NO_EN = re.compile(r"(?i)\b(no|nope|nah|nahi|nahin|na|decline|disagree|don'?t)\b")
_YES_HI, _NO_HI = re.compile(r"हाँ|हां|जी हाँ|जी हां|ठीक है|सहमत"), re.compile(r"नहीं|नही|मना")


@dataclass
class VoiceResult:
    action: str                       # "say" = speak `say` then wait for next input | "forward" = give agent_text to your agent | "end" = speak then hang up
    say: str = ""
    agent_text: str = ""              # raw transcript for the agent (only when action == "forward")
    masked_text: str = ""             # safe to log
    notify: list = field(default_factory=list)
    rights_ref: str | None = None


def parse_answer(speech: str = "", digits: str = "") -> bool | None:
    """True/False for a clear answer, None if unclear or contradictory. Digits win over speech (stronger evidence)."""
    d = (digits or "").strip()
    if d in ("1", "2"):
        return d == "1"
    t = speech or ""
    yes = bool(_YES_EN.search(t) or _YES_HI.search(t)); no = bool(_NO_EN.search(t) or _NO_HI.search(t))
    return True if yes and not no else False if no and not yes else None


class VoiceGuard:
    def __init__(self, guard: Guard, channel: str = "voice"):
        self.g, self.channel = guard, channel

    # state lives in the guard's store, so a dropped call resumes where it stopped
    def _st(self, pid, key, default=None): return self.g.store.get_state(self.g.tenant, pid, key, default)
    def _set(self, pid, key, val): self.g.store.set_state(self.g.tenant, pid, key, val)

    def _ask(self, idx, lang, prefix=""):
        p = self.g.purposes[idx]
        label = self.g.cfg["purposes"][p].get(lang) or self.g.cfg["purposes"][p]["en"]
        return (prefix + " " if prefix else "") + notices.render("voice_ask", lang, self.g.cfg, purpose=label)

    def handle(self, user_id: str, speech: str = "", digits: str = "") -> VoiceResult:
        g = self.g; pid = g._pid(user_id)
        lang = notices.lang_of(speech or "", self._st(pid, "lang", g.default_lang)); self._set(pid, "lang", lang)
        mid_flow = self._st(pid, "voice_i") is not None
        has_consent = bool(g.store.consent_state(g.tenant, pid))

        # rights are honoured at any point, even mid-consent: never trap a caller in the consent menu
        if speech and intent_mod.classify(speech, g.use_llm, g.llm_client):
            return self._from_guard(g.process(speech, user_id, self.channel))

        if has_consent and not mid_flow:
            return self._from_guard(g.process(speech or digits, user_id, self.channel))

        if not mid_flow:                                           # first contact: intro + first purpose
            self._set(pid, "voice_i", 0); self._set(pid, "voice_ans", {})
            g.store.append_event(g.tenant, "voice_notice_played", pid, {"notice_version": g.cfg["version"], "purposes": g.purposes})
            return VoiceResult("say", self._ask(0, lang, notices.render("voice_intro", lang, g.cfg, business=g.business)))

        i, answers = self._st(pid, "voice_i"), dict(self._st(pid, "voice_ans", {}))
        ans = parse_answer(speech, digits)
        if ans is None:                                            # unclear: repeat, record nothing
            return VoiceResult("say", self._ask(i, lang, notices.render("voice_repeat", lang, g.cfg)))
        answers[g.purposes[i]] = [ans, "voice-dtmf" if (digits or "").strip() in ("1", "2") else "voice-speech"]   # method recorded PER ANSWER
        if i + 1 < len(g.purposes):
            self._set(pid, "voice_i", i + 1); self._set(pid, "voice_ans", answers)
            return VoiceResult("say", self._ask(i + 1, lang))
        for p, (a, method) in answers.items():                     # all asked: record per-purpose consents against the ledger
            g.store.record_consent(g.tenant, pid, p, a, method, g.cfg["version"])
        self._set(pid, "voice_i", None); self._set(pid, "voice_ans", {})
        if all(answers.get(r, [False])[0] for r in g.required):
            return VoiceResult("say", notices.render("voice_done", lang, g.cfg))
        return VoiceResult("end", notices.render("consent_declined", lang, g.cfg))

    def _from_guard(self, r) -> VoiceResult:
        if r.action == "forward":
            return VoiceResult("forward", agent_text=r.message, masked_text=r.masked_message, notify=r.notify)
        return VoiceResult("end" if r.action == "block" else "say", r.reply_text, masked_text=r.masked_message, notify=r.notify, rights_ref=r.rights_ref)
