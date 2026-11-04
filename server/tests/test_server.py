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
    c.post(f"/v1/rights-requests/{ref}/execute")
    # the erasure message also withdrew consent per purpose, which queues a (redundant, narrower) purpose-scoped job
    assert c.post("/v1/workers/run").json()["erasure_done"] >= 1
    assert {j["status"] for j in c.get("/v1/erasure").json()} == {"done"}
    with db.tenant_cur(tid) as cur:
        cur.execute("select count(*) n from transcripts where principal=%s", (r["principal"],)); assert cur.fetchone()["n"] == 0


def test_withdrawing_marketing_erases_only_marketing_pii(tenant):
    tid, c = tenant
    p = "pp1"
    c.post("/v1/consents", json={"principal": p, "purpose": "order_updates", "granted": True})
    c.post("/v1/consents", json={"principal": p, "purpose": "marketing", "granted": True})
    c.post("/v1/pii", json={"principal": p, "kind": "phone", "purpose": "order_updates", "masked": "x", "retention_days": 90})
    c.post("/v1/pii", json={"principal": p, "kind": "email", "purpose": "marketing", "masked": "y", "retention_days": 90})
    c.post("/v1/transcripts", json={"principal": p, "role": "user", "text": "hi"})
    c.post("/v1/consents", json={"principal": p, "purpose": "marketing", "granted": False})     # withdraw
    job = c.get("/v1/erasure").json()[0]
    assert job["scope"] == "purpose:marketing"
    assert c.post("/v1/workers/run").json()["erasure_done"] == 1
    with db.tenant_cur(tid) as cur:
        cur.execute("select purpose, erased_at is not null as gone from pii_records where principal=%s", (p,))
        gone = {r["purpose"]: r["gone"] for r in cur.fetchall()}
        cur.execute("select count(*) n from transcripts where principal=%s", (p,)); transcripts = cur.fetchone()["n"]
    assert gone == {"order_updates": False, "marketing": True}      # order-update data untouched
    assert transcripts == 1                                         # transcripts not wiped by a single-purpose withdrawal


def test_declining_never_granted_purpose_queues_nothing(tenant):
    tid, c = tenant
    c.post("/v1/consents", json={"principal": "q", "purpose": "marketing", "granted": False})
    assert c.get("/v1/erasure").json() == []


def test_purpose_scoped_job_keeps_scope_after_failed_retry(tenant):
    """Regression: scope used to live in results[0] and was lost when a failed attempt overwrote results -> over-deletion."""
    tid, c = tenant
    import psycopg
    pid = "pscope"
    with psycopg.connect(db.ADMIN_URL, autocommit=True) as conn:
        conn.execute("create table if not exists cust_vectors(id serial, principal text, body text)")
        conn.execute("delete from cust_vectors where principal=%s", (pid,))     # table persists across runs
        conn.execute("insert into cust_vectors(principal, body) values (%s,'keep me')", (pid,))
    c.post("/v1/connectors", json={"kind": "pgvector", "config": {"dsn": db.ADMIN_URL, "table": "cust_vectors"}})
    c.post("/v1/connectors", json={"kind": "webhook", "config": {"url": "http://127.0.0.1:1/x", "secret": "s"}})   # fails -> job requeued
    c.post("/v1/consents", json={"principal": pid, "purpose": "marketing", "granted": True})
    c.post("/v1/consents", json={"principal": pid, "purpose": "marketing", "granted": False})
    for _ in range(2):
        c.post("/v1/workers/run")
    job = c.get("/v1/erasure").json()[0]
    assert job["scope"] == "purpose:marketing" and job["attempts"] >= 1
    with psycopg.connect(db.ADMIN_URL) as conn:       # the principal-wide SQL connector must NOT have run
        assert conn.execute("select count(*) from cust_vectors where principal=%s", (pid,)).fetchone()[0] == 1


