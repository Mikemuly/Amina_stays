# Amina Stays: verified stack brief (25 Nov 2026)

**Method.** Versions and dates come from registry JSON queried today (`pypi.org/pypi/<pkg>/json`, `registry.npmjs.org/<pkg>/latest`); other sources are linked inline. *(src)* means a research sub-agent read it from source code or CI and I did not re-run it. **[local]** means I checked it on your machine. **UNVERIFIED** means I found no primary evidence.

## 0. What changes the plan
- **Django 6.1.3** is current (Python 3.12–3.15, PostgreSQL ≥15) [6.1](https://docs.djangoproject.com/en/6.1/releases/6.1/). Mainstream support ends Apr 2027. **6.2 LTS arrives Apr 2027 (extended support to Apr 2030)**, then releases are calendar-named "Django 2028" [download](https://www.djangoproject.com/download/).
- **openapi-typescript is abandoned.** The maintainer said on 2026-09-19 there will be no further updates, security included. Use Orval [#2874](https://github.com/openapi-ts/openapi-typescript/issues/2874).
- **Africa's Talking's Python SDK dropped Payments on 2023-11-07** [commit](https://github.com/AfricasTalkingLtd/africastalking-python/commit/1f5d934b1e88fc6f652721a00fc4cf8ac7fae45d). The Node SDK has no payments module either. Call the REST API yourself.
- **shadcn/ui defaults to Base UI** since 2026-07-02 [changelog](https://ui.shadcn.com/docs/changelog/2026-07-base-ui-default.md).
- **TypeScript 7.0.2 is npm `latest`, but tooling lags.** Pin `~6.0.3` [TS 7](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/), [ts-eslint#13196](https://github.com/typescript-eslint/typescript-eslint/issues/13196).
- **Use Next ≥16.4.5.** October RCEs hit `use cache` and the Image API, and November fixed cache disclosures [Oct](https://nextjs.org/blog/nextjs-security-update-october-14-2026), [Nov](https://nextjs.org/blog/november-2026-security-release). Your scaffold is 16.4.6 **[local]**.
- **PostgreSQL 19 went GA 2026-11-19** [pg.org](https://www.postgresql.org/). Stay on 18.7. Django 6.1 documents PG18 features; PG19 support is **UNVERIFIED**.
- Also: Sentry Python **3.0.0** (2026-11-23) is breaking, simplejwt is stale, `@tremor/react` is stale (React ^18 peer), and DRF 3.18 changed the `many=True` error shape.

## 1. Backend
- **Django 6.1.3** (2026-11-03).
  - 6.0 added built-in CSP (`ContentSecurityPolicyMiddleware`, `SECURE_CSP`, nonces), template partials, the Tasks API (no worker) and `AsyncPaginator` [6.0](https://docs.djangoproject.com/en/6.1/releases/6.0/).
  - 6.1 added `fetch_mode(FETCH_PEERS)` (removes N+1 in list endpoints), DB-level `on_delete`, `MAILERS`, `UUID7()` and virtual `GeneratedField` (PG≥18) [6.1](https://docs.djangoproject.com/en/6.1/releases/6.1/).
- **DRF 3.18.3** (2026-10-06) [notes](https://www.django-rest-framework.org/community/release-notes/):
  - 3.17: Django 6.0 + Python 3.14, dropped Python 3.9.
  - 3.18: Django 6.1, dropped Django ≤5.1; 3.18.1 added a compat setting for the new list-error format; 3.18.2 has security fixes + Python 3.15.
- **Python:** 3.15.2 is out [python.org](https://www.python.org/downloads/). Django 6.1.3 and `psycopg-binary` support it. Run 3.14 in production and add 3.15 to CI.
- **psycopg 3.3.9:** `psycopg-binary` ships cp314/cp315 manylinux wheels (PyPI), and the changelog records 3.14 support [news](https://www.psycopg.org/psycopg3/docs/news.html).
  - Native pool since Django 5.1 [5.1](https://docs.djangoproject.com/en/5.1/releases/5.1/): `OPTIONS={"pool": True}`, needs `psycopg[pool]` (psycopg-pool 3.3.3), `CONN_MAX_AGE=0`, and no persistent connections under ASGI [docs](https://docs.djangoproject.com/en/6.1/ref/databases/).
- **Config:** `django-environ` 0.14.0, or plain `os.environ` + `dj-database-url` 3.1.2 (your scaffold). Both are fine. Keep `.env` dev-only.
- **Layout** (opinion): `config/` plus `apps/<domain>/{models,services,selectors,tasks}.py` and `api/{serializers,views,permissions,urls}.py`. Use `/api/v1/` and put webhooks in their own app [HackSoft](https://github.com/HackSoftware/Django-Styleguide). Your scaffold already matches **[local]**.
- **OpenAPI:** drf-spectacular 0.30.0 emits 3.0.3 (3.1 opt-in); PyPI lists Django ≤6.0 [changelog](https://drf-spectacular.readthedocs.io/en/latest/changelog.html).
  - **[local] smoke test on Django 6.1.3 / Python 3.14.4 generated a 109 KB schema, and the open py3.14 segfault report did not reproduce.**
  - Set `COMPONENT_SPLIT_REQUEST=True`, `ENUM_NAME_OVERRIDES`, `SCHEMA_PATH_PREFIX` and `@extend_schema(exclude=True)` on webhooks. Run `spectacular --validate --fail-on-warn` in CI [guide](https://drf-spectacular.readthedocs.io/en/latest/client_generation.html).
- **TS client → Orval 8.49.0** (2026-11-22; TanStack Query v5 hooks, zod 3/4, MSW; Node ≥22.18) [orval](https://orval.dev/docs). Fallback: `@hey-api/openapi-ts` 0.99.0 (pre-1.0, crashes on TS 7 [#4235](https://github.com/hey-api/hey-api/issues/4235)). Commit the generated code.
- **Africa's Talking:** `africastalking` 2.0.3 (2026-07-31).
  - It depends on `requests`, `schema` and the test library `responses`, and declares no Python classifiers.
  - Services: SMS (+premium), Voice, Airtime, MobileData, Insights, WhatsApp, Token, Application. USSD is webhook-only [repo](https://github.com/AfricasTalkingLtd/africastalking-python).
  - The Payments REST endpoint (`payments.africastalking.com/mobile/checkout/request`) last appears in AT's 2024 Postman docs [Postman](https://www.postman.com/africastalking/africa-s-talking-apis/request/xhxm28r/mobile-checkout). Current availability is **UNVERIFIED**, so confirm with AT. Safaricom Daraja STK Push is the direct fallback [guide](https://www.bykabiro.com/blog/mpesa-daraja-api-guide.html) (secondary source).
  - **Skip the SDK.** Use a thin client on `requests` 2.34.2, or `httpx` 0.28.1 (stable dates from 2024-12; only 1.0.dev pre-releases since).
  - USSD replies must start with `CON` or `END` [AT help](https://help.africastalking.com/en/articles/484351-why-am-i-seeing-the-error-messages-response-should-start-with-a-con-or-an-end).

## 2. Auth (Next ↔ Django)
- **Best fit: same-origin session cookie + CSRF.** The browser calls `/api/*` on the Next origin and `rewrites()` proxies it to Django. Cookies are first-party, no token reaches JS, and no CORS is needed.
  - Django needs `CSRF_TRUSTED_ORIGINS=[public origin]`: Origin must match Host, and the proxy changes Host *(src)* [settings](https://docs.djangoproject.com/en/6.1/ref/settings/).
  - Send `X-CSRFToken` from the `csrftoken` cookie [howto](https://docs.djangoproject.com/en/6.1/howto/csrf/), and set `SECURE_PROXY_SSL_HEADER`.
  - Server Components must forward the session cookie themselves (my analysis). Treat `proxy.ts` gates as optimistic and enforce on Django.
- **Proxy gotchas** *(src)* [docs](https://nextjs.org/docs/app/api-reference/config/next-config-js/rewrites):
  - Next 308-redirects trailing slashes before rewrites, which loops with `APPEND_SLASH`. Use DRF `trailing_slash=False` + `APPEND_SLASH=False`; end-to-end behaviour is **UNVERIFIED**.
  - Default proxy timeout is 30 s, `Set-Cookie` passes through, and with `proxy.ts` request bodies up to 10 MB are buffered.
- **JWT:** simplejwt 5.5.1 (2025-07-21) lists Django ≤5.2 and no Python 3.14, and its home org Jazzband is winding down [news](https://jazzband.co/news/2026/03/14/sunsetting-jazzband).
- **DRF tokens** target "native desktop and mobile clients" [DRF](https://www.django-rest-framework.org/api-guide/authentication/) and never expire. If a native app appears, use `django-rest-knox` 6.0.0 (hashed, 10 h default TTL) [knox](https://github.com/django-commons/django-rest-knox).
- **allauth 65.22.1 headless:** `browser` (cookie) and `app` (`X-Session-Token`) clients, an optional JWT strategy, and its own OpenAPI spec [config](https://docs.allauth.org/en/latest/headless/configuration.html).
  - **Native phone login:** `ACCOUNT_LOGIN_METHODS={"phone"}` plus a custom adapter to store numbers and send SMS. Code TTL is 900 s and 3 attempts by default [phone](https://docs.allauth.org/en/latest/account/phone.html).
  - **My pick:** allauth headless with an AT-backed adapter.
- **OTP hardening:**
  - Normalise to E.164 with `phonenumbers` 9.0.44 + `django-phonenumber-field` 9.0.0 (region KE), and hash codes.
  - Limit per number, prefix **and** country, plus a server-side country allow-list against SMS pumping; per-IP limits alone fail [guide](https://nhimg.org/sms-pumping-and-irsf-guide) (secondary).
  - DRF throttles use Django's cache and can race, so use a shared cache [DRF](https://www.django-rest-framework.org/api-guide/throttling/). Use `django-axes` 9.1.0 for lockouts.
- **Roles:** Django Groups (guest/host/staff) → DRF `BasePermission` + `get_queryset()` scoping. `has_object_permission` is not applied to lists or creates [DRF](https://www.django-rest-framework.org/api-guide/permissions/).

## 3. Background jobs (30 s cadence)
- **`django.tasks` is an API only.** It ships Immediate/Dummy backends, with no worker, retries or cron; use `transaction.on_commit` [docs](https://docs.djangoproject.com/en/6.1/topics/tasks/).
  - `django-tasks` 0.12.0 is now a pre-6.0 backport.
  - The DB backend is `django-tasks-db` 0.13.0 (Beta): polling, SKIP LOCKED, **no retries or periodic, at-most-once** *(src)* [repo](https://github.com/RealOrangeOne/django-tasks-db).
- **Procrastinate 3.12.0** (2026-11-19, Postgres-only):
  - `@app.periodic(cron=…)` takes an optional 6th seconds field ("as frequent as 1 per second"; UTC default) [docs](https://procrastinate.readthedocs.io/en/stable/howto/advanced/cron.html), so every 30 s is `* * * * * */30`.
  - A UNIQUE-row dedupe makes two workers safe. It also has `queueing_lock`, `lock`, `schedule_in`, retry strategies and LISTEN/NOTIFY wake-ups *(src)*.
  - CI covers Python 3.11–3.15 × Django 5.2–6.1 × PG15–19, though PyPI omits the 3.14 classifier *(src)*.
  - Gotchas: the worker exits if the DB is down >30 s, so use a restart policy. `.defer()` runs outside Django's transaction, so use `on_commit`. LISTEN needs a non-PgBouncer-transaction connection.
- **Others:**
  - django-q2 1.11.1: tick hard-coded to 30 s; sub-minute scheduling only on unreleased master.
  - Huey 3.5.4: cron is 1-minute granularity.
  - Dramatiq 2.2.1 and Celery 5.7.0 need Redis or RabbitMQ.
  - APScheduler 3.11.3 is fine in-process; 4.x says "do NOT use in production".
  - Python 3.14 made `forkserver` the default start method, while q2, Huey and Celery pin `fork` *(src)* [3.14](https://docs.python.org/3/whatsnew/3.14.html).
- **Pick Procrastinate** as a separate `worker` container (`restart: always`).
  - Run sweepers on their own queue with `queueing_lock`: hold expiry, auto-checkout, scheduled SMS, outbox drain.
  - Use `lock=unit_id` for iCal sync (`icalendar` 7.3.2) and compare-and-set `UPDATE … WHERE status='held'`.
  - Runner-up: `django.tasks` + `django-tasks-db` + your own ticker under `pg_try_advisory_lock`.

## 4. Real-time dashboards
- **Start with polling:** TanStack Query `refetchInterval` of 5–10 s. Background polling is off unless `refetchIntervalInBackground` is set [docs](https://tanstack.com/query/latest/docs/framework/react/guides/polling).
- **Step 2:** SSE from an async Django view under ASGI [docs](https://docs.djangoproject.com/en/6.1/ref/request-response/#streaminghttpresponse), with `X-Accel-Buffering: no` and a 15 s `: ping`, fed by LISTEN/NOTIFY.
  - psycopg `notifies()` has a payload limit under 8000 B, is not persisted, and breaks under PgBouncer transaction pooling [NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html).
  - Route `/events` at the edge proxy, **not** through Next rewrites: gzip buffers SSE (open bug [#102264](https://github.com/vercel/next.js/issues/102264)).
- **Channels** 4.3.2 (2025-11-20; Django 6.1 only on main) is only worth it for WebSockets, and `channels_redis` needs Redis *(src)*.

## 5. PostgreSQL patterns
- **Versions:** 19.0 (2026-11-19), 18.7 (supported to Nov 2030); 14 is EOL [policy](https://www.postgresql.org/support/versioning/).
  - PG19 adds `REPACK (CONCURRENTLY)`, `pg_plan_advice` and JIT off by default [19](https://www.postgresql.org/docs/release/19.0/).
  - PG18 adds AIO, skip scan, `uuidv7()`, virtual generated columns, OAuth, `RETURNING OLD/NEW` and **`WITHOUT OVERLAPS`/`PERIOD`** [18](https://www.postgresql.org/docs/release/18.0/).
  - PG17 adds `MERGE … RETURNING`, `JSON_TABLE` and incremental backup [17](https://www.postgresql.org/docs/release/17.0/).
- **No double-booking:** use `DateRangeField`, whose canonical `[)` form gives check-in inclusive and check-out exclusive [fields](https://docs.djangoproject.com/en/6.1/ref/contrib/postgres/fields/).
  - Migrate `BtreeGistExtension()` first, then `ExclusionConstraint(expressions=[("unit", EQUAL), ("stay", OVERLAPS)], condition=Q(status__in=[…]))` [docs](https://docs.djangoproject.com/en/6.1/ref/contrib/postgres/constraints/).
  - SQL equivalent: `EXCLUDE USING gist (unit_id WITH =, stay WITH &&) WHERE (status IN ('held','confirmed'))` [PG](https://www.postgresql.org/docs/current/rangetypes.html).
  - `btree_gist` is *trusted*, so a non-superuser owner can install it [PG](https://www.postgresql.org/docs/18/btree-gist.html).
- **Holds with expiry:** index predicates must be immutable, so no `now()` [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html).
  - Flip `held→expired` with the 30 s sweeper **and** lazy-expire inside the booking transaction before inserting.
  - Keep EXCLUDE because it accepts `WHERE`. PG18 `WITHOUT OVERLAPS` PK/UNIQUE has no predicate (cancelled rows would block) and Django has no API for it [CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html).
- **Concurrency:** the constraint is the source of truth, so catch `IntegrityError` and return 409.
  - Use `select_for_update()` inside `atomic()` on the unit row to serialise pricing rules [Django](https://docs.djangoproject.com/en/6.1/ref/models/querysets/).
  - Use `pg_advisory_xact_lock` for non-row resources [PG](https://www.postgresql.org/docs/current/explicit-locking.html).
- **Idempotency:** put a unique `(provider, provider_txn_id)` on callbacks and insert with `ON CONFLICT DO NOTHING`. Confirm payments with an STK status query rather than trusting the callback [guide](https://www.bykabiro.com/blog/mpesa-daraja-api-guide.html), and use a client `Idempotency-Key` [Stripe](https://docs.stripe.com/api/idempotent_requests).
- **Outbox:** write the SMS row in the same transaction; the worker drains it with SKIP LOCKED [pattern](https://microservices.io/patterns/data/transactional-outbox.html).
- **Postgres without root [local]:** already running. micromamba 2.10.0, env `amina-pg` (conda-forge `postgresql` 18.7) is on :5432 with `btree_gist` present.
  - Recipe: `micromamba create -n amina-pg -c conda-forge "postgresql=18"`, then `initdb` and `pg_ctl -o "-k /tmp" start` via `micromamba run`.
  - conda-forge also has 19.0 and 17.12 and ships contrib *(src)* [feedstock](https://github.com/conda-forge/postgresql-feedstock).
  - **Avoid** `pgserver` 0.1.4 (2024, Python ≤3.12) and `pixeltable-pgserver` 0.7.2: they bundle only plpgsql and pgvector, with no `btree_gist` *(src)*.
  - npm `embedded-postgres` has contrib but no psql or pg_dump.
  - `.data/` is untracked and **not gitignored**.

## 6. Frontend
- **Next 16.4.6** (2026-11-09; Node ≥20.9; Active LTS) [upgrade](https://nextjs.org/docs/app/guides/upgrading/version-16), [16.4](https://nextjs.org/blog/next-16-4):
  - Turbopack is the default for dev **and** build. A custom webpack config fails the build; `--webpack` opts out.
  - `proxy.ts` replaces `middleware.ts` (Node runtime only).
  - Cache Components (`cacheComponents`, `'use cache'`, `cacheLife/cacheTag/updateTag`) turns `dynamic/revalidate` exports into errors and drew the Oct/Nov advisories, so enable it deliberately.
  - Sync `cookies()` and `params` are removed, `next lint` is gone, and `reactCompiler` is stable but opt-in.
- **Images:** `dangerouslyAllowLocalIP` defaults to false, so Django media on localhost or a private IP returns 400 (enable in dev only); `qualities` default is `[75]` [docs](https://nextjs.org/docs/app/api-reference/components/image).
- **Config snippets:**
  - `rewrites: async()=>({beforeFiles:[{source:'/api/:path*',destination:'http://api:8000/api/:path*'}]})`
  - `images:{remotePatterns:[{protocol:'https',hostname:'amina.example',pathname:'/media/**'}]}`
  - Also use `output:'standalone'`, `sitemap.ts`, `robots.ts` and `manifest.ts`.
- **React 19.3.1** (scaffold has 19.3.0 **[local]**): 19.2 added `<Activity>` and `useEffectEvent` [19.2](https://react.dev/blog/2025/10/01/react-19-2); 19.3 added stable `<ViewTransition>` [19.3](https://react.dev/blog/2026/09/09/react-19-3).
- **Tailwind 4.3.5:** `@import "tailwindcss"` + `@theme` + `@tailwindcss/postcss`.
  - Browser floor is Chrome 111 / Safari 16.4 / Firefox 128 [compat](https://tailwindcss.com/docs/compatibility), the same as Next 16 [browsers](https://nextjs.org/docs/architecture/supported-browsers). Opera Mini and KaiOS lack cascade layers, so serve them via SMS/USSD.
  - Your scaffold uses `@tailwindcss/turbopack` 4.3.3 **[local]**. 4.3.4 reportedly broke CJS/ESM *(src)*, so the documented PostCSS path is safer.
- **TypeScript / lint / Node:**
  - TS `~6.0.3` and ESLint ^9. eslint-config-next's plugins cap at ^9 per npm metadata, while Next's docs claim ESLint 10 works; the two conflict.
  - Node 26 has been LTS since 2026-10-28 [schedule](https://raw.githubusercontent.com/nodejs/Release/main/schedule.json).
  - `@types/node` should match the runtime (scaffold has ^20) **[local]**.
- **shadcn 4.23.0:** non-interactive `npx shadcn@latest init -d -b radix -f` (`-b base|radix|aria`, `-t next`; there is no `--base-color`), and `add -y -o`.
  - `Field` replaced `Form`. The data-table docs now use TanStack Table 9, and `calendar` installs react-day-picker@latest [CLI](https://ui.shadcn.com/docs/cli).
- **react-day-picker 10.0.2:** v10 removed v9-deprecated props [upgrade](https://daypicker.dev/upgrading).
  - Range mode includes disabled days unless `excludeDisabled` is set.
  - Use `timeZone="Africa/Nairobi"`. date-fns 4.4.0 has no Swahili locale.
  - Hoist custom Root/Chevron components to avoid a remount bug [#11134](https://github.com/shadcn-ui/ui/issues/11134).
- **Forms:** zod 4.6.7, `@hookform/resolvers` 7.0.9, RHF 7.92.0. Use `z.input`/`z.output` and avoid `z.coerce`. React Compiler flags `watch()`, so use `useWatch` [lint](https://react.dev/reference/eslint-plugin-react-hooks/lints/incompatible-library).
- **TanStack Query 5.108.4:** prefetch on the server and use `HydrationBoundary`. `prefetchQuery`, `fetchQuery` and `ensureQueryData` are `@deprecated` in the typings in favour of `queryClient.query()` *(src)* [SSR](https://tanstack.com/query/latest/docs/framework/react/guides/advanced-ssr).
- **Maps:** Leaflet 1.9.4 + react-leaflet 5.0.0 (React ^19 only; Leaflet 2 is still beta) is ≈41 KB gz against MapLibre 6.19.0 at ≈291 KB *(src)* [leaflet](https://leafletjs.com/).
  - **OSM tiles** require attribution, a valid UA/Referer and cache-honouring, and forbid bulk or offline use. There is no SLA and they may block you [policy](https://operations.osmfoundation.org/policies/tiles/). That is fine for low traffic; keep the tile URL in env.
  - Google directions deep-links need no key.
- **UI libs:**
  - Recharts 3.11.1 (`react-is` must match React).
  - Tremor is stale and Vercel-acquired [post](https://vercel.com/blog/vercel-acquires-tremor).
  - lucide-react 1.79.0 (v1 removed brand icons [migration](https://lucide.dev/guide/react/migration)).
  - sonner 2.0.8, and vaul 1.1.2 is stale.
  - input-otp 1.5.0 (set `autoComplete="one-time-code"`).
  - next-themes 0.4.6 has an open React 19.2 dev warning, reportedly harmless.
- **i18n / PWA:**
  - next-intl 4.16.1 uses `proxy.ts`; `sw` and `en-KE` exist in Node 26 ICU, browsers **UNVERIFIED** [docs](https://next-intl.dev/docs/routing/middleware).
  - Serwist's classic plugin is webpack-only under Next 16 [Serwist](https://serwist.pages.dev/docs/next). Use `app/manifest.ts` + a hand-written `public/sw.js` (offline page; push via `pywebpush` 2.5.0) [guide](https://nextjs.org/docs/app/guides/progressive-web-apps).
  - iOS push needs a Home-Screen install.
- **Testing:**
  - Playwright 1.65.1.
  - Vitest 5.1.1 + `vite ^8.3.8`, because plugin-react 6.3.0 peers vite ^8 [Vitest 5](https://vitest.dev/blog/vitest-5).
  - jsdom 31.0.1, RTL 16.3.3 + `@testing-library/dom` ^10, MSW 3.0.7.
  - Vitest can't test async Server Components, so use Playwright for those [guide](https://nextjs.org/docs/app/guides/testing/vitest).
- **Peer/engine gotchas (npm metadata):**
  - `@tremor/react` peers React ^18.
  - typescript-eslint peers TS <6.1.
  - openapi-typescript peers TS ^5.
  - react-leaflet peers React ^19 and Leaflet ^1.9.
  - plugin-react peers vite ^8.
  - orval and hey-api need Node ≥22.18; vitest and msw need ≥22.12.

## 7. Alternatives & big platforms
- **FastAPI** 0.165.0: still 0.x, with 11 breaking-change releases between 2026-10-18 and 11-13 [notes](https://fastapi.tiangolo.com/release-notes/), and no admin.
- **NestJS** 12.6.0: TypeORM has `@Exclusion`; Prisma has no range types, an issue open since 2020 [#3287](https://github.com/prisma/orm/issues/3287).
- **Rails** 8.1.4.1: Solid Queue avoids Redis, and it has `t.exclusion_constraint` [guide](https://guides.rubyonrails.org/active_record_postgresql.html). The AT gem is stale (2024-01).
- **Laravel** 13.44.1: no range/EXCLUDE API in the docs, and the AT PHP SDK dates from 2024-03 [docs](https://laravel.com/docs/13.x/releases).
- React Router 8.5.3, SvelteKit 3.4.0 and Nuxt 4.7.0 replace Next, not Django.
- **Why Django:** built-in admin; a documented no-overlapping-reservations `ExclusionConstraint` pattern; and an actively released AT Python SDK.
- **Closest rival:** Rails, for the fewest moving parts. Kenyan .ke sites are 95.2% PHP, a rough proxy for the local talent pool [aguko](https://www.aguko.com/cat/programming-languages/ke).
- **Airbnb:** moved from a Rails monolith to services [InfoQ](https://www.infoq.com/news/2019/02/airbnb-monolith-migration-soa/). It uses Kotlin/Java and open-sourced the **Viaduct** GraphQL layer on 2025-09-15 [Viaduct](https://viaduct.airbnb.tech/about/). Its web front end is TypeScript [InfoQ](https://www.infoq.com/news/2020/08/airbnb-typescript-migration/).
- **Booking.com:** Perl-heavy historically. Per an AWS re:Invent 2025 page it rewrote its reservation backend to Java Lambdas + DynamoDB [AWS](https://repost.aws/articles/ARo70NlhSuQTyDpsdnLW3LEQ/re-invent-2025-designing-mission-critical-applications-with-serverless-services). It runs 120+ GraphQL subgraphs [talk](https://www.youtube.com/watch?v=4xCcSqdablo). Perl's current share is **UNVERIFIED**.
- **Expedia/Vrbo:** Kotlin/Spring with a GraphQL gateway, and React/Apollo on the web [Kotlin](https://kotlinlang.org/case-studies/expedia/), [InfoQ](https://www.infoq.com/news/2024/03/expedia-graphql-micro-frontends/).
- None of this applies at single-host scale.

## 8. Deployment & ops
- **Compose:**
  - `db`: `postgres:18`, mount `/var/lib/postgresql` [image](https://github.com/docker-library/postgres/blob/master/18/trixie/Dockerfile), with a `pg_isready` healthcheck.
  - `api`, `worker`, and `web` (Next standalone) [example](https://github.com/vercel/next.js/blob/canary/examples/with-docker/Dockerfile).
  - `caddy` 2.11.9: auto-TLS, flushes SSE [docs](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
  - Use ASGI for `api`: DRF sync views run through a thread adapter, and WSGI can't stream efficiently [async](https://docs.djangoproject.com/en/6.1/topics/async/). gunicorn 27.0.1 has a native `--worker-class asgi` [docs](https://gunicorn.org/asgi/) (Django not documented, **UNVERIFIED**); or use uvicorn 0.54.0.
- **Hosting regions:**
  - No managed option has an African Postgres region: Render, Railway, Neon and Supabase don't, and Fly has `jnb` compute but no Managed Postgres [Render](https://render.com/docs/regions), [Fly](https://docs.fly.io/reference/regions), [Neon](https://neon.com/docs/introduction/regions). The exception is AWS RDS in af-south-1 [AWS](https://docs.aws.amazon.com/general/latest/gr/rds-service.html).
  - Vercel has `cpt1`, but Hobby is non-commercial and streaming counts toward function duration [Vercel](https://vercel.com/docs/regions).
- **Pricing and extensions** (Nov 2026, *(src)*):
  - Render: web from $7/mo, Postgres from $6; free web sleeps after 15 min and free PG expires in 30 days [Render](https://render.com/pricing.md).
  - Railway: $5/mo Hobby, usage-billed [Railway](https://docs.railway.com/pricing/plans).
  - Fly Managed Postgres: from $4/mo, PG 16/17 only [Fly](https://docs.fly.io/postgres).
  - Neon: free 100 CU-h; PgBouncer transaction pooling needs `DISABLE_SERVER_SIDE_CURSORS=True` [Neon](https://neon.com/docs/guides/django.md).
  - Supabase: Pro $25/mo [Supabase](https://supabase.com/pricing).
  - `btree_gist` is documented on Render, Fly, Neon and Supabase; on Railway it is **UNVERIFIED**.
- **Recommend a Johannesburg VPS** (from $5/mo [Vultr](https://api.vultr.com/v2/plans)) with Compose and an off-box `pg_dump`. Nairobi→Vultr JNB measured 62 ms against 73 ms to AWS Cape Town, one server-to-server measurement [latency](https://tracemapper.com/blog/cloud-latency-33-cities).
- **Webhook tunnels** *(src)*:
  - ngrok free: one dev domain, 20k req/mo; the interstitial hits only browser GETs [ngrok](https://ngrok.com/docs/pricing-limits/free-plan-limits).
  - `cloudflared` quick tunnels: 200 in-flight requests, no SSE, random URL [CF](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
  - AT simulator: [help](https://help.africastalking.com/en/articles/1170660-how-do-i-get-started-on-the-africa-s-talking-sandbox).
  - No AT callback signatures or IP lists are documented (**UNVERIFIED**); use a secret path token and verify via the API.
- **Django security:**
  - Run `manage.py check --deploy` with `SECURE_PROXY_SSL_HEADER`, `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` (ramp up), secure cookies, `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` [checklist](https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/).
  - Built-in CSP covers Django-served pages such as the admin [CSP](https://docs.djangoproject.com/en/6.1/ref/csp/). Set the app's CSP in Next `proxy.ts` [guide](https://nextjs.org/docs/app/guides/content-security-policy).
  - `django-ratelimit` 4.1.0 dates from 2023-07, so use DRF throttles + `django-axes`.
  - `django-cors-headers` 4.9.0 supports Django 6.0 (6.1 support is on main, unreleased) and is only needed in dev.
- **Observability:**
  - `sentry-sdk` 3.0.0: span streaming is the default, `send_default_pii` is replaced by `data_collection`, and logging integrations are off by default [migration](https://docs.sentry.io/platforms/python/migration/2.x-to-3.x/).
  - `@sentry/nextjs` 11.17.0; `structlog` 26.1.0 + `django-structlog` 11.0.0.
- **Testing:** `pytest` 9.2.0, `pytest-django` 4.14.0, `model-bakery` 1.25.0, `time-machine` 3.6.0, `ruff` 0.17.6. `factory-boy` 3.3.3 is from Feb 2025 with no Python 3.14 or Django 6 classifiers.

## 9. Unverified / open
- AT Payments availability and AT callback authentication.
- The Next trailing-slash loop end-to-end.
- `@tailwindcss/turbopack` 4.3.5 fix status.
- PG19 with Django and psycopg.
- shadcn calendar on react-day-picker v10 at runtime.
- Orval with MSW 3.
- Browser `sw` Intl coverage.
- Mombasa-specific latency.

## Recommended final stack (with exact package names + versions) and why
**Data:** PostgreSQL **18.7** + `btree_gist`.

**Backend (uv, Python 3.14.4):**
- `django==6.1.3` (→ 6.2 LTS), `djangorestframework==3.18.3`, `psycopg[binary,pool]==3.3.9`, `drf-spectacular==0.30.0`, `django-filter==26.2`
- `procrastinate[django]==3.12.0`, `django-allauth[headless]==65.22.1`, `phonenumbers==9.0.44`, `django-phonenumber-field==9.0.0`
- `requests==2.34.2`, `icalendar==7.3.2`, `django-axes==9.1.0`, `whitenoise==6.12.0`, `gunicorn==27.0.1` / `uvicorn==0.54.0`
- `sentry-sdk==3.0.0`, `structlog==26.1.0`, optional `django-environ==0.14.0`
- Dev: `pytest==9.2.0`, `pytest-django==4.14.0`, `model-bakery==1.25.0`, `time-machine==3.6.0`, `ruff==0.17.6`
- Skip: the AT SDK, simplejwt, django-csp, django-ratelimit, Channels (for now).

**Frontend (Node 26 or 24):**
- Framework: `next@16.4.6`, `react` and `react-dom@19.3.1`, `typescript@~6.0.3`, `@types/node@^24`, `tailwindcss` and `@tailwindcss/postcss@4.3.5`
- UI: `shadcn@4.23.0` (+ `radix-ui@1.8.1` or `@base-ui/react@1.9.0`), `tw-animate-css@1.4.0`, `lucide-react@1.79.0`, `sonner@2.0.8`
- Data and forms: `@tanstack/react-query@5.108.4`, `@tanstack/react-table@9.3.1`, `react-hook-form@7.92.0`, `zod@4.6.7`, `@hookform/resolvers@7.0.9`
- Dates and charts: `react-day-picker@10.0.2`, `date-fns@4.4.0`, `recharts@3.11.1` + `react-is@19.3.1`
- Maps and misc: `leaflet@1.9.4` + `react-leaflet@5.0.0` + `@types/leaflet@1.9.22`, `next-intl@4.16.1`, `input-otp@1.5.0`
- Tooling: `orval@8.49.0`, `eslint@^9` + `eslint-config-next@16.4.6`, `@sentry/nextjs@11.17.0`
- Test: `@playwright/test@1.65.1`, `vitest@5.1.1`, `vite@^8.3.8`, `@vitejs/plugin-react@6.3.0`, `jsdom@31.0.1`, `@testing-library/react@16.3.3` + `@testing-library/dom@^10`, `msw@3.0.7`
- Skip: `@tremor/react`, openapi-typescript, next-pwa, Serwist (for now).

**Ops:** Compose (`postgres:18`, api, Procrastinate worker, Next standalone, Caddy 2.11.9) on a Johannesburg VPS; ngrok or cloudflared for dev webhooks; Sentry.

**Why:**
1. The database enforces no-double-booking, not application code.
2. One Postgres runs data, queue, scheduler and notifications, so no Redis.
3. Same-origin cookies avoid token and CORS pitfalls.
4. Every pin is supported by its neighbours (TS 6, ESLint 9, vite 8, Next ≥16.4.5).
5. Africa's Talking is plain REST behind a thin client, so it is immune to SDK drift.
6. Django 6.1 → 6.2 LTS gives support to Apr 2030.
