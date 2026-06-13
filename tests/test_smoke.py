from datetime import datetime, timedelta, timezone

from httpx import AsyncClient

from tests.conftest import (
    add_member_to_org,
    login,
    register_admin,
)


async def test_register_creates_admin(client: AsyncClient):
    ctx = await register_admin(client)
    assert ctx["user"]["role"] == "admin"
    assert ctx["user"]["organization_id"]


async def test_login_sets_cookie(client: AsyncClient):
    ctx = await register_admin(client)
    client.cookies.clear()
    r = await client.post(
        "/auth/login",
        json={"email": ctx["email"], "password": ctx["password"]},
    )
    assert r.status_code == 200
    assert "access_token" in r.cookies


async def test_cross_org_resource_invisible(client: AsyncClient):
    """User z org A nie widzi zasobu z org B (multi-tenancy boundary)."""
    # Org A + zasób w org A
    a = await register_admin(client)
    r = await client.post("/resources", json={"name": "Sala A"})
    assert r.status_code == 201
    resource_a_id = r.json()["id"]

    # Org B (świeży klient = świeży cookie jar)
    client.cookies.clear()
    await register_admin(client)
    listing = await client.get("/resources")
    assert listing.status_code == 200
    ids_visible_to_b = {r["id"] for r in listing.json()}
    assert resource_a_id not in ids_visible_to_b

    # 404 (nie 403) przy próbie GET cudzego zasobu — security through obscurity
    r = await client.get(f"/resources/{resource_a_id}")
    assert r.status_code == 404


async def test_member_cannot_create_resource(client: AsyncClient):
    """Member dostaje 403 na POST /resources. Admin dalej może."""
    admin_ctx = await register_admin(client)
    member_email = await add_member_to_org(admin_ctx["org_id"])

    # Member POST -> 403
    client.cookies.clear()
    await login(client, member_email)
    r = await client.post("/resources", json={"name": "Hack"})
    assert r.status_code == 403
    assert "admin" in r.json()["detail"].lower()

    # Admin POST -> 201 (sanity check)
    client.cookies.clear()
    await login(client, admin_ctx["email"])
    r = await client.post("/resources", json={"name": "Sala dozwolona"})
    assert r.status_code == 201


async def test_cancel_booking_owner_only(client: AsyncClient):
    """Owner może cancelować swój booking. Inny user dostaje 403."""
    admin_ctx = await register_admin(client)
    member_email = await add_member_to_org(admin_ctx["org_id"])

    # Admin tworzy zasób
    r = await client.post("/resources", json={"name": "Sala C"})
    assert r.status_code == 201
    resource_id = r.json()["id"]

    # Admin tworzy booking
    start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(
        minute=0, second=0, microsecond=0
    )
    end = start + timedelta(hours=1)
    r = await client.post(
        "/bookings",
        json={
            "resource_id": resource_id,
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
        },
    )
    assert r.status_code == 201, r.text
    booking_id = r.json()["id"]

    # Member (inna osoba w tej samej org) próbuje cancelować -> 403
    client.cookies.clear()
    await login(client, member_email)
    r = await client.post(f"/bookings/{booking_id}/cancel")
    assert r.status_code == 403

    # Owner (admin) cancel -> 200, status flips
    client.cookies.clear()
    await login(client, admin_ctx["email"])
    r = await client.post(f"/bookings/{booking_id}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"

    # Powtórny cancel -> 409
    r = await client.post(f"/bookings/{booking_id}/cancel")
    assert r.status_code == 409