def test_checker_rate_limited(tenant, monkeypatch):
    _, c = tenant
    monkeypatch.setenv("CHECKER_RATE_PER_MIN", "3")
    from app import main
    main._hits.clear()
    codes = [c.post("/v1/checker", json={"text": "hi"}).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    main._hits.clear()


def test_gsheets_connector_deletes_matching_rows_bottom_up(tenant, monkeypatch):
    import httpx
    from app import connectors
    calls = []
    def fake_get(url, headers=None, timeout=None):
        calls.append(("GET", url))
        return httpx.Response(200, json={"values": [["hdr"], ["P1", "a"], ["other", "b"], ["P1", "c"]]}, request=httpx.Request("GET", url))
    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(("POST", url, json))
        return httpx.Response(200, json={}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "get", fake_get); monkeypatch.setattr(httpx, "post", fake_post)
    res = connectors.gsheets("t", "P1", {"token": "tok", "spreadsheet_id": "S", "sheet_name": "Leads", "sheet_id": 7}, {})
    assert res["deleted"] == 2
    reqs = calls[1][2]["requests"]
    assert [r["deleteDimension"]["range"]["startIndex"] for r in reqs] == [3, 1]      # bottom-up
    assert all(r["deleteDimension"]["range"]["sheetId"] == 7 for r in reqs)
    calls.clear()
    assert connectors.gsheets("t", "nobody", {"token": "t", "spreadsheet_id": "S", "sheet_name": "Leads", "sheet_id": 7}, {})["deleted"] == 0
    assert len(calls) == 1                                                             # no batchUpdate when nothing matches


def test_tenant_config_custom_purposes_drive_guard(tenant):
    tid, c = tenant
    r = c.put("/v1/config", json={"business": "Dr Rao Clinic", "required_purposes": ["appointments"], "optional_purposes": ["health_tips"],
                                  "purposes": {"appointments": {"en": "Appointments: book and remind you of visits.", "retention_days": 30},
                                               "health_tips": {"en": "Health tips: send wellness advice.", "retention_days": 365}}})
    assert r.status_code == 200
    n = c.post("/v1/guard", json={"message": "hi", "user_id": "u1"}).json()["reply_text"]
    assert "Dr Rao Clinic" in n and "Appointments: book" in n and "Health tips" in n and "Marketing" not in n
    assert c.post("/v1/guard", json={"message": "1", "user_id": "u1"}).json()["granted"] == ["appointments"]
    c.post("/v1/guard", json={"message": "my number 9876543210", "user_id": "u1"})
    with db.tenant_cur(tid) as cur:
        cur.execute("select purpose, (expires_at < now() + interval '31 days') as short from pii_records"); row = cur.fetchone()
        cur.execute("select count(*) n from events where type='config_changed'"); logged = cur.fetchone()["n"]
    assert row["purpose"] == "appointments" and row["short"]      # custom 30-day retention applied
    assert logged == 1


def test_tenant_config_validation_and_isolation(tenant):
    tid, c = tenant
    assert c.put("/v1/config", json={"required_purposes": ["nope"]}).status_code == 422
    assert c.put("/v1/config", json={"required_purposes": []}).status_code == 422
    assert c.put("/v1/config", json={"required_purposes": ["Bad-Id"], "purposes": {"Bad-Id": {"en": "x"}}}).status_code == 422
    other = c.__class__(c.app); k = other.post("/admin/tenants", json={"id": tid + "_b", "name": "B"}, headers={"X-Admin-Token": "adm"}).json()["api_key"]
    other.headers["Authorization"] = f"Bearer {k}"
    c.put("/v1/config", json={"business": "A Corp"})
    assert other.get("/v1/config").json() == {}                   # another tenant doesn't see it


def test_connector_listing_redacts_secrets_and_delete(tenant):
    tid, c = tenant
    cid = c.post("/v1/connectors", json={"kind": "webhook", "name": "crm", "config": {"url": "http://x", "secret": "TOPSECRET"}}).json()["id"]
    rows = c.get("/v1/connectors").json()
    assert rows == [{"id": cid, "kind": "webhook", "name": "crm", "config_keys": ["secret", "url"]}] and "TOPSECRET" not in str(rows)
    assert c.delete(f"/v1/connectors/{cid}").status_code == 200 and c.get("/v1/connectors").json() == []
    assert c.delete(f"/v1/connectors/{cid}").status_code == 404

def test_principal_lookup_matches_guard_and_is_logged(tenant):
    tid, c = tenant
    r = c.post("/v1/guard", json={"message": "hi", "user_id": "919876543210"}).json()
    assert c.get("/v1/principals/lookup", params={"user_id": "+91 98765 43210"}).json()["principal"] == r["principal"]
    with db.tenant_cur(tid) as cur:
        cur.execute("select count(*) n from access_log where action='lookup'"); assert cur.fetchone()["n"] == 1

def test_notices_endpoint_includes_custom_purposes(tenant):
    _, c = tenant
    c.put("/v1/config", json={"required_purposes": ["appointments"], "purposes": {"appointments": {"en": "Appts", "retention_days": 30}}})
    n = c.get("/v1/notices").json()
    assert "appointments" in n["purposes"] and "marketing" in n["purposes"] and "DRAFT" in n["status"]


# ---- public waitlist (applies the product's own rules)
def _wl(c, **kw):
    return c.post("/v1/waitlist", json={"email": f"{kw.pop('n', 'a')}@example.com", **kw})

def test_waitlist_requires_explicit_consent_and_valid_email(tenant):
    from app import main
    _, c = tenant; main._hits.clear()
    assert _wl(c, n="x1").status_code == 422                                   # no consent -> nothing stored
    assert _wl(c, n="x1", consent_tips=True).status_code == 422                # optional consent alone is not enough
    assert c.post("/v1/waitlist", json={"email": "not-an-email", "consent_contact": True}).status_code == 422
    with db.raw_cur(db.ADMIN_URL) as cur:
        cur.execute("select count(*) n from waitlist where email like 'x1@%'"); assert cur.fetchone()["n"] == 0

def test_waitlist_purposes_separate_retention_and_delete_token(tenant):
    from app import main
    _, c = tenant; main._hits.clear()
    r = _wl(c, n="w1", consent_contact=True).json()
    assert r["purposes"] == ["launch_contact"] and r["retention_days"] == 365          # tips NOT implied
    r2 = _wl(c, n="w2", consent_contact=True, consent_tips=True).json()
    assert r2["purposes"] == ["launch_contact", "tips"]
    with db.raw_cur(db.ADMIN_URL) as cur:
        cur.execute("select (expires_at > now() + interval '364 days') as ok, token_hash <> %s as hashed from waitlist where email='w1@example.com'", (r["delete_token"],))
        row = cur.fetchone(); assert row["ok"] and row["hashed"]                       # expiry set; raw token not stored
    assert c.delete("/v1/waitlist", params={"token": "wrong"}).status_code == 404
    assert c.delete("/v1/waitlist", params={"token": r["delete_token"]}).status_code == 200
    assert c.delete("/v1/waitlist", params={"token": r["delete_token"]}).status_code == 404   # single use
    with db.raw_cur(db.ADMIN_URL) as cur:
        cur.execute("select count(*) n from waitlist where email='w1@example.com'"); assert cur.fetchone()["n"] == 0

def test_waitlist_retention_purge_and_admin_only_listing(tenant):
    from app import main
    _, c = tenant; main._hits.clear()
    _wl(c, n="old1", consent_contact=True)
    with db.raw_cur(db.ADMIN_URL) as cur:
        cur.execute("update waitlist set expires_at = now() - interval '1 day' where email='old1@example.com'")
    assert main.purge_waitlist() >= 1
    with db.raw_cur(db.ADMIN_URL) as cur:
        cur.execute("select count(*) n from waitlist where email='old1@example.com'"); assert cur.fetchone()["n"] == 0
    assert c.get("/admin/waitlist").status_code == 403                                 # tenant key is not admin
    assert c.get("/admin/waitlist", headers={"X-Admin-Token": "adm"}).status_code == 200

def test_waitlist_rate_limited(tenant, monkeypatch):
    from app import main
    _, c = tenant; main._hits.clear(); monkeypatch.setenv("WAITLIST_RATE_PER_MIN", "2")
    codes = [_wl(c, n=f"r{i}", consent_contact=True).status_code for i in range(4)]
    assert codes == [200, 200, 429, 429]; main._hits.clear()
