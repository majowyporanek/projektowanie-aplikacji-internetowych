# ADR-5: JWT w httpOnly cookie zamiast sesji serwerowej i Authorization header

## Kontekst

Aplikacja jest server-rendered (HTMX + Jinja, patrz ADR-3), więc auth musi działać dla przeglądarki, która wysyła zwykłe requesty (klik w link, submit formularza, `hx-post`). Front-end nie jest aplikacją JavaScriptową która trzyma token w pamięci i ręcznie dokleja go do każdego requestu — to byłoby sprzeczne z duchem HTMX.

Drugi czynnik: cały stack jest w Pythonie, jeden proces API, brak load balancera, więc nie potrzebuję session store który by przeżył restart wielu workerów. JWT bez stanu wystarczy.

Trzeci czynnik: payload tokena musi nieść `user_id` **i** `organization_id`. Multi-tenancy (ADR-6) wymaga żeby każdy request od razu wiedział z której organizacji userka — bez tego każde `get_current_user` musiałoby wczytywać usera z bazy żeby pobrać `organization_id`. JWT pozwala wpisać `org_id` do claimów i czytać go bez DB lookup (chociaż obecnie i tak wczytuję usera z DB w `get_current_user`, claim zostaje na przyszłość).

## Decyzja

JWT podpisany **HS256**, niesiony w cookie `access_token` z flagami `HttpOnly` + `SameSite=Lax`, TTL konfigurowalne (`settings.jwt_ttl_seconds`, domyślnie 7 dni). Payload:

```json
{
  "sub": "<user uuid>",
  "org_id": "<organization uuid>",
  "iat": <epoch>,
  "exp": <epoch>
}
```

Cookie ustawiane jest w `POST /auth/register` i `POST /auth/login` przez helper `set_access_cookie`. Czyszczone w `POST /auth/logout`. Odczyt + walidacja przez dependency `get_current_user` (w `app/api/deps.py`), wariant `get_current_user_optional` dla stron które renderują się różnie dla zalogowanych i niezalogowanych (np. `/`, `/login`).

Brak refresh tokenów. Brak blacklisty. Logout = `delete_cookie` po stronie przeglądarki, token żyje jeszcze w teorii do `exp`, ale bez sposobu żeby się nim posłużyć z normalnej sesji.

## Alternatywy

**Sesje server-side w Redisie (Starlette SessionMiddleware lub własna implementacja).** Klasyczne podejście, daje natychmiastową rewokację (kasujemy klucz w Redisie, sesja martwa). Wymaga jednak osobnego lookupu w Redis na każdy zalogowany request, więcej kodu, i duplikuje rolę Redisa który u mnie służy jako cache dostępności (ADR-8). Nie potrzebuję natychmiastowej rewokacji w MVP, więc dorzucanie kolejnej infrastruktury jest niepotrzebne.

**JWT w nagłówku `Authorization: Bearer ...`.** Standard dla SPA i public API. Dla HTMX zły wybór — przeglądarka nie wysyła automatycznie nagłówków auth, musiałabym dodać JS który by tag każdy `hx-get` / `hx-post` doklejał header. To dodaje warstwę JavaScriptu po stronie klienta po to, żeby uniknąć cookie — odwracam to przez cookie i mam zero JS-u na ścieżce auth.

**OAuth2 / Keycloak / Auth0.** Dla pojedynczej małej aplikacji to overkill. Cały setup external IdP, redirect flow, JWKs caching, scope mapping — kilka godzin samego pisania, plus nowy kontener w `docker-compose`. Dla projektu klasowego: niewspółmierne narzędzie.

**Plain server-rendered sessions z Flask-style `session` cookie.** FastAPI nie ma natywnego mechanizmu sesji opartego o podpisane cookie (`itsdangerous`-style) — `SessionMiddleware` w Starlette jest do tego najbliżej, ale wymaga ręcznego trzymania state w `request.session`. Ostatecznie to wciąż cookie + jakaś forma serializacji, czyli wariant JWT bez standardowej składni — bez korzyści, z mniejszą czytelnością.

