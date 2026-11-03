import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import time
from collections import defaultdict, deque
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import audit, auth, breach as breach_mod, checker, db, ledger, workers


@asynccontextmanager
async def lifespan(app):
    task = None
    if os.environ.get("RUN_WORKERS") == "1":
        async def loop():
            while True:
                with db.raw_cur(db.ADMIN_URL) as cur:
                    cur.execute("select id from tenants"); ids = [r["id"] for r in cur.fetchall()]
                for t in ids:
                    await asyncio.to_thread(workers.run_retention, t)
                    await asyncio.to_thread(workers.run_erasure, t)
                await asyncio.sleep(30)
        task = asyncio.create_task(loop())
    yield
    if task:
        task.cancel()

app = FastAPI(title="DPDP Guard ledger", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","), allow_methods=["*"], allow_headers=["*"])
T = Depends(auth.tenant_from_key)


class EventIn(BaseModel):
    type: str; principal: str | None = None; payload: dict = {}
class StateIn(BaseModel):
    principal: str; key: str; value: object = None
class ConsentIn(BaseModel):
    principal: str; purpose: str; granted: bool; channel: str | None = None; notice_version: str | None = None
class PIIIn(BaseModel):
    principal: str; kind: str; purpose: str; masked: str; retention_days: int; location: str = "transcript"
class RightsIn(BaseModel):
    principal: str; kind: str; detail: str = ""; auto_execute: bool = False
class TranscriptIn(BaseModel):
    principal: str; role: str; text: str
class ConnectorIn(BaseModel):
    kind: str; name: str | None = None; config: dict = {}
class BreachIn(BaseModel):
    title: str; description: str; data_kinds: list[str] = []; affected_principals: list[str] = []; detected_at: datetime | None = None
class BreachNoticeIn(BaseModel):
    business: str; what: str; action: str; advice: str; contact: str; lang: str = "en"
class GuardIn(BaseModel):
    """Per-call fields override the tenant config saved via PUT /v1/config."""
    message: str; user_id: str; channel: str = "web"
    business: str | None = None; required_purposes: list[str] | None = None; optional_purposes: list[str] | None = None
    privacy_url: str | None = None
class PurposeIn(BaseModel):
    en: str; hi: str | None = None; retention_days: int = 90
class ConfigIn(BaseModel):
    business: str = "Your Business"; privacy_url: str = "https://example.com/privacy"
    required_purposes: list[str] = ["order_updates"]; optional_purposes: list[str] = []
    purposes: dict[str, PurposeIn] = {}          # custom purposes; built-ins (order_updates, support, marketing) need no definition
class CheckIn(BaseModel):
    text: str
class TenantIn(BaseModel):
    id: str; name: str


@app.get("/health")
def health(): return {"ok": True}


@app.post("/admin/tenants", dependencies=[Depends(auth.require_admin)])
def new_tenant(b: TenantIn): return {"tenant": b.id, "api_key": auth.create_tenant(b.id, b.name)}


@app.post("/v1/events")
def post_event(b: EventIn, t=T):
    with db.tenant_cur(t) as cur: return {"hash": ledger.append(cur, t, b.type, b.principal, b.payload)}


@app.get("/v1/state")
def get_state(principal: str, key: str, t=T):
    with db.tenant_cur(t) as cur:
        cur.execute("select value from state where tenant_id=%s and principal=%s and key=%s", (t, principal, key))
        r = cur.fetchone(); return {"value": r["value"] if r else None}


@app.post("/v1/state")
def set_state(b: StateIn, t=T):
    with db.tenant_cur(t) as cur:
        cur.execute("insert into state values(%s,%s,%s,%s) on conflict(tenant_id,principal,key) do update set value=excluded.value", (t, b.principal, b.key, json.dumps(b.value)))
    return {"ok": True}


@app.post("/v1/consents")
def post_consent(b: ConsentIn, t=T):
    with db.tenant_cur(t) as cur:
        workers.record_consent(cur, t, b.principal, b.purpose, b.granted, b.channel, b.notice_version)
    return {"ok": True}


@app.get("/v1/consents/state")
def consent_state(principal: str, t=T):
    with db.tenant_cur(t) as cur:
        cur.execute("select purpose, granted from consents where tenant_id=%s and principal=%s order by id", (t, principal))
        return {r["purpose"]: r["granted"] for r in cur.fetchall()}


