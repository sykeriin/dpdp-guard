import io, json, zipfile
import psycopg, pytest
from dpdp_guard import Guard, HttpStore
from app import db, workers

def test_auth_required(tenant):
    _, c = tenant
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).get("/v1/consents").status_code == 401

def test_admin_required():
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).post("/admin/tenants", json={"id": "x", "name": "x"}).status_code == 403

def test_tenant_isolation_rls(tenant):
    tid, c = tenant
    c.post("/v1/consents", json={"principal": "p1", "purpose": "a", "granted": True})
    # raw query as app role with the WRONG tenant set must see nothing
    with db.tenant_cur("someone_else") as cur:
        cur.execute("select count(*) n from consents where principal='p1'"); assert cur.fetchone()["n"] == 0
    # and with no tenant set at all
    with db.raw_cur() as cur:
        cur.execute("select count(*) n from consents"); assert cur.fetchone()["n"] == 0

def test_events_append_only_even_for_owner(tenant):
    tid, c = tenant
    c.post("/v1/events", json={"type": "x"})
    for sql in ("update events set type='y'", "delete from events", "truncate events"):
        with pytest.raises(psycopg.errors.Error):
            with psycopg.connect(db.ADMIN_URL, autocommit=True) as conn: conn.execute(sql)

def test_chain_verify_and_tamper(tenant):
    tid, c = tenant
    for i in range(5): c.post("/v1/events", json={"type": f"e{i}", "payload": {"i": i}})
    assert c.get("/v1/ledger/verify").json()["ok"]
    # an attacker with owner access disables the trigger and edits history
    with psycopg.connect(db.ADMIN_URL, autocommit=True) as conn:
        conn.execute("alter table events disable trigger events_no_update")
        conn.execute("update events set event = jsonb_set(event,'{type}','\"forged\"') where tenant_id=%s and event->>'type'='e2'", (tid,))
        conn.execute("alter table events enable trigger events_no_update")
    r = c.get("/v1/ledger/verify").json()
    assert not r["ok"] and r["first_bad_index"] == 2

def test_guard_over_http_end_to_end(tenant):
    tid, c = tenant
    g = Guard(tid, "Acme", ["order_updates"], ["marketing"], store=HttpStore("", "", client=c))
    assert g("hi", "u1", "whatsapp").action == "reply"
    assert g("1", "u1").granted == ["order_updates"]
    r = g("call me on 9876543210", "u1")
    assert r.action == "forward" and "9876543210" not in r.masked_message
    pid = g.pid("u1")
    assert c.get("/v1/consents/state", params={"principal": pid}).json() == {"order_updates": True, "marketing": False}
    assert c.get(f"/v1/principals/{pid}/export").json()["personal_data"][0]["masked"].endswith("10")
    assert c.get("/v1/ledger/verify").json()["ok"]

def test_erasure_flow_with_sql_and_transcripts(tenant):
    tid, c = tenant
    pid = "pidX"
    with psycopg.connect(db.ADMIN_URL, autocommit=True) as conn:   # stand-in for customer's vector table (plain table, no pgvector ext)
        conn.execute("create table if not exists cust_vectors(id serial, principal text, body text)")
        conn.execute("insert into cust_vectors(principal, body) values (%s,'a'),(%s,'b'),('other','c')", (pid, pid))
    c.post("/v1/connectors", json={"kind": "pgvector", "name": "kb", "config": {"dsn": db.ADMIN_URL, "table": "cust_vectors", "column": "principal"}})
    c.post("/v1/transcripts", json={"principal": pid, "role": "user", "text": "hello"})
    c.post("/v1/pii", json={"principal": pid, "kind": "phone", "purpose": "support", "masked": "***10", "retention_days": 30})
    ref = c.post("/v1/rights-requests", json={"principal": pid, "kind": "erasure"}).json()["ref"]
    assert c.post(f"/v1/rights-requests/{ref}/execute").json()["job"]
    assert c.post("/v1/workers/run").json()["erasure_done"] == 1
    with psycopg.connect(db.ADMIN_URL) as conn:
        assert conn.execute("select count(*) from cust_vectors where principal=%s", (pid,)).fetchone()[0] == 0
        assert conn.execute("select count(*) from cust_vectors").fetchone()[0] >= 1      # others untouched
    with db.tenant_cur(tid) as cur:
        cur.execute("select count(*) n from transcripts where principal=%s", (pid,)); assert cur.fetchone()["n"] == 0
        cur.execute("select count(*) n from events where type='erasure_proof'"); assert cur.fetchone()["n"] == 1
    assert [r for r in c.get("/v1/rights-requests").json() if r["ref"] == ref][0]["status"] == "fulfilled"
    job = c.get("/v1/erasure").json()[0]
    assert job["status"] == "done" and {r["kind"] for r in job["results"]} == {"transcripts", "pgvector"}

def test_failed_connector_retries_not_marked_done(tenant):
    tid, c = tenant
    c.post("/v1/connectors", json={"kind": "webhook", "config": {"url": "http://127.0.0.1:1/x", "secret": "s"}})
    ref = c.post("/v1/rights-requests", json={"principal": "pz", "kind": "erasure", "auto_execute": True}).json()["ref"]
    assert c.post("/v1/workers/run").json()["erasure_done"] == 0
    job = c.get("/v1/erasure").json()[0]
    assert job["status"] == "queued" and job["attempts"] == 1
    assert [r for r in c.get("/v1/rights-requests").json() if r["ref"] == ref][0]["status"] == "open"

