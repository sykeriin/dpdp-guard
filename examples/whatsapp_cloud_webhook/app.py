"""WhatsApp Cloud API webhook with DPDP Guard in front of your agent.
Consent is asked inside the 24h service window the user opened, so notices cost nothing (replies in-window are free)."""
import os

import httpx
from fastapi import FastAPI, Request, Response
from dpdp_guard import Guard, HttpStore

VERIFY_TOKEN = os.environ.get("WA_VERIFY_TOKEN", "change-me")
WA_TOKEN, WA_PHONE_ID = os.environ.get("WA_TOKEN"), os.environ.get("WA_PHONE_NUMBER_ID")

guard = Guard(tenant=os.environ.get("GUARD_TENANT", "demo"), business="Acme Store",
              required_purposes=["order_updates"], optional_purposes=["marketing"],
              store=HttpStore(os.environ.get("GUARD_URL", "http://localhost:8000"), os.environ.get("GUARD_API_KEY", "")))
sent: list[tuple[str, str]] = []   # test hook


def send(to: str, text: str):
    sent.append((to, text))
    if WA_TOKEN:
        httpx.post(f"https://graph.facebook.com/v20.0/{WA_PHONE_ID}/messages", headers={"Authorization": f"Bearer {WA_TOKEN}"},
                   json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}, timeout=10)


def my_agent(text: str) -> str:   # replace with LangGraph / n8n / your LLM agent
    return f"(agent) got: {text[:60]}"


app = FastAPI()


@app.get("/webhook")
def verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == VERIFY_TOKEN:
        return Response(q.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


@app.post("/webhook")
async def inbound(request: Request):
    body = await request.json()
    for entry in body.get("entry", []):
        for ch in entry.get("changes", []):
            for m in ch.get("value", {}).get("messages", []):
                text = m.get("text", {}).get("body") or m.get("interactive", {}).get("button_reply", {}).get("id", "")
                r = guard(text, m["from"], "whatsapp")
                send(m["from"], my_agent(r.message) if r.action == "forward" else r.reply_text)
    return {"ok": True}
