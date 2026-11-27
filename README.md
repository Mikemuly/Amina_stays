# Amina Stays

**Book, pay, check in and get help — on the web, by USSD, by SMS or with a phone call.**

Amina Stays is a direct-booking and guest-communication platform for a small host with several apartments on the Kenyan coast. It was built for the *Innovate Mombasa: Hospitality & Tourism Hackathon* (Africa's Talking, Nov 2026), AMINA-STAYS challenge:

> Amina has several apartments in Mombasa and struggles to communicate prices, suites, breakfast preferences and check-in information to guests.

Our answer is one source of truth for every home: prices, suites, breakfast, check-in. It is available on **every channel** a Kenyan or international guest might use, and it automates the whole stay from enquiry to review. Amina runs it from a host console, or from her own phone by SMS.

| | |
|---|---|
| 🌍 **Web** | Search with an all-in price, listing pages, checkout by card through Stripe (or M-Pesa with a Paybill fallback, once Safaricom's Go-Live is done), in full or with a 30% deposit, and a living trip page with directions, Wi-Fi, door code, breakfast, extras, help, date changes and extensions, and a tax invoice |
| 📟 **USSD** | Full booking with no data and no smartphone. Also: prices, my booking, breakfast, report a problem, talk to Amina (a call-back, **a typed question answered on the spot**, a complaint, my requests), check out, emergency, and More: the local guide, service status, rewards and language |
| 💬 **SMS — "Ask Amina"** | Natural-language booking in English, Kiswahili, Italian, German and French; instant answers from each home's knowledge base; complaints with a reference (`COMPLAIN`, `TICKETS`), the local guide (`EXPLORE`), service status (`ALERTS`), rewards (`POINTS`); HELP for emergencies |
| 📞 **Voice — "Call Amina"** | English/Kiswahili IVR: availability and booking, prices, directions, bridge to Amina, voicemail, a complaint by voice message, things to do nearby, emergencies; call-backs that ring Amina and connect her to the guest |
| 🛎️ **Host console** | Today view, multi-home calendar and pricing, reservations, a unified inbox, tasks and kitchen, listings editor, guest CRM, messaging automations, reviews, insights with the TRA return, payments, safety and channels, plus the support desk, service alerts, local guide and rewards & airtime |

**Research first.** We studied Airbnb, Booking.com, Vrbo, Agoda and Trip.com, small-host operations, Kenyan regulation and Africa's Talking's real limits before writing code, then compared every guest and host flow end to end with Airbnb, Hospitable and Hostaway. See [docs/RESEARCH.md](docs/RESEARCH.md) for the problem → solution matrix, and [docs/research/](docs/research/) for the eight full briefs with sources.

**Run it on your machine:** [Windows](#windows) · [Linux](#linux) · [Docker, any system](#any-system-docker). You don't need any API keys: SMS, voice and payments are simulated.

---

## For the judges

| Criterion | Where to look |
|---|---|
| **Usefulness** | Amina's daily pain (prices, suites, breakfast, check-in) is answered on every channel from one knowledge base. Her console's Today view and morning SMS digest show what needs doing; staff work from SMS. |
| **Solves the problem** | Prices: the same all-in price on web/USSD/SMS/voice. Suites: what's free on the guest's dates, by SMS, USSD (book, or just ask) and voice. Breakfast: structured preferences that reach the cook's sheet. Check-in: staged directions, Wi-Fi and a door code on arrival morning. Other details: a knowledge base that answers on SMS and USSD, and passes anything else to Amina's phone. See the [simulator demo](#demo-script-on-the-africas-talking-simulator-5-minutes) and the [problem → solution matrix](docs/RESEARCH.md#industry-problems-and-how-amina-stays-answers-them). |
| **Implementation** | Django + PostgreSQL with a database-enforced no-double-booking guarantee, idempotent payments, an outbox for messages, a single-instance scheduler and Stripe card payments confirmed three ways (webhook, return page, scheduler); Next.js 16 front end; 629 backend tests, including end-to-end flow suites for every channel. See [Architecture](docs/ARCHITECTURE.md). |
| **Africa's Talking** | SMS (two-way, delivery reports, opt-out, service alerts), USSD, Voice (IVR, call-back bridging, voice complaints, escalation and safety calls), Airtime (rewards, referrals, gifts), Mobile Data (outage and reward bundles), SIM Swap; WhatsApp and AT checkout optional. Every challenge area is covered: see [the add-ons](#africas-talking-challenge-add-ons). |
| **Demo** | On the free Africa's Talking sandbox: five guests and Amina in the [simulator](#demo-script-on-the-africas-talking-simulator-5-minutes), with real USSD sessions, SMS and airtime. Or `/demo` (`DEMO=1`) runs every channel in the browser, with no handset or API key needed. |

---

## Africa's Talking challenge add-ons

Amina Stays also answers the six challenge areas of Africa's Talking's hospitality and tourism hackathons. They all use the same phone-number account, work with no data and are simulated when there are no API keys.

| Challenge | What Amina Stays does | AT APIs | Try it |
|---|---|---|---|
| **Customer service & support** | A **support desk**. Every complaint, question or call-back request gets a reference (T12) and a reply-by time, whether it came by SMS (`COMPLAIN …`, `CALL ME`), USSD (Talk to Amina → Make a complaint), a voice message (press 5) or the website. Amina answers in the console or by SMS (`T12 …`), or taps **Call**: Africa's Talking rings her phone and connects her to the guest. An unanswered request escalates: an SMS to Amina and her backup, then a phone call. Guests rate the outcome 1–5 by SMS. | Voice, SMS | Demo Lab: as Wanjiku, text `COMPLAIN the music next door is too loud`, then answer from Amina's phone with the reference she got (`T7 Pole sana!` on fresh demo data); Host › Support desk |
| **USSD services** | Everything works with no data: booking, my booking, breakfast, report a problem, talk to Amina, check out, emergency and **More**: the local guide, service status, rewards and language. Under Talk to Amina, **Ask a question** takes a typed question ("free suites this weekend", "Diani", "is there a pool?", "breakfast", "wifi password") and answers it on screen from the same homes, calendars and knowledge base as the website, with links by SMS; anything else goes to Amina's phone. Every screen fits in 160 characters. | USSD | Demo Lab USSD phone: 6 → 2 (Ask a question), 8 → 1 (Explore), 8 → 2 (Service status), 8 → 3 (Rewards) |
| **Service & network notifications** | **Service alerts**. Amina, or a caretaker by SMS (`OUTAGE POWER ALL generator on`), posts an outage or planned maintenance. The guests staying at those homes, and anyone arriving while it lasts, get an SMS: a day ahead for planned work, again if the expected time changes, and when it's fixed. A guest who reports a problem an alert already covers gets the alert instead of a new work order. `ALERTS` by SMS or USSD shows the status. | SMS | Demo Lab time machine: *Wi-Fi outage at this home*, then *Fix it*; Host › Service alerts |
| **Airtime & customer incentives** | **Amina Rewards**: points for every stay and for feedback, swapped for airtime (`REDEEM AIRTIME`); invite codes (`REF <code>`) that pay airtime to both guests after the friend's first stay; airtime gifts from the console. Every top-up goes through one ledger with an idempotency key, a monthly budget (over it, rewards wait for Amina's approval) and Africa's Talking's delivery callbacks; a failed top-up gives the points back. | Airtime | Demo Lab: text `POINTS`, then `REDEEM AIRTIME`; the guest's account page; Host › Rewards & airtime |
| **Mobile connectivity** | When the Wi-Fi or power fails, every guest staying gets a mobile-data bundle automatically (a guest who arrives later can text `DATA`). Points also swap for data (`REDEEM DATA`), and arriving guests can get a welcome bundle. | Mobile Data | The time-machine outage: the guest's alert SMS mentions the bundle; Host › Rewards › payouts |
| **Smart communication platforms** | One conversation per guest across SMS, USSD, voice, WhatsApp and the web: a request raised on USSD is answered by SMS and closed after a call; a tourist with no data browses the guide by USSD and gets the map link by SMS. | SMS, USSD, Voice | All of the above |

The **local guide** has 28 real places on the coast and what's on, sorted by distance from the guest's home. It's on the web at `/guide`, by USSD, by SMS (`EXPLORE`, `EVENTS`, `FOOD`) and on a call (press 6).

The app is also packaged for the **Africa's Talking Marketplace** as one Docker image: see [Africa's Talking Marketplace](#africas-talking-marketplace).

---

## What makes it work for Mombasa

- **No double bookings across channels.** A PostgreSQL exclusion constraint makes the database itself refuse overlapping stays from the web, USSD, SMS, voice and iCal (Airbnb/Booking.com). A two-channel race is covered by a test.
- **All-in prices everywhere.** Nights + cleaning + 2% tourism levy, with USD/EUR/GBP approximations. No surprise fees.
- **Check-in without a phone call.**
  - Address once booked; directions and Wi-Fi 48 h before.
  - The **door code by SMS at 08:00 on arrival day**, only once the balance is paid, the guest register is complete and an **Africa's Talking SIM-swap check** passes.
  - The code stops working at checkout.
- **Breakfast that reaches the kitchen.** Style (Swahili, continental, full English, vegetarian), people, time and dietary needs (halal, vegan, gluten-free…) are chosen at booking, on the trip page, by SMS or USSD. The cook gets tomorrow's sheet at 18:00.
- **Payments that recover.**
  - Cards go through **Stripe Checkout**, Stripe's hosted page, so card numbers never touch the server. The stay confirms the moment the guest is back from Stripe (or when Stripe's webhook arrives). Guests on USSD, SMS or a phone call get a short card link by SMS, and a cancellation refund goes back to the card by itself.
  - M-Pesa is built in and switches on after Safaricom's Daraja Go-Live. A failed prompt (wrong PIN, cancelled, low balance, phone unreachable) then gets a plain explanation and the right next step: resend, pay the 30% deposit, card, or the **Paybill** with the booking reference as the account number. Paybill payments are matched to the booking automatically.
  - Balances are chased by a reminder ladder, overpayments are refunded, and every stay gets a numbered invoice (with credit notes for refunds).
- **Plans change.** Guests change dates or guests, or extend, from the trip page or by texting EXTEND. The stay is re-priced, and they pay the difference or get it back under the cancellation policy; Amina can require approval. Sold-out dates offer "Notify me" and an SMS when they free up.
- **Safety.**
  - Text HELP, dial 9 on USSD, press 9 on a call, or tap SOS. Amina, the caretaker and security are alerted together, and voice calls escalate until someone answers.
  - Emergency numbers (999 / 112 / 1199 / 1514) are always one tap away.
- **Operations.**
  - Checkout creates a cleaning task; guest problems become work orders assigned to the right person.
  - Staff reply DONE by SMS.
  - The guard gets the day's arrivals and car plates; Amina gets a morning digest.
- **Compliance built in.**
  - TRA licence on every listing and receipt, with renewal reminders before it expires.
  - An encrypted, consented guest register kept for the 5-year legal period, then purged.
  - A one-click monthly TRA return and the tourism levy in every quote.
  - Data Protection Act export and erasure; promotional SMS only 08:00–18:00, with STOP.

### Africa's Talking products used

**SMS** (two-way, delivery reports, opt-out, service alerts) · **USSD** · **Voice** (IVR, bridging, recording, call-backs, voice complaints, escalation and safety calls) · **Airtime** (rewards, referrals, gifts, an automatic apology when Amina cancels) · **Mobile Data** (outage and reward bundles, an optional welcome bundle) · **Insights SIM Swap** (before door codes) · WhatsApp (optional) · M-Pesa checkout via AT (optional; see [payments](#payments)).

---

## Quick start

You need three tools, or Docker on its own:
- [uv](https://docs.astral.sh/uv/), which also downloads the Python version the backend uses (3.14);
- Node.js 20.9+;
- PostgreSQL 16+.

Clone the repository (or download the ZIP) and open a terminal in its folder.

### Any system: Docker

With [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows, macOS) or Docker Engine (Linux):

```bash
docker compose up --build
```

This starts PostgreSQL 18, the API, the scheduler and the website, and loads the demo data. Ctrl+C stops it; `docker compose down -v` also deletes the database.

### Linux

These steps are for Ubuntu 24.04+ and Debian 13+. Other distributions need the same tools from their own package manager.

1. Install the tools:

   ```bash
   sudo apt update && sudo apt install -y git curl postgresql
   curl -LsSf https://astral.sh/uv/install.sh | sh                                  # uv
   curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash  # nvm, for Node.js
   ```

   Open a new terminal and run `nvm install --lts`. The distribution's own Node.js is too old for Next.js 16.

2. Create the database user and database:

   ```bash
   sudo -u postgres psql -c "CREATE ROLE amina LOGIN CREATEDB PASSWORD 'amina';"
   sudo -u postgres createdb -O amina amina
   ```

3. Start everything:

   ```bash
   export DATABASE_URL=postgres://amina:amina@localhost:5432/amina
   scripts/dev.sh
   ```

   The first run installs the dependencies, creates the tables and loads the demo data. After that, the API (port 8000), the scheduler and the website (port 3000) run until you press Ctrl+C. `scripts/dev.sh --reseed` resets the demo data.

If you can't use sudo, or your distribution's PostgreSQL is older than 16, leave PostgreSQL out of step 1 and skip step 2. Then run `scripts/dev.sh` without `DATABASE_URL`. It uses either:
- PostgreSQL 18 run from the project folder, which you set up with `scripts/db.sh install && scripts/db.sh init` (needs [micromamba](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html)); or
- a database container, if Docker is installed.

<details>
<summary>Linux step by step, instead of <code>scripts/dev.sh</code></summary>

```bash
cp .env.example .env                       # demo mode and the database address
cd backend
uv sync
uv run python manage.py migrate
uv run python manage.py seed_demo
uv run python manage.py runserver          # API on :8000
uv run python manage.py run_scheduler      # second terminal, in backend/
npm install && npm run dev                 # third terminal, in frontend/ → http://localhost:3000
```
</details>

### Windows

**Recommended: WSL 2.**
1. In PowerShell opened as administrator, run `wsl --install`, then restart.
2. Open **Ubuntu** from the Start menu and clone the project into your Ubuntu home folder (`~`). Avoid `/mnt/c`: installs and live reload are much slower there.
3. Follow the Linux steps inside Ubuntu.
4. Open http://localhost:3000 in your Windows browser as usual.

If the database isn't running after a restart, start it with `sudo service postgresql start`.

**Or natively, in PowerShell** (Windows 10 or 11):

1. Install the tools:

   ```powershell
   winget install -e --id Git.Git
   winget install -e --id OpenJS.NodeJS.LTS
   winget install -e --id astral-sh.uv
   winget install -e --id PostgreSQL.PostgreSQL.18 --interactive
   ```

   In the PostgreSQL installer, choose a password for the `postgres` user and keep port 5432. Then close and reopen PowerShell so it finds the new commands, and allow it to run npm (once):

   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
   ```

2. Create the database user and database. Type the `postgres` password when asked:

   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -c "CREATE ROLE amina LOGIN CREATEDB PASSWORD 'amina';"
   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -c "CREATE DATABASE amina OWNER amina;"
   ```

3. Start everything from the project folder:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
   ```

   This works like `scripts/dev.sh` on Linux. The first run installs the dependencies, creates the tables and loads the demo data. After that, the API (port 8000), the scheduler and the website (port 3000) run in this window until you press Ctrl+C. Add `-Reseed` to reset the demo data.

If you have Docker Desktop, you can skip installing PostgreSQL and step 2. When nothing is listening on port 5432, `scripts\dev.ps1` starts the database in a container.

<details>
<summary>Windows step by step, instead of <code>scripts\dev.ps1</code></summary>

1. In the project folder, copy the local settings (demo mode and the database address), then set up and start the API:

   ```powershell
   Copy-Item .env.example .env
   cd backend
   uv sync
   uv run python manage.py migrate
   uv run python manage.py seed_demo
   uv run python manage.py runserver
   ```

2. In a second PowerShell window, from the project folder, start the scheduler. It sends reminders, door codes and automated messages:

   ```powershell
   cd backend
   uv run python manage.py run_scheduler
   ```

3. In a third window, from the project folder, start the website:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```
</details>

### Open the app

| URL | What |
|---|---|
| http://localhost:3000 | Guest site |
| http://localhost:3000/demo | **Demo Lab**: SMS, USSD and voice phones in the browser, Amina's phone and a lifecycle time machine |
| http://localhost:3000/host | Host console: log in as **+254 700 000 001** (Amina); in demo mode the login code is shown on screen |
| http://localhost:8000/api/docs | OpenAPI docs |

Configuration is environment-driven. Every variable is documented, with where to get each key, in [.env.example](.env.example) (the API, the scheduler and Docker Compose; copy it to `.env`) and [frontend/.env.example](frontend/.env.example) (the website; copy it to `frontend/.env.local`). With no keys at all you get:
- dry-run SMS and voice (logged, not sent);
- a simulated card checkout, until a card provider's key is set (Paystack or Stripe; M-Pesa is off; `MPESA_PROVIDER=simulate` adds a pretend M-Pesa prompt for demos);
- simulated smart-lock codes;
- the Demo Lab to drive every channel.

Demo personas (seeded): Giulia 🇮🇹 and Wanjiku 🇰🇪 are staying now, Hans 🇩🇪 arrives today with his ID missing (so his door code is held), Sarah 🇬🇧 arrives tomorrow with a deposit paid and an early check-in request, Peter 🇰🇪 checks out today. Staff: Fatuma (cleaner), Juma (caretaker), Mama Zawadi (cook), Hassan (security).

## Connecting Africa's Talking

1. Create a sandbox app at [africastalking.com](https://account.africastalking.com) and set `AT_USERNAME=sandbox`, `AT_API_KEY`, `AT_USSD_CODE`, `AT_SMS_NUMBER` and a long random `AT_WEBHOOK_SECRET` in `.env`.
2. Expose port 3000: `ngrok http 3000` (or `cloudflared tunnel --url http://localhost:3000`) and set `PUBLIC_URL=https://<your-tunnel>` and `FRONTEND_URL` to the same address. Links in SMS (card payments, trip pages) use `FRONTEND_URL`, and Africa's Talking rejects any SMS that contains a localhost link (HTTP 403).
3. Register these callback URLs in the AT dashboard (replace `<secret>`):

| Product | Callback URL |
|---|---|
| USSD | `https://<tunnel>/at/<secret>/ussd` |
| USSD end-of-session (optional) | `https://<tunnel>/at/<secret>/ussd/events` |
| SMS incoming messages | `https://<tunnel>/at/<secret>/sms/incoming` |
| SMS delivery reports | `https://<tunnel>/at/<secret>/sms/delivery` |
| SMS opt-out | `https://<tunnel>/at/<secret>/sms/optout` |
| Voice (live number only; Voice has no sandbox) | `https://<tunnel>/at/<secret>/voice` |
| Airtime status | `https://<tunnel>/at/<secret>/airtime/status` |
| Mobile Data status | `https://<tunnel>/at/<secret>/data/status` |
| SIM Swap (Insights) | `https://<tunnel>/at/<secret>/insights/simswap` |

4. Test with the [AT simulator](https://developers.africastalking.com/simulator): dial your USSD code or text your shortcode. The host console's **Channels** page shows which products are configured, plus the AT balance.

### Five guests in the simulator

Amina and her guests share one database. The host's number (`AMINA_PHONE`) gets Amina's USSD menu (today, free tonight, requests, message guests) and her SMS commands; every other number is a guest. To show several guests at once, list their numbers in `.env` (any +254 numbers) and add them to the data:

```bash
# .env
SIMULATOR_GUESTS=+254711000001,+254711000002,+254711000003,+254711000004,+254711000005

cd backend
uv run python manage.py simulator_guests   # or reseed: seed_demo --reset adds them too
```

Each becomes a real guest at a different point of a stay, so every menu has something to show. Unlike the seeded personas, their SMS really go out through Africa's Talking:

| # | Guest | Stage | On USSD (dial the code) | By SMS (to the shortcode) |
|---|---|---|---|---|
| 1 | Asha Njeri | Planning a trip, no booking | 2 (prices & homes) · 6 → 2 and type `free suites this weekend` · 1 (book, then pay with the card link) | `Bei?` · `breakfast` |
| 2 | Kevin Mutua | Arrives in two days, paid | 3 → 1 (check-in info) · 4 (breakfast) | `ETA 3pm` · `directions` |
| 3 | Grace Atieno | Staying now | 6 → 2 and type `wifi password` · 5 (report a problem) · 3 → 3 (late checkout) | `no hot water` · `LATE` |
| 4 | Daniel Kiprono | Next week, 30% deposit paid | 3 → 2 (pay the balance by card link) · 6 → 1 (call me back) | `STATUS` · `COMPLAIN …` |
| 5 | Halima Abdalla | Stayed last month, Kiswahili | 8 → 3 (rewards: airtime or data) | `POINTS` · `REDEEM AIRTIME` |

Open the [simulator](https://developers.africastalking.com/simulator) in a new tab (or a private window) for each number, plus one as `AMINA_PHONE`. Amina's phone gets each new booking, problem, complaint and question. She answers by SMS (`#12 <reply>`, `T7 …`, `YES 34`, `STATUS`), or from the host console, where every guest's USSD, SMS and web messages share one inbox.

### Payments

Card payments go through a hosted checkout page, so card numbers never touch this server. For a business registered in Kenya, use **Paystack** (`CARD_PROVIDER=paystack` and `PAYSTACK_SECRET_KEY`, webhook `https://<your-site>/api/payments/paystack/webhook`): Stripe doesn't open accounts for Kenyan businesses and sends them to Paystack, its African company. Paystack's page also takes M-Pesa, and its refunds are sent from the Paystack dashboard, then marked as sent in **Host › Payments**. Elsewhere, **Stripe Checkout** needs two keys in `.env`:

| Variable | What it is |
|---|---|
| `STRIPE_SECRET_KEY` | From the Stripe Dashboard: **Developers → API keys**. A test key (`sk_test_…`) takes Stripe's test card `4242 4242 4242 4242` (any future date, any CVC) and moves no money; a live key (`sk_live_…`) takes real payments. Setting it is all it takes to switch card payments to Stripe. |
| `STRIPE_WEBHOOK_SECRET` | Optional, but it makes every payment confirm at once. In **Developers → Webhooks**, add the endpoint `https://<your-site>/api/payments/stripe/webhook` with the events `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed` and `checkout.session.expired`, then copy its signing secret (`whsec_…`). On a laptop, `stripe listen --forward-to localhost:3000/api/payments/stripe/webhook` prints one. Without a webhook a payment still confirms: when the guest comes back from Stripe, or within 2 minutes. |

Guests on USSD, SMS or a phone call get a short link by SMS (`/pay/card/…`) that opens the same checkout. When a stay is cancelled, the refund goes back to the card through Stripe by itself, split across the stay's card payments (a deposit and the balance, say). A refund that includes money paid another way (cash at the door, say) waits in **Host › Payments** for Amina to send and mark as sent.

M-Pesa is built but **off** until Safaricom's Daraja Go-Live, which takes a while. When it's done:

| Variable | Options |
|---|---|
| `MPESA_PROVIDER` | `off` (default: card only, on every channel) · `simulate` (a pretend prompt, for demos) · `daraja` (Safaricom STK push; set the `DARAJA_*` keys; callback `https://<your-site>/api/payments/daraja/callback/<secret>`) · `africastalking` (AT mobile checkout, onboarding-gated, with no sandbox) |
| `DARAJA_TRANSACTION_TYPE` | `CustomerPayBillOnline` (default, a Paybill) · `CustomerBuyGoodsOnline` (a Till: set `DARAJA_SHORTCODE` to the store number and `DARAJA_PARTY_B` to the Till number) |
| `MPESA_SHORTCODE` | The Paybill guests can pay into when a prompt fails (defaults to `DARAJA_SHORTCODE`). Paybill only: a Till payment carries no account number, so it can't be matched to a booking. Set `DARAJA_CALLBACK_SECRET` (a hex value: Safaricom rejects callback URLs containing words such as `exe`, `cmd` or `sql`); the M-Pesa prompt and Paybill callbacks share it. Then register the Paybill callbacks once by running `uv run python manage.py register_c2b` in `backend/` (it prints the validation and confirmation URLs). |
| `CARD_PROVIDER` | Empty (default): Stripe once its key is set, else a simulated card page · `paystack` (`PAYSTACK_SECRET_KEY`; webhook `https://<your-site>/api/payments/paystack/webhook`) |

Africa's Talking no longer offers self-serve payments with a sandbox (see [research](docs/research/04-africas-talking.md)), so the payment layer is pluggable: Paystack or Stripe for cards today, Safaricom Daraja for M-Pesa once it's approved.

## Going live

Real guests need no code changes. Each simulated service switches to the real one as soon as its keys are set, and the only keys a live site needs are **Africa's Talking's** and a card provider's: **Paystack** for a business in Kenya, **Stripe** where it operates. Direct M-Pesa prompts (Daraja) can be added later.

1. In `backend/`, run `uv run python manage.py check --deploy`. Along with Django's own checks, it lists every key or setting a live site still needs and the variable to set (warnings `amina.W001`–`W020`). It also catches the mistakes that only show up with real guests: no SMS sender, a `PUBLIC_URL` missing from `ALLOWED_HOSTS`, a Stripe test key on a live site, a tunnel URL with live M-Pesa, the sandbox shortcode in production and the demo host phone. Once those are gone, only hosting is left.
2. Fill in `.env` (or your host's environment variables):

   | For | Set |
   |---|---|
   | The site | `DEBUG=0`, `DEMO=0`, `SECRET_KEY`, `ALLOWED_HOSTS`, `FRONTEND_URL` and `PUBLIC_URL` (your https address), `ID_ENCRYPTION_KEY`, `AMINA_PHONE` (the host's own number) |
   | Africa's Talking | `AT_USERNAME`, `AT_API_KEY`, `AT_SENDER_ID` (a sender ID approved in the AT dashboard; without it or `AT_SMS_NUMBER`, AT's default sender only reaches Airtel numbers), `AT_SMS_NUMBER`, `AT_USSD_CODE`, `AT_VOICE_NUMBER`, `AT_WEBHOOK_SECRET`; optionally `AT_DATA_PRODUCT` (the Mobile Data product for outage and reward bundles: without it, live sites offer no data bundles) and `AT_WHATSAPP_NUMBER` |
   | Cards (Paystack, for Kenya) | `CARD_PROVIDER=paystack` and `PAYSTACK_SECRET_KEY` (the live `sk_live_…` key) |
   | Cards (Stripe) | `STRIPE_SECRET_KEY` (the live `sk_live_…` key) and `STRIPE_WEBHOOK_SECRET` |
   | M-Pesa (later, optional) | `MPESA_PROVIDER=daraja`, `DARAJA_ENV=production`, `DARAJA_CONSUMER_KEY`, `DARAJA_CONSUMER_SECRET`, `DARAJA_SHORTCODE`, `DARAJA_PASSKEY` (emailed after Daraja Go-Live), `DARAJA_CALLBACK_SECRET`, `MPESA_SHORTCODE`; for a Till, `DARAJA_TRANSACTION_TYPE=CustomerBuyGoodsOnline` and `DARAJA_PARTY_B` |
   | Smart locks (optional) | `IGLOOHOME_API_KEY`, `IGLOOHOME_API_BASE`, and each home's lock device ID in the listing editor. igloohome's API tokens now expire every 24 hours while the app takes one fixed token, so real locks need a code change first (see `.env.example`) |

3. Register the callback URLs:
   - the [Africa's Talking table above](#connecting-africas-talking);
   - the Stripe webhook, in the Stripe Dashboard ([Payments](#payments) lists the URL and events).

   Once M-Pesa is on, also register the Paybill callbacks with `register_c2b` (M-Pesa prompts carry their own callback URL). Live M-Pesa callbacks must be on your own https domain: Safaricom blocks ngrok and similar tunnels in production.
4. Serve the site over HTTPS, on any host or with `docker compose up -d` behind a TLS proxy, and keep the scheduler running. Reminders, door codes and payment checks depend on it. `migrate` also creates the cache table that every API worker shares, so login-code limits and provider tokens hold across workers. Without Docker, also run `uv run python manage.py collectstatic --noinput` in `backend/` (with `DEBUG=0` set) after each update; the Docker image does this when it's built.

## Africa's Talking Marketplace

Amina Stays is also packaged as a plugin for the [Africa's Talking Marketplace](https://marketplace.africastalking.dev): any business can pick a plan, click Deploy and get its own instance. The root [Dockerfile](Dockerfile) builds one image with the website, the API and the scheduler. It listens on `$PORT` (8080) and needs only PostgreSQL. On every start, [docker/supervise.py](docker/supervise.py) waits for the database and migrates. It loads the demo data when `DEMO=1` and makes `AMINA_PHONE` the host's login.

```bash
docker build --platform linux/amd64 -t <registry-host>/<username>/amina-stays:v1.0.0 .
docker push <registry-host>/<username>/amina-stays:v1.0.0
```

[marketplace/README.md](marketplace/README.md) has every field of the submission form: name, slug, descriptions, logo, image URL, database (PostgreSQL), environment variables, AT products (USSD, Voice, Airtime, Insights, Bulk SMS, Mobile Data), industry and pricing plans. It also covers what a customer does after deploying. [marketplace/listing.json](marketplace/listing.json) has the same in machine-readable form. The [CI workflow](.github/workflows/ci.yml) runs the tests, then builds the image and pushes it from `main` or a tag once the `AT_REGISTRY`, `AT_REGISTRY_USERNAME` and `AT_REGISTRY_PASSWORD` repository secrets are set. `docker compose up` works as before.

## Demo script on the Africa's Talking simulator (5 minutes)

With `DEMO=0`, the five guests from [Five guests in the simulator](#five-guests-in-the-simulator), and Amina's number, each in its own simulator tab (`*384*30249#` and shortcode `88539` below stand for your `AT_USSD_CODE` and `AT_SMS_NUMBER`). Keep the host console open at `/host`, logged in as Amina. The steps follow the challenge: Amina struggles to communicate **room prices, available suites, breakfast preferences, check-in information and other details**.

1. **The problem (30 s).** Amina runs apartments across Mombasa and answers the same questions all day, by phone and chat. Now every guest asks on any phone, with or without data, and every answer comes from one database.
2. **Room prices.** As Asha, text `Bei?` to 88539: every home's all-in price per night, the same figure as the website. Dial `*384*30249#`, choose 2 (Prices & homes) and pick a home: its beds, price and breakfast on screen, photos by SMS.
3. **Available suites.** Asha dials, chooses 6 (Talk to Amina) → 2 (Ask a question) and types `free suites this weekend`: what's free and what the stay costs. Then she books: 1 → Nyali → This weekend → 2 nights → 2 guests → the home → breakfast → confirm. The card link arrives by SMS; pay on the card page, and "Booked!" arrives by SMS while Amina's phone gets "New booking".
4. **Breakfast preferences.** As Kevin (arriving), dial and choose 4 (Breakfast) → Swahili → 2 people: "Kitchen told". Amina's console has it on the kitchen sheet, which goes to the cook at 18:00. Daniel can do the same by SMS: `BREAKFAST`, then `2`.
5. **Check-in information.** As Grace (staying), text `wifi` (her own home's Wi-Fi) and `CODE` (her door code). As Kevin, dial 3 (My booking) → 1: directions, landmark, map and Wi-Fi by SMS, released 48 hours before arrival.
6. **Other details, and Amina managing it all.** Asha texts `Is there parking?` and `Can my cousin visit?`. The first is answered at once; the second reaches Amina's phone as `#<n> Asha Njeri: …`. As Amina, reply `#<n> Of course, karibu!` and Asha gets it. As Grace, dial 5 (Report problem) → Wi-Fi: the caretaker gets a task and Amina an SMS. Amina texts `STATUS`, or dials the code for her own menu: today, free tonight, requests, message all guests. In the console, Messages shows every guest's SMS and USSD in one inbox.
7. **Airtime.** As Halima (returning, Kiswahili), dial 8 (Zaidi) → 3 (Zawadi) → 1: KES 100 of airtime sent through Africa's Talking.

## Demo script with the Demo Lab (5 minutes, `DEMO=1`)

1. **The problem.** Amina answers the same questions all day across WhatsApp, calls and SMS. Breakfast orders get lost, guests wait outside for keys, and she can't see who's arriving.
2. **Feature-phone booking.** In the Demo Lab, holding *New guest*'s phone, dial USSD and answer 1 (book) → 1 (Nyali) → 3 (this weekend) → 2 nights → 2 guests → 1 (the home) → 1 (Swahili breakfast) → 1 (confirm & pay). The session ends with "We'll text you a secure card payment link"; tap that link on the SMS phone and pay (with Stripe test keys: card 4242 4242 4242 4242, any future date and CVC). The confirmation SMS with a trip link arrives on the SMS phone.
3. **Ask Amina by SMS.** Text "Bei?" (Kiswahili for "price?"), then "WIFI", then "Nataka nyumba Diani 12 Dec siku 3 watu 2" (a booking in plain Kiswahili).
4. **Call Amina.** Press 2 for Kiswahili, then 2 for prices and breakfast. The IVR is read aloud in the browser.
5. **Web.** Search → listing → checkout with breakfast, choosing the 30% deposit, then *Pay by card*: the card page opens (Stripe's checkout once its test key is set, a simulated card page without one), and back on Amina Stays the booking confirms in seconds. Open the trip page: the checklist, directions unlocking 48 h before, the balance due before arrival, the receipt and the tax invoice.
6. **Time machine.** Pick Hans's booking and press *Release door code*: it is held because the guest register (ID) is missing. Hold Hans's phone, text "ID C01X00T47", release again, and the door code arrives by SMS in German.
7. **Safety.** Holding Wanjiku's phone, text "HELP": she gets an instant reply in Kiswahili and Amina gets an SMS alert. Switch to Amina's phone and *Answer the SOS safety call*: it names the guest, home and booking, and pressing 1 connects Amina to her.
8. **Host console.** Today (the Today | Upcoming reservation cards), Calendar and Messages (Amina can also reply from her phone with "#3 …"). Then open the Menu for the kitchen sheet, insights and the one-click TRA return.

More flows, if there's time:
- **Change of plans.** On a confirmed trip, *Change dates or guests* (or *Extend your stay* once checked in) shows the new price before the guest commits; pay the difference and the dates move. Turn off *Instant date changes* in Settings and the request waits on Amina's Today page instead.
- **M-Pesa, once it's approved.** Start with `MPESA_PROVIDER=simulate`: checkout offers an M-Pesa prompt next to the card, a failed prompt (*Simulate "insufficient funds"*) offers the 30% deposit, a card or the Paybill, and the Demo Lab's *Simulate Paybill payment* is matched to the booking by its reference.
- **Waitlist.** On a listing whose dates are taken, *Notify me*; cancel the blocking stay in the console and the waiting guest gets an SMS offer.
- **Support desk.** Holding Wanjiku's phone, text `COMPLAIN the music next door is too loud`: she gets a reference, and Amina's phone gets the complaint. Reply from Amina's phone using the reference in her SMS (T7 on fresh demo data): `T7 Pole sana, Juma is on his way` (or open Host › Support desk), then `RESOLVE T7`: Wanjiku is asked to rate it, and texting `5` closes the loop. In the console, *Call guest* rings Amina first; in the Demo Lab, hold Amina's phone and *Answer a support call-back*.
- **Service alert.** In the time machine, pick Wanjiku's booking and press *Wi-Fi outage at this home*: her phone gets the alert and a 100 MB data bundle. Text "no wifi" and she's told it's known, with no new work order. *Fix it* sends "it's fixed".
- **Local guide.** Text `EXPLORE`, reply `3` (beaches), then `1` for the details and a map link; or dial USSD 8 → 1; or call and press 6. The same places are on the web at `/guide` and on each trip page, sorted by distance.
- **Rewards.** Text `POINTS`, then `REDEEM AIRTIME`: the airtime is sent through Africa's Talking (simulated without keys). Each guest's invite code (`REF <code>`) pays airtime to both after the friend's first stay. Host › Rewards & airtime has the budget, payouts and gifts.

## Tests

They use the database from the quick start; pytest creates and drops its own test database. Run them from the project folder; the commands are the same in bash and PowerShell:

```bash
cd backend
uv run pytest            # 629 tests, incl. end-to-end flow suites (tests/test_flows_*.py)
uv run ruff check .
cd ../frontend
npx tsc --noEmit
npm run lint
```

## Project structure

```
backend/                 Django 6 + DRF API, Africa's Talking webhooks, scheduler
  apps/core              settings, scheduler, audit log, demo endpoints, seed data
  apps/accounts          phone-number users, OTP login, ID encryption, data rights
  apps/properties        homes, photos, pricing, calendars, iCal, quote engine
  apps/bookings          booking lifecycle, add-ons, breakfast, guest register, door codes
  apps/payments          cards (Stripe / simulated / Paystack), M-Pesa (off / simulated / Daraja / AT), refunds
  apps/messaging         outbox, templates (5 languages), automations, FAQ, broadcasts
  apps/comms             AT client, SMS bot, USSD, voice IVR, SIM swap, webhooks
  apps/operations        tasks, staff, kitchen sheet, gate list, digest, CRM
  apps/safety            SOS alerts and escalation, guest register export
  apps/reviews           ratings and responses
  apps/insights          occupancy, ADR, RevPAR, TRA monthly return
  apps/support           support desk: tickets, call-back bridging, escalation, ratings
  apps/notices           service alerts: outages and maintenance, the outage data bundle
  apps/guide             local guide: places and events by USSD, SMS, voice and web
  apps/rewards           points, invite codes, the airtime and data ledger
  tests/                 pytest suite
frontend/                Next.js 16 (App Router), Tailwind CSS v4, TanStack Query, Radix
  src/app/(site)         guest site, Demo Lab
  src/app/host           host console
  src/components         UI kit, site, host and demo components
docs/                    research synthesis, architecture, full research briefs
scripts/                 dev.sh (run everything on Linux, macOS, WSL), dev.ps1 (the same on Windows), db.sh (local PostgreSQL)
docker/                  supervise.py: entrypoint of the all-in-one marketplace image (root Dockerfile)
marketplace/             Africa's Talking Marketplace listing, logo and deployment guide
.github/workflows/       CI: tests, type check, lint, image build and push
```

More: [Architecture](docs/ARCHITECTURE.md) · [Research](docs/RESEARCH.md) · [Project brief](<AMINA-STAYS_Project_Brief (2).pdf>)

## Credits

- 3D icons: [Microsoft Fluent Emoji](https://github.com/microsoft/fluentui-emoji) (MIT licence), downscaled copies in `frontend/public/3d`.
- Photos: [Unsplash](https://unsplash.com) (Unsplash licence), loaded from their CDN.
- Map data: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.
- Typeface: [Figtree](https://fonts.google.com/specimen/Figtree) (SIL Open Font License).
- Interaction patterns follow the published Airbnb product (see [research 06/07](docs/RESEARCH.md#design-language)); all branding, names and artwork are Amina Stays' own.
