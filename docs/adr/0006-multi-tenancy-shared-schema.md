# ADR-6: Multi-tenancy: shared schema z organization_id

## Kontekst

System rezerwacji ma obsługiwać wiele organizacji niezależnie — każda ma własnych użytkowników i zasoby, dane jednej nie mogą wyciekać do drugiej. Wszystkie istotne tabele (`user_account`, `resource`, docelowo `booking`) są związane z konkretną organizacją.

## Decyzja

Shared schema: jedna baza, jeden schemat, każda tabela "tenancyjna" ma kolumnę `organization_id` jako FK do `organization`. Filtrowanie po tenancie dzieje się w warstwie aplikacji — każdy endpoint pobiera `organization_id` z zalogowanego użytkownika (przez `get_current_user`, JWT z httpOnly cookie) i dokleja `WHERE organization_id = ...` do każdego query.

## Alternatywy

**Database-per-tenant** — każda organizacja dostaje osobną bazę PostgreSQL. Najmocniejsza izolacja (fizyczna), ale fragmentacja connection poola, koszty infrastruktury rosną liniowo z liczbą tenantów, a migracje trzeba puszczać N razy. Sensowne dopiero przy bardzo dużych klientach z wymaganiami compliance.

**Schema-per-tenant** — jedna baza, ale każda organizacja ma własny schemat PostgreSQL. SQLAlchemy + Alembic obsługują to słabo — migracje trzeba aplikować do każdego schematu osobno, a `search_path` ustawiać per-request. Operacyjna uciążliwość przy każdej zmianie modelu.

**Postgres Row-Level Security** — RLS wymusza filtr na poziomie bazy: zanim aplikacja dostanie wiersz, policy sprawdza, czy `current_setting('app.current_org')` zgadza się z `organization_id`. Bardzo eleganckie i odporne na zapomnienie filtra w kodzie. Ale wymaga `SET app.current_org = '...'` dla każdego połączenia z poola, co przy async + pgbouncer staje się problematyczne.

## Uzasadnienie

Shared schema jest najprostszy operacyjnie: jedna migracja, jeden backup, jeden monitoring. Skala projektu (rzędy: dziesiątki organizacji, tysiące rezerwacji) nie uzasadnia mocniejszej izolacji.

Filtrowanie po `organization_id` znajduje się w jednym miejscu — dependency `get_current_user` zwraca obiekt User z `organization_id`, a każdy endpoint deklaratywnie go pobiera i używa w `WHERE`. To ten sam wzorzec co `get_session` — multi-tenancy nie jest wyjątkiem, lecz jednym z dependency.

Ryzyko wycieku danych (programista pominie filtr) realnie istnieje, ale jest ograniczone: każdy endpoint i tak musi zadeklarować `Depends(get_current_user)`, żeby obsłużyć request zalogowanego użytkownika — `user.organization_id` jest łatwo dostępne, a brak filtru będzie widoczny w code review.

## Trade-offy

Nie mam fizycznej izolacji — bug w aplikacji może teoretycznie pokazać dane innej organizacji. RLS dałby twardszą gwarancję, ale przy małej skali i jednej osobie pracującej z kodem koszt komplikacji przewyższa zysk. Jeśli kiedyś projekt urośnie i pojawi się compliance wymagający izolacji bazodanowej, droga migracji to: dodać policies RLS na istniejące tabele, włączyć je, zostawić warstwę aplikacyjną jako defense in depth.

Indeks na `organization_id` (każda tabela tenancyjna go ma — patrz Resource) jest obowiązkowy, bo prawie każde query startuje od tego filtra. Bez indeksu seq scan rośnie liniowo z całą bazą, zamiast z rozmiarem konkretnej organizacji.

"Noisy neighbor" — jedna duża organizacja może spowolnić zapytania innym. Przy tej skali nie stanowi to problemu, ale jest to coś, co RLS i schema-per-tenant rozwiązują automatycznie.
