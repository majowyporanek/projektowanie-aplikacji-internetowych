# ADR-2: PostgreSQL + SQLAlchemy 2.0 (async) + Alembic

## Kontekst

Aplikacja wymaga warstwy persystencji dla 4 encji (User, Organization, Resource, Booking) z relacjami N:1 i 1:N między nimi. Najważniejsze ograniczenie: muszę móc atomowo wymusić, że dwa "aktywne" Bookingi tego samego Resource nie nakładają się w czasie (patrz ADR-4). Wymaga to konkretnej funkcjonalności bazy: range types + exclusion constraints.

Backend jest asynchroniczny (ADR-1, FastAPI + Uvicorn), więc baza również musi działać asynchronicznie, aby nie blokować pętli zdarzeń.

## Decyzja

PostgreSQL 16 + SQLAlchemy 2.0 (async API) + asyncpg + Alembic.

## Alternatywy

**SQLite** — pojedynczy plik, zero infrastruktury, idealny do prototypów. Brak range types i exclusion constraints sprawia, że strategia race condition z ADR-4 staje się niemożliwa. Pozostałoby SERIALIZABLE + globalny writer lock (SQLite dopuszcza jednego writera naraz) — działa, ale to inny problem i inna obrona. Wykluczone przez ADR-4.

**MySQL / MariaDB** — asynchroniczne drivery istnieją (aiomysql), ale brak `tstzrange` i `EXCLUDE USING gist`. Race conditions trzeba by obsługiwać przez SERIALIZABLE isolation + retry, patrz alternatywy z ADR-4. Funkcjonalnie wykluczone.

**MongoDB** — relacje N:1/1:N nie są natywne, integralność po stronie aplikacji. Sprawdzanie nakładających się przedziałów wymagałoby pełnego scanu kolekcji lub ręcznych indeksów — bez deklaratywnego constraintu.

**Tortoise ORM / Piccolo** — alternatywne async ORM-y. SQLAlchemy 2.0 jest dojrzalsze, ma typed declarative API (`Mapped[...]` + `mapped_column`), największą społeczność i natywne wsparcie dla Postgres-specific (`ExcludeConstraint`, `JSONB`, `TSTZRANGE`).

## Uzasadnienie

Wybór bazy jest podyktowany ADR-4: tylko Postgres ma `EXCLUDE USING gist` i `tstzrange`. Każda inna baza zmusiłaby do innej strategii zarządzania race conditions, a ta jest sercem projektu. Reszta to konsekwencje.

SQLAlchemy 2.0 daje typed declarative models (`Mapped[uuid.UUID]`) — IDE i mypy widzą typy, refactor jest bezpieczny. Async API (`AsyncSession`) zachowuje znajome wzorce ORM-owe, ale z await na operacjach I/O.

asyncpg jest natywnie async (nie wrapper na sync drivera), najszybszy dla Postgresa.

Alembic mapuje migracje na pliki w repo — historia zmian schematu jest w gicie, deploy = `alembic upgrade head`. Autogenerate wykrywa zmiany w modelach (nowa tabela, kolumna, FK), wystarczy do rutynowych przypadków. Bardziej złożone konstrukcje (jak właśnie `EXCLUDE USING gist` z `WHERE`) piszę ręcznie przez `op.execute("ALTER TABLE ... EXCLUDE ...")` — Alembic nie potrafi tego autogenerować, co nie stanowi problemu.

## Trade-offy

**Vendor lock-in na Postgresa.** Świadomy. Cały design (ADR-4) polega na Postgres-specific features. Migracja do innej bazy nie jest możliwa bez przeprojektowania core invariantu.

**Alembic autogenerate ma luki.** Nie wykrywa: exclusion constraints, partial indexes, GIN/GIST indexes z customowymi expressions, niektórych zmian w `CHECK`. Po każdym `--autogenerate` trzeba zerknąć w wygenerowany plik. Migracje sercowe (jak Booking z exclusion) piszę od początku ręcznie — bezpieczniej i lepiej rozumiem, co się dzieje.

**Async ORM ma własną specyfikę.** `await session.scalar(...)` zamiast `session.query(...).first()`. Eager loading przez `selectinload` zamiast lazy access (lazy loading w async jest problematyczny). Czasem trzeba sięgnąć po raw SQL przez `text()` (np. funkcje PostgreSQL typu `gen_random_uuid()`).

**Dodatkowy kontener.** docker-compose ma `db` jako osobną usługę z volume na `pgdata`. To wymóg R5 i tak (konteneryzacja).

**Pojedynczy connection pool.** Async SQLAlchemy + asyncpg trzymają pool per worker. Przy skalowaniu poziomym (więcej API workerów) suma connectionów rośnie — w produkcji wymaga pgbouncera. Out of scope dla MVP.