@app.get("/v1/consents")
def list_consents(limit: int = 200, t=T):
    with db.tenant_cur(t) as cur:
        ledger.log_access(cur, t, "api", "read", "consents")
        cur.execute("select principal,purpose,granted,channel,notice_version,ts from consents where tenant_id=%s order by id desc limit %s", (t, limit))
        return cur.fetchall()


@app.post("/v1/pii")
def post_pii(b: PIIIn, t=T):
    pid = uuid.uuid4().hex
    with db.tenant_cur(t) as cur:
        cur.execute("insert into pii_records(id,tenant_id,principal,kind,purpose,masked,expires_at,location) values(%s,%s,%s,%s,%s,%s,%s,%s)",
                    (pid, t, b.principal, b.kind, b.purpose, b.masked, datetime.now(timezone.utc) + timedelta(days=b.retention_days), b.location))
        ledger.append(cur, t, "pii_recorded", b.principal, {"kind": b.kind, "purpose": b.purpose, "retention_days": b.retention_days})
    return {"id": pid}


@app.post("/v1/transcripts")
def post_transcript(b: TranscriptIn, t=T):
    """Store a (masked) transcript line in the built-in transcript store. Pass masked text only."""
    with db.tenant_cur(t) as cur:
        cur.execute("insert into transcripts(tenant_id,principal,role,text) values(%s,%s,%s,%s)", (t, b.principal, b.role, b.text))
    return {"ok": True}


@app.post("/v1/rights-requests")
def post_rights(b: RightsIn, t=T):
    ref = "R-" + uuid.uuid4().hex[:8].upper()
    with db.tenant_cur(t) as cur:
        cur.execute("insert into rights_requests(ref,tenant_id,principal,kind,detail) values(%s,%s,%s,%s,%s)", (ref, t, b.principal, b.kind, b.detail))
        ledger.append(cur, t, "rights_request", b.principal, {"ref": ref, "kind": b.kind})
        if b.auto_execute and b.kind in ("erasure", "withdraw"):
            workers.queue_erasure(cur, t, b.principal, b.kind, ref)
    return {"ref": ref}


@app.get("/v1/rights-requests")
def list_rights(status: str | None = None, t=T):
    with db.tenant_cur(t) as cur:
        cur.execute("select * from rights_requests where tenant_id=%s and (%s::text is null or status=%s) order by created_at desc", (t, status, status))
        return cur.fetchall()


@app.post("/v1/rights-requests/{ref}/execute")
def execute_rights(ref: str, t=T):
    with db.tenant_cur(t) as cur:
        cur.execute("select * from rights_requests where tenant_id=%s and ref=%s", (t, ref)); r = cur.fetchone()
        if not r: raise HTTPException(404)
        if r["kind"] in ("erasure", "withdraw"):
            cur.execute("update rights_requests set status='in_progress' where ref=%s", (ref,))
            return {"job": workers.queue_erasure(cur, t, r["principal"], r["kind"], ref)}
        cur.execute("update rights_requests set status='fulfilled', resolved_at=now() where ref=%s", (ref,))
        ledger.append(cur, t, "rights_resolved", r["principal"], {"ref": ref, "kind": r["kind"]})
        return {"job": None}


@app.get("/v1/principals/{principal}/export")
def export_principal(principal: str, t=T):
    """Access request fulfilment: what we hold about this principal (masked values + consent history)."""
    with db.tenant_cur(t) as cur:
        ledger.log_access(cur, t, "api", "read", f"principal:{principal[:8]}")
        cur.execute("select purpose,granted,ts from consents where tenant_id=%s and principal=%s order by id", (t, principal)); c = cur.fetchall()
        cur.execute("select kind,purpose,masked,expires_at,erased_at from pii_records where tenant_id=%s and principal=%s", (t, principal)); p = cur.fetchall()
        return {"consents": c, "personal_data": p}


@app.post("/v1/connectors")
def add_connector(b: ConnectorIn, t=T):
    from .connectors import REGISTRY
    if b.kind not in REGISTRY: raise HTTPException(400, f"unknown connector; have {sorted(REGISTRY)}")
    with db.tenant_cur(t) as cur:
        cur.execute("insert into connectors(tenant_id,kind,name,config) values(%s,%s,%s,%s) returning id", (t, b.kind, b.name, json.dumps(b.config)))
        return {"id": cur.fetchone()["id"]}


