import csv
import io
import json
import zipfile

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from . import db, ledger


def _csv(rows, cols):
    s = io.StringIO(); w = csv.writer(s); w.writerow(cols)
    for r in rows:
        w.writerow([r.get(c, "") for c in cols])
    return s.getvalue()


def build(tenant: str, business: str) -> bytes:
    with db.tenant_cur(tenant) as cur:
        ledger.log_access(cur, tenant, "dashboard", "export", "audit_pack")
        cur.execute("select principal,purpose,granted,channel,notice_version,ts from consents where tenant_id=%s order by id", (tenant,)); consents = cur.fetchall()
        cur.execute("select purpose, kind, count(*) n, min(expires_at) earliest_expiry, bool_or(location='transcript') in_transcripts from pii_records where tenant_id=%s group by purpose, kind order by purpose, kind", (tenant,)); ropa = cur.fetchall()
        cur.execute("select ref,principal,kind,status,created_at,resolved_at from rights_requests where tenant_id=%s order by created_at", (tenant,)); rights = cur.fetchall()
        cur.execute("select id,principal,reason,status,attempts,created_at,finished_at,results from erasure_jobs where tenant_id=%s order by id", (tenant,)); jobs = cur.fetchall()
        cur.execute("select seq,ts,type,principal,hash from events where tenant_id=%s order by seq desc limit 5000", (tenant,)); evs = cur.fetchall()
        cur.execute("select actor,action,resource,ts from access_log where tenant_id=%s order by id desc limit 5000", (tenant,)); acc = cur.fetchall()
        ok, bad = ledger.verify(cur, tenant)
    for j in jobs:
        j["results"] = json.dumps(j["results"], default=str)
    pdf = io.BytesIO(); c = canvas.Canvas(pdf, pagesize=A4); y = 800
    for line in [f"DPDP Audit Pack - {business}", "DRAFT: tooling output, not legal advice.", "",
                 f"Consent records: {len(consents)}", f"Processing register rows: {len(ropa)}", f"Rights requests: {len(rights)}",
                 f"Erasure jobs: {len(jobs)} (done: {sum(j['status']=='done' for j in jobs)})", f"Ledger events (last 5000 exported): {len(evs)}",
                 f"Ledger hash-chain verification: {'PASS' if ok else 'FAIL at event index %s' % bad}"]:
        c.drawString(50, y, line); y -= 18
    c.save()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("summary.pdf", pdf.getvalue())
        z.writestr("consents.csv", _csv(consents, ["principal", "purpose", "granted", "channel", "notice_version", "ts"]))
        z.writestr("processing_register.csv", _csv(ropa, ["purpose", "kind", "n", "earliest_expiry", "in_transcripts"]))
        z.writestr("rights_requests.csv", _csv(rights, ["ref", "principal", "kind", "status", "created_at", "resolved_at"]))
        z.writestr("erasure_history.csv", _csv(jobs, ["id", "principal", "reason", "status", "attempts", "created_at", "finished_at", "results"]))
        z.writestr("ledger_extract.csv", _csv(evs, ["seq", "ts", "type", "principal", "hash"]))
        z.writestr("access_log.csv", _csv(acc, ["actor", "action", "resource", "ts"]))
        z.writestr("chain_verification.json", json.dumps({"ok": ok, "first_bad_index": bad}))
    return out.getvalue()
