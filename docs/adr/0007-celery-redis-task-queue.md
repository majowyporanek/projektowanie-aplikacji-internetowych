# ADR-7: Kolejka zadań (Celery + Redis) — rozważona i odrzucona

**Status: ODRZUCONA.** Pierwotnie planowałam Celery do asynchronicznych przypomnień
mailowych i nawet postawiłam infrastrukturę (worker w `docker-compose`, broker na
Redisie, task `ping`). Po przemyśleniu skali projektu wycofałam ją przed obroną.
Ten wpis dokumentuje *dlaczego* — bo świadoma rezygnacja jest decyzją
architektoniczną tak samo jak wprowadzenie.

## Kontekst

Naturalny kandydat na pracę asynchroniczną w systemie rezerwacji to przypomnienie
mailowe: wyślij userowi maila na 24h przed `booking.starts_at`. To zadanie ma dwie
cechy, które sugerują kolejkę: jest **odroczone w czasie** (ETA daleko w przyszłości)
i musi **przetrwać restart aplikacji** (nie może pozostawać w pamięci procesu API).

Dokument wymagań wymienia "Task queue" jako jeden z punktowanych elementów
dodatkowych, więc pokusa była podwójna: realna potrzeba domenowa plus punkty.

## Decyzja

Nie wprowadzam kolejki zadań. Reminder mailowy zostaje jako pomysł na rozszerzenie,
nie jako zaimplementowana funkcja. Redis zostaje w stacku, ale wyłącznie jako cache
dostępności (ADR-8), nie jako broker.

## Alternatywy

**Celery 5 + Redis (broker + result backend).** To był pierwotny plan. Task
`send_booking_reminder` schedulowany przy `POST /bookings` z `apply_async(eta=...)`,
worker w osobnym kontenerze. Daje retry, ETA, monitoring (Flower). Cena: drugi proces
do utrzymania, rozwlekła konfiguracja, serializacja zadań i cały ten aparat dla
*jednego* typu zadania.

**FastAPI `BackgroundTasks`.** Najprostsze, zero infrastruktury. Odrzucone dla tego
przypadku użycia, bo zadanie istnieje tylko w obrębie request-response — nie obsługuje
ETA (odroczenia o godziny) i nie przetrwa restartu. Nadaje się do "wyślij maila teraz,
po odpowiedzi", nie do "wyślij za 23 godziny".

**APScheduler w procesie API.** Lżejszy od Celery, ma scheduling z ETA. Ale trzyma
zadania w pamięci procesu (albo w jobstore, co cofa do problemu osobnej infrastruktury)
i nie skaluje się między workerami API — przy >1 workerze to samo zadanie uruchomiłoby
się wielokrotnie. Pułapka ujawniająca się dopiero przy skalowaniu poziomym.

**Cron + osobny skrypt** odpytujący bazę, które bookingi zaczynają się za ~24h.
Prosty, odporny, bezstanowy. Realnie najsensowniejsza alternatywa, gdyby reminder był
wymagany — ale to dalej osobny proces i osobny deployment.

## Uzasadnienie

Kluczowe kryterium z dokumentu wymagań: *architektura ma pasować do skali projektu*.
Tu skala jest mała — wewnętrzny system rezerwacji, jedna instancja API, jeden typ
zadania asynchronicznego, i to zadania, którego SMTP i tak nie jest częścią oceny.

Celery dla jednego maila to klasyczny over-engineering: wprowadzam drugi proces, broker
w nowej roli, warstwę serializacji i całą semantykę retry/ETA, żeby obsłużyć
funkcjonalność, której nawet nie realizuję do końca (mail trafiał do stuba zapisującego
do stdout). To jest dokładnie ten rodzaj "dodaję, bo to punktowane / bo się tak robi",
przed którym wymagania wprost ostrzegają.

Mam już sześć innych elementów dodatkowych użytych *realnie* i uzasadnionych: cache
(ADR-8), walidacja Pydantic, testy (w tym hero test na race condition), observability
(structlog + `/health` + panel stanu), dokumentacja API (Swagger), seed data,
multi-tenancy. Element "task queue" nie jest mi potrzebny do kompletu, a jego
wstawienie psułoby spójność — najważniejsze kryterium oceny.

Gdyby reminder kiedyś stał się wymaganiem, droga jest jasna: zacznę od cron + skryptu
odpytującego bazę (najprostsze co działa), a po Celery sięgnę dopiero gdy typów zadań
asynchronicznych będzie więcej niż jeden.

## Trade-offy

**Tracę punktowany element "task queue".** Świadomie — bo punkty za element dodany na
siłę są iluzoryczne, jeśli nie broni się on w Q&A ("pokaż mi to zadanie"), a spójność
architektoniczna waży więcej niż liczba odhaczonych bonusów.

**Brak gotowej infrastruktury async, gdyby pojawiła się druga potrzeba.** Jeśli dojdzie
generowanie raportów albo cleanup, zacznę od zera. Akceptuję — przedwczesna
infrastruktura to dług, nie aktywo.

**Reminder mailowy nie istnieje jako funkcja.** User nie dostanie przypomnienia. Dla
wewnętrznego MVP, gdzie kalendarz i lista rezerwacji są zawsze pod ręką, to
akceptowalny brak, nie krytyczna luka.
