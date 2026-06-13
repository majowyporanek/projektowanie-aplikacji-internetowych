"""Hero test dla ADR-4: EXCLUDE USING gist + tstzrange chroni przed double-bookingiem.

Scenariusz: dwóch userów w tej samej organizacji wysyła równolegle POST /bookings
na ten sam zasób, ten sam slot czasowy. Constraint na bazie musi wpuścić DOKŁADNIE
jeden, drugi powinien dostać 409.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.conftest import add_member_to_org, login, register_admin, unique_email


async def _new_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_concurrent_bookings_one_wins_one_409(client: AsyncClient):
    """HERO test ADR-4: dwa równoległe POSTy na identyczny slot → {201, 409}.

    Solo run jest deterministyczny (3/3 stabilnie). W pełnym suite może być
    flaky przez pytest-asyncio + asyncpg cleanup race - to NIE jest issue
    ADR-4 (constraint zawsze działa atomowo na bazie), tylko cleanup
    connection pool między testami. Demo na obronie: uruchom solo
    `pytest tests/test_race_condition.py`.
    """
    admin = await register_admin(client)
    member_email = await add_member_to_org(admin["org_id"])

    r = await client.post("/resources", json={"name": "Sala race"})
    assert r.status_code == 201
    resource_id = r.json()["id"]

    start = (datetime.now(timezone.utc) + timedelta(days=3)).replace(
        minute=0, second=0, microsecond=0
    )
    end = start + timedelta(hours=1)
    payload = {
        "resource_id": resource_id,
        "starts_at": start.isoformat(),
        "ends_at": end.isoformat(),
    }

    client_admin = await _new_client()
    client_member = await _new_client()
    try:
        await login(client_admin, admin["email"])
        await login(client_member, member_email)

        results = await asyncio.gather(
            client_admin.post("/bookings", json=payload),
            client_member.post("/bookings", json=payload),
            return_exceptions=False,
        )
    finally:
        await client_admin.aclose()
        await client_member.aclose()

    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 409], f"Spodziewane [201, 409], dostałam {statuses}"

    conflict = next(r for r in results if r.status_code == 409)
    assert "conflict" in conflict.json()["detail"].lower()


async def test_overlapping_bookings_serially(client: AsyncClient):
    """Drugi POST z czasowo nakładającym slotem (nawet częściowo) -> 409.

    Mniejszy nakładający się przypadek żeby pokazać że `&&` w EXCLUDE działa
    nie tylko na dokładnie te same przedziały.
    """
    admin = await register_admin(client)
    r = await client.post("/resources", json={"name": "Sala overlap"})
    resource_id = r.json()["id"]

    start1 = (datetime.now(timezone.utc) + timedelta(days=4)).replace(
        minute=0, second=0, microsecond=0
    )
    end1 = start1 + timedelta(hours=2)
    # Drugi slot zaczyna się 1h po starcie pierwszego (overlap)
    start2 = start1 + timedelta(hours=1)
    end2 = start2 + timedelta(hours=2)

    r1 = await client.post(
        "/bookings",
        json={
            "resource_id": resource_id,
            "starts_at": start1.isoformat(),
            "ends_at": end1.isoformat(),
        },
    )
    assert r1.status_code == 201

    r2 = await client.post(
        "/bookings",
        json={
            "resource_id": resource_id,
            "starts_at": start2.isoformat(),
            "ends_at": end2.isoformat(),
        },
    )
    assert r2.status_code == 409


async def test_back_to_back_bookings_allowed(client: AsyncClient):
    """Slot kończący się dokładnie wtedy, gdy zaczyna się kolejny -> OK.

    Sprawdza że tstzrange jest pół-otwarty `[start, end)` — `&&` nie traktuje
    sąsiadujących przedziałów jako konfliktu.
    """
    await register_admin(client)
    r = await client.post("/resources", json={"name": "Sala back-to-back"})
    resource_id = r.json()["id"]

    start1 = (datetime.now(timezone.utc) + timedelta(days=5)).replace(
        minute=0, second=0, microsecond=0
    )
    end1 = start1 + timedelta(hours=1)
    start2 = end1  # styk na sekundę
    end2 = start2 + timedelta(hours=1)

    r1 = await client.post(
        "/bookings",
        json={
            "resource_id": resource_id,
            "starts_at": start1.isoformat(),
            "ends_at": end1.isoformat(),
        },
    )
    r2 = await client.post(
        "/bookings",
        json={
            "resource_id": resource_id,
            "starts_at": start2.isoformat(),
            "ends_at": end2.isoformat(),
        },
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
