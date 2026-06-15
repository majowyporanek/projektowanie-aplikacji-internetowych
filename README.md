# Booking System

Projekt zaliczeniowy z przedmiotu **Projektowanie Aplikacji Internetowych** (UJ, 2025/2026).

System rezerwacji zasobów (sale, sprzęt) z obsługą multi-tenancy (organizacje) i odpornością na race conditions przy współbieżnych rezerwacjach.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async)
- **Baza:** PostgreSQL 16 + Alembic (kluczowo: `tstzrange` + `EXCLUDE USING gist` dla bookingów)
- **Cache:** Redis (cache dostępności zasobów z TTL + invalidacją)
- **Frontend:** HTMX + Jinja2 (SSR, zero bundlera)
- **Auth:** JWT w httpOnly cookie

Uzasadnienia wyborów: zobacz `docs/adr/`.

## Uruchomienie

```bash
cp .env.example .env

docker compose up --build
```

- API + frontend: http://localhost:8000
- Swagger / OpenAPI: http://localhost:8000/docs
- Health check: http://localhost:8000/health

Migracje uruchamiają się automatycznie przy starcie `api` (`alembic upgrade head`).

### Tworzenie nowej migracji

```bash
docker compose exec api alembic revision --autogenerate -m "add user table"
docker compose exec api alembic upgrade head
```

## Architektura

```
┌──────────────┐    HTTP     ┌─────────────┐   cache     ┌─────────────┐
│   Browser    │ ──────────► │   FastAPI   │ ──────────► │   Redis     │
│  HTMX/Jinja  │ ◄────────── │   (api)     │ ◄────────── │ (dostępność)│
└──────────────┘   HTML/JSON └──────┬──────┘  TTL + inval└─────────────┘
                                    │
                                    │ SQL
                                    ▼
                              ┌─────────────┐
                              │  Postgres   │
                              │  + Alembic  │
                              │  + gist     │
                              └─────────────┘
```

## Domena

```
User ─N:1─→ Organization ─1:N─→ Resource
  │                                 ▲
  │                                 │ N:1
  └───────── 1:N ──→ Booking ───────┘
```

- `User` — konto + rola (`member` / `admin`)
- `Organization` — najwyższa jednostka multi-tenancy (np. firma, klub, koło naukowe)
- `Resource` — sala / sprzęt, należy do `Organization`
- `Booking` — `tstzrange` z constraintem `EXCLUDE USING gist (resource_id WITH =, time_range WITH &&)`
