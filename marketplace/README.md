# Amina Stays on the Africa's Talking Marketplace

Everything needed to publish Amina Stays as a plugin on the [Africa's Talking Marketplace](https://marketplace.africastalking.dev): how the image is built and pushed, the values for each section of the submission form, and what a customer does after deploying.

| File | What it is |
|---|---|
| [`../Dockerfile`](../Dockerfile) | The plugin image: the website, the API and the scheduler in one container, listening on `$PORT` (8080) |
| [`../docker/supervise.py`](../docker/supervise.py) | The image's entrypoint: settings from the environment, database wait, migrations, demo data, then the three processes |
| [`../.github/workflows/ci.yml`](../.github/workflows/ci.yml) | Tests, then builds the image and pushes it to the marketplace registry |
| [`listing.json`](listing.json) | The listing below, machine-readable |
| [`logo.png`](logo.png) · [`logo-1024.png`](logo-1024.png) · [`logo.svg`](logo.svg) | The logo (512 px, 1024 px, vector). The form won't submit without a logo |

## How the image runs

One container per customer instance. The Next.js server answers on `0.0.0.0:$PORT` and passes `/api`, `/at` (the Africa's Talking callbacks), `/admin`, `/static`, `/media` and `/health` to Django (gunicorn) on `127.0.0.1:8000`; the scheduler runs alongside. On every start `docker/supervise.py`:

1. takes the database from `DATABASE_URL`, or composes it from `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD`, `POSTGRES_HOST`/… or `PGHOST`/… (whichever the platform injects);
2. defaults `FRONTEND_URL` to `PUBLIC_URL`, and `ALLOWED_HOSTS` to the `PUBLIC_URL` host, `.africastalking.marketplace.dev`, loopback and the container's own addresses;
3. refuses to start without a valid `ID_ENCRYPTION_KEY`, or without `SECRET_KEY` unless `DEMO=1` (see the variables below);
4. waits up to 60 s for PostgreSQL, runs `migrate`, loads the demo data on a demo's first start, and gives `AMINA_PHONE` the owner role;
5. starts gunicorn, then the website once the API answers, then the scheduler, and writes the go-live warnings (`manage.py check --deploy --tag security`) to the log.

If any of the three processes dies the container exits, so the platform restarts it. `SIGTERM` stops everything in about 5 seconds (`STOP_TIMEOUT`).

## 1. Build and push the image

The marketplace pulls images from its own registry. Your credentials are on the marketplace under **AT Registry Credentials**: a **Registry Host**, a **Username** and a **Password**. The submission form only accepts an image URL shaped like `registry-host/username/image-name:tag` (no slashes or dots in the image name, and a tag is required).

### By hand

From the repository root, with Docker:

```bash
REGISTRY=<Registry Host>                 # e.g. registry.example.com
NAMESPACE=<Username>                     # lowercase
IMAGE=$REGISTRY/$NAMESPACE/amina-stays

docker login "$REGISTRY"                 # Username and Password from AT Registry Credentials
docker build --platform linux/amd64 -t "$IMAGE:v1.0.0" -t "$IMAGE:latest" .
docker push "$IMAGE:v1.0.0"
docker push "$IMAGE:latest"
```

`--platform linux/amd64` matters on Apple Silicon and other ARM machines: the marketplace runs amd64. If the Registry Host the marketplace shows already ends in your namespace (`registry.example.com/yourname`), use it as it is: `IMAGE=<Registry Host>/amina-stays`.

Try the image before pushing it, with a throwaway database:

```bash
docker network create amina-test
docker run -d --name amina-test-db --network amina-test \
  -e POSTGRES_USER=amina -e POSTGRES_PASSWORD=amina -e POSTGRES_DB=amina postgres:18
docker run --rm --network amina-test -p 8080:8080 \
  -e DB_HOST=amina-test-db -e DB_NAME=amina -e DB_USER=amina -e DB_PASSWORD=amina \
  -e DEMO=1 -e PUBLIC_URL=http://localhost:8080 \
  -e ID_ENCRYPTION_KEY="$(python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')" \
  "$IMAGE:v1.0.0"
# http://localhost:8080 (guest site), /demo (Demo Lab), /host (log in as +254 700 000 001; the code shows on screen)
docker rm -f amina-test-db && docker network rm amina-test
```

### With GitHub Actions

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs the backend tests (PostgreSQL 18), the frontend type check and lint, then builds the image. In the GitHub repository, add three secrets under **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `AT_REGISTRY` | the Registry Host |
| `AT_REGISTRY_USERNAME` | the Username |
| `AT_REGISTRY_PASSWORD` | the Password |

Every push to `main` and every tag then pushes `<AT_REGISTRY>/<AT_REGISTRY_USERNAME>/amina-stays:latest` and `:sha-<short commit>`, plus `:<tag>` for a tag such as `v1.0.0`. Pull requests and other branches, and runs without the secrets, only build the image. For the listing, prefer a version tag (`:v1.0.0`) over `:latest`, so each deployment runs a known build.

## 2. The submission form

### Name and slug

- **Name:** `Amina Stays`
- **Slug:** `amina-stays`

### Logo

Upload [`logo.png`](logo.png) (512 × 512, transparent corners). [`logo-1024.png`](logo-1024.png) and [`logo.svg`](logo.svg) are there if a larger or vector version is asked for.

### Short description

```text
Direct bookings and guest care for hotels, guesthouses and short-stay hosts, on the web, USSD, SMS and voice, built on Africa's Talking.
```

### Long description

Markdown, 5,000 characters at most (this one is about 3,700):

```markdown
**Amina Stays** gives hotels, guesthouses and short-stay hosts one booking and guest-care system that works on every phone. Guests book and get help on the website, or by **USSD, SMS and voice** through Africa's Talking, so a guest with a feature phone or no data is served like everyone else.

### What it does
- **Bookings on every channel.** Search, all-in prices and card checkout on the web; a full booking by USSD (any phone, no data), by text in English, Kiswahili, French, German or Italian, or by calling the voice menu. One calendar, kept in sync with Airbnb and Booking.com, so a room is never sold twice.
- **Support desk with call-backs.** Every request gets a reference on whichever channel it arrives. Reply from the console or by SMS, or tap Call: Africa's Talking rings you first, then connects you to the guest without showing their number. Unanswered requests escalate by SMS, then by phone.
- **Service alerts.** Tell the guests a power, water or Wi-Fi outage affects before they ask, and again when it's fixed. Guests caught by a Wi-Fi or power cut get a mobile data bundle.
- **Local guide.** Beaches, food, transport and what's on, by USSD, SMS, voice and web, closest to the guest's home first.
- **Rewards in airtime and data.** Points for stays and reviews, swapped for airtime or data bundles; a referral pays both guests.
- **Safer check-in.** The door code goes out by SMS on arrival morning, only once the balance is paid, the guest register is complete and an Africa's Talking **SIM-swap check** passes.
- **Runs the stay.** Messages from booking to review, breakfast orders for the kitchen, cleaning tasks, an SOS line that alerts the host and staff, an encrypted guest register and the tourism levy return.

### Who it's for
Hosts with a handful to a few dozen rooms or apartments (guesthouses, small hotels, serviced apartments, holiday homes), especially where many guests use feature phones or have little data. Built for Kenya's coast: prices are in KES and M-Pesa is supported; SMS, USSD and voice work wherever Africa's Talking does.

### What you set up in Africa's Talking
You use your own Africa's Talking account; SMS, USSD, voice, airtime and data are billed to it.

1. A live app (or the sandbox to try it): its username and API key.
2. An approved **sender ID** or a two-way **shortcode** for SMS (without one, messages only reach Airtel numbers in Kenya).
3. A **USSD code**, and a **voice number** for calls (Voice has no sandbox).
4. Optionally, a **Mobile Data** product and airtime balance for rewards and outage bundles.
5. These callback URLs, where `<instance>` is your instance's address and `<secret>` your `AT_WEBHOOK_SECRET`:

| Product | Callback URL |
|---|---|
| USSD | `https://<instance>/at/<secret>/ussd` |
| USSD end of session (optional) | `https://<instance>/at/<secret>/ussd/events` |
| SMS incoming messages | `https://<instance>/at/<secret>/sms/incoming` |
| SMS delivery reports | `https://<instance>/at/<secret>/sms/delivery` |
| SMS opt-out | `https://<instance>/at/<secret>/sms/optout` |
| Voice | `https://<instance>/at/<secret>/voice` |
| Airtime status | `https://<instance>/at/<secret>/airtime/status` |
| Mobile Data status | `https://<instance>/at/<secret>/data/status` |
| SIM Swap (Insights) | `https://<instance>/at/<secret>/insights/simswap` |

Card payments go to your own Stripe account (webhook: `https://<instance>/api/payments/stripe/webhook`); M-Pesa through Safaricom's Daraja can be added after its Go-Live. To look around first, deploy with `DEMO=1`: demo homes and bookings, and a Demo Lab that drives USSD, SMS and voice in the browser, no handset needed.
```

### Image URL

`<Registry Host>/<Username>/amina-stays:v1.0.0`: the image pushed in step 1. It must match `^(?:([a-zA-Z0-9][a-zA-Z0-9.-]+)\/([a-zA-Z0-9_-]+)\/)?([a-zA-Z0-9_-]+):([a-zA-Z0-9_.-]+)$`, so a registry host with a port (`host:5000`) isn't accepted. A leading `https://` is stripped by the form.

### Git repository (optional)

`https://github.com/David-0chieng/Amina_stays`. Leave the repository username and password empty while it's public.

### Database

**PostgreSQL**. Bookings rely on a PostgreSQL exclusion constraint (the `btree_gist` extension, created by the first `migrate`; on PostgreSQL 13+ the database owner may create it). MySQL and MongoDB won't work.

### Environment variables

What customers set when they deploy. "Secret" values should be marked secret in the marketplace (in its bulk text box, end the line with `#[isSecret]`).

| Variable | Required | Description | Example |
|---|---|---|---|
| `PUBLIC_URL` | **Yes** | The instance's https address: its Domain on the instance page, or your own domain. Links in SMS (trips, card payments), payment returns and logins depend on it: without it, logging in and booking from the browser fail. Set it after the first deploy if the address isn't known before, then restart the instance. | `https://your-app.africastalking.marketplace.dev` |
| `SECRET_KEY` | **Yes** (secret) | Signs logins and login codes. Keep it stable: changing it logs everyone out. With `DEMO=1` and no key, a random one is used on each start. | `python3 -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `ID_ENCRYPTION_KEY` | **Yes** (secret) | Encrypts guests' ID and passport numbers (Kenya's Data Protection Act). The container won't start without a valid one. Never change it once guests have registered: their ID numbers would become unreadable. | `python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` |
| `AMINA_PHONE` | **Yes** | The host's own phone number: the login for the host console at `/host` (made the owner account on every start). Set it before the first start: it also becomes the Host phone in **Settings → Business** (relayed questions, SOS calls, the morning digest), which can be changed there later. | `+254712345678` |
| `AT_USERNAME` | To go live | The Africa's Talking app username; `sandbox` sends to the simulator only. | `sandbox` |
| `AT_API_KEY` | To go live (secret) | That app's API key. Without it every SMS, call, airtime and data top-up is a dry run (logged, not sent). | *(from the AT dashboard)* |
| `AT_SENDER_ID` | One of the two | An approved alphanumeric sender ID for outgoing SMS. | `AMINASTAYS` |
| `AT_SMS_NUMBER` | One of the two | The two-way shortcode or number for "Ask Amina" (incoming SMS), shown to guests. | `20880` |
| `AT_USSD_CODE` | For USSD | The USSD code shown to guests. Add it as its own row: the bulk box drops everything from a `#` (the container puts a missing closing `#` back). | `*384*12345#` |
| `AT_VOICE_NUMBER` | For voice | The voice number, in international format. | `+254711082000` |
| `AT_DATA_PRODUCT` | No | The Mobile Data product name for welcome, outage and reward bundles. | `AminaData` |
| `AT_WEBHOOK_SECRET` | Recommended (secret) | Puts a secret in every callback URL (`/at/<secret>/…`), so nobody can post fake USSD, SMS, voice or payment callbacks. Use letters and digits only. | `python3 -c "import secrets; print(secrets.token_hex(24))"` |
| `DEMO` | No | `1` adds the Demo Lab, demo shortcuts and login codes shown on screen, so **anyone can log in as the host**: for trying it out only, with `AT_USERNAME=sandbox` (the demo data has made-up phone numbers). Default `0`. | `0` |
| `SEED_DEMO` | No | Demo homes and bookings on the first start. Empty: only with `DEMO=1`; `1`: even without it; `0`: never. A database that already has homes is never seeded. | *(empty)* |
| `STRIPE_SECRET_KEY` | No (secret) | Card payments through Stripe Checkout. Empty: a simulated card page (no money moves). | `sk_live_…` |
| `STRIPE_WEBHOOK_SECRET` | No (secret) | Signing secret of a Stripe webhook to `https://<instance>/api/payments/stripe/webhook` for the `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed` and `checkout.session.expired` events: confirms card payments at once (otherwise on the guest's return, or within 2 minutes). | `whsec_…` |
| `GUIDE_REGION` | No | Added to local-guide map searches ("Fort Jesus, Old Town, Kenya"). Default `Kenya`. | `Kenya` |
| `WEB_CONCURRENCY` | No | API worker processes (4 threads each, roughly 100 MB of memory each). Default `2`; `1` on a 512 MB instance. | `2` |

Less common ones: `AT_WHATSAPP_NUMBER` (WhatsApp channel), `SIM_SWAP_PROVIDER` (`africastalking` or `simulate`), `MPESA_PROVIDER` and the `DARAJA_*` keys (M-Pesa, see the main [README](../README.md#payments)), `CARD_PROVIDER`/`PAYSTACK_SECRET_KEY`, `IGLOOHOME_API_KEY`/`IGLOOHOME_API_BASE` (smart locks), `SECURE_HSTS_SECONDS` (once the domain is final), `ALLOWED_HOSTS` (replaces the default list; only needed for an extra domain), `LOG_LEVEL`, `SCHEDULER_INTERVAL_SECONDS`, `DB_WAIT_SECONDS` (60) and `STOP_TIMEOUT` (5). [`.env.example`](../.env.example) documents them all. Never set `DEBUG` on an instance. The database variables come from the platform.

For the bulk text box (fill in the values; lines starting with `#` are ignored):

```dotenv
PUBLIC_URL=https://your-app.africastalking.marketplace.dev
SECRET_KEY=<generated> #[isSecret]
ID_ENCRYPTION_KEY=<generated> #[isSecret]
AMINA_PHONE=+254712345678
DEMO=0
AT_USERNAME=sandbox
AT_API_KEY=<from Africa's Talking> #[isSecret]
AT_WEBHOOK_SECRET=<generated> #[isSecret]
# AT_SENDER_ID=AMINASTAYS
# AT_SMS_NUMBER=20880
# AT_VOICE_NUMBER=+254711082000
# AT_DATA_PRODUCT=AminaData
# STRIPE_SECRET_KEY=sk_live_... #[isSecret]
# STRIPE_WEBHOOK_SECRET=whsec_... #[isSecret]
```

Then add `AT_USSD_CODE` as a row of its own.

### Categorisation

- **Africa's Talking products:** USSD, Voice, Airtime, Insights, Bulk SMS, Mobile Data (Insights is the SIM-swap check; Premium SMS isn't used).
- **Industry:** Other (hospitality and tourism).

### Pricing plans

| Plan | Currency | Amount | Billing | Trial | Description |
|---|---|---|---|---|---|
| Starter | KES | 2,500 | Monthly | 14 days | Up to 3 homes or rooms. Bookings on the web, USSD, SMS and voice; support desk, service alerts, local guide, rewards and the host console. Africa's Talking usage is billed to your own AT account. |
| Business | KES | 7,500 | Monthly | 14 days | Up to 15 homes or rooms, with everything in Starter: for guesthouses and small hotels with staff (cleaners, cook, caretaker, security). Africa's Talking usage is billed to your own AT account. |

Notes for the seller: the app doesn't enforce the home limits, so they describe the tier rather than lock it. Both plans are in KES because the app is built for Kenya: stays are priced in KES (with USD, EUR and GBP estimates), and airtime and data rewards need Kenyan (+254) numbers. Add plans in other currencies once the app supports them.

### Terms and privacy

Tick the box accepting the marketplace's Terms of Service and Privacy Policy: the form won't submit without it. If the form asks about in-app purchases, the answer is no (guests pay the host through Stripe or M-Pesa; nothing is sold inside the plugin).

## 3. After the first deploy

1. Open the instance page, copy its **Domain** and set `PUBLIC_URL` to `https://<that domain>` (or your custom domain) in the instance's environment variables, then **Restart**.
2. In the Africa's Talking dashboard, register the callback URLs from the table above for the USSD code, the SMS shortcode (incoming messages, delivery reports, opt-out), the voice number, Airtime, Mobile Data and Insights. In Stripe, add the webhook.
3. Log in at `https://<instance>/host` with `AMINA_PHONE`. The code comes by SMS with live keys, in the [simulator](https://developers.africastalking.com/simulator) (as that number) with `sandbox`, on screen with `DEMO=1`, and only in the instance log (`Login code for …`) without keys.
4. Read the instance log after a start. Its `[check]` lines list each setting a live site still needs and the variable that fixes it:
   - `amina.W001`–`W020`: DEMO still on (W001), Africa's Talking missing or in sandbox (W002, W003), no webhook secret (W004), `PUBLIC_URL` not https or missing from `ALLOWED_HOSTS` (W005, W015), simulated cards or a Stripe test key or no webhook (W009, W018–W020), no SMS sender (W013), the demo `AMINA_PHONE` (W017), M-Pesa settings (W006–W008, W014, W016), smart locks not connected (W012, optional);
   - Django's `security.W004` (HSTS) and `security.W008` (SSL redirect) are expected: HTTPS ends at the marketplace's front end. Leave the SSL redirect off; set `SECURE_HSTS_SECONDS` once the domain is final.
5. In the host console, **Channels** shows which Africa's Talking products are configured and the account balance. Dial the USSD code and text the shortcode in the simulator to check the callbacks.

## Known limitations

- **Uploaded photos live on the container's disk** (`/app/backend/media`): they're lost when the instance is redeployed or moves, and not shared between instances. Add listing photos by URL (the listing editor takes `https://` photo links), or mount a volume at `/app/backend/media` if the platform offers one.
- **Scaling to zero pauses the scheduler.** Reminders, door codes, hold expiry, payment checks and automatic checkouts run only while the instance is up, which is why the scheduler runs inside the container rather than as a separate service. Jobs that fell due while it was asleep run on the next start (daily jobs the same day). To keep it running, keep one instance warm if the plan allows, or have an uptime monitor open `https://<instance>/health` every few minutes. Where cron can reach the database, `python manage.py tick` runs one pass: `docker run --rm -e DATABASE_URL=… <image> python manage.py tick` (the entrypoint runs any command with the same settings).
- **Cold starts take several seconds.** The first USSD session or call after the instance has scaled to zero can time out on Africa's Talking's side; keeping it warm avoids that.
- **`DEMO=1` is for evaluation only:** login codes show on screen, so anyone can log in as the host. Without `SECRET_KEY`, a demo instance also logs everyone out on each restart.
- **Memory:** about 420 MB with the default two API workers (measured: website 105 MB, each API worker 90 MB, scheduler 90 MB, the rest 50 MB), about 330 MB with `WEB_CONCURRENCY=1`. 512 MB is the minimum; 1 GB leaves room.
- **Port 8000 is taken inside the container** (the API). The platform's `PORT` can be anything else.
- Several instances of one deployment are safe (start-up migrations and scheduler passes take PostgreSQL advisory locks), but each has its own uploaded files.
- Kenya-specific features: KES prices, M-Pesa, airtime and data rewards (+254 numbers), the tourism levy return and Kenyan ID types. Phone numbers typed in local format are read as Kenyan; other countries' numbers need their `+` code (USSD, SMS and voice callbacks already carry it).
- The image is built for `linux/amd64`.
