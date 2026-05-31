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
| ADR-2 | PostgreSQL + SQLAlchemy + Alembic | todo |
| [ADR-3](0003-htmx-jinja-zamiast-spa.md) | HTMX + Jinja zamiast SPA | ✓ |
| ADR-4 | Strategia race conditions: EXCLUDE USING gist + tstzrange | todo |
| ADR-5 | JWT cookie auth zamiast OAuth/sesji serwerowych | todo |
| [ADR-6](0006-multi-tenancy-shared-schema.md) | Multi-tenancy: shared schema z organization_id | ✓ |
| ADR-7 | Celery + Redis dla email reminders | todo |
