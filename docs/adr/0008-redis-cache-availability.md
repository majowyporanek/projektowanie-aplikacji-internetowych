# ADR-8: Cache dostępności zasobu w Redis

## Kontekst

Endpoint `GET /resources/{id}/availability?from=...&to=...` zwraca listę zajętych slotów (rezerwacji w statusie `pending` lub `confirmed`) dla danego zasobu w wybranym przedziale czasowym. To zapytanie jest naturalnie powtarzalne: użytkownik przewija kalendarz, zmienia widok dnia/tygodnia, wraca do tego samego widoku — za każdym razem strona odpytuje o ten sam zasób w tym samym lub bardzo podobnym oknie czasowym.

W typowym scenariuszu kalendarza zespołowego dwóch użytkowników z tej samej organizacji w ciągu minuty otwiera widok tego samego pokoju na ten sam tydzień. Dwa identyczne zapytania → dwa razy ten sam SQL (JOIN, partial index na `(resource_id)` z filtrem `status IN ('pending','confirmed')` + zakres czasu). Wynik jest niezmienny między tworzeniem/anulowaniem rezerwacji, czyli najczęściej.

Redis jest w stacku wyłącznie dla tego cache — to jego jedyna rola, odkąd zrezygnowałam z Celery (patrz ADR-7). Świadomie godzę się na jedną dodatkową usługę w `docker-compose`, bo cache z dyscypliną TTL + invalidacja jest tu realnym elementem do pokazania, a nie dekoracją.

## Decyzja

Wprowadzam cache na poziomie response w Redis:

- Klucz: `availability:{organization_id}:{resource_id}:{from_iso}:{to_iso}` — multi-tenancy w prefiksie, żeby było widać że to NIE jest globalny cache i że żaden cross-tenant lookup nie może go dotknąć.
- Wartość: JSON list `{starts_at, ends_at, status}`.
- TTL: 60 sekund — krótki, ale wystarczający, by zaabsorbować typowe serie kliknięć w UI.
- Invalidacja na zapis: po udanym `POST /bookings` i po `POST /bookings/{id}/cancel` usuwam wszystkie klucze pasujące do prefiksu `availability:{org}:{resource}:` przez `SCAN` + `DEL`.
- Response zawiera flagę `cached: bool` — głównie do testowania i obserwowalności, w produkcji wewnętrzny detal.

## Alternatywy

**Brak cache, polegamy na partial indexie w bazie.** Index `ix_booking_organization_id` + EXCLUDE USING gist na `(resource_id, tstzrange(...))` z `WHERE status IN ('pending','confirmed')` już jest, więc kwerenda jest szybka. Realistycznie dla mojego MVP byłoby to wystarczające. Wybrałam cache nie dla wydajności, lecz żeby zademonstrować pełną integrację Redisa z aplikacją (element bonusowy z dokumentu wymagań) i jednocześnie mieć ADR o trudnej dyscyplinie "cache invalidation".

**In-memory cache w procesie API** (`functools.lru_cache`, `cachetools`). Najprostsze, zero infrastruktury. Wykluczone przy >1 workerze (każdy worker ma własną kopię — niespójność), nie przetrwa restartu i fundamentalnie miesza warstwy: cache to data plane, nie process state.

**Materialized view w Postgresie** + `REFRESH MATERIALIZED VIEW CONCURRENTLY` przy zmianach. Czyste rozwiązanie z punktu widzenia spójności (transakcja widzi swoje zmiany), ale `REFRESH` blokuje albo wymaga `CONCURRENTLY` (które wymaga unique indexu i scanuje całą tabelę). Dla 50 rezerwacji to przesada. Dla 50 milionów rozważyłabym.

**Cache na podstawie ETag + `If-None-Match`** (HTTP caching). Działa świetnie dla publicznych zasobów, ale availability zależy od `organization_id`, więc cache HTTP musiałby per-user. Komplikuje warstwę CDN/proxy. Redis daje pełną kontrolę.

