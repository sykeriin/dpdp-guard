import hashlib
import json

from . import connectors, db, ledger


def queue_erasure(cur, tenant, principal, reason, rights_ref=None, scope="all") -> int:
    cur.execute("insert into erasure_jobs(tenant_id,principal,reason,rights_ref,scope) values(%s,%s,%s,%s,%s) returning id",
                (tenant, principal, reason, rights_ref, scope))
    jid = cur.fetchone()["id"]
    ledger.append(cur, tenant, "erasure_queued", principal, {"job": jid, "reason": reason, "scope": scope})
    return jid


def record_consent(cur, tenant, principal, purpose, granted, channel=None, notice_version=None):
    """Insert consent + ledger event. Withdrawing a previously granted purpose queues an erasure scoped to that purpose."""
    cur.execute("select granted from consents where tenant_id=%s and principal=%s and purpose=%s order by id desc limit 1", (tenant, principal, purpose))
    prev = cur.fetchone()
    cur.execute("insert into consents(tenant_id,principal,purpose,granted,channel,notice_version) values(%s,%s,%s,%s,%s,%s)", (tenant, principal, purpose, granted, channel, notice_version))
    ledger.append(cur, tenant, "consent_granted" if granted else "consent_declined", principal, {"purpose": purpose, "channel": channel, "notice_version": notice_version})
    if not granted and prev and prev["granted"]:
        queue_erasure(cur, tenant, principal, f"withdrawn:{purpose}", scope=f"purpose:{purpose}")


def run_retention(tenant) -> int:
    """Expire PII records past expires_at. Principals with nothing left unexpired get a full erasure job."""
    n = 0
    with db.tenant_cur(tenant) as cur:
        cur.execute("select id, principal, kind, purpose from pii_records where tenant_id=%s and erased_at is null and expires_at < now()", (tenant,))
        expired = cur.fetchall()
        by = {}
        for r in expired:
            by.setdefault(r["principal"], []).append(r)
        for p, recs in by.items():
            cur.execute("update pii_records set erased_at=now() where id = any(%s)", ([r["id"] for r in recs],))
            ledger.append(cur, tenant, "retention_expired", p, {"pii_ids": [r["id"] for r in recs], "kinds": sorted({r["kind"] for r in recs})})
            cur.execute("select count(*) c from pii_records where tenant_id=%s and principal=%s and erased_at is null", (tenant, p))
            if cur.fetchone()["c"] == 0:
                queue_erasure(cur, tenant, p, "retention", scope="all"); n += 1
    return n


def run_erasure(tenant, max_jobs=20) -> int:
    done = 0
    for _ in range(max_jobs):
        with db.tenant_cur(tenant) as cur:
            cur.execute("select * from erasure_jobs where tenant_id=%s and status='queued' and run_after <= now() order by id limit 1 for update skip locked", (tenant,))
            job = cur.fetchone()
            if not job:
                break
            cur.execute("update erasure_jobs set status='running', attempts=attempts+1 where id=%s", (job["id"],))
            cur.execute("select kind, name, config from connectors where tenant_id=%s", (tenant,))
            conns = cur.fetchall()
        scope = job["scope"]
        results, ok = [], True
        # built-in transcript store always runs
        plan = [("transcripts", "built-in", {})] + [(c["kind"], c["name"] or c["kind"], c["config"]) for c in conns]
        purpose = scope.split(":", 1)[1] if scope.startswith("purpose:") else None
        for kind, name, cfg in plan:
            if purpose and kind not in connectors.PURPOSE_AWARE:
                # these connectors delete by principal only and cannot target one purpose; never over-delete
                results.append({"connector": name, "kind": kind, "ok": True, "deleted": 0, "detail": "skipped: no purpose scoping"})
                continue
            try:
                res = connectors.REGISTRY[kind](tenant, job["principal"], cfg, job)
                results.append({"connector": name, "kind": kind, "ok": True, **res})
            except Exception as e:
                ok = False
                results.append({"connector": name, "kind": kind, "ok": False, "error": str(e)[:300]})
        with db.tenant_cur(tenant) as cur:
            proof = hashlib.sha256(json.dumps(results, sort_keys=True).encode()).hexdigest()
            if ok:
                cur.execute("update erasure_jobs set status='done', finished_at=now(), results=%s where id=%s", (json.dumps(results), job["id"]))
                if purpose:
                    cur.execute("update pii_records set erased_at=coalesce(erased_at, now()) where tenant_id=%s and principal=%s and purpose=%s", (tenant, job["principal"], purpose))
                else:
                    cur.execute("update pii_records set erased_at=coalesce(erased_at, now()) where tenant_id=%s and principal=%s", (tenant, job["principal"]))
                if job["rights_ref"]:
                    cur.execute("update rights_requests set status='fulfilled', resolved_at=now() where ref=%s", (job["rights_ref"],))
                ledger.append(cur, tenant, "erasure_proof", job["principal"], {"job": job["id"], "proof_sha256": proof, "connectors": [(r["kind"], r["ok"], r.get("deleted")) for r in results]})
            else:
                backoff = min(2 ** job["attempts"], 60)
                cur.execute("update erasure_jobs set status=%s, results=%s, run_after=now() + (%s || ' minutes')::interval where id=%s",
                            ("failed" if job["attempts"] >= 5 else "queued", json.dumps(results), backoff, job["id"]))
                ledger.append(cur, tenant, "erasure_failed", job["principal"], {"job": job["id"], "attempt": job["attempts"], "errors": [r for r in results if not r["ok"]]})
        done += ok
    return done
