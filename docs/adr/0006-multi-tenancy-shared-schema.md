# ADR-6: Multi-tenancy: shared schema z organization_id

## Kontekst

System rezerwacji ma obsługiwać wiele organizacji niezależnie — każda ma własnych użytkowników i zasoby, dane jednej nie mogą wyciekać do drugiej. Wszystkie istotne tabele (`user_account`, `resource`, docelowo `booking`) są związane z konkretną organizacją.

## Decyzja

Shared schema: jedna baza, jeden schemat, każda tabela "tenancyjna" ma kolumnę `organization_id` jako FK do `organization`. Filtrowanie po tenancie dzieje się w warstwie aplikacji — każdy endpoint pobiera `organization_id` z zalogowanego użytkownika (przez `get_current_user`, JWT z httpOnly cookie) i dokleja `WHERE organization_id = ...` do każdego query.

## Alternatywy

**Database-per-tenant** — każda organizacja dostaje osobną bazę PostgresSQL. Najmocniejsza izolacja (fizyczna), ale fragmentacja connection poola, koszty infrastruktury rosną liniowo z liczbą tenantów, a migracje trzeba puszczać N razy. Sensowne dopiero przy bardzo dużych klientach z wymaganiami compliance.

**Schema-per-tenant** — jedna baza, ale każda organizacja ma własny PostgresSQL schema. SQLAlchemy + Alembic radzą sobie z tym kiepsko — migracje trzeba aplikować do każdego schematu osobno, a `search_path` trzeba ustawiać per-request. Operacyjny ból przy każdej zmianie modelu.

**Postgres Row-Level Security** — RLS wymusza filtr na poziomie bazy: zanim aplikacja dostanie wiersz, policy sprawdza, czy `current_setting('app.current_org')` zgadza się z `organization_id`. Bardzo eleganckie i odporne na zapomnienie filtra w kodzie. Ale wymaga `SET app.current_org = '...'` per każdy connection z poola, co przy async + pgbouncer staje się delikatne.

## Uzasadnienie

Shared schema jest najprostszy operacyjnie: jedna migracja, jeden backup, jeden monitoring. Skala projektu (rzędy: dziesiątki organizacji, tysiące rezerwacji) tego nie naprasza.

Filtrowanie po `organization_id` siedzi w jednym miejscu — dependency `get_current_user` zwraca obiekt User z `organization_id`, każdy endpoint deklaratywnie go zaciąga i używa w `WHERE`. To ten sam wzorzec co `get_session` — multi-tenancy nie jest specjalną sprawą, tylko jednym z dependency.

Risk data leaku (programista zapomni filtra) realnie istnieje, ale jest ograniczony: każdy endpoint i tak musi zadeklarować `Depends(get_current_user)` żeby cokolwiek zrobić z requestem zalogowanego usera — `user.organization_id` jest na wyciągnięcie ręki, brak filtru będzie widoczny w code review.

## Trade-offy

Nie mam fizycznej izolacji — bug w aplikacji może teoretycznie pokazać dane innej organizacji. RLS dałby twardszą gwarancję, ale przy małej skali i jednej osobie pracującej z kodem koszt komplikacji przewyższa zysk. Jeśli kiedyś projekt urośnie i pojawi się compliance wymagający izolacji bazodanowej, droga migracji to: dodać policies RLS na istniejące tabele, włączyć je, zostawić warstwę aplikacyjną jako defense in depth.

Indeks na `organization_id` (każda tabela tenancyjna go ma — patrz Resource) jest obowiązkowy, bo prawie każde query startuje od tego filtra. Bez indeksu seq scan rośnie liniowo z całą bazą, zamiast z rozmiarem konkretnej organizacji.

"Noisy neighbor" — jedna duża organizacja może spowolnić queries innym. Przy tej skali nie problem, ale to coś, co RLS i schema-per-tenant rozwiązują automatycznie.
