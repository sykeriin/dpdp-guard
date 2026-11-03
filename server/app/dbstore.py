"""Store backed directly by Postgres (same interface as LocalStore/HttpStore) so /v1/guard can run Guard server-side."""
import json
import uuid
from datetime import datetime, timedelta, timezone

from . import db, ledger, workers


class DbStore:
    def __init__(self, tenant):
        self.t = tenant

    def append_event(self, tenant, type, principal, payload=None):
        with db.tenant_cur(self.t) as cur: return ledger.append(cur, self.t, type, principal, payload)

    def get_state(self, tenant, principal, key, default=None):
        with db.tenant_cur(self.t) as cur:
            cur.execute("select value from state where tenant_id=%s and principal=%s and key=%s", (self.t, principal, key)); r = cur.fetchone()
            return r["value"] if r else default

    def set_state(self, tenant, principal, key, value):
        with db.tenant_cur(self.t) as cur:
            cur.execute("insert into state values(%s,%s,%s,%s) on conflict(tenant_id,principal,key) do update set value=excluded.value", (self.t, principal, key, json.dumps(value)))

    def record_consent(self, tenant, principal, purpose, granted, channel, notice_version):
        with db.tenant_cur(self.t) as cur:
            workers.record_consent(cur, self.t, principal, purpose, granted, channel, notice_version)

    def consent_state(self, tenant, principal):
        with db.tenant_cur(self.t) as cur:
            cur.execute("select purpose, granted from consents where tenant_id=%s and principal=%s order by id", (self.t, principal))
            return {r["purpose"]: r["granted"] for r in cur.fetchall()}

    def record_pii(self, tenant, principal, kind, purpose, masked, retention_days, location="transcript"):
        pid = uuid.uuid4().hex
        with db.tenant_cur(self.t) as cur:
            cur.execute("insert into pii_records(id,tenant_id,principal,kind,purpose,masked,expires_at,location) values(%s,%s,%s,%s,%s,%s,%s,%s)",
                        (pid, self.t, principal, kind, purpose, masked, datetime.now(timezone.utc) + timedelta(days=retention_days), location))
            ledger.append(cur, self.t, "pii_recorded", principal, {"kind": kind, "purpose": purpose, "retention_days": retention_days})
        return pid

    def create_rights_request(self, tenant, principal, kind, detail=""):
        ref = "R-" + uuid.uuid4().hex[:8].upper()
        with db.tenant_cur(self.t) as cur:
            cur.execute("insert into rights_requests(ref,tenant_id,principal,kind,detail) values(%s,%s,%s,%s,%s)", (ref, self.t, principal, kind, detail))
            ledger.append(cur, self.t, "rights_request", principal, {"ref": ref, "kind": kind})
        return ref

    def log_transcript(self, tenant, principal, role, text):
        with db.tenant_cur(self.t) as cur:
            cur.execute("insert into transcripts(tenant_id,principal,role,text) values(%s,%s,%s,%s)", (self.t, principal, role, text))
