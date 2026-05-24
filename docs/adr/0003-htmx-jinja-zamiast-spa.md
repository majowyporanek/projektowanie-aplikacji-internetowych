# ADR-3: HTMX + Jinja2 zamiast SPA

## Kontekst

Frontend dla systemu rezerwacji. Apka ma ~6-8 widoków CRUD-owych. Wymaganie R3 dopuszcza SPA, SSR lub HTMX.

Backend jest zaprojektowany jako single source of truth: race conditions atomowo egzekwowane przez constraint bazodanowy (ADR-4), multi-tenancy przez dependency `get_current_org`, auth przez JWT w httpOnly cookie. Frontend nie podejmuje autonomicznych decyzji — pyta serwer i renderuje to co przyszło.

## Decyzja

SSR w Jinja2 + interaktywność przez HTMX (z extension `json-enc` do form → JSON). Bez bundlera.

## Alternatywy

**React + TypeScript jako SPA** — wymaga routing, state managera, API clienta z typowaniem kontraktów, auth flow w JS. Każdy element to osobna powierzchnia bugów i decyzji, a żaden nie wnosi wartości w domenie gdzie state mieszka w bazie.

**Next.js (SSR + RSC)** — hybrydowe SSR z Reactem. Dla 6 widoków CRUD-owych nadbudowuje Node ecosystem + React + warstwę Next-ową bez funkcjonalnego zysku.

**Czysty Jinja2 bez JS** — każda akcja przeładowuje całą stronę, UX z 2005.

## Uzasadnienie

Domena ma jedną decydującą właściwość: cała interesująca logika dzieje się na serwerze. Race condition musi być atomowo zweryfikowana przez bazę (dwa requesty mogą zderzyć się na ten sam slot), multi-tenancy filtruje przez `WHERE organization_id`, autoryzacja sprawdza ważność JWT.

Trzymanie kopii stanu w przeglądarce (Redux + cache invalidation) duplikuje to co już jest w bazie. Optymistyczne UI byłoby wręcz szkodliwe: pokazanie *"zarezerwowano"* przed weryfikacją serwera, którą musimy cofnąć po odrzuceniu race condition.

HTMX wpisuje się w tę filozofię: atrybuty `hx-*` wysyłają AJAX, serwer zwraca fragment HTML, HTMX podmienia w DOM. Pydantic schematy są jedynym źródłem prawdy o kontraktach — bez osobnego typowania po stronie klienta.

Pozycjonowanie: HTMX to najlżejszy przedstawiciel rodziny *server-side rendering z enhancement* — tym samym podejściem jest Hotwire (Rails / Basecamp), Phoenix LiveView (Elixir), częściowo React Server Components w Next.js. Wspólna teza: state powinien siedzieć blisko bazy, nie być replikowany w przeglądarce.

## Trade-offy

Każda interakcja to roundtrip — brak optymistycznego UI. Dla CRUD-a z server-side validation nie ma znaczenia. Dla apek z drag-and-drop / edytorem / real-time collab byłby to dealbreaker; żaden z tych przypadków nie występuje w domenie.

Brak client-side routingu. Mobile app na tym backendzie wymagałby dorobienia oddzielnych endpointów JSON (FastAPI ma to trywialnie przez `/docs`).

Typowanie kontraktów żyje tylko po stronie Pythona. JS w HTMX to stringi w atrybutach HTML, bez sprawdzania typów. Type-safety mam na granicy systemu (Pydantic walidacja payloadów).
