# Research → product decisions

Amina Stays was designed from eight research briefs written on 25–26 Nov 2026. The full briefs, with sources, are in [`docs/research/`](research/):

| Brief | What it covers |
|---|---|
| [01 Global platforms](research/01-global-str-platforms.md) | Airbnb, Booking.com, Vrbo/Expedia, Agoda, Trip.com: guest UX, design language, host tools, engineering lessons, industry problems and fixes 2019–2026 |
| [02 Small-host operations](research/02-small-host-operations.md) | Pain points of 2–10-unit hosts, PMS tooling (Hospitable, Hostaway, Guesty…), KPIs, message timelines, top guest FAQs |
| [03 Kenya & Mombasa](research/03-kenya-mombasa-context.md) | TRA licensing (Tourism Enterprises Regulations 2025), Tourism Levy, KRA, guest register, Data Protection Act, SMS rules, safety, payments, coastal operations |
| [04 Africa's Talking](research/04-africas-talking.md) | SMS, USSD, Voice, Payments, Airtime, Mobile Data, Insights, SDKs, callbacks, sandbox limits |
| [05 Tech stack](research/05-tech-stack.md) | Django/DRF + PostgreSQL + Next.js choices, auth across origins, jobs, Postgres patterns, deployment |
| [06 Airbnb guest UX (2025–26)](research/06-airbnb-guest-ux.md) | Page-by-page anatomy of the current guest product: header and search, home feed, search results and map, listing page, checkout, trips, account; design tokens and the top details to replicate |
| [07 Airbnb host UX (2025–26)](research/07-airbnb-host-ux.md) | Hosting mode: Today / Calendar / Listings / Messages / Menu, reservation cards and statuses, calendar and pricing tools, inbox, earnings, insights; comparable PMS patterns and a recommended console IA |
| [08 End-to-end flows: gap analysis](research/08-end-to-end-flows.md) | Every guest/host flow compared with Airbnb, Hospitable and Hostaway; M-Pesa result codes and recovery, Paybill/C2B, Paystack verification, Africa's Talking USSD/SMS/voice edge cases, Kenyan tax and licence compliance; ranked MUST/SHOULD/NICE gaps |

## The challenge

> Amina has several apartments in Mombasa and struggles to communicate prices, suites, breakfast preferences and check-in information to guests.
> — AMINA-STAYS brief, Innovate Mombasa Hospitality & Tourism Hackathon

The research showed this is the visible tip of a bigger problem. For small hosts, **87% of pre-arrival questions have static answers** (Wi-Fi, check-in, parking, directions, door code), yet **15% go unanswered** because the information isn't written down (brief 02). Hosts lose more time on **cleaning, maintenance and admin** than on messaging, and they juggle 3–5 inboxes. In Kenya, many guests and staff use feature phones or have no data, and the law now requires a guest register, TRA licensing and monthly returns (brief 03).

So Amina Stays is not only a booking site. It is **one source of truth for every home**, available on every channel: web, USSD, SMS and voice. It also automates the whole stay and covers the operations and compliance work behind it.

## What we adopted from the industry leaders

| Pattern | Who does it | How it shows up in Amina Stays |
|---|---|---|
| Where / When / Who search pill, category tabs, map, photo-carousel cards | Airbnb | Home page search, category tabs, map toggle, swipeable cards with "Guest favourite" |
| **Total price display** with all mandatory fees | Airbnb (2022); FTC fee rule (May 2025) | Every quote is all-in (nights + cleaning + 2% tourism levy + VAT if registered), on web, USSD, SMS and voice |
| Guest favourite badge (top homes by rating and reviews) | Airbnb (2023) | Rating ≥ 4.8 with ≥ 5 reviews, computed from verified stays only |
| Reserve now, pay later / deposits | Airbnb, Vrbo, Agoda | Pay 30% now and the rest one day before arrival (M-Pesa prompt or pay link) |
| Staged disclosure: area → address → directions → door code | Airbnb | Address once booked, directions and Wi-Fi 48 h before, door code only on arrival morning |
| A living itinerary | Airbnb Trips | Trip hub: checklist, door code, directions, Wi-Fi, breakfast, extras, help, receipt, timeline |
| Services and add-ons | Airbnb Services (2025) | Breakfast, airport/SGR pickup, early/late checkout, dhow cruise, cooking class, groceries, baby cot |
| AI and auto-answers with human escalation | Airbnb (~40% of issues resolved by AI) | "Ask Amina": facts answered instantly, requests go to Amina, problems become tasks |
| 24/7 safety line | Airbnb Safety Line | Text HELP, USSD 9, press 9 on a call, or the trip-page SOS: alerts Amina, the caretaker and security, then escalates by voice call |
| Indoor-camera ban, outdoor-camera disclosure | Airbnb (Apr 2024) | Per-home safety disclosures on the listing ("Things to know") |
| Party and fraud screening | Airbnb anti-party system | Risk score from one-night weekend, same-day and last-minute bookings, first stays, full occupancy and past incidents, shown to Amina |
| Partner 2FA after account takeovers | Booking.com (2024) | Phone OTP login with a 30-second resend gap, 5-codes-per-hour cap and lockout after 5 wrong attempts; SIM-swap check before door codes |
| Never pay off-platform | Airbnb, Booking.com | Every payment message: "Pay only via the official prompt — we never ask you to send money to a personal number" |

## Industry problems and how Amina Stays answers them

| # | Problem (evidence) | Our answer | Where |
|---|---|---|---|
| 1 | **Double bookings**: iCal is polled every 2–3 h (Airbnb, Booking.com), and two channels can grab the same night (brief 02) | PostgreSQL exclusion constraint on `(unit, daterange)` for live bookings, a per-unit row lock when holding, 10-minute holds, iCal import/export with conflict alerts | `bookings/models.py`, `bookings/services.py::create_hold`, `properties/services.py` (iCal); tested with a two-thread race |
| 2 | **Hidden fees** ("$40 night, $90 total"); FTC and EU rules (brief 01) | All-in quotes everywhere; itemised receipt; no booking fee for direct guests | `properties/services.py::quote`, checkout, trip receipt |
| 3 | **Repetitive questions**: 87% static, 15% unanswered for lack of info (brief 02) | One knowledge base per home (prices, suites, breakfast, Wi-Fi, directions, rules) feeding web, SMS FAQ auto-answers, USSD and voice; FAQ manager with a test console | `messaging/` (FAQ, templates), `comms/smsbot.py`, host Messaging page |
| 4 | **Breakfast and preferences lost in chat** (the brief) | Structured breakfast (style, people, time, dietary needs) at booking, from the trip page, by SMS "BREAKFAST" or USSD 4; a nightly kitchen sheet for the cook | `bookings/services.py::set_breakfast`, host Kitchen page, `kitchen_sheet` job |
| 5 | **Check-in chaos** and lockouts | Self check-in codes valid only for the stay, released at 08:00 on arrival day once paid and registered, revoked at checkout; directions with landmarks | `bookings/locks.py`, `release_code`, Demo Lab time machine |
| 6 | **No data or no smartphone** (most Kenyan phones, many domestic guests and staff) | Full booking, payment, breakfast, issues, checkout and emergencies over USSD and voice (English and Kiswahili), and natural-language SMS | `comms/ussd.py`, `comms/voice.py`, `comms/smsbot.py` |
| 7 | **Language**: about 94% of Mombasa's visitors are international, with Italian and German big on the coast (brief 03) | Templates and SMS replies in English, Kiswahili, Italian, German and French; Kiswahili voice prompts | `messaging/templates_default.py`, `comms/nlu.py` |
| 8 | **Payment fraud and fake hosts** (Booking.com phishing surge; Kisauni fake-host case, brief 03) | M-Pesa STK push and hosted card checkout only; idempotent callbacks; amount check; late payments re-hold or are refunded; SIM-swap check (AT Insights) before door codes | `payments/`, `comms/simswap.py` |
| 9 | **Guest safety** | HELP from any channel; an escalation ladder (SMS to Amina and staff, then voice calls, retried until acknowledged); visible emergency numbers 999/112/1199/1514 | `safety/services.py`, `comms/voice.py::alert_call` |
| 10 | **Cleaning and maintenance are the biggest time sinks** (PriceLabs 2025; Hostaway 2025) | Turnover task created at every checkout; guest issues become prioritised work orders assigned to the right staff member, who can close them by SMS "DONE" | `operations/`, host Tasks page |
| 11 | **Fragmented inboxes** across 3–5 platforms (Breezeway) | One inbox for SMS, web chat, USSD requests, voicemail and staff messages; Amina can reply from her own phone ("#12 text", "YES 34") | `messaging/`, `HostCommands` in `comms/smsbot.py` |
| 12 | **Bad reviews hurt** (71% of hosts fear them; brief 02) | "All good?" check on arrival evening catches problems early; review requests by SMS (reply 1–5) and web with category scores; host responses | `reviews/`, automations |
| 13 | **Compliance**: TRA licence, 5-year guest register, monthly TRA return, 2% levy, ODPC, promotional-SMS rules (brief 03) | Licence shown on listings and receipts; encrypted guest register with consent and CSV export; one-click monthly TRA return; levy in every quote plus a monthly reminder; data export and erasure; promotional SMS only 08:00–18:00 with STOP | `insights/services.py::tra_return`, `safety/views.py::guest_register`, `accounts/services.py`, `messaging/services.py` |
| 14 | **Gate and estate security** (PSRA visitor-log directive) | Morning gate list for the security guard: arrivals, names, plates, ETAs | `operations/services.py`, `gate_list` job |
| 15 | **Power and water cuts** on the coast | Backup power and water-tank information in FAQs and house manuals; the issue flow sends water, power and plumbing problems to the caretaker as high priority (lock and security problems are urgent and raise an alert) | seed FAQs, `operations` categories |
| 16 | **OTA commissions** (Airbnb 15.5%, Booking.com ≈15%, Vrbo 12%) | Direct booking with M-Pesa; OTA calendars synced by iCal so Amina can still list on Airbnb and Booking.com without double bookings | `properties` iCal feeds, host Channels page |
| 17 | **Cancellations and refunds disputes** (Agoda fine, brief 01) | Four plain policies, shown before payment; the refund amount is shown before the guest confirms; host cancellations refund in full plus an airtime apology (AT Airtime) | `bookings/services.py::refund_quote`, `send_goodwill` |
| 18 | **Response-time expectations** (Airbnb ranks on 24 h response) | Instant answers 24/7; unanswered threads flagged with waiting time in the inbox; a morning digest to Amina by SMS | inbox, `host_digest` job |
| 19 | **Failed M-Pesa prompts**: wrong PIN, cancelled, low balance, phone unreachable, another prompt open (brief 08) | Every Daraja result code maps to a plain message and the right next step: resend, wait a minute, pay the 30% deposit, card or Paybill. The hold stays in place while the guest retries | `payments/results.py`, `payment-help.tsx`, checkout |
| 20 | **No STK prompt at all**, or the guest simply prefers Paybill | Lipa na M-Pesa Paybill fallback: the booking reference is the account number, the payment is matched automatically (C2B confirmation) and confirmed by SMS; anything unmatched waits in a queue Amina clears in one click | `payments/c2b.py`, host Payments |
| 21 | **Plans change after booking** (Airbnb lets guests alter a reservation and pay or get back the difference) | Change dates or guests, or extend, from the trip page or by SMS `EXTEND`: re-priced at current rates, pay the difference by M-Pesa or card, reductions refunded by the cancellation policy; Amina can require approval | `bookings` `ChangeRequest`, `trip-change.tsx`, Today |
| 22 | **Unpaid balances before arrival** (Airbnb gives 72 h, then cancels) | A balance ladder: reminder a week ahead, M-Pesa prompt on the due day, then an overdue SMS with the Paybill details; an overdue badge on the trip page; an Outstanding list for Amina; the door code stays held until paid | `run_balance_ladder`, host Payments |
| 23 | **Sold-out dates lose demand** | "Notify me" on the web as well as SMS, USSD and voice; when the dates free up, everyone waiting for them gets an SMS offer with a booking link, oldest request first | `bookings` waitlist, listing page, Account |
| 24 | **Tax paperwork** (VAT 16%, KRA eTIMS) | Numbered invoices and credit notes, a printable invoice page, sales-register and payments-ledger CSVs | `payments/invoices.py`, `/trips/[ref]/invoice` |
| 25 | **A lapsed TRA licence** (licences expire on 31 Dec) | Renewal reminders 45, 30, 14, 7 and 1 days before the expiry date, with a compliance alert until it is renewed | `safety/services.py::licence_reminder` |
| 26 | **Messages that silently fail** (opted-out numbers, no SMS credit, USSD sessions timing out on slow payment APIs) | SMS errors split into final (no retry) and transient (retried after 1 and 5 minutes); a 405 "no credit" alerts Amina; the M-Pesa push from USSD and voice is sent after the session's reply; an unanswered SOS call escalates at once | `messaging/services.py`, `comms/deferred.py`, `comms/voice.py` |

## Kenya-specific requirements (brief 03, top 15) — coverage

| Requirement | Status |
|---|---|
| TRA licence shown on listings and receipts, with a verify link | ✅ Licence on every listing, receipt and footer; per-home override; renewal reminders before the expiry date |
| Digital guest register (all occupants, ID, nationality, plate), kept 5 years, exportable | ✅ Encrypted, consented, last-4 only in the UI; CSV export; purged automatically after `id_retention_days` (1,825) |
| Monthly TRA return (occupancy, visitors by country, revenue) | ✅ Host Insights, "TRA return" |
| Tourism Levy engine | ✅ 2% in every quote; monthly reminder (5th) |
| KRA / VAT tracking | ⚠️ VAT switch in settings (applies once registered); numbered invoices and credit notes with a sales-register CSV; eTIMS transmission is out of scope |
| M-Pesa STK push, callbacks as the only proof, reconciliation, refunds | ✅ Daraja provider plus reconciliation job; result-code guidance; Paybill (C2B) fallback with automatic matching; refunds tracked to "sent", with an SMS to the guest |
| Card path for foreign guests | ✅ Hosted card checkout (Paystack in production, confirmed with Verify Transaction and reconciled; simulated in the demo) |
| Safety-by-design check-in, SOS, emergency numbers | ✅ |
| Data protection built in (consent, 7-day access, 14-day erasure) | ✅ Self-service export and erasure; privacy notice |
| Compliant SMS (opt-in, STOP, 08:00–18:00 for promotions) | ✅ |
| USSD and voice in English and Swahili | ✅ |
| Outage and water resilience information | ✅ FAQs and house manuals; ⚠️ KPLC feed ingestion is future work |
| Arrival logistics by mode (SGR Miritini, Moi airport, Likoni vs Dongo Kundu) | ✅ Area "getting there" guides, pickups, arrival mode at booking |
| Seasonality-aware pricing and calendar sync | ✅ Price rules (season, weekend, last-minute, early-bird, length of stay), date overrides, iCal |
| Local trust and culture layer (licence verify, tout tips, Old Town etiquette, halal breakfast) | ✅ FAQs, breakfast dietary options, licence verify link |

## How we use Africa's Talking (brief 04)

| Product | Used for |
|---|---|
| **SMS** (two-way, delivery reports, opt-out callback) | "Ask Amina" bot, confirmations, door codes, reminders, staff tasks, host commands, OTP login |
| **USSD** | Full no-data booking and trip management, staff and host menus |
| **Voice** | English/Kiswahili IVR (availability, booking, prices, directions), bridge to Amina, voicemail, outbound SOS escalation calls, optional welcome call |
| **Airtime** | Automatic goodwill airtime when Amina has to cancel a paid stay |
| **Mobile Data** | Optional welcome data bundle for Kenyan guests on arrival |
| **Insights – SIM Swap** | Door codes held if the guest's SIM was swapped recently |
| **WhatsApp** (preview) | Optional channel for guests who prefer it |
| **Payments** | M-Pesa checkout via AT is supported as a provider, but AT Payments is onboarding-gated with no sandbox (brief 04). That is why the payment layer is pluggable: simulated for the demo, Safaricom Daraja for production. |

Design consequences of AT's documented limits:
- **USSD screens** fit 160 characters (Safaricom) and the 10-second response window. Menus use paging ("98 More"), "0 Back", "00 Home", and the text chain is replayed so sessions survive.
- **No webhook signatures**: callbacks live under a secret path `/at/<AT_WEBHOOK_SECRET>/…`.
- **No voice sandbox**: the Demo Lab plays our real voice XML in the browser with speech synthesis.
- **Sandbox SMS never reaches real phones**: the Demo Lab shows each simulated handset's inbox.

## Design language

We measured the live Airbnb product (Nov 2026: computed styles, layouts and screenshots of the home feed, search, listing, checkout and hosting pages) and rebuilt our UI on the same patterns, under our own coastal brand (name, sail-and-wave mark, coral `#e8553e`). Details are in briefs [06](research/06-airbnb-guest-ux.md) and [07](research/07-airbnb-host-ux.md).

- **Tokens:**
  - Ink `#222`, secondary `#6C6C6C`, tertiary `#8C8C8C`, disabled `#C1C1C1`.
  - Hairlines `#DDD`/`#EBEBEB`, surfaces `#F7F7F7`, `#F2F2F2` fills.
  - Type weights capped at 600.
  - Buttons: 8 px radius on 32 px buttons and 12 px on larger ones; the primary action is a pill with a pointer-following gradient; the search button is a flat, deeper brand tone.
  - 20 px photo radii; Airbnb's E2/E3 elevation for badges, search, popovers and the active checkout step.
- **Type:** Figtree. The guest-UX brief measured 12 free fonts against Cereal: Manrope matches metrics most closely, and Figtree matches the friendly geometry best.
- **3D icons:** Microsoft Fluent Emoji 3D (MIT), used where Airbnb uses its own 3D set: header tabs, search suggestions, listing highlights, "Things to know", "Guests mention", filters, and the account and hosting menus.
- **Guest site:**
  - **Header:** Homes / Experiences / Services tabs over a soft band; collapses into the compact "Anywhere · Anytime · Add guests" pill on scroll and expands over a dimmed page.
  - **Home feed:** carousel rows (7-up at 1440 px).
  - **Search (`/s`):**
    - Chips, led by Free cancellation and Guest favourite.
    - A Filters dialog: price histogram, rooms, amenities, type.
    - A sticky half-width map whose price pills light up as you hover cards.
  - **Listing:**
    - 1 + 4 photo grid and a photo tour by room; guest-favourite laurels; 3D highlights; a sticky section nav; rating breakdown plus "Guests mention"; "Meet your host" and "Things to know".
    - Total-first booking card with a "Price details" popover and a "KES X today · Free cancellation before {date}" pill.
  - **Checkout:** Airbnb's numbered accordion beside a summary card.
  - **Phones:** "Start your search" pill, "pillow" tab chips, full-screen search, a bottom tab bar that hides on scroll, and a full-bleed 20:19 listing hero with a "1 / N" counter under a rounded sheet.
- **Host console:** Airbnb's hosting mode. A top bar (Today · Calendar · Listings · Messages) with a grouped Menu (dropdown on desktop, a page and bottom tab on phones). Today opens with a Today | Upcoming toggle and "You have N reservations" cards; reservations, tasks, kitchen, safety and channels stay one tap away.

Prices are always in KES, with USD/EUR/GBP approximations for international guests.

## Out of scope (for now)

- eTIMS transmission and KRA filing (numbered invoices, credit notes and CSV exports only)
- Special offers, security deposits and damage claims (ranked in [brief 08](research/08-end-to-end-flows.md#what-we-built))
- Two-way OTA API channel management (iCal only; brief 02 explains why APIs are partner-gated)
- Native mobile apps (the site is a responsive web app; USSD/SMS/voice cover feature phones)
- AI-generated free-text replies (deterministic NLU plus FAQ matching, with every unknown question escalated to Amina)
