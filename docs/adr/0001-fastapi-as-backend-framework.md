# ADR-1: FastAPI jako framework backendowy
## Kontekst

Piszę backend dla systemu rezerwacji w Pythonie. Apka ma kilkanaście endpointów (CRUD na zasobach i rezerwacjach + login/register), gada z PostgreSem i z Redisem (cache dostępności). Muszę gdzieś walidować payloady (wymaganie R5) i ładnie byłoby mieć dokumentację API bez pisania jej ręcznie.

Python wybrałam wcześniej — bo w nim umiem i ma dojrzały ekosystem do tego, co robię. Pytanie tylko: który framework.

## Decyzja

FastAPI (0.115+) na Uvicornie.

## Alternatywy

**Flask** — pierwszy odruch, bo to mikroframework i wszyscy go znają. Odpadł, bo jest domyślnie synchroniczny, a ja chcę async (asyncpg + `redis.asyncio`). Walidację trzeba doklejać marshmallowem albo pydantikiem ręcznie. OpenAPI też nie ma z pudełka — trzeba `flasgger` albo `flask-smorest`. Czyli i tak musiałabym pozszywać te same klocki co już są w FastAPI.

**Django + DRF** — kompletny, ma admin panel, ORM, migracje. Ale na 4 modele i 15 endpointów to przerost formy nad treścią. Admin byłby nieużywany (jedynym adminem jestem ja i pracuję w konsoli), a konwencje DRF (ViewSets, Serializers, routery) wymagają osobnej krzywej uczenia. Django ORM dopiero zaczyna być async, więc i tak musiałabym kombinować.

**Litestar** — filozoficznie bliski FastAPI, czasem lepiej zaprojektowany (np. DI). Ale młodszy, mniejsza społeczność i przy obronie projektu trudniej powiedzieć "wybrałam, bo dojrzały". Nie warto ryzykować na zaliczeniu.

## Uzasadnienie

Najbardziej istotne dla mnie było to, że FastAPI dostaje OpenAPI/Swagger za darmo z type hintów i Pydantic — wymaganie "dokumentacja API" odhaczone bez minuty roboty. Drugie: Pydantic robi walidację, serializację i dokumentację z jednego źródła. Jeden mechanizm zamiast trzech.

Async pasuje do reszty stacku — asyncpg do Postgresa, `redis.asyncio` do cache dostępności. Przy race conditions na rezerwacjach (główna ADR projektu, patrz ADR-4) async event loop trzyma się lepiej niż gunicorn z sync workerami.

System dependency injection przez `Depends()` jest dla mnie kluczowy ze względu na multi-tenancy — `get_current_user`, `get_current_org` i `get_session` wstrzykuję deklaratywnie do każdego handlera. Filtr `organization_id` nie powtarza się w każdym query, tylko siedzi w jednym dependency. Mniejsze ryzyko zapomnienia = mniejsze ryzyko data leaka między tenantami.

Krzywą uczenia mam za sobą — pisałam już w FastAPI wcześniej.

## Trade-offy

Nie dostaję admin panelu jak w Django. Akceptuję — użytkownicy końcowi mają HTMX views, a ja jedyna admin używam SQL-a albo Swaggera.

Async wymaga dyscypliny. Wystarczy jedno blokujące wywołanie (`requests.get` zamiast `httpx.AsyncClient`) i zatyka się event loop. Pilnuję, żeby całe I/O szło przez async klienty (asyncpg, `redis.asyncio`, `httpx`).

FastAPI daje narzędzia, nie strukturę — to ja decyduję, jak ułożyć `app/api/`, `app/models/`, `app/web/`. W Django struktura jest narzucona i to bywa wygodne. Tu wolę elastyczność, bo apka jest mała i własna struktura jest prostsza niż walka z konwencjami.

Auth muszę napisać sama, bo nie ma czegoś jak `django-allauth`. Ale scope auth tutaj jest mały (login/register/logout, JWT w cookie — ADR-5), więc nie jest to dużo kodu.