@app.get("/v1/connectors")
def list_connectors(t=T):
    """Config values (tokens, DSNs, secrets) are never returned; only which keys are set."""
    with db.tenant_cur(t) as cur:
        cur.execute("select id, kind, name, config from connectors where tenant_id=%s order by id", (t,))
        return [{"id": r["id"], "kind": r["kind"], "name": r["name"], "config_keys": sorted((r["config"] or {}).keys())} for r in cur.fetchall()]


@app.delete("/v1/connectors/{cid}")
def delete_connector(cid: int, t=T):
    with db.tenant_cur(t) as cur:
        cur.execute("delete from connectors where tenant_id=%s and id=%s", (t, cid))
        if cur.rowcount != 1: raise HTTPException(404)
        ledger.append(cur, t, "connector_removed", None, {"id": cid})
    return {"ok": True}


@app.get("/v1/principals/lookup")
def lookup_principal(user_id: str, t=T):
    """Operators know phone numbers, the ledger only has hashes. Computes the hash server-side; user_id is not stored."""
    from dpdp_guard import Guard
    from dpdp_guard.chain import hash_principal
    with db.tenant_cur(t) as cur:
        ledger.log_access(cur, t, "dashboard", "lookup", "principal")
    return {"principal": hash_principal(t, Guard._norm(user_id), "")}


@app.get("/v1/notices")
def active_notices(t=T):
    from dpdp_guard import notices
    cfg = notices.load(); c = _tenant_config(t)
    purposes = {**cfg["purposes"], **{k: {"en": v["en"], "hi": v.get("hi") or v["en"], "retention_days": v.get("retention_days", 90)} for k, v in (c.get("purposes") or {}).items()}}
    return {"version": cfg["version"], "status": "DRAFT - lawyer review required", "purposes": purposes, "templates": cfg["templates"]}


@app.get("/v1/erasure")
def list_erasure(t=T):
    with db.tenant_cur(t) as cur:
        cur.execute("select * from erasure_jobs where tenant_id=%s order by id desc limit 200", (t,)); return cur.fetchall()


@app.post("/v1/workers/run")
def run_workers(t=T):
    return {"retention_queued": workers.run_retention(t), "erasure_done": workers.run_erasure(t)}


@app.get("/v1/ledger/verify")
def verify(t=T):
    with db.tenant_cur(t) as cur:
        ok, bad = ledger.verify(cur, t); cur.execute("select count(*) c from events where tenant_id=%s", (t,))
        return {"ok": ok, "first_bad_index": bad, "events": cur.fetchone()["c"]}


@app.post("/v1/breaches")
def new_breach(b: BreachIn, t=T):
    det = b.detected_at or datetime.now(timezone.utc)
    with db.tenant_cur(t) as cur:
        cur.execute("insert into breaches(tenant_id,title,description,detected_at,affected_principals,data_kinds,board_report_due) values(%s,%s,%s,%s,%s,%s,%s) returning id",
                    (t, b.title, b.description, det, b.affected_principals, b.data_kinds, breach_mod.board_deadline(det)))
        i = cur.fetchone()["id"]; ledger.append(cur, t, "breach_opened", None, {"id": i, "title": b.title})
    return {"id": i, **breach_mod.countdown(det)}


@app.get("/v1/breaches")
def list_breaches(t=T):
    with db.tenant_cur(t) as cur:
        cur.execute("select * from breaches where tenant_id=%s order by id desc", (t,)); rows = cur.fetchall()
    return [{**r, "countdown": breach_mod.countdown(r["detected_at"])} for r in rows]


def _breach(cur, t, bid):
    cur.execute("select * from breaches where tenant_id=%s and id=%s", (t, bid)); r = cur.fetchone()
    if not r: raise HTTPException(404)
    return r


@app.post("/v1/breaches/{bid}/user-notices")
def breach_notices(bid: int, b: BreachNoticeIn, t=T):
    with db.tenant_cur(t) as cur:
        r = _breach(cur, t, bid)
        txt = breach_mod.user_notice(b.business, b.what, b.action, b.advice, b.contact, b.lang)
        cur.execute("update breaches set users_notified_at=now() where id=%s", (bid,))
        ledger.append(cur, t, "breach_users_notified", None, {"id": bid, "count": len(r["affected_principals"])})
    return {"disclaimer": breach_mod.DISCLAIMER, "text": txt, "principals": r["affected_principals"]}


