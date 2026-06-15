# ADR-4: Strategia race conditions — EXCLUDE USING gist + tstzrange

## Kontekst

Centralny invariant systemu: jeden zasób nie może mieć dwóch nakładających się aktywnych rezerwacji. To jest pytanie obronne projektu — co zrobić, gdy dwa requesty równolegle próbują zarezerwować ten sam slot.

Naiwna implementacja jest broken:

```python
existing = await session.scalar(
    select(Booking).where(
        Booking.resource_id == resource_id,
        Booking.starts_at < ends_at,
        Booking.ends_at > starts_at,
        Booking.status.in_(("pending", "confirmed")),
    )
)
if existing is None:
    session.add(Booking(...))
    await session.commit()
```

Między `SELECT` a `INSERT` inny transaction może zacommitować swój wiersz. Oba dostają "no conflict found" w `SELECT`, oba commitują, mamy double-booking. Async + connection pool sprzyja temu szczególnie, bo wielu workerów obsługuje requesty równolegle.

## Decyzja

PostgreSQL `EXCLUDE USING gist` jako constraint na tabeli `booking`:

```sql
EXCLUDE USING gist (
    resource_id WITH =,
    tstzrange(starts_at, ends_at, '[)') WITH &&
) WHERE (status IN ('pending', 'confirmed'))
```

Wymagane rozszerzenie `btree_gist` (GIST natywnie obsługuje operatory zakresowe, ale nie `=` na UUID — `btree_gist` dodaje wsparcie B-tree do GIST). Migracja włącza je przez `CREATE EXTENSION IF NOT EXISTS btree_gist`.

Zakres half-open `[)`: rezerwacja 10:00-11:00 i 11:00-12:00 *nie* kolidują (typowe dla wydarzeń back-to-back). `WHERE status IN ('pending', 'confirmed')` — anulowane bookingi nie blokują slotów, ale zostają w tabeli dla historii.

Aplikacja łapie `sqlalchemy.exc.IntegrityError`, sprawdza `pgcode == '23P01'` (exclusion_violation) i zwraca 409 Conflict.

## Alternatywy

**SERIALIZABLE isolation** — Postgres potrafi wykryć konflikt zapisów na poziomie predicate locks i odrzucić jeden z transactionów z `serialization_failure`. Działa, ale wprowadza retry loop w aplikacji ("jeśli serialization failure, spróbuj ponownie z exponential backoff"). Trudniej rozumować, kiedy retry zadziała, a kiedy nie — i czy retry idempotent. Cena: kompleksowość kodu aplikacyjnego dla problemu, który baza może rozwiązać deklaratywnie.

**SELECT FOR UPDATE na wierszu Resource** — przed `INSERT` na booking robię `SELECT id FROM resource WHERE id = ? FOR UPDATE`. To serializuje wszystkie rezerwacje per resource. Działa, ale zabija concurrency: dwa requesty na różne sloty tego samego zasobu blokują się nawzajem bez powodu (logicznie nie kolidują).

**Distributed lock w Redis (SETNX z TTL)** — przed INSERT biorę lock per `resource_id`. Działa, ale dodaje infrastrukturalną zależność: invariant zaczyna zależeć od Redis i kodu aplikacyjnego, zamiast od bazy. Lock musi mieć TTL (bo aplikacja może umrzeć między lock a unlock), TTL musi być dłuższy niż request, ale krótki w razie crashu — kompromis bez czystego rozwiązania.

**Walidacja tylko w aplikacji bez zmiany izolacji** — patrz Kontekst, broken.

## Uzasadnienie

`EXCLUDE USING gist` przenosi invariant z kodu do schematu. Baza atomowo (w jednym statemencie `INSERT`) sprawdza, czy nowy wiersz nie koliduje z żadnym istniejącym, i odrzuca operację jeśli koliduje. Nie ma okna race window, nie ma retry, nie ma locków blokujących niezwiązane operacje.

To jest dokładnie ten feature, do którego Postgres dodał exclusion constraints — generalizacja UNIQUE na operatory dowolnego typu. Range types z `&&` (overlap) były dorzucone do Postgresa 9.2 między innymi po to.

Half-open zakresy `[)` pasują do domeny: wydarzenie kończące się o 11:00 i wydarzenie zaczynające się o 11:00 to dwa różne wydarzenia. Otwarte zakresy `()` byłyby błędne (rezerwacja 10:00-11:00 i 11:00-12:00 dla narzędzia, które trzeba fizycznie przekazać — wymaga buforu). Domknięte `[]` blokowałyby legalne back-to-back. `[)` jest standardem dla event scheduling.

