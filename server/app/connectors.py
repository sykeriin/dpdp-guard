"""Erasure connectors. Contract: customers tag records in their own stores with the principal hash
(Guard.pid(user_id)); connectors delete by that tag. Each returns {"deleted": int, "detail": str}.
Verified in tests: transcripts, sql (pgvector-style table), webhook. UNVERIFIED against live APIs: hubspot, zoho, pinecone."""
import hashlib
import hmac
import json
import re

import httpx
import psycopg

from . import db

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(s):
    if not _IDENT.match(s):
        raise ValueError(f"bad identifier {s!r}")
    return s


def transcripts(tenant, principal, config, job):
    with db.tenant_cur(tenant) as cur:
        cur.execute("delete from transcripts where tenant_id=%s and principal=%s", (tenant, principal))
        return {"deleted": cur.rowcount, "detail": "built-in transcript store"}


def sql(tenant, principal, config, job):
    """Generic/pgvector: delete from <table> where <column> = principal. config: dsn, table, column (default principal)."""
    table, col = _ident(config["table"]), _ident(config.get("column", "principal"))
    with psycopg.connect(config["dsn"], autocommit=True) as c:
        cur = c.execute(f"delete from {table} where {col} = %s", (principal,))
        return {"deleted": cur.rowcount, "detail": f"{table}.{col}"}


def webhook(tenant, principal, config, job):
    body = json.dumps({"principal": principal, "job_id": job["id"], "scope": job.get("scope", "all"), "reason": job.get("reason")}).encode()
    sig = hmac.new(config["secret"].encode(), body, hashlib.sha256).hexdigest()
    r = httpx.post(config["url"], content=body, headers={"X-Guard-Signature": sig, "Content-Type": "application/json"}, timeout=15)
    r.raise_for_status()
    try:
        n = int(r.json().get("deleted", 0))
    except Exception:
        n = 0
    return {"deleted": n, "detail": f"webhook {r.status_code}"}


def hubspot(tenant, principal, config, job):  # UNVERIFIED
    h = {"Authorization": f"Bearer {config['token']}"}
    prop = config.get("property", "dpdp_principal")
    r = httpx.post("https://api.hubapi.com/crm/v3/objects/contacts/search", headers=h, timeout=15,
                   json={"filterGroups": [{"filters": [{"propertyName": prop, "operator": "EQ", "value": principal}]}]})
    r.raise_for_status()
    n = 0
    for c in r.json().get("results", []):
        d = httpx.post("https://api.hubapi.com/crm/v3/objects/contacts/gdpr-delete", headers=h, json={"objectId": c["id"]}, timeout=15)
        d.raise_for_status(); n += 1
    return {"deleted": n, "detail": "hubspot gdpr-delete"}


def zoho(tenant, principal, config, job):  # UNVERIFIED
    h = {"Authorization": f"Zoho-oauthtoken {config['token']}"}
    base = config.get("api_domain", "https://www.zohoapis.in")
    field = config.get("field", "DPDP_Principal")
    r = httpx.get(f"{base}/crm/v2/Contacts/search", headers=h, params={"criteria": f"({field}:equals:{principal})"}, timeout=15)
    if r.status_code == 204:
        return {"deleted": 0, "detail": "zoho no match"}
    r.raise_for_status()
    ids = ",".join(x["id"] for x in r.json().get("data", []))
    if ids:
        httpx.delete(f"{base}/crm/v2/Contacts", headers=h, params={"ids": ids}, timeout=15).raise_for_status()
    return {"deleted": len(ids.split(",")) if ids else 0, "detail": "zoho delete"}


def pinecone(tenant, principal, config, job):  # UNVERIFIED; metadata-filter delete is not supported on all index types
    r = httpx.post(f"{config['host']}/vectors/delete", headers={"Api-Key": config["api_key"]}, timeout=15,
                   json={"filter": {config.get("field", "principal"): {"$eq": principal}}, "namespace": config.get("namespace", "")})
    r.raise_for_status()
    return {"deleted": -1, "detail": "pinecone filter delete (count unknown)"}


# connectors that receive the job scope and can honour a single purpose (webhook gets scope in its payload)
PURPOSE_AWARE = {"webhook"}

def gsheets(tenant, principal, config, job):  # UNVERIFIED against the live API; tested with a mocked HTTP layer only
    """Delete rows whose <column> equals the principal hash. config: token (OAuth/service-account bearer), spreadsheet_id,
    sheet_name, sheet_id (numeric gid), column (0-based index, default 0). Rows are deleted bottom-up so indexes stay valid."""
    h = {"Authorization": f"Bearer {config['token']}"}
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{config['spreadsheet_id']}"
    col = int(config.get("column", 0))
    r = httpx.get(f"{base}/values/{config['sheet_name']}", headers=h, timeout=15)
    r.raise_for_status()
    rows = r.json().get("values", [])
    hits = [i for i, row in enumerate(rows) if len(row) > col and row[col] == principal]
    if not hits:
        return {"deleted": 0, "detail": "gsheets no match"}
    reqs = [{"deleteDimension": {"range": {"sheetId": int(config["sheet_id"]), "dimension": "ROWS", "startIndex": i, "endIndex": i + 1}}} for i in reversed(hits)]
    httpx.post(f"{base}:batchUpdate", headers=h, json={"requests": reqs}, timeout=15).raise_for_status()
    return {"deleted": len(hits), "detail": "gsheets deleteDimension"}


REGISTRY = {"gsheets": gsheets, "transcripts": transcripts, "sql": sql, "pgvector": sql, "webhook": webhook, "hubspot": hubspot, "zoho": zoho, "pinecone": pinecone}
