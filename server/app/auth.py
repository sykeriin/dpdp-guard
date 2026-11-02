import hashlib
import os
import secrets

from fastapi import Header, HTTPException

from . import db


def hash_key(k: str) -> str:
    return hashlib.sha256(k.encode()).hexdigest()


def create_tenant(tenant_id: str, name: str) -> str:
    key = "dg_" + secrets.token_urlsafe(24)
    with db.raw_cur(db.ADMIN_URL) as cur:
        cur.execute("insert into tenants(id,name) values(%s,%s) on conflict do nothing", (tenant_id, name))
        cur.execute("insert into api_keys(key_hash,tenant_id,label) values(%s,%s,'default')", (hash_key(key), tenant_id))
    return key


def tenant_from_key(authorization: str = Header(default="")) -> str:
    key = authorization.removeprefix("Bearer ").strip()
    if not key:
        raise HTTPException(401, "missing API key")
    with db.raw_cur() as cur:
        cur.execute("select tenant_id from api_keys where key_hash=%s", (hash_key(key),))
        r = cur.fetchone()
    if not r:
        raise HTTPException(401, "invalid API key")
    return r["tenant_id"]


def require_admin(x_admin_token: str = Header(default="")):
    tok = os.environ.get("ADMIN_TOKEN", "")
    if not tok or not secrets.compare_digest(x_admin_token, tok):
        raise HTTPException(403, "admin only")
