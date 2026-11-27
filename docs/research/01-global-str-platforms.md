# Short-term-rental platform research brief (as of 25 Nov 2026)

**Summary.** Airbnb has become an "AI-native" super-app (homes, services, experiences, hotels). Its growth levers are total-price transparency, flexible payments, trust/safety tooling and server-driven UI. Q3-2026 revenue grew 19% to $4.9B (https://news.airbnb.com/airbnb-q3-2026-financial-results). Its public engineering record is most useful on idempotent payments (Orpheus), async payment states, change-data-capture and server-driven UI. Booking.com leans on Genius loyalty, experimentation and AI. Vrbo leans on host tooling and payments. Agoda and Trip.com lean on AI assistants and bundling. The big 2024–26 problems were fee opacity, phishing/fake listings, parties/cameras, licensing/housing rules and antitrust (parity clauses). Regulators have now hit Booking.com (fraud probe, parity), Trip.com (parity) and Agoda (fee disclosure). ⚠ marks a third-party or unofficial source. I also read the repo's availability/bookings/payments/lifecycle files, and that informs the takeaways.

## 1. Guest-facing features & UX
**Discovery**
- Airbnb's 2022 redesign put 55 Categories on the home screen. Results regroup by destination-relevant category and the map auto-zooms. https://news.airbnb.com/2022-summer-release
- Flexible dates (2021): weekend/week/month searches or ±N days. More than a third of searchers were flexible. https://news.airbnb.com/new-flexible-search https://www.airbnb.com/help/article/252
- Behaviour behind the UI: over 75% of guests use maps, over 90% browse multiple photos, 70% read reviews, and bookings average 3 guests. https://news.airbnb.com/airbnb-q3-2026-financial-results
- 2026 AI layer: search by words or voice, AI filters ("baby" surfaces cribs), AI listing summaries, wishlist comparison, review highlights over 1B+ reviews, neighbourhood pages (Paris first). https://news.airbnb.com/airbnb-2026-fall-update https://www.airbnb.com/resources/hosting-homes/a/now-theres-even-more-to-airbnb-763
- Booking.com has Smart Filters (free text to filters), an AI Trip Planner and Property Q&A. https://partner.booking.com/en-us/click-magazine/industry-perspectives/how-we-use-generative-ai
- Agoda's AI Assistant has a trip-planner canvas, retained preferences and live inventory. Its AI also pairs room/pool photos with matching reviews. https://www.prnewswire.com/apac/news-releases/agodas-ai-assistant-brings-travel-planning-and-booking-into-one-conversation-302934130.html https://www.prnewswire.com/apac/news-releases/agoda-rolls-out-suite-of-new-features-focused-on-real-time-updates-and-smarter-trip-planning-302812942.html
- Trip.com's TripGenie takes text/voice, builds day-by-day plans and translates menus. https://sg.trip.com/ask/questions/tripgenie-trip.com.html

**Listing page & trust**
- Airbnb shows an approximate-location circle until the booking is confirmed; the street address comes only after. https://www.airbnb.com/help/article/2141
- ⚠ Page pattern: 5-photo mosaic (large left + 2×2), sticky booking card ("You won't be charged yet"), and a "Things to know" strip (house rules · safety & property · cancellation). https://github.com/nexu-io/open-design/blob/main/plugins/_official/design-systems/airbnb/DESIGN.md
- Guest favourite is a daily relative ranking on ratings/reviews/reliability. Top 1/5/10% highlights need at least 5 reviews in 4 years. https://www.airbnb.com/help/article/3495
- Superhost needs ≥4.8, <1% cancellations and 90% replies within 24 h. https://www.airbnb.com/help/article/829
- Booking.com accepts reviews only from guests who booked or stayed. It also collects sub-scores (location, cleanliness, staff, comfort, facilities, value, Wi-Fi). https://www.booking.com/content-moderation-policy/guest-reviews-standards.en-us.html
- Airbnb rating inflation: mean 4.7★, with 91–94% of listings ≥4.5★. https://link.springer.com/article/10.1007/s11002-020-09546-4
- Accessibility is structured: step-free thresholds under 5 cm, and at least one photo per feature. https://www.airbnb.com/e/accessibility-photos

**Pricing/checkout**
- Total price display: 2019 (parts of EU/AU/CA/KR), then an opt-in toggle in 2023 (~17M users), then the worldwide default on 21 Apr 2025. https://news.airbnb.com/total-price-display-is-now-standard-globally
- By end-2023 about 300k listings had cut fees, and ~40% of active listings charged no cleaning fee. https://abc7.com/post/airbnb-will-now-show-total-prices-default/16216095/
- Flexible pay: Pay Part Now/Later, Klarna, and Reserve Now Pay Later. RNPL launched in the US in 2025 and went global in Feb 2026, with over 70% adoption on eligible Q4-2025 bookings. https://news.airbnb.com/reserve-now-pay-later-is-now-available-worldwide
- RNPL gave a ~3% net nights lift in Q3-2026. https://www.fool.com/earnings/call-transcripts/2026/11/06/airbnb-abnb-q3-2026-earnings-call-transcript/ Vrbo is adding it. https://www.businesswire.com/news/home/20261028207262/en/
- Request-to-book gives the host 24 h, with no charge if declined or expired. https://www.airbnb.com/help/article/85
- Loyalty: Booking.com Genius has 10/15/20% levels and a default 10% on the cheapest/most popular room. Genius properties get a badge and surface in filtered searches, and the programme targets returning guests who spend 15% more. https://partner.booking.com/en-gb/help/performance/tools-programmes/understanding-genius-marketing-programme https://partner.booking.com/en-gb/solutions/genius_programme https://partner.booking.com/en-gb/click-magazine/bookingcom-news/booking-holdings-q1-2026-earnings-call
- Vrbo's One Key rewards reach Vrbo bookings via Vrbo Payments (pilot). https://www.businesswire.com/news/home/20260901924619/en/

**Trips/arrival/messaging**
- The Trips tab became a "living itinerary". https://www.itsnicethat.com/articles/airbnb-app-redesign-140525
- Detailed check-in instructions are released 48 h before arrival, though the check-in method is visible earlier. https://www.airbnb.com/help/article/1926
- Messaging was rebuilt with photo/video and in-chat payments. More than 90% of stays involve guest–host chat. https://news.airbnb.com/airbnb-2025-summer-release https://news.airbnb.com/airbnb-q3-2026-financial-results
- Vrbo's Welcome Guide sends access instructions with delivery confirmation. Scheduled messages/templates reuse its tags. https://www.businesswire.com/news/home/20260901924619/en/

## 2. Airbnb design language (public record)
- DLS (2016) aimed to be "beautiful and accessible". Its principles are Unified/Universal/Iconic/Conversational.
  - The foundation is type, accessible colour, icons, spacing and information architecture.
  - Components have required elements (a mandatory divider toggled by logic), and the phone set was adapted to tablet. https://karrisaarinen.com/posts/building-airbnb-design-system/
- The Cereal typeface (Dalton Maag, May 2018) draws its "a" from the Bélo logo's single stroke. https://www.fastcompany.com/90172242/exclusive-airbnbs-new-font-holds-the-secret-to-designs-future
- Motion: Lottie (2017) plays After Effects→JSON natively. It caches the wish-list heart, and JSON can be loaded remotely for A/B tests. https://medium.com/airbnb-engineering/introducing-lottie-4ff4a0afac0e
- The 2025 redesign used an in-house team for UI, 3D and illustration (VP Design Teo Connor). It has softer curves, an animated UI, an icon set built up over ~2 years and a "fun, alive, simple" brief. https://www.itsnicethat.com/articles/airbnb-app-redesign-140525
- Tabs named in the release: Explore, Trips, Messages, Profile. https://news.airbnb.com/airbnb-2025-summer-release
- ⚠ Unofficial tokens scraped from airbnb.com (verify; sources disagree on body weight 400 vs 500):
  - Rausch is #ff385c (pressed #e00b41), used on only 3 of 33 components (CTA, search orb, heart). Ink is #222 and hairline #ddd.
  - Cereal VF headings are 28/22/21/20 px, titles 16, body 16/14, captions 14/13, badge 11, rating display 64 px.
  - Radii are 4/8/14/20/32/pill. Spacing is 2/4/8/12/16/24/32/48/64 on an 8 px base. https://www.shadcn.io/design/airbnb
- ⚠ Components:
  - Listing photos are 4:3 with a 14 px radius and no shadow.
  - The search pill (Where/When/Who) has a 32 px radius and a shadow of 0 2px 6px at 4%.
  - The booking card has a 3-layer shadow and collapses to a bottom "Reserve" bar on mobile.
  - Icon buttons are circular, 32–44 px. Pressed state is scale 0.92. Mobile has a bottom tab bar, and 3D icons sit above 16 px tab labels. https://github.com/nexu-io/open-design/blob/main/plugins/_official/design-systems/airbnb/DESIGN.md
- Gap: I found no official current token/shadow/ratio spec.

## 3. Host-facing tools
- **Calendar:** 2025 added a Today tab, an hour-by-hour view and Google Calendar sync. https://news.airbnb.com/airbnb-2025-summer-release
- **Multi-listing calendar (2026):** bulk price/policy/discount edits, listing groups, and min-stay and last-minute-discount recommendations. About 1 in 4 eligible hosts opted in. https://news.airbnb.com/airbnb-q3-2026-financial-results
- iCal import refreshes only every 3 h, which leaves a double-booking window. https://www.airbnb.com/help/article/99
- **Pricing/insights:** 2026 "dynamic pricing" (host sets a range, one tap), AI earnings insights and 3D floor plans. https://news.airbnb.com/airbnb-2026-fall-update
- ⚠ Host-only 15.5% fee (16% Brazil) replaced the 3% host + guest fee: PMS hosts on 27 Oct 2025, others on 1 Dec 2025. https://hello.pricelabs.co/blog/airbnb-host-fee-update/ https://www.rentalscaleup.com/airbnb-host-only-fee/
- **Messaging:** scheduled quick replies fire on new booking/check-in/checkout. They have a timeline, skip/edit, sharing with co-hosts and a last-minute fallback. https://www.airbnb.com/help/article/2897
- **Co-Host Network:** vetted, ID-verified local co-hosts set their own services and prices. It runs in 13 jurisdictions, not Kenya. https://www.airbnb.com/help/article/3378 https://www.airbnb.gy/resources/hosting-homes/a/join-the-co-host-network-629
- **Payouts:** released about 1 business day after check-in. They are held until checkout if a listing is unverified, a policy is breached or Airbnb sees risk. Fast Pay takes ≤30 min, and earnings are itemised including the co-host share. https://www.airbnb.com/resources/hosting-homes/a/how-youll-get-paid-for-hosting-20
- **Quality gates:**
  - Airbnb's surfacing tips are a complete listing, quality photos, a far-ahead open calendar and discounts. https://www.airbnb.com/resources/hosting-homes/a/now-theres-even-more-to-airbnb-763
  - Booking Genius needs ≥3 reviews and a score of ≥7.5. https://partner.booking.com/en-gb/help/performance/tools-programmes/understanding-genius-marketing-programme
- **Vrbo (1 Sep 2026):**
  - Pay-per-booked-night Sponsored Listings and same-day booking (until 12 pm).
  - Full-refund policies at 5 days or 1 day before check-in.
  - Host with Confidence (beta; covers damage, chargebacks, cancellation income) and a Vrbo Payments pilot. https://www.businesswire.com/news/home/20260901924619/en/

## 4. Engineering lessons
- **SOA:** Airbnb moved from a Rails monolith to Java/Dropwizard services with Thrift IDL. This gave typed contracts and generated clients; hand-built clients had made teams shy of SOA. https://medium.com/airbnb-engineering/building-services-at-airbnb-part-1-c4c1d8fa811b
- **Viaduct:** the resulting "spaghetti" led to Viaduct, one central GraphQL schema. By 2020, 80 entities served 75% of API traffic. https://medium.com/airbnb-engineering/taming-service-oriented-architecture-using-a-data-oriented-service-mesh-da771a841344
  - By 2025: 8× traffic, 130+ teams, 1.5M lines of code. Modules are owned by one team and composed via re-entrant queries, not code dependencies. It was open-sourced Sept 2025. https://viaduct.airbnb.tech/blog/archive/2025/
  - v1.0 (May 2026) gave ~10× large-query throughput; v3.0 shipped Oct 2026. https://viaduct.airbnb.tech/blog/
- **Ghost Platform, server-driven UI (2021):** the backend returns screens plus sections (already localized/formatted) and server-defined actions. It uses one shared GraphQL schema for web/iOS/Android, which fixes client divergence and app-release lag. https://medium.com/airbnb-engineering/a-deep-dive-into-airbnbs-server-driven-ui-system-842244c5f5
- Airbnb's planned 2027 agent will compose "hundreds" of UI elements (maps, calendars, comparisons) instead of a chat window. https://news.airbnb.com/airbnb-q3-2026-financial-results
- **Idempotency, Orpheus (2019):** https://medium.com/airbnb-engineering/avoiding-double-payments-in-a-distributed-payments-system-2981f6b070bb
  - It is a library, not a service, because of latency and shared failure modes. It uses an idempotency key, with tables on a sharded master (replica lag causes duplicates).
  - Each request is split into Pre-RPC/RPC/Post-RPC, with no network call inside DB transactions and no DB call during the RPC.
  - Errors are classed retryable vs non-retryable. It explicitly covers a "user clicking Book twice".
- **Payments:** Boleto cash payments became the general async pattern (pending→confirmed). Mutable Rails records with audit triggers were replaced by append-only gateway events and a billing interface of discrete line items. Scale is 191 countries and 70+ currencies. https://medium.com/airbnb-engineering/scaling-airbnbs-payment-platform-43ebfc99b324
- **Availability:** I found no public calendar-service write-up. The closest is SpinalTap CDC, which turns the DB changelog into ordered, lossless events. Dual writes can't give ordering or transaction boundaries. It feeds availability, pricing and search. https://medium.com/airbnb-engineering/capturing-data-evolution-in-a-service-oriented-architecture-72f7c643ee6f
- **Messaging Sync:** sequence-id delta sync, an offline inbox, and a server that subscribes to booking/review changes. Mobile messages rose 3.8–5.3% and inbox visits 96–200%. https://medium.com/airbnb-engineering/messaging-sync-scaling-mobile-messaging-at-airbnb-659142036f06
- **Search ranking (2020):** a position-bias feature, cold-start estimates (+14% new-listing bookings), a two-tower model (−33% p99 latency) and diversity. https://arxiv.org/abs/2002.05515
- **Booking.com (2017 paper):** more than 1,000 concurrent experiments, including hotelier tools and customer-service phone lines. Every change, even bug fixes, is wrapped in an experiment. Experiments double as a safety net and feature release, with a searchable archive and dual metric pipelines. https://arxiv.org/abs/1710.08217
- **Expedia (2021):** one cross-brand GraphQL graph via Federation, A/B-ramped 50/50 against schema stitching, with ~50% less compute. https://www.apollographql.com/blog/expedia-improved-performance-by-moving-from-schema-stitching-to-apollo-federation
- **Lessons (my synthesis):**
  - Holds/double-booking: keep reservation state in one strongly consistent store, emit changes from its log, and treat calendar imports as stale hints.
  - Payments: use an idempotency key, persisted request state, retry classification, and pending→confirmed for async methods.
  - Notifications: event-driven from state changes, deduped, with delivery confirmation.
  - Server-driven UI: one schema, backend-composed screens, reusable versioned sections.

## 5. Problems & fixes (2019–2026)
- **Junk fees:**
  - Nightly-first display hid fees (a $40 night totalled $90). Airbnb's fixes were total price, sort by total, and limits on checkout chores (Nov 2022). https://www.cbsnews.com/news/airbnb-cleaning-fees-overhaul/
  - FTC rule (effective 12 May 2025): the advertised lodging price must include all mandatory fees; optional fees stay separate. https://www.ftc.gov/news-events/news/press-releases/2025/05/ftc-rule-unfair-or-deceptive-fees-take-effect-may-12-2025
  - Agoda was fined about KRW 2.42bn (6 Jul 2026) for unclear refund terms and fees, including a pay-later "5% adjustment". https://www.kmcc.go.kr/user.do?boardId=1113&page=A05030000&boardSeq=69122&mode=view
- **Scams/phishing:**
  - Storm-1865 ClickFix emails stole hotels' Booking.com credentials (Dec 2024 onward; guests were targeted in 2023). https://www.microsoft.com/en-us/security/blog/2025/03/13/phishing-campaign-impersonates-booking-com-delivers-a-suite-of-credential-stealing-malware/
  - Hijacked accounts then message guests via the platform or WhatsApp. https://www.sekoia.com/blog/phishing-campaigns-i-paid-twice-targeting-booking-com-hotels-and-customers
  - The EC opened a DSA probe on 21 Oct 2026 (fake listings, phishing/smishing, ad labelling). Booking admitted a 500–900% scam rise in Jun 2024. https://www.theregister.com/2026/10/21/20267/
  - Booking now requires partner 2FA (Pulse app). https://partner.booking.com/en-us/help/account-and-log/security/securing-your-account
  - Airbnb: off-platform payment voids AirCover, and 200M+ users are ID-verified. https://www.airbnb.com/help/article/209 https://news.airbnb.com/airbnb-2025-summer-release
- **Cameras:** indoor cameras are banned globally (announced 11 Mar, effective 30 Apr 2024). Outdoor cameras and noise monitors must be disclosed pre-booking. https://news.airbnb.com/an-update-on-our-policy-on-security-cameras
- **Parties:**
  - ML screens entire-home, short, last-minute and nearby bookings. About 51k bookings were blocked or redirected on two US 2024 weekends, and under 0.06% of US reservations drew party reports. https://news.airbnb.com/cracking-down-on-summer-holiday-parties-with-anti-party-technology
  - The party-report rate is down over 50% since the 2020 ban. Support includes a 24-h Safety Line, a neighbour line and noise sensors. https://news.airbnb.com/en-ca/airbnb-rolls-out-anti-party-system-for-halloween
  - The Safety Line now covers 16 languages. https://news.airbnb.com/2022-summer-release
- **Discrimination:** Project Lighthouse found booking success of 91.4% for perceived-Black guests vs 94.1% for perceived-white (2022). https://news.airbnb.com/sixyearadupdate
- **Regulation:**
  - NYC LL18 (enforced 5 Sep 2023; platforms must verify registration) took ~38k listings on one site down to ~3k registrations. https://criminaljustice.cityofnewyork.us/press-release/ll18-report-sheds-light-on-eliminated-illegal-rentals-in-nyc/
  - EU Reg. 2024/1028 applies from 20 May 2026. Opt-in states require registration numbers, platform display/verification and monthly data via a single digital entry point. https://single-market-economy.ec.europa.eu/news/new-rules-bring-increased-transparency-short-term-rentals-sector-2026-05-20_en
  - Spain's registry started 1 Jul 2025. About 65k Airbnb ads were removed and 54,728 more flagged. https://www.lamoncloa.gob.es/serviciosdeprensa/notasprensa/derechos-sociales-consumo-agenda-2030/Paginas/2025/300725-retirada-anuncios-airbnb.aspx
  - Barcelona won't renew ~10,000 licences after Nov 2028. https://www.barcelona.cat/metropolis/en/contents/the-city-that-doesnt-want-single-tourist-flat
- **Competition:**
  - The CNMC fined Booking.com €413.24M (Jul 2024), and the CJEU (C-264/23, 19 Sep 2024) ruled parity clauses unlawful. https://cms.law/es/esp/publication/clausulas-de-paridad-y-restricciones-a-la-competencia-en-el-sector-de-las-reservas-online-de-establecimientos-hoteleros
  - SAMR fined Trip.com RMB 5.2bn in total (25 Jul 2026) for algorithmic exclusivity/price-parity enforcement. The remedies end both. https://www.legal500.com/intelligence/china/antitrust-competition-law/a-costly-trip-lessons-from-chinas-rmb-52-billion-tripcom-decisions
- **Support/refunds:**
  - AirCover for guests covers host cancels, inaccurate listings and failed check-in, with a 24-h line and rebook/refund. https://www.airbnb.com/help/article/3227
  - AirCover for hosts gives $3M damage and $1M liability cover. https://www.airbnb.com/e/safety_stay_protections_hosts_guests
  - Airbnb's AI assistant resolved ~40% of all issues unaided in Q3 2026 (a third in Q2). Support cost per booking fell 17%. https://news.airbnb.com/airbnb-q3-2026-financial-results

## 6. Latest launches (2025–26)
- **Airbnb:**
  - 13 May 2025: Services (10 categories, 260 cities; vetted, ID-verified), Experiences (650 cities) and a rebuilt app. https://news.airbnb.com/airbnb-2025-summer-release
  - 20 May 2026: AI support in 11 languages with interactive cards, shared itineraries, groceries/airport pickups/luggage/car rentals, and boutique hotels with price-match credit. https://www.airbnb.com/resources/hosting-homes/a/now-theres-even-more-to-airbnb-763
  - 30 Sep 2026: AI search/filters/comparison, 50+-language support, voice, the multi-listing calendar, and meal-delivery/laundry/baby-gear services. https://news.airbnb.com/airbnb-2026-fall-update
  - 5 Nov 2026: 50+ launches in Q3. Hotels are in 60+ destinations (~35% of hotel-first guests rebook a home). The AI agent is due H1 2027. https://news.airbnb.com/airbnb-q3-2026-financial-results
- **Booking.com:** agentic flows for complaints/cancellations, Smart Filters rolled out globally, and Genius extending beyond hotels. https://partner.booking.com/en-gb/click-magazine/bookingcom-news/booking-holdings-q1-2026-earnings-call https://www.investing.com/news/transcripts/booking-holdings-at-citis-2026-global-tmt-conference-ai-loyalty-lead-93CH-4892462 It was a launch partner for ChatGPT apps (6 Oct 2025). https://techcrunch.com/2025/10/06/openai-launches-apps-inside-of-chatgpt/
- **Vrbo/Expedia (28 Oct 2026):** natural-language search, RNPL (coming) and an AI voice support agent. https://www.businesswire.com/news/home/20261028207262/en/
- **Agoda:** AI Assistant in 21 markets (Nov 2026) and single-transaction multi-product booking (links in §1).
- **Trip.com:** TripGenie traffic up 125% YoY, and Trip.Planner launched Aug 2025. https://group.trip.com/media/article_detail/trip-itb-asia-2025?id=526

## 7. Gaps / caveats
- Medium engineering URLs returned 403 to my fetcher. I read them via mirrors and summaries and cite the canonical links.
- Airbnb help-center articles were seen on regional domains; I list them under airbnb.com using the same article IDs.
- I found no official Airbnb calendar/availability-service write-up and no current design-token spec.
- Expedia Fall 2026, Booking Q1-2026/Citi and FTC pages were verified via search snippets only (fetch blocked or timed out).
- ⚠ The host-only fee (PriceLabs), design tokens and Kenya licensing rely on secondary sources.
- Airbnb's Q2 "45% of AI-initiated issues" and Q3 "40% of all issues" aren't comparable.

## 8. Top 25 takeaways to apply to a small direct-booking host platform
1. Quote one all-in KES total (nights + cleaning + levies) on web, USSD, SMS and voice, and fold cleaning into the nightly rate (§1, §5).
2. Repo note: `createHold` checks then inserts on synchronous SQLite, which is safe in one process. Before adding a second instance, iCal sync or an OTA channel, add per-night rows with UNIQUE(unit, night) in one transaction (§3 iCal lag, §4 "Book twice").
3. The repo already matches Airbnb/Boleto patterns: 5-minute hold, duplicate-callback no-op, and late-payment reconfirm-or-`refund_due`. Next: persist provider IDs (CheckoutRequestID/receipt) as unique idempotency keys before calling Daraja, add retryable/non-retryable error classes, and add an STK-query reconciliation job (§4).
4. Drive `refund_due` to a closed state (automated or tracked) and append every payment event to an immutable ledger (§4).
5. Keep the `notifications(booking, kind)` primary key. Add status, retries and AT delivery receipts, and show "delivered" to the host (§1, §3).
6. Trigger scheduled messages from events (booked, D-3, D-1, check-in, checkout, review) with host skip/edit and a last-minute fallback (§3).
7. Reveal location and door code in stages (approximate area, then directions at T-48h, then code on arrival) on one "My booking" page, plus STATUS via SMS/USSD (§1).
8. Add Reserve-Now-Pay-Later or a deposit (30–50% via M-Pesa, balance before arrival) for flexible/moderate policies, and A/B test it (§1).
9. Offer two plain policies (full refund ≥5 days / ≥1 day) and show the deadline and fees before the STK push (§3, §5).
10. Collect verified-stay reviews with 3–4 sub-scores via SMS, and compute a relative "Guest favourite" badge across your own stays, since raw averages inflate (§1, §5).
11. Keep communication and payments on-platform. Send SMS only from a registered sender ID, never request PINs or pay-links, and warn that off-platform payment voids protection (§5).
12. Replace the static host PIN with OTP/2FA, lockout and an audit log; Booking.com mandated partner 2FA after hijacks (§5).
13. Add party/risk rules: flag entire-unit, 1-night, last-minute and distant-or-unknown-number bookings. Require ID plus a deposit, or redirect to a smaller unit (§5).
14. Run a 24/7 "text HELP" safety line with escalation, a neighbour-complaint number and decibel-only noise sensors. Use no indoor cameras and disclose outdoor ones (§5). Kenya's guard-log/CCTV expectations: https://businessradar.co.ke/airbnb-tra-licence-kenya-2025-regulations/ ⚠
15. Keep a per-unit disclosure checklist: house rules, safety & property, cancellation, and accessibility features each with a photo (§1).
16. Search = Where/When/Who pill + categories + flexible dates + map + total price. Mirror it in USSD (3 prompts) and in "Ask Amina" SMS (natural language to structured query, with a deterministic fallback) (§1).
17. Make "My booking" a living itinerary (code, directions, Wi-Fi, checkout, tips) across web/SMS/USSD/voice (§1).
18. Sell mini-services (airport pickup, groceries, laundry, late checkout) via M-Pesa, using partner discounts as Airbnb Services does (§6).
19. Give hosts bilingual quick replies/templates and property Q&A auto-answers drawn from listing data; AI drafts need approval (§1, §3).
20. Define a channel-agnostic "section" JSON (title, price, availability, actions) rendered by web, USSD menus, SMS templates and voice scripts, which is the Ghost Platform idea (§4).
21. Ship behind flags, log exposure, and run small A/Bs (total price vs nightly, deposit vs full, voice scripts) with phone-hash cohorts (§4).
22. Prepare for regulation: a licence/registration field per unit shown on the listing (Kenya TRA licence under the 2025 regulations; verify ⚠), itemised tax lines, and an exportable nights-booked report (§5).
23. Give hosts an itemised statement per booking (nightly, cleaning, taxes, fee, co-host share). Release payout at check-in and hold it for unverified units (§3).
24. Build AI/SMS support around strict intents (extend stay, late check-out, Wi-Fi, refund), with human escalation, a tracked resolution rate (Airbnb ~40%) and a voice IVR fallback (§5).
25. Show hosts their total payout and fee breakdown upfront. If you ever take a commission, publish one simple all-in fee (Airbnb's host-only 15.5% shift ⚠) (§3).
