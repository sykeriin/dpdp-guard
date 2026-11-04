"""Generic voice-bot webhook: your telephony/ASR layer POSTs {user_id, speech, digits}; we return what to say or what to give your agent.
Not tied to any provider (Twilio, Exotel, Plivo, ...): map their webhook fields onto this JSON in a thin shim.
UNTESTED against a real telephony provider or ASR. Call recordings are personal data: see dpdp_guard/voice.py docstring."""
import hmac
import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from dpdp_guard import Guard, HttpStore, VoiceGuard


class TurnIn(BaseModel):
    user_id: str          # caller's number / id as your telephony layer reports it
    speech: str = ""      # ASR transcript of the last utterance
    digits: str = ""      # DTMF digits pressed


def create_app(voice: VoiceGuard, secret: str | None) -> FastAPI:
    app = FastAPI()

    @app.post("/voice")
    def turn(b: TurnIn, x_voice_secret: str = Header(default="")):
        if not secret or not hmac.compare_digest(x_voice_secret, secret):     # fail closed: no secret configured = no traffic
            raise HTTPException(403, "bad or missing secret")
        r = voice.handle(b.user_id, b.speech, b.digits)
        return {"action": r.action, "say": r.say, "agent_text": r.agent_text, "notify": r.notify, "rights_ref": r.rights_ref}

    return app


if os.environ.get("GUARD_API_KEY"):      # only build the live app when configured (keeps imports in tests side-effect free)
    app = create_app(VoiceGuard(Guard(os.environ.get("GUARD_TENANT", "demo"), os.environ.get("BUSINESS", "Acme"), ["order_updates"], ["marketing"],
                                      store=HttpStore(os.environ.get("GUARD_URL", "http://localhost:8000"), os.environ["GUARD_API_KEY"]))),
                     os.environ.get("VOICE_SECRET"))