Partial index `WHERE status IN (...)` to ważny szczegół — anulowanie booking nie kasuje wiersza (audit, statystyki, historia), a anulowany booking nie powinien blokować slotu. Constraint wymusza to po stronie bazy, w jednym miejscu, bez ifów w kodzie aplikacyjnym.

Performance: GIST index na `(resource_id, tstzrange)` daje O(log n) lookup czasowy — dla 100k rezerwacji w bazie sprawdzenie konfliktu to milisekundy. Bez indeksu trzeba by skanować wszystkie wiersze danego resource.

## Trade-offy

**Deadlock zamiast czystego 409 pod prawdziwą współbieżnością.** `EXCLUDE USING gist`
przy dwóch *naprawdę* równoczesnych INSERT-ach nie zawsze daje `23P01` — obie
transakcje wstawiają wiersz i każda czeka, aż druga się zacommituje, żeby sprawdzić
konflikt. Postgres wykrywa to jako deadlock (`40P01`) i zabija jedną transakcję.
To **nie** jest `IntegrityError`, więc naiwny handler przepuściłby to jako HTTP 500.
Łapię `40P01` (i `40001` serialization_failure) w `create_booking` i ponawiam INSERT
(max 3 próby) — deadlock jest przejściowy, więc po retry przegrana transakcja widzi
już zacommitowany wiersz zwycięzcy i dostaje czyste `23P01` → 409. Dzięki temu wynik
jest deterministyczny `[201, 409]`, nie losowy `[201, 500]`.

Subtelność implementacyjna: skalary (`organization_id`, `resource_id`, `user_id`)
wyciągam do zwykłych zmiennych *przed* pętlą retry. Po `rollback()` obiekty ORM są
expired, a dostęp do ich atrybutów wymusiłby lazy-load — synchroniczne IO w kontekście
async, czyli `MissingGreenlet`. To była realna pułapka, którą złapałam dopiero
puszczając hero test kilkanaście razy pod rząd (pojedynczy run bywał zielony).

Tę samą ekspozycję na deadlock ma teoretycznie `update_booking` (przeniesienie
rezerwacji na inny zasób dzieli ten sam constraint), ale tam nie ma realnej
współbieżności w demo, więc na razie zostaje bez retry — świadomie, do ewentualnego
dopisania.

**Lock-in na PostgreSQL.** `EXCLUDE USING gist`, `tstzrange`, `btree_gist` to feature'y Postgresa. MySQL ich nie ma (najlepiej co mogę zrobić to SERIALIZABLE + retry lub trigger). SQLite tym bardziej. Świadomy wybór — projekt celuje w Postgresa od ADR-2, nie ma sensownego planu migracji.

**Constraint logic rozproszona po dwóch miejscach.** Pydantic waliduje `ends_at > starts_at` (żeby zwrócić 422 zamiast 500 dla głupiego inputu), CHECK constraint w bazie powtarza tę walidację jako defense in depth. Ktoś czytający kod musi wiedzieć o obu — model `Booking` ma `CheckConstraint`, ale Pydantic schema też robi swoje sprawdzenie. Akceptuję duplikację, bo:
- Pydantic łapie wcześniej i daje sensowny komunikat
- CHECK constraint jest niezawodnym backstopem dla wpisów z innych źródeł (raw SQL, console)

**Coupling do Postgres error codes.** Endpoint mapuje `23P01` na 409 i `23514` na 422. To stałe SQLSTATE z dokumentacji Postgresa — zmieniają się raz na dekadę (SQLSTATE jest standardem SQL). Nie martwi mnie to.

**Aplikacja musi rozumieć semantykę 409.** Frontend dostaje 409 i musi pokazać sensowny komunikat ("ten slot został właśnie zajęty"). Bez tego user widzi generyczny error. Patrz wpięcie HTMX (`hx-on::after-request`).

**Constraint nie obejmuje organization_id.** Resource należy do jednej organizacji, więc dwa bookingi tego samego zasobu z różnych orgów nie mogą się zdarzyć (FK to wymusza). Constraint na `resource_id` jest wystarczający. Gdyby kiedyś pojawiło się sharing zasobów między organizacjami, constraint trzeba by rozszerzyć.

**Brak "pakietów" rezerwacji.** Constraint patrzy na pojedynczy zasób. Nie ma natywnego sposobu na "zarezerwuj salę + projektor + krzesła razem albo nic" — to wymagałoby transactional wrapping w aplikacji (wszystko INSERT w jednej transakcji, rollback przy pierwszym konflikcie). Out of scope dla MVP.
