import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "voice_webhook"))
from fastapi.testclient import TestClient
from dpdp_guard import Guard, LocalStore, VoiceGuard
import importlib.util
spec = importlib.util.spec_from_file_location("voice_app", pathlib.Path(__file__).parent.parent / "voice_webhook" / "app.py")
va = importlib.util.module_from_spec(spec); spec.loader.exec_module(va)

def client(secret="s3"):
    return TestClient(va.create_app(VoiceGuard(Guard("t", "Acme", ["order_updates"], store=LocalStore())), secret))

def test_requires_secret_and_fails_closed_when_unset():
    assert client().post("/voice", json={"user_id": "u"}).status_code == 403
    assert client().post("/voice", json={"user_id": "u"}, headers={"X-Voice-Secret": "wrong"}).status_code == 403
    assert client(secret=None).post("/voice", json={"user_id": "u"}, headers={"X-Voice-Secret": ""}).status_code == 403

def test_call_flow_over_http():
    c, h = client(), {"X-Voice-Secret": "s3"}
    r = c.post("/voice", json={"user_id": "u", "speech": "hello"}, headers=h).json()
    assert r["action"] == "say" and "Acme" in r["say"]
    assert "saved" in c.post("/voice", json={"user_id": "u", "digits": "1"}, headers=h).json()["say"]
    r = c.post("/voice", json={"user_id": "u", "speech": "book me for tomorrow"}, headers=h).json()
    assert r["action"] == "forward" and r["agent_text"] == "book me for tomorrow"
