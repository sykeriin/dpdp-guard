import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

APP_URL = os.environ.get("DATABASE_URL", "postgresql://guard_app:guard_app@localhost/dpdpguard")
ADMIN_URL = os.environ.get("ADMIN_DATABASE_URL", "postgresql://guard:guard@localhost/dpdpguard")
_pools: dict[str, ConnectionPool] = {}


def pool(url: str | None = None) -> ConnectionPool:
    url = url or APP_URL
    if url not in _pools:
        _pools[url] = ConnectionPool(url, min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=True)
    return _pools[url]


@contextmanager
def tenant_cur(tenant: str, url: str | None = None):
    """Transaction scoped to a tenant: RLS policy reads app.tenant."""
    with pool(url).connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select set_config('app.tenant', %s, true)", (tenant,))
            yield cur


@contextmanager
def raw_cur(url: str | None = None):
    with pool(url).connection() as conn:
        with conn.cursor() as cur:
            yield cur


def init_schema(admin_url: str | None = None):
    sql = (Path(__file__).parent.parent / "schema.sql").read_text()
    with psycopg.connect(admin_url or ADMIN_URL, autocommit=True) as c:
        c.execute(sql)
