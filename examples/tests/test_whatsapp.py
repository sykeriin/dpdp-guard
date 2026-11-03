import hashlib, hmac, json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "whatsapp_cloud_webhook"))
from fastapi.testclient import TestClient
from dpdp_guard import Guard, LocalStore
from app import create_app

SECRET = "s3cret"

def make():
    sent, calls = [], []
    g = Guard("t", "Acme", ["order_updates"], ["marketing"], store=LocalStore())
    app = create_app(g, lambda to, text: sent.append((to, text)), lambda m: calls.append(m) or "agent-reply", SECRET)
    return TestClient(app), sent, calls, g

def post(c, text, mid, secret=SECRET, sign=True):
    body = json.dumps({"entry": [{"changes": [{"value": {"messages": [{"id": mid, "from": "9199", "text": {"body": text}}]}}]}]}).encode()
    h = {"X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()} if sign else {}
    return c.post("/webhook", content=body, headers=h)

def test_bad_or_missing_signature_rejected_and_nothing_processed():
    c, sent, calls, g = make()
    assert post(c, "hi", "m1", secret="wrong").status_code == 403
    assert post(c, "hi", "m2", sign=False).status_code == 403
    assert sent == [] and g.store.events("t") == []

def test_unconfigured_secret_fails_closed():
    g = Guard("t", "Acme", ["order_updates"], store=LocalStore())
    c = TestClient(create_app(g, lambda *a: None, lambda m: "", app_secret=None))
    assert post(c, "hi", "m1").status_code == 403

def test_duplicate_delivery_processed_once():
    c, sent, calls, g = make()
    assert post(c, "hi", "m1").status_code == 200
    assert post(c, "1", "m2").status_code == 200
    n = len(g.store.events("t"))
    assert post(c, "1", "m2").status_code == 200                # Meta retry of the same message id
    assert len(g.store.events("t")) == n and len(sent) == 2     # no second consent record, no second reply

def test_full_flow_agent_only_after_consent():
    c, sent, calls, g = make()
    post(c, "hi", "a"); assert calls == []                       # agent never sees pre-consent text
    post(c, "1", "b"); post(c, "my number 9876543210", "c")
    assert calls == ["my number 9876543210"] and sent[-1][1] == "agent-reply"

def test_verify_handshake():
    c, *_ = make()
    assert c.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "change-me", "hub.challenge": "42"}).text == "42"
    assert c.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "bad", "hub.challenge": "42"}).status_code == 403
