# Architecture Decision Records

Każda istotna decyzja architektoniczna mieszka tu jako osobny plik `NNNN-tytul.md`.

## Szablon wpisu

```markdown
# ADR-NNNN: Tytuł

## Kontekst
Jaki problem rozwiązujemy? Jakie są ograniczenia?

## Decyzja
Co wybraliśmy.

## Alternatywy
Co rozważaliśmy i dlaczego odpadło.

## Uzasadnienie
Dlaczego ten wybór w kontekście tego projektu.

## Trade-offy
Czego się wyrzekamy, jakie są konsekwencje.
```

## Lista ADR-ów

| ID | Tytuł | Status |
|---|---|---|
| [ADR-1](0001-fastapi-as-backend-framework.md) | FastAPI jako framework backendowy | ✓ |
| [ADR-2](0002-postgres-sqlalchemy-alembic.md) | PostgreSQL + SQLAlchemy + Alembic | ✓ |
| [ADR-3](0003-htmx-jinja-zamiast-spa.md) | HTMX + Jinja zamiast SPA | ✓ |
| [ADR-4](0004-race-conditions-exclude-using-gist.md) | Strategia race conditions: EXCLUDE USING gist + tstzrange | ✓ |
| [ADR-5](0005-jwt-cookie-auth.md) | JWT cookie auth zamiast OAuth/sesji serwerowych | ✓ |
| [ADR-6](0006-multi-tenancy-shared-schema.md) | Multi-tenancy: shared schema z organization_id | ✓ |
| [ADR-7](0007-celery-redis-task-queue.md) | Kolejka zadań (Celery + Redis) — rozważona i odrzucona | ✗ odrzucona |
| [ADR-8](0008-redis-cache-availability.md) | Cache dostępności zasobu w Redis | ✓ |