@app.get("/v1/breaches/{bid}/board-report")
def breach_report(bid: int, business: str, t=T):
    with db.tenant_cur(t) as cur:
        return Response(breach_mod.board_report(_breach(cur, t, bid), business), media_type="text/plain")


@app.post("/v1/breaches/{bid}/mark-filed")
def breach_filed(bid: int, t=T):
    with db.tenant_cur(t) as cur:
        _breach(cur, t, bid)
        cur.execute("update breaches set board_report_filed_at=now(), status='filed' where id=%s", (bid,))
        ledger.append(cur, t, "breach_board_report_filed", None, {"id": bid})
    return {"ok": True}


@app.get("/v1/audit-pack")
def audit_pack(business: str = "Your Business", t=T):
    return Response(audit.build(t, business), media_type="application/zip", headers={"Content-Disposition": "attachment; filename=audit-pack.zip"})


_hits: dict[str, deque] = defaultdict(deque)


def _rate_limit(ip: str, limit: int, window: float = 60.0):
    """Sliding window per client IP. In-memory: single process only, resets on restart."""
    now_, q = time.monotonic(), _hits[ip]
    while q and now_ - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": str(int(window))})
    q.append(now_)


@app.post("/v1/checker")
def run_checker(b: CheckIn, request: Request):
    """Public, unauthenticated, nothing stored. Rate limited per IP (CHECKER_RATE_PER_MIN, default 20)."""
    _rate_limit(request.client.host if request.client else "?", int(os.environ.get("CHECKER_RATE_PER_MIN", "20")))
    if len(b.text) > 50_000: raise HTTPException(413, "too long")
    return checker.check(b.text)


def _tenant_config(t) -> dict:
    with db.raw_cur() as cur:
        cur.execute("select config from tenants where id=%s", (t,)); r = cur.fetchone()
    return (r or {}).get("config") or {}


@app.get("/v1/config")
def get_config(t=T): return _tenant_config(t)


@app.put("/v1/config")
def put_config(b: ConfigIn, t=T):
    import re
    known = set(b.purposes) | {"order_updates", "support", "marketing"}
    bad = [p for p in b.required_purposes + b.optional_purposes if p not in known]
    if bad: raise HTTPException(422, f"undefined purposes: {bad}; define them under 'purposes'")
    if not b.required_purposes: raise HTTPException(422, "at least one required purpose")
    if any(not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", p) for p in b.purposes): raise HTTPException(422, "purpose ids must be snake_case")
    with db.raw_cur() as cur:
        cur.execute("update tenants set config=%s where id=%s", (b.model_dump_json(), t))
        if cur.rowcount != 1: raise HTTPException(404)
    with db.tenant_cur(t) as cur:
        ledger.append(cur, t, "config_changed", None, {"required": b.required_purposes, "optional": b.optional_purposes, "custom_purposes": sorted(b.purposes)})
    return {"ok": True}


@app.post("/v1/guard")
def guard_endpoint(b: GuardIn, t=T):
    """Hosted guard(): for non-Python stacks (Node SDK, n8n). Config = saved tenant config, overridden per call."""
    import copy
    from dpdp_guard import Guard, notices
    from .dbstore import DbStore
    c = _tenant_config(t)
    cfg = copy.deepcopy(notices.load())
    for pid, d in (c.get("purposes") or {}).items():
        cfg["purposes"][pid] = {"en": d["en"], "hi": d.get("hi") or d["en"], "retention_days": d.get("retention_days", 90)}
    req = b.required_purposes or c.get("required_purposes") or ["order_updates"]
    opt = b.optional_purposes if b.optional_purposes is not None else c.get("optional_purposes") or []
    unknown = [p for p in req + opt if p not in cfg["purposes"]]
    if unknown: raise HTTPException(422, f"undefined purposes: {unknown}")
    g = Guard(t, b.business or c.get("business") or "Your Business", req, opt, store=DbStore(t),
              privacy_url=b.privacy_url or c.get("privacy_url") or "https://example.com/privacy", notice_cfg=cfg)
    r = g(b.message, b.user_id, b.channel)
    return {"action": r.action, "message": r.message, "masked_message": r.masked_message, "reply_text": r.reply_text,
            "intent": r.intent, "granted": r.granted, "rights_ref": r.rights_ref, "review_ref": r.review_ref, "notify": r.notify, "principal": g.pid(b.user_id)}
