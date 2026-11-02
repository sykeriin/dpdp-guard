import json

from dpdp_guard.chain import GENESIS, compute_hash, verify_chain


def append(cur, tenant: str, type: str, principal: str | None, payload: dict | None = None) -> str:
    from datetime import datetime, timezone
    cur.execute("select pg_advisory_xact_lock(hashtext(%s))", (tenant,))
    cur.execute("select hash from events where tenant_id=%s order by seq desc limit 1", (tenant,))
    r = cur.fetchone()
    prev = r["hash"] if r else GENESIS
    ev = {"type": type, "principal": principal, "payload": payload or {}, "ts": datetime.now(timezone.utc).isoformat()}
    h = compute_hash(prev, ev)
    cur.execute("insert into events(tenant_id,ts,type,principal,event,prev_hash,hash) values(%s,%s,%s,%s,%s,%s,%s)",
                (tenant, ev["ts"], type, principal, json.dumps(ev), prev, h))
    return h


def rows(cur, tenant: str):
    cur.execute("select seq, prev_hash, hash, event from events where tenant_id=%s order by seq", (tenant,))
    return cur.fetchall()


def verify(cur, tenant: str):
    return verify_chain(rows(cur, tenant))


def log_access(cur, tenant: str, actor: str, action: str, resource: str):
    cur.execute("insert into access_log(tenant_id,actor,action,resource) values(%s,%s,%s,%s)", (tenant, actor, action, resource))
    append(cur, tenant, "access", None, {"actor": actor, "action": action, "resource": resource})
