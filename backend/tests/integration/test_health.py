import re

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

# Closed port + fake password: connection is refused instantly and the fake
# password lets us assert credentials never leak into the response.
UNREACHABLE_URL = "postgresql+asyncpg://bevosita:sekretpw@127.0.0.1:59999/bevosita"


async def test_healthz_returns_ok_without_touching_db(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readyz_503_when_db_unreachable(client_factory):
    async with client_factory(UNREACHABLE_URL) as client:
        resp = await client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert set(body) == {"error"}
    err = body["error"]
    assert set(err) == {"code", "message_key", "detail", "request_id"}
    assert err["code"] == "NOT_READY"
    assert err["message_key"] == "errors.notReady"
    assert err["detail"] == "database_unreachable"
    assert err["request_id"]
    assert resp.headers["x-request-id"] == err["request_id"]
    for leak in ("sekretpw", "asyncpg", "postgresql", "127.0.0.1", "Traceback"):
        assert leak not in resp.text


async def test_readyz_503_when_migrations_not_at_head(
    client, test_database_url, db_at_head, alembic_head
):
    engine = create_async_engine(test_database_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(sa.text("UPDATE alembic_version SET version_num = 'deadbeefcafe'"))
        resp = await client.get("/readyz")
        assert resp.status_code == 503
        err = resp.json()["error"]
        assert err["code"] == "NOT_READY"
        assert err["message_key"] == "errors.notReady"
        assert err["detail"] == "migrations_out_of_date"
        assert err["request_id"]
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("UPDATE alembic_version SET version_num = :head"),
                {"head": alembic_head},
            )
        await engine.dispose()


async def test_readyz_200_when_db_reachable_and_at_head(client, db_at_head):
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}
    assert SAFE_REQUEST_ID.fullmatch(resp.headers["x-request-id"])


async def test_every_response_carries_request_id(client, db_at_head):
    for path in ("/healthz", "/readyz"):
        resp = await client.get(path)
        rid = resp.headers.get("x-request-id")
        assert rid, f"missing X-Request-ID on {path}"
        assert SAFE_REQUEST_ID.fullmatch(rid)


async def test_client_supplied_safe_request_id_is_kept(client):
    resp = await client.get("/healthz", headers={"X-Request-ID": "req-abc.123_XYZ"})
    assert resp.headers["x-request-id"] == "req-abc.123_XYZ"


async def test_unsafe_request_id_is_replaced(client):
    unsafe = "bad id {with} spaces"
    resp = await client.get("/healthz", headers={"X-Request-ID": unsafe})
    rid = resp.headers["x-request-id"]
    assert rid != unsafe
    assert SAFE_REQUEST_ID.fullmatch(rid)


async def test_oversized_request_id_is_replaced(client):
    oversized = "a" * 300
    resp = await client.get("/healthz", headers={"X-Request-ID": oversized})
    rid = resp.headers["x-request-id"]
    assert rid != oversized
    assert len(rid) <= 128
    assert SAFE_REQUEST_ID.fullmatch(rid)
