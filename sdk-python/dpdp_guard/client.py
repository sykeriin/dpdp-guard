"""HttpStore: same interface as LocalStore, backed by the hosted ledger API."""
import httpx


class HttpStore:
    def __init__(self, base_url: str, api_key: str, timeout: float = 5.0, client: httpx.Client | None = None):
        self.c = client or httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)

    def _post(self, path, **body):
        r = self.c.post(path, json=body); r.raise_for_status(); return r.json()

    def _get(self, path, **params):
        r = self.c.get(path, params=params); r.raise_for_status(); return r.json()

    # tenant arg is ignored: the API key identifies the tenant
    def append_event(self, tenant, type, principal, payload=None):
        return self._post("/v1/events", type=type, principal=principal, payload=payload or {})["hash"]

    def get_state(self, tenant, principal, key, default=None):
        v = self._get("/v1/state", principal=principal, key=key).get("value")
        return default if v is None else v

    def set_state(self, tenant, principal, key, value):
        self._post("/v1/state", principal=principal, key=key, value=value)

    def record_consent(self, tenant, principal, purpose, granted, channel, notice_version):
        self._post("/v1/consents", principal=principal, purpose=purpose, granted=granted, channel=channel, notice_version=notice_version)

    def consent_state(self, tenant, principal):
        return self._get("/v1/consents/state", principal=principal)

    def record_pii(self, tenant, principal, kind, purpose, masked, retention_days, location="transcript"):
        return self._post("/v1/pii", principal=principal, kind=kind, purpose=purpose, masked=masked,
                          retention_days=retention_days, location=location)["id"]

    def create_rights_request(self, tenant, principal, kind, detail=""):
        return self._post("/v1/rights-requests", principal=principal, kind=kind, detail=detail)["ref"]

    def log_transcript(self, tenant, principal, role, text):
        self._post("/v1/transcripts", principal=principal, role=role, text=text)