## Uzasadnienie

Cookie zamiast nagłówka — bo HTMX. Browser dokleja cookie automatycznie do każdego requestu z origin'u, w tym do `hx-post`. Zero kodu po stronie klienta, zero ryzyka że ktoś zapomni doczepić tokena w nowym widoku.

`HttpOnly` — JavaScript nie może odczytać `document.cookie['access_token']`. Nawet jeśli kiedykolwiek zdarzy się XSS (np. user wkleja w `notes` rezerwacji niesanitizowane `<script>`), atak nie wyciągnie tokena. Defense in depth: nadal sanitizuję dane na wyjściu (Jinja `autoescape` jest on by default), ale `HttpOnly` jest darmową dodatkową linią obrony.

`SameSite=Lax` — cookie nie poleci przy cross-origin POST (przed atakiem CSRF), ale poleci przy nawigacji po linkach (czyli normalne UX). Wybór `Lax` zamiast `Strict` jest świadomy: `Strict` zerwałby flow w którym user klika w link do mojej aplikacji z e-maila — cookie by nie poleciało, user dostałby ekran logowania mimo że jest zalogowany.

`HS256` (symetryczny) zamiast `RS256` (asymetryczny): mam jeden serwis który podpisuje i weryfikuje. Klucz nie wycieka poza ten proces. `RS256` jest sensowny gdy weryfikatorów jest wielu i piszący ma być oddzielony (klasyczny case: auth-service podpisuje, kilka mikroserwisów weryfikuje przez public key). U mnie sztuczne.

TTL 7 dni — kompromis. Krótszy (15 min + refresh token) wymagałby mechanizmu odświeżania i listy aktywnych refresh tokenów w bazie. Dłuższy (30 dni) zwiększa ryzyko że skradziony token długo działa. 7 dni dla wewnętrznej aplikacji o niskim risk profile (organizacja, znajomi userzy) jest rozsądne i nie wymaga refresh logiki.

## Trade-offy

**Brak natywnej rewokacji.** Jeśli skradną komuś token (np. przez wycieknięty backup przeglądarki), żyje do `exp`. Logout po stronie serwera tylko czyści cookie u tej konkretnej przeglądarki — token jako string wciąż jest ważny. **Plan B na obronie**: jeśli ktoś dopyta — można dodać blacklistę tokenów w Redisie z TTL równym pozostałemu `exp` tokena. Robi to z JWT pseudo-sesyjny mechanizm, akceptowalny kompromis. Świadomie nie implementuję — overkill dla MVP.

**`secure=False` w dev.** W `app/auth/cookies.py` flaga `secure` jest na `False`, co pozwala cookie iść po `http://`. W produkcji trzeba przełączyć na `True` (z konfiga, nie hardkodować) razem z HTTPS. To znana pułapka deployu — wymaga sprawdzenia podczas wdrożenia. Akceptuję w devie żeby `docker compose up` działało bez TLS.

**Token rośnie z każdym claimem.** Obecnie kilka pól (`sub`, `org_id`, `iat`, `exp`) — kilkaset bajtów po podpisaniu. Jeśli dodam role, scope, permissions, organization name etc. — może rosnąć szybciej niż jest to potrzebne. Stąd `role` aktualnie czytam z bazy w `get_current_user` zamiast wpisywać do tokena. Jeśli stałoby się to hot pathem, mogę zmienić — ale wtedy zmiana roli w bazie nie propaguje się do aktywnych tokenów (kolejna pułapka rewokacji).

**Cookie a CORS.** Jeśli kiedyś dodałabym osobny frontend na innym domain (typu React SPA na innym subdomain), cookie wymaga `SameSite=None; Secure` i `CORS` z `credentials: include` po stronie fetch'a. To inny tryb pracy, dziś nieaktualny — wszystko jest same-origin.

**JWT są nieuznawalne (opaque to browser).** Nie da się ich przeglądać bez dekodowania — w devtools widzę tylko base64 string. To minus przy debuggingu, ale `jwt.io` i `decode_access_token` w testach radzą sobie z tym łatwo.
