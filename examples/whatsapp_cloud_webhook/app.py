"""WhatsApp Cloud API webhook with DPDP Guard in front of your agent.
Consent is asked inside the 24h service window the user opened, so notices cost nothing (in-window replies are free).

Safety: verifies Meta's X-Hub-Signature-256 and de-duplicates by message id (Meta retries deliveries).
Dedupe here is in-memory + single process; use Redis or a DB unique key if you run several workers."""
import hashlib
import hmac
import os
from collections import OrderedDict

import httpx
from fastapi import FastAPI, Request, Response
from dpdp_guard import Guard, HttpStore


def create_app(guard, send, agent, app_secret: str | None, verify_token: str = "change-me", dedupe_size: int = 10_000) -> FastAPI:
    app = FastAPI()
    seen: OrderedDict[str, None] = OrderedDict()

    def valid_sig(body: bytes, header: str) -> bool:
        if not app_secret:
            return False   # fail closed: refuse unsigned traffic unless explicitly configured
        want = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(want, header or "")

    @app.get("/webhook")
    def verify(request: Request):
        q = request.query_params
        if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == verify_token:
            return Response(q.get("hub.challenge", ""), media_type="text/plain")
        return Response(status_code=403)

    @app.post("/webhook")
    async def inbound(request: Request):
        raw = await request.body()
        if not valid_sig(raw, request.headers.get("X-Hub-Signature-256", "")):
            return Response(status_code=403)
        body = await request.json()
        for entry in body.get("entry", []):
            for ch in entry.get("changes", []):
                for m in ch.get("value", {}).get("messages", []):
                    mid = m.get("id")
                    if mid:
                        if mid in seen:
                            continue                      # retry of a message we already handled
                        seen[mid] = None
                        if len(seen) > dedupe_size:
                            seen.popitem(last=False)
                    text = m.get("text", {}).get("body") or m.get("interactive", {}).get("button_reply", {}).get("id", "")
                    r = guard(text, m["from"], "whatsapp")
                    send(m["from"], agent(r.message) if r.action == "forward" else r.reply_text)
                    for n in r.notify:                    # e.g. guardian invite. NOTE: outside a 24h window this needs an approved template
                        send(n["to"], n["text"])
        return {"ok": True}

    return app


def _wa_sender():
    token, phone_id = os.environ.get("WA_TOKEN"), os.environ.get("WA_PHONE_NUMBER_ID")
    sent: list[tuple[str, str]] = []

    def send(to: str, text: str):
        sent.append((to, text))
        if token:
            httpx.post(f"https://graph.facebook.com/v20.0/{phone_id}/messages", headers={"Authorization": f"Bearer {token}"},
                       json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}, timeout=10)
    send.sent = sent
    return send


def my_agent(text: str) -> str:   # replace with LangGraph / n8n / your LLM agent
    return f"(agent) got: {text[:60]}"


guard = Guard(tenant=os.environ.get("GUARD_TENANT", "demo"), business=os.environ.get("BUSINESS", "Acme Store"),
              required_purposes=["order_updates"], optional_purposes=["marketing"],
              store=HttpStore(os.environ.get("GUARD_URL", "http://localhost:8000"), os.environ.get("GUARD_API_KEY", "")))
send = _wa_sender()
sent = send.sent   # kept for the demo/test hook
app = create_app(guard, send, my_agent, os.environ.get("WA_APP_SECRET"), os.environ.get("WA_VERIFY_TOKEN", "change-me"))
