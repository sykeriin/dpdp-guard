"""Store interface used by Guard. LocalStore = SQLite (demo/offline). HttpStore = hosted ledger."""
import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from .chain import GENESIS, compute_hash, verify_chain


def now() -> datetime:
    return datetime.now(timezone.utc)


class LocalStore:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.db.executescript("""
        create table if not exists events(seq integer primary key autoincrement, tenant text, ts text, type text, principal text,
            event text, prev_hash text, hash text);
        create trigger if not exists events_no_update before update on events begin select raise(abort,'events is append-only'); end;
        create trigger if not exists events_no_delete before delete on events begin select raise(abort,'events is append-only'); end;
        create table if not exists consents(id integer primary key autoincrement, tenant text, principal text, purpose text,
            granted integer, channel text, notice_version text, ts text);
        create table if not exists pii(id text primary key, tenant text, principal text, kind text, purpose text, masked text,
            expires_at text, location text, erased_at text);
        create table if not exists rights(ref text primary key, tenant text, principal text, kind text, status text, ts text, detail text);
        create table if not exists transcripts(id integer primary key autoincrement, tenant text, principal text, role text, text text, ts text);
        create table if not exists state(tenant text, principal text, key text, value text, primary key(tenant,principal,key));
        """)

    # --- ledger
    def append_event(self, tenant, type, principal, payload=None):
        with self.lock:
            last = self.db.execute("select hash from events where tenant=? order by seq desc limit 1", (tenant,)).fetchone()
            prev = last["hash"] if last else GENESIS
            ev = {"type": type, "principal": principal, "payload": payload or {}, "ts": now().isoformat()}
            h = compute_hash(prev, ev)
            self.db.execute("insert into events(tenant,ts,type,principal,event,prev_hash,hash) values(?,?,?,?,?,?,?)",
                            (tenant, ev["ts"], type, principal, json.dumps(ev), prev, h))
            self.db.commit()
            return h

    def events(self, tenant):
        rows = self.db.execute("select * from events where tenant=? order by seq", (tenant,)).fetchall()
        return [{"seq": r["seq"], "prev_hash": r["prev_hash"], "hash": r["hash"], "event": json.loads(r["event"])} for r in rows]

    def verify(self, tenant):
        return verify_chain(self.events(tenant))

    # --- state (e.g. notice_pending, lang)
    def get_state(self, tenant, principal, key, default=None):
        r = self.db.execute("select value from state where tenant=? and principal=? and key=?", (tenant, principal, key)).fetchone()
        return json.loads(r["value"]) if r else default

    def set_state(self, tenant, principal, key, value):
        with self.lock:
            self.db.execute("insert or replace into state values(?,?,?,?)", (tenant, principal, key, json.dumps(value)))
            self.db.commit()

    # --- consent
    def record_consent(self, tenant, principal, purpose, granted, channel, notice_version):
        with self.lock:
            self.db.execute("insert into consents(tenant,principal,purpose,granted,channel,notice_version,ts) values(?,?,?,?,?,?,?)",
                            (tenant, principal, purpose, int(granted), channel, notice_version, now().isoformat()))
            self.db.commit()
        self.append_event(tenant, "consent_granted" if granted else "consent_declined", principal,
                          {"purpose": purpose, "channel": channel, "notice_version": notice_version})

    def consent_state(self, tenant, principal) -> dict:
        """purpose -> latest granted bool"""
        out = {}
        for r in self.db.execute("select purpose, granted from consents where tenant=? and principal=? order by id", (tenant, principal)):
            out[r["purpose"]] = bool(r["granted"])
        return out

    def consents(self, tenant):
        return [dict(r) for r in self.db.execute("select * from consents where tenant=? order by id", (tenant,))]

    # --- PII register
    def record_pii(self, tenant, principal, kind, purpose, masked, retention_days, location="transcript"):
        pid = uuid.uuid4().hex
        exp = (now() + timedelta(days=retention_days)).isoformat()
        with self.lock:
            self.db.execute("insert into pii values(?,?,?,?,?,?,?,?,null)", (pid, tenant, principal, kind, purpose, masked, exp, location))
            self.db.commit()
        self.append_event(tenant, "pii_recorded", principal, {"kind": kind, "purpose": purpose, "expires_at": exp, "location": location})
        return pid

    def pii(self, tenant, principal=None):
        q, a = "select * from pii where tenant=?", [tenant]
        if principal:
            q += " and principal=?"; a.append(principal)
        return [dict(r) for r in self.db.execute(q, a)]

    # --- rights
    def create_rights_request(self, tenant, principal, kind, detail=""):
        ref = "R-" + uuid.uuid4().hex[:8].upper()
        with self.lock:
            self.db.execute("insert into rights values(?,?,?,?,?,?,?)", (ref, tenant, principal, kind, "open", now().isoformat(), detail))
            self.db.commit()
        self.append_event(tenant, "rights_request", principal, {"ref": ref, "kind": kind})
        return ref

    def rights(self, tenant):
        return [dict(r) for r in self.db.execute("select * from rights where tenant=? order by ts", (tenant,))]

    def log_transcript(self, tenant, principal, role, text):
        with self.lock:
            self.db.execute("insert into transcripts(tenant,principal,role,text,ts) values(?,?,?,?,?)", (tenant, principal, role, text, now().isoformat()))
            self.db.commit()

    def erase_principal(self, tenant, principal):
        """Local-mode erasure: transcripts + PII register. Ledger events are kept (hashed IDs only)."""
        with self.lock:
            n = self.db.execute("delete from transcripts where tenant=? and principal=?", (tenant, principal)).rowcount
            self.db.execute("update pii set erased_at=? where tenant=? and principal=? and erased_at is null", (now().isoformat(), tenant, principal))
            self.db.commit()
        self.append_event(tenant, "erasure_proof", principal, {"transcripts_deleted": n})
        return n