**Trigger Postgresowy z LISTEN/NOTIFY** wysyłający invalidację do Redisa. Architektonicznie eleganckie (cache invalidate trzymane razem ze źródłem prawdy), ale wymaga osobnego subscribera w aplikacji i jest cięższe do debugowania niż invalidacja explicite w endpoincie.

## Uzasadnienie

Cache invalidation jest [jednym z dwóch trudnych problemów w computer science](https://martinfowler.com/bliki/TwoHardThings.html), więc obrona musi być przemyślana. Mam dwie linie obrony:

1. **TTL 60 sekund** — twardy bound na stale data. Nawet gdybym w przyszłości dodała nowy endpoint piszący do `Booking` i zapomniała o invalidacji, niespójność trwa max minutę.
2. **Explicit invalidacja w `POST /bookings` i `POST /bookings/{id}/cancel`** — w typowym przypadku cache jest zawsze świeży po zmianie.

Prefiks z `organization_id` w kluczu jest świadomy: nawet gdybym kiedykolwiek miała bug w endpoincie który pomylił by tenanty, cache trzyma się tej samej dyscypliny co reszta kodu — każdy lookup zaczyna się od organizacji.

Invalidacja przez `SCAN` (a nie `KEYS`) — `KEYS` blokuje Redis przy dużej liczbie kluczy, `SCAN` iteruje paczkami po 200. Na małej skali nie ma różnicy, ale przyzwyczajenie operacyjne się liczy.

JSON jako format zamiast pickle — czytelny w `redis-cli` przy debugowaniu, bezpieczny (deserializacja pickle to RCE, jeśli ktoś umieści spreparowane dane w Redisie), wieloplatformowy.

## Trade-offy

**Eventual consistency w obrębie TTL.** Jeśli A tworzy rezerwację i invalidacja Redisa się nie powiedzie (timeout, restart), to B przez do 60 sekund widzi stary stan. **Nie jest to problem dla samego mechanizmu rezerwacji** — `EXCLUDE USING gist` z ADR-4 i tak odrzuci konflikt w bazie. Cache jest tylko hintem "co jest zajęte"; źródło prawdy to baza.

**`SCAN` invalidacja jest niedeterministyczna.** Jeśli między `SCAN` a `DEL` ktoś doda nowy klucz pasujący do prefiksu, nie zostanie usunięty. Akceptowalne — TTL i tak go wkrótce usunie. W produkcji można by używać Redis sets do śledzenia kluczy per tenant, ale to rozwiązanie nadmiarowe dla MVP.

**Cache jest invalidated globally per resource** — nie per zakres czasowy. Jeśli ktoś tworzy rezerwację na pojutrze, kasujemy też cache dla "dzisiaj". To nadmierne czyszczenie, ale poprawne. Skomplikowana invalidacja per-range byłaby źródłem subtelnych bugów (np. zapomnieć o sąsiednich tygodniach).

**Singleton Redis client.** `app/cache.py` trzyma jeden `Redis.from_url(...)` na proces — wewnętrznie biblioteka zarządza connection poolem. Przy `--reload` uvicorna mogą pozostawać porzucone connectiony — w devie nieszkodliwe, w prodzie nie używamy `--reload`.

**Dodatkowa zależność na ścieżce krytycznej zapisu.** `POST /bookings` teraz robi też `SCAN` + `DEL` w Redisie. Jeśli Redis ulegnie awarii, request jako całość nie zakończy się błędem cicho (Redis client rzuci wyjątek po `await session.commit()`), ale użytkownik otrzyma 500. Można by to opakować w try/except i zignorować błąd inwalidacji cache — ale wtedy nieaktualne dane zostają na cały TTL, co w trakcie awarii Redisa może oznaczać dłuższą niespójność. Świadomie wybieram fail-fast: lepsze 500 i ponowienie niż udawanie, że wszystko działa poprawnie.
