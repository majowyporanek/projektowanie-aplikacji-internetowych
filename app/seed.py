"""Seed danymi demo: 2 organizacje, 4 userów (admin+member w każdej), 5 zasobów, 10 bookingów.

Uruchomienie wewnątrz kontenera api:
    docker compose exec api python -m app.seed

Skrypt jest idempotentny - jeśli organizacja "Acme Corp" już istnieje, kończy bez zmian.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.models.booking import Booking
from app.models.organization import Organization
from app.models.resource import Resource
from app.models.user import User

DEMO_PASSWORD = "password123"


async def seed() -> None:
    async with SessionLocal() as s:
        existing = await s.scalar(
            select(Organization).where(Organization.name == "Acme Corp")
        )
        if existing is not None:
            print("Seed już był (Acme Corp istnieje). Pomijam.")
            return

        acme = Organization(name="Acme Corp")
        beta = Organization(name="Beta Studio")
        s.add_all([acme, beta])
        await s.flush()

        users = [
            User(
                email="alice@example.com",
                password_hash=hash_password(DEMO_PASSWORD),
                organization_id=acme.id,
                role="admin",
            ),
            User(
                email="bob@example.com",
                password_hash=hash_password(DEMO_PASSWORD),
                organization_id=acme.id,
                role="member",
            ),
            User(
                email="carol@example.com",
                password_hash=hash_password(DEMO_PASSWORD),
                organization_id=beta.id,
                role="admin",
            ),
            User(
                email="dave@example.com",
                password_hash=hash_password(DEMO_PASSWORD),
                organization_id=beta.id,
                role="member",
            ),
        ]
        alice, bob, carol, dave = users
        s.add_all(users)
        await s.flush()

        resources = [
            Resource(
                organization_id=acme.id,
                name="Sala A",
                description="Salka konferencyjna na 8 osób",
            ),
            Resource(
                organization_id=acme.id,
                name="Sala B",
                description="Salka na 4 osoby",
            ),
            Resource(
                organization_id=acme.id,
                name="Projektor BENQ",
                description="Mobilny, do biura",
            ),
            Resource(
                organization_id=beta.id,
                name="Studio fotograficzne",
                description="Białe tło, 30m²",
            ),
            Resource(
                organization_id=beta.id,
                name="Aparat Sony A7",
                description="Z obiektywem 50mm",
            ),
        ]
        sala_a, sala_b, projektor, studio, aparat = resources
        s.add_all(resources)
        await s.flush()

        # zaokrąglenie do najbliższej pełnej godziny w przyszłości
        h = datetime.now(timezone.utc).replace(
            minute=0, second=0, microsecond=0
        ) + timedelta(hours=1)

        bookings = [
            Booking(
                organization_id=acme.id,
                resource_id=sala_a.id,
                user_id=alice.id,
                starts_at=h + timedelta(days=2, hours=9),
                ends_at=h + timedelta(days=2, hours=10),
                status="confirmed",
                notes="Daily standup",
            ),
            Booking(
                organization_id=acme.id,
                resource_id=sala_a.id,
                user_id=bob.id,
                starts_at=h + timedelta(days=2, hours=13),
                ends_at=h + timedelta(days=2, hours=15),
                status="confirmed",
                notes="Spotkanie z klientem",
            ),
            Booking(
                organization_id=acme.id,
                resource_id=sala_b.id,
                user_id=alice.id,
                starts_at=h + timedelta(days=2, hours=8),
                ends_at=h + timedelta(days=2, hours=9),
                status="confirmed",
            ),
            Booking(
                organization_id=acme.id,
                resource_id=sala_b.id,
                user_id=alice.id,
                starts_at=h + timedelta(days=3, hours=14),
                ends_at=h + timedelta(days=3, hours=15),
                status="confirmed",
                notes="Review tygodnia",
            ),
            Booking(
                organization_id=acme.id,
                resource_id=projektor.id,
                user_id=bob.id,
                starts_at=h + timedelta(days=2, hours=11),
                ends_at=h + timedelta(days=2, hours=13),
                status="confirmed",
                notes="Prezentacja zarządowi",
            ),
            Booking(
                organization_id=acme.id,
                resource_id=sala_a.id,
                user_id=alice.id,
                starts_at=h + timedelta(days=3, hours=10),
                ends_at=h + timedelta(days=3, hours=11),
                status="confirmed",
                notes="Sync z marketingiem",
            ),
            Booking(
                organization_id=acme.id,
                resource_id=sala_b.id,
                user_id=bob.id,
                starts_at=h + timedelta(days=4, hours=14),
                ends_at=h + timedelta(days=4, hours=15),
                status="cancelled",
                notes="Plan się zmienił",
            ),
            Booking(
                organization_id=beta.id,
                resource_id=studio.id,
                user_id=carol.id,
                starts_at=h + timedelta(days=2, hours=9),
                ends_at=h + timedelta(days=2, hours=12),
                status="confirmed",
                notes="Sesja portretowa - klient A",
            ),
            Booking(
                organization_id=beta.id,
                resource_id=aparat.id,
                user_id=dave.id,
                starts_at=h + timedelta(days=2, hours=15),
                ends_at=h + timedelta(days=2, hours=17),
                status="confirmed",
                notes="Plener miejski",
            ),
            Booking(
                organization_id=beta.id,
                resource_id=aparat.id,
                user_id=dave.id,
                starts_at=h + timedelta(days=5, hours=11),
                ends_at=h + timedelta(days=5, hours=13),
                status="confirmed",
                notes="Sesja z zespołem",
            ),
        ]
        s.add_all(bookings)
        await s.commit()

        print("Seed OK:")
        print("  2 organizacje (Acme Corp, Beta Studio)")
        print("  4 userzy, 5 zasobów, 10 bookingów")
        print()
        print("Konta demo (hasło dla wszystkich: password123):")
        print("  alice@example.com  - admin  w Acme Corp")
        print("  bob@example.com    - member w Acme Corp")
        print("  carol@example.com  - admin  w Beta Studio")
        print("  dave@example.com   - member w Beta Studio")


if __name__ == "__main__":
    asyncio.run(seed())
