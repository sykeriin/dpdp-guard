import os, uuid
os.environ["ADMIN_TOKEN"] = "adm"
import pytest
from fastapi.testclient import TestClient
from app import db
from app.main import app

@pytest.fixture(scope="session", autouse=True)
def schema():
    db.init_schema()

@pytest.fixture
def tenant():
    tid = "t_" + uuid.uuid4().hex[:8]
    c = TestClient(app)
    key = c.post("/admin/tenants", json={"id": tid, "name": "Acme"}, headers={"X-Admin-Token": "adm"}).json()["api_key"]
    c.headers["Authorization"] = f"Bearer {key}"
    return tid, c