def test_webhook_connector_signed(tenant, monkeypatch):
    import hashlib, hmac, httpx
    seen = {}
    def fake_post(url, content=None, headers=None, timeout=None):
        seen.update(url=url, body=content, sig=headers["X-Guard-Signature"])
        return httpx.Response(200, json={"deleted": 3}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    tid, c = tenant
    c.post("/v1/connectors", json={"kind": "webhook", "config": {"url": "http://crm.local/erase", "secret": "s3"}})
    c.post("/v1/rights-requests", json={"principal": "pw", "kind": "erasure", "auto_execute": True})
    assert c.post("/v1/workers/run").json()["erasure_done"] == 1
    assert seen["sig"] == hmac.new(b"s3", seen["body"], hashlib.sha256).hexdigest()
    assert json.loads(seen["body"])["principal"] == "pw"

def test_retention_expiry_queues_erasure(tenant):
    tid, c = tenant
    c.post("/v1/pii", json={"principal": "pr", "kind": "phone", "purpose": "s", "masked": "x", "retention_days": -1})
    assert c.post("/v1/workers/run").json()["retention_queued"] == 1
    assert c.get("/v1/erasure").json()[0]["reason"] == "retention"

def test_breach_kit(tenant):
    tid, c = tenant
    b = c.post("/v1/breaches", json={"title": "Sheet exposed", "description": "public link", "data_kinds": ["phone"], "affected_principals": ["a", "b"]}).json()
    assert 71 < b["hours_left"] <= 72 and not b["overdue"]
    n = c.post(f"/v1/breaches/{b['id']}/user-notices", json={"business": "Acme", "what": "phone", "action": "link revoked", "advice": "beware of spam", "contact": "dpo@acme.in"}).json()
    assert "Acme" in n["text"] and n["principals"] == ["a", "b"]
    assert "Rule 7" in c.get(f"/v1/breaches/{b['id']}/board-report", params={"business": "Acme"}).text
    assert c.get("/v1/breaches").json()[0]["users_notified_at"]

def test_audit_pack_zip_and_access_logged(tenant):
    tid, c = tenant
    c.post("/v1/consents", json={"principal": "p", "purpose": "a", "granted": True})
    r = c.get("/v1/audit-pack", params={"business": "Acme"})
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert {"summary.pdf", "consents.csv", "processing_register.csv", "erasure_history.csv", "ledger_extract.csv", "chain_verification.json"} <= set(z.namelist())
    assert json.loads(z.read("chain_verification.json"))["ok"]
    assert z.read("summary.pdf")[:4] == b"%PDF"
    with db.tenant_cur(tid) as cur:
        cur.execute("select count(*) n from access_log where resource='audit_pack'"); assert cur.fetchone()["n"] == 1

def test_checker_flags_bad_bot_and_passes_better(tenant):
    _, c = tenant
    bad = "Bot: Hi! By continuing you agree to our terms. What's your phone? User: 9876543210 Bot: great, here are offers!"
    r = c.post("/v1/checker", json={"text": bad}).json()
    codes = {f["code"] for f in r["findings"]}
    assert {"BUNDLED_CONSENT", "NO_ERASURE_PATH", "UNMASKED_PII"} <= codes and r["score"] < 60
    good = ("Bot: I'm an AI assistant. We will use your name and phone only to send order updates and keep it for 90 days. Privacy notice: x. "
            "Do you consent? Reply 1 for order updates. Reply 2 for marketing (optional). You can say stop or delete my data anytime.")
    assert c.post("/v1/checker", json={"text": good}).json()["score"] > 80

def test_hosted_guard_endpoint_and_transcript_masking(tenant):
    tid, c = tenant
    body = lambda m: {"message": m, "user_id": "u9", "channel": "whatsapp", "business": "Acme", "required_purposes": ["order_updates"], "optional_purposes": ["marketing"]}
    assert c.post("/v1/guard", json=body("hi")).json()["action"] == "reply"
    assert c.post("/v1/guard", json=body("1")).json()["granted"] == ["order_updates"]
    r = c.post("/v1/guard", json=body("my number 9876543210")).json()
    assert r["action"] == "forward" and r["message"] == "my number 9876543210" and "9876543210" not in r["masked_message"]
    with db.tenant_cur(tid) as cur:
        cur.execute("select text from transcripts where principal=%s", (r["principal"],)); texts = " ".join(x["text"] for x in cur.fetchall())
    assert "9876543210" not in texts and "[PHONE:" in texts           # raw PII never reached the stored transcript
    c.post("/v1/guard", json=body("meri details hatao"))
    ref = c.get("/v1/rights-requests").json()[0]["ref"]
    c.post(f"/v1/rights-requests/{ref}/execute"); assert c.post("/v1/workers/run").json()["erasure_done"] == 1
    with db.tenant_cur(tid) as cur:
        cur.execute("select count(*) n from transcripts where principal=%s", (r["principal"],)); assert cur.fetchone()["n"] == 0
