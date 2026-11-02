"""End-to-end: live ledger server + simulated WhatsApp conversation -> consent -> PII -> erasure -> proof -> audit pack.
Usage: GUARD_URL=http://localhost:8000 ADMIN_TOKEN=adm python examples/e2e_demo.py"""
import io, os, sys, uuid, zipfile
import httpx
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "whatsapp_cloud_webhook"))
URL, ADMIN = os.environ.get("GUARD_URL", "http://localhost:8000"), os.environ.get("ADMIN_TOKEN", "adm")
tid = "demo_" + uuid.uuid4().hex[:6]
key = httpx.post(f"{URL}/admin/tenants", json={"id": tid, "name": "Demo"}, headers={"X-Admin-Token": ADMIN}).json()["api_key"]
os.environ.update(GUARD_URL=URL, GUARD_API_KEY=key, GUARD_TENANT=tid)
from fastapi.testclient import TestClient
import app as wa
c = TestClient(wa.app)
api = httpx.Client(base_url=URL, headers={"Authorization": f"Bearer {key}"})

def say(text, who="919876543210"):
    c.post("/webhook", json={"entry": [{"changes": [{"value": {"messages": [{"from": who, "text": {"body": text}}]}}]}]})
    print(f"  user: {text}\n  bot : {wa.sent[-1][1].splitlines()[0]}{' ...' if len(wa.sent[-1][1].splitlines())>1 else ''}")
    return wa.sent[-1][1]

print("1) first contact -> notice, agent never sees the message"); say("hi")
print("2) per-purpose consent (order updates yes, marketing no)"); say("1")
print("3) PII flows to agent, masked in the ledger"); say("my number is 9876543210, deliver to 560001")
pid = wa.guard.pid("919876543210")
api.post("/v1/transcripts", json={"principal": pid, "role": "user", "text": "my number is [PHONE:********10]"})
print("4) 'meri details hatao' -> rights request"); say("meri details hatao")
ref = [r for r in api.get("/v1/rights-requests").json() if r["kind"] == "erasure"][0]["ref"]
api.post(f"/v1/rights-requests/{ref}/execute"); print("5) erasure executed:", api.post("/v1/workers/run").json())
job = api.get("/v1/erasure").json()[0]; print("   job:", job["status"], [(r["kind"], r.get("deleted")) for r in job["results"]])
print("6) ledger verify:", api.get("/v1/ledger/verify").json())
z = zipfile.ZipFile(io.BytesIO(api.get("/v1/audit-pack", params={"business": "Acme Store"}).content)); print("7) audit pack:", z.namelist())
assert job["status"] == "done"; print("OK")
