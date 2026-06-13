import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.db as _db
from app.auth.passwords import hash_password
from app.config import settings

# W testach każda sesja musi dostać świeży connection - asyncpg connection jest
# związany z event loopem, a pytest-asyncio często rotuje loopy między testami.
# NullPool nie cachuje connectionów, więc problem znika.
_test_engine = create_async_engine(settings.database_url, poolclass=NullPool, future=True)
_db.engine = _test_engine
_db.SessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)

import app.cache as _cache  # noqa: E402
from app.db import SessionLocal  # noqa: E402  (po podmianie)
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset_redis_singleton():
    """Redis async client jest bound do event loopa w którym powstał.
    Pytest-asyncio rotuje event loopy między testami, więc resetujemy singleton
    przed każdym testem - client zostanie odtworzony przy pierwszym wywołaniu.
    """
    if _cache._redis is not None:
        try:
            await _cache._redis.aclose()
        except Exception:
            pass
        _cache._redis = None
    yield
    if _cache._redis is not None:
        try:
            await _cache._redis.aclose()
        except Exception:
            pass
        _cache._redis = None


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def unique_email(prefix: str = "u") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}@example.com"


def unique_org() -> str:
    return f"Org_{uuid.uuid4().hex[:8]}"


async def register_admin(client: AsyncClient) -> dict:
    """Tworzy nową organizację — pierwszy user = admin. Zwraca {email, password, user_dict, org_id}."""
    email = unique_email("admin")
    password = "password123"
    r = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "organization_name": unique_org(),
        },
    )
    assert r.status_code == 201, r.text
    user = r.json()
    return {
        "email": email,
        "password": password,
        "user": user,
        "org_id": user["organization_id"],
    }


async def add_member_to_org(org_id: str, email: str | None = None) -> str:
    """Bezpośredni INSERT membera (brak endpointu invite). Zwraca email."""
    email = email or unique_email("member")
    async with SessionLocal() as s:
        s.add(
            User(
                email=email,
                password_hash=hash_password("password123"),
                organization_id=uuid.UUID(org_id),
                role="member",
            )
        )
        await s.commit()
    return email


async def login(client: AsyncClient, email: str, password: str = "password123") -> None:
    """Loguje, cookie ląduje w cookie jarze klienta."""
    r = await client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
