# ADR-1: FastAPI jako framework backendowy
## Kontekst

Piszę backend dla systemu rezerwacji w Pythonie. Aplikacja ma kilkanaście endpointów (CRUD na zasobach i rezerwacjach + login/register), komunikuje się z PostgreSQL i z Redisem (cache dostępności). Muszę walidować dane wejściowe (wymaganie R5) i zależy mi na dokumentacji API generowanej automatycznie, bez pisania jej ręcznie.

Python wybrałam wcześniej — bo mam w nim doświadczenie i dysponuje on dojrzałym ekosystemem do tego, co realizuję. Pozostaje pytanie: który framework.

## Decyzja

FastAPI (0.115+) na Uvicornie.

## Alternatywy

**Flask** — naturalny pierwszy wybór jako mikroframework o szerokiej rozpoznawalności. Odrzucam go, ponieważ jest domyślnie synchroniczny, a potrzebuję async (asyncpg + `redis.asyncio`). Walidację trzeba dodawać ręcznie (marshmallow albo Pydantic), a OpenAPI nie jest dostępne natywnie — wymaga `flasgger` albo `flask-smorest`. Musiałabym więc samodzielnie złożyć te same komponenty, które FastAPI udostępnia od razu.

**Django + DRF** — kompletny, ma panel administracyjny, ORM, migracje. Ale dla 4 modeli i 15 endpointów jest to rozwiązanie nadmiarowe wobec skali. Panel administracyjny pozostałby nieużywany (jedynym administratorem jestem ja i pracuję w konsoli), a konwencje DRF (ViewSets, Serializers, routery) wymagają osobnej krzywej uczenia. Django ORM dopiero wchodzi w fazę async, więc i tak wymagałby obejść.

**Litestar** — filozoficznie bliski FastAPI, miejscami lepiej zaprojektowany (np. DI). Jest jednak młodszy, ma mniejszą społeczność i przy obronie projektu trudniej uzasadnić jego wybór dojrzałością. Nie chcę podejmować tego ryzyka w projekcie zaliczeniowym.

## Uzasadnienie

Najistotniejsze było dla mnie to, że FastAPI generuje OpenAPI/Swagger automatycznie z type hintów i Pydantic — wymaganie "dokumentacja API" spełnione bez dodatkowego nakładu pracy. Drugie: Pydantic zapewnia walidację, serializację i dokumentację z jednego źródła. Jeden mechanizm zamiast trzech.

Async pasuje do reszty stacku — asyncpg do PostgreSQL, `redis.asyncio` do cache dostępności. Przy race conditions na rezerwacjach (główna decyzja projektu, patrz ADR-4) asynchroniczna pętla zdarzeń sprawdza się lepiej niż gunicorn z synchronicznymi workerami.

System dependency injection przez `Depends()` jest dla mnie kluczowy ze względu na multi-tenancy — `get_current_user`, `get_current_org` i `get_session` wstrzykuję deklaratywnie do każdego handlera. Filtr `organization_id` nie powtarza się w każdym query, lecz znajduje się w jednym dependency. Mniejsze ryzyko pominięcia oznacza mniejsze ryzyko wycieku danych między tenantami.

Krzywą uczenia mam już za sobą — pisałam w FastAPI wcześniej.

## Trade-offy

Nie otrzymuję panelu administracyjnego jak w Django. Akceptuję to — użytkownicy końcowi mają widoki HTMX, a ja jako jedyny administrator korzystam z SQL-a albo Swaggera.

Async wymaga dyscypliny. Wystarczy jedno blokujące wywołanie (`requests.get` zamiast `httpx.AsyncClient`) i pętla zdarzeń się blokuje. Dbam, aby całe I/O przechodziło przez asynchroniczne klienty (asyncpg, `redis.asyncio`, `httpx`).

FastAPI daje narzędzia, nie strukturę — to ja decyduję, jak ułożyć `app/api/`, `app/models/`, `app/web/`. W Django struktura jest narzucona, co bywa wygodne. Tu wolę elastyczność, bo aplikacja jest mała, a własna struktura jest prostsza niż dostosowywanie się do narzuconych konwencji.

Autentykację muszę napisać samodzielnie, bo nie ma odpowiednika `django-allauth`. Ale jej zakres jest tu niewielki (login/register/logout, JWT w cookie — ADR-5), więc nie jest to dużo kodu.
