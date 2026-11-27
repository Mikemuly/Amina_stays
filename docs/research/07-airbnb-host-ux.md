# Airbnb host UI/UX as of 25 Nov 2026: anatomy for the Amina Stays host console

## 0. Summary

- **Shell:** Hosting mode is five destinations: **Today · Calendar · Listings · Messages · Menu** [RC-738]. On mobile they form the bottom tab bar with Listings in the centre [RC-638]. Everything else lives behind Menu or inside the Listing editor.
- **Reservations page is gone.** A `Today > Reservations` list with tabs Upcoming / Completed / Canceled / All existed until at least Sep 2025 [WB-3]. The current Help text (Nov 2026) says:
  - current and upcoming reservations are in Today (a Today | Upcoming toggle plus a Filter);
  - completed ones are in Earnings > Paid;
  - canceled ones are in Messages > Trip stage [HC-3037].
  - A Sep 2026 community thread says the sortable "All reservations" table was removed [CC-2]. Your Reservations page is a differentiator, not something to mirror.
- **Airbnb has no housekeeping.** The Pro-tools "Tasks" feature was switched off on 20 Apr 2024 [SEC-1, CC-3]. HC-2499 still lists it, but that is stale.
- **Your 6 listings sit exactly on a 2026 threshold.** The redesigned **multi-listing calendar** becomes the default desktop calendar for hosts with 6 or more listings, "in the coming months" [RC-776]. The AI earnings insights are for hosts with 5 or fewer [RC-776, HC-304].
- **2026 changes to mirror:**
  - Reservations redesigned [RC-765].
  - Messaging upgrades: AI auto-replies, suggested actions, priority messages [RC-770].
  - Seasonal and last-minute pricing [RC-766] and dynamic pricing [RC-777].
  - Insights inside the calendar [RC-768].
  - A single 15.5% host-paid service fee [RC-771].
  - A house-rules overhaul, effective 20 Nov 2026 [RC-21].
- **Compliance constraint:** the new house-rules policy bars hosts from asking guests to sign separate contracts or give a government ID "except where required by law" [HC-4168]. Your guest-register and TRA flows must be channel-aware.
- **Visual language:** hosting uses the same DLS as the guest side. I verified the palette, radii, weights, font and button tokens in Airbnb's live CSS (§8). Which pages use black versus Rausch buttons, page widths, toasts and sheets are not publicly documented ⚠.
- **Access limit:** the host console is login-gated and I had no host login. Primary sources are Help and Resource Center text, newsroom posts, Airbnb Community threads, Wayback snapshots and live CSS. Anything I could not confirm is marked ⚠.

## 1. Navigation and shell

**Tabs.** The Today tab "is what you see when you open the app". The Menu "gives you access to your earnings, insights, and other settings", personalised tips and resources [RC-738]. Desktop Help steps use the same labels (`Click Today > Menu > Earnings` [HC-3037], `Click Messages, then Settings` [HC-2898]).

**Renames and routes.**
- "Inbox" became "Messages". A March 2023 snapshot lists Reservations / Today / Inbox / Calendar [WB-1].
- Link targets give the route map: Today `/hosting`, Calendar `/multicalendar` (also `/calendar-router` [RC-768]), Listings `/hosting/listings`, Messages `/hosting/messages`, Earnings `/users/transaction_history`, Insights `/performance/opportunities` [HC-2500], Reviews `/progress/reviews` [RC-665].

**Switching modes.**
- Desktop: "Next to your profile photo, click Switch to hosting / Switch to traveling" [HC-3546].
- App: **hold Profile → Hosting**; in hosting mode **hold Menu → Traveling** [HC-3546]. This press-and-hold switcher is verified.
- Mobile hosting has no Profile tab, and Account sits under Menu. That is inferred from the tab list and the Account settings path ⚠.

**Menu contents.**

| Verified | Evidence |
|---|---|
| Earnings | `Today > Menu > Earnings` [HC-3037] |
| Insights (Reviews; Performance → Quality, Conversion, etc.) | [HC-1257, HC-2500] |
| Refer a Host | `Menu > Refer a Host` [HC-3872] |
| Account settings → Notifications etc. | [HC-2893 snippet] |
| Hosting resources → Community Center, Help Center, Resource Center | [HC-1183 snippet, HC-2739] |

- Account settings has nine groups [HC-280]: Personal information; Login and security; Privacy and sharing; Notifications; Payments and payouts; Translation; Taxes; Professional hosting tools; Accessibility.
- An iOS flow catalogue shows Menu leading to Guidebooks, Gift cards, Refer a host, Insights, Earnings and Find a co-host [SEC-2]. The capture date is unknown ⚠, and Help now puts Guidebooks under Listing editor → Arrival guide [HC-249].
- Co-hosts live in Listing editor → Co-hosts [HC-1244].
- "Create a new listing" in the Menu is not confirmed. Help says "in the host section of your profile" [HC-1336] ⚠.
- "Reservations" was in the Menu or Today in 2023–25 and is now removed.

**Notifications.** Preferences are at Menu > Account settings > Notifications (email, SMS, push) [HC-2893, HC-14]. A bell icon and its position are not documented ⚠.

**Pro tools.** An opt-in at Account settings → "Use professional tools" [HC-2499]. It unlocks multi-calendar, occupancy tax, Insights/Performance, rule-sets and additional fees. It is desktop-oriented: rule-sets and bulk edit are desktop only [HC-2061, RC-649].

**Early Access.** New host features were gated behind an in-app "Early Access" opt-in [NEWS-25S, NEWS-23W]. Individual hosts can therefore see different UIs.

## 2. Today tab

**Purpose.** "Reservation details at a glance". It switches between current and upcoming reservations, supports private notes, and shows per-reservation tips such as "asking guests how things are going or reading a review" [RC-738].

**Structure (mobile, June 2025 [CC-1]).**
- Two options sit at the top: **Today | Upcoming**.
- Upcoming opens a new animated window titled "You have XX upcoming reservations", listed chronologically.
- Today's headline reads "You have 4 reservations". New check-ins show a time (3:00 p.m., the listing's check-in start) and in-house guests show "All day".
- Booking requests appeared as a stack of tap-to-reveal "flash cards". Hosts called it "beautiful, but redundant" and slow.
- Desktop: `Today → (Upcoming) → Filter → select one or more listings → Apply → click a reservation` [HC-3037]. If you host other listing types, you can also filter by type.

**Alerts and banners.**
- `You're ready to publish` (Publish button) and `Required to publish` banners appear on Today [HC-883].
- 2026 reservation alerts cover tasks such as "smart lock disconnected" [RC-765].

**2026 redesign [RC-765].**
- Booking requests show potential earnings and guest rating, Accept and Decline buttons, and a **24-hour countdown**.
- Reservation detail has Message / Call buttons, editable check-in and checkout times, private notes for you and co-hosts, reminders and alerts, cancellation-policy cutoff dates and times, and an itemised earnings breakdown (guest pays, service fees, taxes, payout).
- Actions: **Manage reservation → Change reservation** (dates, guests, price or listing → Save → Review → Send request [HC-50]) or **Cancel reservation** (questions plus a message to the guest [HC-166]).

**Status vocabulary** (listing time zone [HC-363]).
- **Pre-trip:** Inquiry; Invite sent; Special offer sent; Awaiting guest ID (12 h); Awaiting payment (24 h); Confirmed; Change pending / Trip change requested / sent / declined; Arrives in X days; Arriving tomorrow; Arriving today; Trip changed by Airbnb.
- **During:** Currently hosting.
- **Post-trip:** Checking out today; Review guest (14-day window); Awaiting guest review; Past guest.
- **Ended:** Request withdrawn / declined / expired; Trip declined; Invite expired; Offer expired; Not possible; Canceled; Canceled by host / guest / Airbnb.

**Chip set from your brief.** "Pending review" is not in the current status table. The `Checking out / Currently hosting / Arriving soon / Upcoming / Pending review` chip row is not in current docs and may be the pre-2025 web design ⚠. The "Write a review for…" wording is also unverified ⚠.

**Not verified ⚠:** the greeting copy (older web UIs used "Welcome, <name>" from memory), the empty-state copy, and the desktop list/detail layout.

## 3. Calendar

**Single-listing view.**
- Pick a listing, then a month grid. Available nights are **white**; blocked nights have a **line through the date**. Selecting a blocked night shows whether you or Airbnb blocked it [HC-447].
- Select a night or range, then enable **Available / Blocked**. Mixed selections show **Edit** to choose. You cannot unblock cancelled reservations, synced-calendar nights, or legally blocked nights [HC-447].
- Mobile: press-hold then swipe across and down to select a range. A **Year** view (dropdown) shows all 12 months with each month's price; tapping a month edits that month's nightly price [RC-585].
- Reservations are highlighted in different colours for current, future and pending stays [RC-585]. Booked bars with guest avatar or name are not documented ⚠.

**Prices.**
- The base price shows on all uncustomised nights.
- Select nights and enter a custom price to override base, Smart Pricing, weekend and long-stay pricing [HC-474].
- **Price tips** show under each night; toggle them with the wand icon [RC-707]. A secondary source describes red/black dot markers ⚠ [SEC-3].
- A button under the price opens a **price breakdown** (guest total, fees, discounts, taxes, your earnings) [RC-582].
- **Smart Pricing:** `Calendar → Pricing → Smart Pricing → min/max → Save`. Nights with a **broken arrow** have Smart Pricing off. While it is on, price tips and similar-listings are hidden [HC-1168].

**Right-hand settings.** Pricing and availability settings were consolidated in one place [RC-582, RC-585].
- **Pricing:**
  - Base price, weekend adjustment, Smart Pricing.
  - Discounts: weekly (7+ nights), monthly (28+), early bird (1–24 months), last-minute (1–28 days). A slider shows average weekly or monthly price and earnings.
  - Promotions: new-listing 20% off the first 3 bookings, custom promotions, and the top-rated-guest 15% discount (guests rated 4.8+ with at least 3 reviews, from Sep 2026) [RC-707, RC-776].
  - Fees: cleaning, pet, extra guest.
- **Availability** [RC-708]:
  - Minimum and maximum nights, plus a custom trip length per date.
  - Advance notice (same day / 1 / 2 / 3 / 7 days) and a same-day cutoff time (6 AM–12 AM).
  - Preparation time (none / 1 / 2 nights) and availability window (3 / 6 / 9 / 12 / 24 months).
  - Check-in and checkout day restrictions (up to 6 days per week).
  - iCal import and export.
  - **Gap tip:** if your minimum is 5 nights and only 4 nights are free between bookings, a tip suggests lowering the minimum.
- **Compare similar listings:** select up to 31 days, then "View similar listings" to see a map of booked and unbooked average prices [RC-583].
- **Date-level panel:** the exact side-panel layout is not documented ⚠.

**2026 additions.**
- **Seasonal prices:** per-month base price plus a weekend adjustment such as +15% [RC-766].
- **Last-minute settings:** shorter minimum stay within 2 weeks, and discounts at 8–14, 2–7 and 0–1 days [RC-766].
- **Extended availability:** booking requests beyond the window, reviewed within 24 h [RC-766].
- **Dynamic pricing** (from Oct 2026 [RC-777]): a suggested price **curve you drag up or down**, optional min/max, a 52-week preview, the recommended price **under your price on each calendar night** for 2 years, and per-night override.
- **Insights in the calendar** [RC-768]: tips such as allow booking further ahead, less notice, add discounts, adjust base price, lower minimum nights.

**Multi-calendar and multi-listing.**
- **Legacy multi-calendar** (Pro tools, `/multicalendar`): "view and manage availability for all your listings in one place" [RC-649]. Rule-sets get a name and **colour shown on the calendar**; they apply pricing, availability and promotions to date selections (desktop only) [HC-2062].
- **Bulk edit:** `Listings → select listings → Edit`. Trip length, length-of-stay discount, cancellation policy, amenities, property type, fees, location, check-in method, standard house rules and location details [RC-649].
- **New multi-listing calendar** [RC-776, NEWS-26F]: open nights and reservations at a glance; update prices, availability, cancellation policies or discounts across all or a few listings; auto-adjust minimum stay to unblock gaps; last-minute discounts; update listings in groups (similar locations or property types).
- The visual layout of the new calendar is not published. Rows per listing and horizontal days is an inference ⚠.
- The hour-by-hour daily view with Google Calendar sync is for Experiences and Services, not Homes [NEWS-25S, HC-2822].

## 4. Listings tab

**Listing list.**
- Cards or rows show photo, title and location. A grid/list toggle is not documented ⚠.
- Desktop shows per-listing checkboxes with bulk **Edit** and **Co-hosts** actions [HC-1244, RC-649].
- Statuses and banners:
  - **Listed / Unlisted** (`Listing editor → Settings → Edit preferences → Listing status`). Unlist for a set period (up to 6 months) or indefinitely, or remove the listing [HC-476, HC-883].
  - **Action required** banner [HC-4084].
  - After publishing, a listing sits "pending" until identity verification [HC-1336].
  - "In progress" is not confirmed ⚠.

**Listing editor (2023 → 2026).** It has two sections, **Your space** and **Arrival guide**, plus Settings and Co-hosts [RC-638, HC-476].
- **Your space:**
  - Title, description and AI-assisted **photo tour**. The AI assigns photos to **19 room and space types**. You can edit the tour, add per-room details (bed sizes, TV) and accessibility features.
  - Amenities: "nearly 150", alphabetical or by category (Entertainment, Family, Outdoor), searchable, added with "+".
  - Sleeping arrangements, location and booking settings (Instant Book) [RC-638, NEWS-23W, HC-3329].
  - **Policies** (cancellation) are edited here [HC-3329].
  - **House rules** [RC-21]: 7 standard rules (max overnight guests, pets, smoking, quiet hours, events, commercial photography, lock up at checkout) plus **Additional rules** (formerly "Requests"). Checkout instructions were removed.
  - **Required action** cards appear for non-compliant rules, with an appeal flow of statement plus upload, one submission only [RC-21].
  - **Contracts** are allowed only for limited reasons and are uploaded under Contracts in listing settings [RC-21].
- **Arrival guide:**
  - Check-in method and time, directions, house manual, Wi-Fi password.
  - **Smart lock:** a unique code per reservation, expiring 30 minutes after checkout. US and Canada first, Schlage / August / Yale [RC-638, NEWS-23W].
  - **Guidebooks:** `Arrival guide → Guidebooks` (title, cover photo, associated listings, "Add to guidebook"). They are public, shareable and printable [HC-249].
  - A **View** button shows the arrival info exactly as guests see it [RC-638].
- **Preview cards and a right-hand preview pane** are not documented ⚠.
- **Other:** Smart Setup (address-based listing creation, US first) and 3D floor plans via iPhone Pro / iPad LiDAR (Sep 2026) [RC-776].

## 5. Reservations (current model and legacy)

- **Current (Nov 2026) [HC-3037]:**
  - Today | Upcoming plus Filter by listing.
  - Completed: `Menu > Earnings > Paid` (filter by date, listing, earnings type), then open a row.
  - Canceled: `Messages > All > Homes > Filters > Trip stage > Canceled reservations`.
- **Legacy [WB-2, WB-3]:**
  - Feb 2025: `Today > Reservations > All reservations → More details`.
  - Sep 2025: tabs **Upcoming / Completed / Canceled / All**.
  - Columns are not documented ⚠. Community posts call it a "sortable table" [CC-2].
- **Guest card.** In a thread, **Details** lists everyone who joined, and tapping a guest photo opens their profile [RC-678]. Requests show the guest's rating [RC-765]. Other fields on the guest card (verified, ID, reviews) are not documented ⚠. Statuses like "Awaiting guest ID" exist [HC-363].
- **Payout breakdown.** Payout = nightly rate + optional fees − host service fee − co-host payouts [HC-459 snippet]. With the single 15.5% fee guests see exactly your price, and you net about 84.5% [RC-771].
- **Review guest.** Start from Messages (select the thread → "Get started") or Profile → Reviews → Reviews by You. You have 14 days [HC-3531, HC-13].
- **Notes.** Private notes are shared with co-hosts [RC-765].

## 6. Messages (host inbox)

- **Categories:** All, Homes, Experiences, Services, Traveling, Support, Direct messages. Co-host and Superhost Ambassador appear when relevant [RC-678].
- **Homes filters:** Unread, **Trip stage** (reservation requests, upcoming, currently hosting, past, canceled), Listings, Starred [RC-678, HC-2899].
- **Search:** names, words, confirmation code. There is an Archive folder, and an archived thread returns to All on a new guest message [HC-2899].
- **Teams:** all members get the same messages, with personal star / read / archive state [HC-2899].
- **Thread:**
  - One thread per reservation; invited co-travellers join the same thread.
  - Top-of-thread **Details** button for reservation and people.
  - Threaded replies, edit within 15 min, unsend within 24 h, read receipts, and photo / video attachments (PNG/JPG up to 50 MB; MP4/MOV up to 100 MB and 60 s).
  - Recommend a guidebook, Experiences or Services [RC-678].
  - Messages auto-translate into the guest's language; the setting is in Account → Translation [HC-2898, HC-280].
- **Composer:** the "+" opens **Send quick reply**. Suggested replies (AI) are visible only to you. Quick replies are managed at `Messages → Settings → Manage quick replies → Create` [RC-73, HC-2898].
  - Templates use placeholder **details** (first name, check-in date, Wi-Fi, door code, house rules, directions, etc. [HC-2898]), a 4,000-character limit, and a hosting-type and listing scope.
  - Scheduling offers e.g. "5 minutes after booking" or "1 day before check-in at 10:00 AM". A reminder appears in the thread before a scheduled message sends; you can adjust or skip it [RC-73].
- **2026 upgrades (rolling out) [RC-770].**
  - **Auto-replies:** AI answers from the listing, labelled as Airbnb, deletable.
  - **Suggested actions:** interactive cards such as changing a reservation.
  - **Priority messages:** time-sensitive threads pinned to the top with labels (inquiries, check-in help).
- **Not documented ⚠:** a dedicated "needs response" badge or unread dot, and the desktop three-pane arrangement.

## 7. Earnings, Insights, Reviews, Guidebooks, Co-hosts

- **Earnings** (`Menu > Earnings`) [HC-304, RC-675]:
  - An interactive chart shows the previous 6 months, this month, and a projection for the next 5 months. Expand it for monthly or yearly views and filter by listing.
  - Below the chart: nights booked and average length of stay, and a year-to-date gross / deductions / net summary.
  - A payment-on-the-way **earnings card** shows payout method, amount and estimated processing time.
  - Tabs on desktop: **Performance / Upcoming / Paid / Reports**.
  - Filters: date, listing, earnings type (Homes, Experiences, Services, Credits, Resolutions), payout method. Search by confirmation code or amount. **Export CSV**.
  - Reservations starting the same day can be paid out in one row. Payout ID shown for bank enquiries.
  - **Reports:** monthly and annual PDFs plus custom reports.
  - The **gear icon** opens payout methods and routing, taxpayer info and tax documents, and recurring donations [RC-675].
  - **AI "Top takeaway"** is for hosts with 5 or fewer listings [HC-304].
  - **History:** the redesigned dashboard shipped in the 2023 Winter Release [NEWS-23W]. The Resource Center chart article is dated Oct 2024 [RC-675].
- **Insights** (Pro tools) [HC-2500, HC-2714, HC-2715]:
  - Sections: **Conversion**, **Occupancy & rates**, **Quality**, **Hosting progress**.
  - Conversion: first-page impressions, search-to-listing, listing-to-booking, lead time, returning guests, views, wishlists.
  - Occupancy: nights booked / blocked / unbooked, check-ins, cancellation rate, length of stay, nightly rate.
  - Time frames: Last week / month / year; Next week / month / 3 / 6 months. Compare to previous periods or similar listings.
  - **Reviews insights:** tips derived from guest feedback (e.g., update photos or check-in instructions) [RC-768].
- **Reviews** [HC-1257, HC-13, HC-32, RC-665]:
  - Category stars: Overall, Cleanliness, Accuracy, Check-in, Communication, Location, Value, each with tag reasons.
  - The rating appears publicly after 3 reviews.
  - Host reviews guests within 14 days.
  - Public response: Profile → Reviews → Reviews about you → Leave public response. Responses sit under the review; you cannot remove reviews.
- **Guidebooks:** see §4.
- **Co-hosts** [HC-1244, HC-1534, NEWS-23W]:
  - Up to **10 per listing**. Invite by phone or email via Listing editor → Co-hosts.
  - Multi-listing invites are desktop only and must use the same permissions.
  - Three permission levels: **Full access / Calendar + messaging / Calendar**.
  - Payout split options include sharing the cleaning fee, or the cleaning fee plus a percentage.
  - Co-host messaging has its own filter.
  - Co-hosts cannot see owner payout or taxpayer data and do not get the new guidebooks [HC-249].

## 8. Visual design of hosting mode

**Same DLS as the guest side.** The product design team says the 2025 app has "a softer feel, more curved edges, a smooth animated interface" and **3D icons** for Homes / Experiences / Services [SEC-4]. Another review notes the logo, typeface and colour palette "remain untouched" and that regular line icons remain for smaller navigation cues [SEC-5]. I found nothing on hosting-specific design beyond this.

**Verified tokens (live Airbnb CSS [CSS-1, CSS-2]).**

| Token | Value |
|---|---|
| Font | `'Airbnb Cereal VF', Circular, -apple-system, BlinkMacSystemFont, Roboto, 'Helvetica Neue', sans-serif` |
| Weights | 400 / 500 / 600 / 700 |
| Type tokens | `title-large32px` (letter-spacing −0.06rem), `title-small22px` (−0.0275rem), `body-text_16_20` (used by buttons), `base-extra-small10px` (10/12px). Tracking wide 0.04em. |
| Text and neutrals | `hof #222222`, `foggy #6A6A6A`, `bobo #B0B0B0`, `deco #DDDDDD`, `bebe #EBEBEB`, `faint #F7F7F7`, `white` |
| Brand | `rausch #FF385C`, `product-rausch #E00B41`, `plus #92174D`, `luxe #222222` |
| Status | error `arches #C13515`, `arches2 #B32505`, `arches12 #FFF8F6` (tint); warning `ondo #E07912`; success `spruce #008A05` |
| Radii | 4, 8, 12, 16, 20, 24, 28, 32 px |
| Translucent material backgrounds | 0.40, 0.50, 0.72, 0.86, 0.925 alpha |
| Button defaults | radius 8px, padding 14px 24px, 16/20 type, weight 500. Colours are variant tokens (hover, focus, active, disabled). On press the button **shrinks 2px** (`scale((w−2)/w)`). |
| Breakpoints | 744 (main), 375, 950, 1128 |

**Not documented for host pages ⚠.**
- **Page title:** the "32px semibold Today" guess matches the `title-large32px` token and the 600 weight, but I could not see the host page.
- **Black versus Rausch:** the community-reconstructed guest-side system uses Rausch for Reserve and search, and #222 for the selected date range [SEC-6]. Black primary buttons on host surfaces are widely observed but not confirmed ⚠.
- **Layout:** page widths, table and chart styles, empty states, toasts, modals and side sheets.
- **Density:** host pages read as card-and-row UIs with filters and export, not dense tables. The June 2025 Today feedback asked for less animation for multi-listing hosts [CC-1].

## 9. Comparable small-host PMS UIs

*(Delegated research, spot-checked: I re-read Hospitable's Task Rules and Inbox pages. Guesty, Hostaway, Lodgify and Smoobu help centres returned 403 to the fetcher, so their points are snippet-level and need a spot-check in a trial account. No screenshots were viewed. No vendor documents Kenya-specific compliance ⚠.)*

- **Hospitable [HOSP-1, HOSP-2]:**
  - Task rules auto-create Cleaning / Check-in / Checkout / Maintenance tasks as soon as a booking is accepted. Each carries a timing offset, a checklist (AI-generated or edited), and a primary plus backup cleaner. Tasks show on a **Task calendar** where status is by pill style (grey + alert = unassigned or declined, outlined = pending, solid = accepted).
  - The thread's reservation panel sits at the top left, with the guest-portal panel below it (tasks, verification, upsells). Check-in and checkout times are click-to-edit.
  - Messaging rules are event-based or scheduled and preview shortcodes on a real booking. E-signed rental agreements are Direct-only. ID checks are paid.
- **Guesty (Lite / Pro):**
  - Task templates and auto-tasks tied to reservation events, with photo checklists and assignment to a group "anyone claims". Cleaners are restricted users in the main app.
  - Inbox layout: inboxes sidebar → conversation list → thread plus widgets (reservation, property, guest, automations). Unread first, snooze, star, assign.
  - Compliance add-ons: GuestVerify and AutoComply (authority reporting).
- **Hostaway:**
  - Task board: To Do → Accepted → In Progress → Done. Calendar cleanliness dot flips from "Not clean" to "Clean".
  - Inbox side panel with an editable Summary tab. Guest portal gates access details on payment or form status.
  - Per-channel **"Applies to"** (19 Nov 2026) lets Airbnb guests skip forms and agreements. Native SES Hospedajes for Spain.
- **Lodgify:**
  - Tasks on the Ultimate plan: cleaning generated per booking, any-cleaner-claims, photo-required checklist items, optional inspector.
  - Inbox filters by lifecycle: Future / Currently hosting / Past / Potential.
  - Check-in form, e-sign agreement and deposit hold.
- **Smoobu:**
  - No built-in tasks; cleaners are read-only staff accounts and the message editor can Bcc a cleaner.
  - Template editor in five sections: Scope · Message · Trigger · Timing & Rules · Attachments.
  - Multi-calendar rows with toggleable booking-bar chips (channel, guest, count, price, nights).
- **Patterns worth copying:**
  - A booking-driven task rule: trigger, offset, checklist, primary and backup.
  - Turnover pills coloured by response state.
  - The cleaner as a restricted role, not a separate product.
  - Per-guest edits of scheduled messages without touching the template.
  - Inbox segments by stay stage.
  - Compliance as a pre-stay checklist scoped per channel.
  - Country-specific registration as pluggable exports.

## (a) Recommended information architecture

**Top level (desktop top bar and mobile bottom bar, same order as Airbnb).**

| Tab | Route (existing) | Contents |
|---|---|---|
| **Today** | `/host` | Today \| Upcoming toggle; listing filter. Request cards (Accept / Decline + 24 h timer for direct requests). Arrivals, in-house, departures. **Needs attention** strip: unanswered messages, ID / guest-register gaps, payments due, overdue housekeeping, channel down. Compact housekeeping-today and breakfast-tomorrow cards linking to Tasks and Kitchen. |
| **Calendar** | `/host/calendar` | Multi-listing view as default (6 rows, days across), plus single-listing month view. Overlays for price, min stay, turnover tasks, breakfast counts. Select dates → side panel: price, Available / Blocked, min stay, discounts. Gear → Pricing and Availability settings. |
| **Listings** | `/host/listings`, `[id]` | Cards with photo, name, location, status. Editor: **Your space / Arrival guide / Safety & compliance (extra) / Settings**. Guidebooks under Arrival guide. Co-hosts / team per listing. "View as guest". |
| **Messages** | `/host/inbox` | Unified inbox with channel filter (Airbnb, Booking, WhatsApp, SMS via Africa's Talking, direct chat) plus Unread / Trip stage / Listing / Starred. Thread with Details panel. Composer: quick replies, scheduled, AI suggestion. **Settings**: Templates, Automations, FAQ, Broadcasts (`/host/messaging`), channel status (`/host/channels`). |
| **Menu** | new `/host/menu` | Page of grouped rows (below). |

**Menu groups.**
- **Business:** Reservations (list + `[ref]` detail, your differentiator) · Earnings (`/host/payments`, including refunds) · Insights (`/host/insights`, Reviews inside) · Guests (CRM)
- **Operations:** Housekeeping tasks (`/host/tasks`) · Breakfast & kitchen sheet (`/host/kitchen`) · Team / co-hosts (permission tiers)
- **Compliance and channels:** Safety & compliance (`/host/safety`) · Channels & Africa's Talking status (`/host/channels`)
- **Account and help:** Account settings (`/host/settings`, Airbnb-style groups) · Hosting resources / help · **Switch to guest site** (the "Switch to traveling" equivalent) · Log out

Surface the extras (tasks, kitchen, channel status) on Today and Calendar, not only inside Menu. Airbnb hides little because it has little; you have daily-use ops that deserve first-class cards.

## (b) Top 25 hosting UI/UX details to replicate (ranked)

1. **Five-tab shell, Listings in centre.** Same labels desktop and mobile; Menu is a page, not just a dropdown. *Implement:* one nav config rendering both top bar and bottom bar; active state in `#222`.
2. **Today = Today | Upcoming toggle + listing Filter + "You have N reservations" + chronological cards.** *Implement:* segmented control; list sorted by date; filter chips; per-card tap-through.
3. **Status vocabulary with next-step hints.** Use the HC-363 set (Arriving today / Currently hosting / Checking out today / Review guest). *Implement:* one enum → chip colour + CTA text.
4. **Request card:** potential earnings, guest rating, Accept / Decline, **24 h countdown**. *Implement:* countdown timer; auto-expire; keep it a plain card (no flip animation).
5. **Reservation detail:** Message / Call on top, Manage reservation (Change / Cancel), editable check-in / out times, private notes, alerts, cancellation cutoffs, itemised earnings. *Implement:* one page, sticky action bar.
6. **Calendar edit model:** select dates → panel with price and Available / Blocked; strikethrough for blocked; mixed selection → Edit; blocked reason on select. *Implement:* drag-select with a side sheet; never silently override a booking.
7. **Multi-listing calendar** for 6+ homes: rows per listing, group selection, bulk edit across all or a few. *Implement:* row-per-home timeline; apply-to-N confirmation with preview and undo.
8. **Calendar settings split:** Pricing (base, weekend, smart, discounts with slider, fees) vs Availability (min/max, notice, prep time, window, restricted days, iCal). *Implement:* two tabs in a settings sheet using Airbnb's exact option sets.
9. **Price breakdown button** under the nightly price (guest pays / you earn). *Implement:* show KES price, 2% tourism levy, VAT, OTA fee and net.
10. **Min-stay gap tips:** detect orphan nights that min-stay blocks. *Implement:* nightly job; inline "lower minimum for these nights" action.
11. **Pricing aids:** custom price overrides base; "broken arrow" for Smart Pricing off; price-tips toggle; seasonal / last-minute settings. *Implement:* simple range-based smart pricing with min / max; per-night override marker.
12. **Messages filter and search model:** categories + Unread / Trip stage / Listing / Starred, search by guest or code, Archive. *Implement:* saved filter chips; team-shared threads with personal star / read.
13. **Composer:** "+" menu → quick replies, scheduled quick replies with in-thread reminder, placeholder "details", attachments, edit and unsend. *Implement:* reuse your templates / automations under one composer menu.
14. **Priority / needs-response pinning** with labels (inquiries, check-in help). *Implement:* a waiting-time badge and pin-to-top rule; AI auto-replies must be labelled as automated.
15. **Thread "Details" panel:** reservation, people, guest profile. *Implement:* right drawer on desktop, full screen on mobile.
16. **Listings cards with status and banners:** Listed / Unlisted / Action required; Today banner "ready to publish". *Implement:* status chip + required-actions list.
17. **Listing editor with two sections + "View as guest" preview.** *Implement:* left section list, right form, preview button for the arrival guide.
18. **Photo tour by room** (19 room types; per-room beds and amenities). *Implement:* manual room tagging for 6 homes; drag to reorder.
19. **House rules model:** 7 standard rules + Additional rules + Contracts; Required-action cards. *Implement:* structured rules; policy checker for "not allowed" phrasing; contracts only where legally required.
20. **Earnings dashboard:** chart with 6 months back, current, 5 projected; earnings cards; tabs Performance / Upcoming / Paid / Reports; CSV; payout ID. *Implement:* one chart + transaction table with filters and export; add M-Pesa payout reference.
21. **Insights structure:** Conversion / Occupancy & rates / Quality / Hosting progress; Last week / month / year and Next 3 / 6 months; compare to previous period. *Implement:* occupancy, ADR, lead time, cancellations, review categories.
22. **Reviews flow:** category ratings with tag reasons, 14-day "Review guest" nudge, public response. *Implement:* auto-create a "review guest" to-do at checkout.
23. **Team permission tiers** (Full / Calendar + messaging / Calendar) and private notes visible to the team. *Implement:* map to owner, housekeeper and caretaker roles.
24. **DLS tokens:** Cereal-style type (use Inter, since Cereal is not licensable), `#222222` text, `#6A6A6A` secondary, `#DDDDDD` borders, `#F7F7F7` surfaces, `#FF385C` accent, `#C13515 / #008A05 / #E07912` states, radii 8 / 12 / 16, 8px button radius with 14×24 padding, 2px press-shrink. *Implement:* Tailwind theme extension; keep one accent.
25. **Account and Menu conventions:** Account settings groups, Hosting resources, mode switch, notifications preferences (email / SMS / push). *Implement:* settings page with the nine Airbnb groups plus your Africa's Talking channel preferences.

## Gaps and uncertainties

- I could not see logged-in host screens, so desktop Today layout, Menu presentation, grid versus list on Listings, booked-bar visuals, the new multi-listing calendar's look, empty states, toasts, side sheets, page widths and the black-vs-Rausch choice are all ⚠.
- "Pending review" and "Write a review for…" strings are unverified.
- Table columns for reservations and earnings are not documented.
- The Guidebooks and Find-a-co-host entries in Menu come from an iOS catalogue of unknown date.
- Several 2026 features (multi-listing calendar, dynamic pricing, messaging upgrades) are "rolling out", so hosts may see different UIs.
- **Verification step:** Amina's own Airbnb host account (6 listings) would show the real screens. Chrome DevTools computed styles would settle page-title size, button colours and widths.
- **Methods that worked:** Help Center pages embed full article text in `<script id="data-injector-instances">` JSON, which includes the accordions the fetcher misses. Wayback snapshots (`web.archive.org/web/<ts>/<url>`) show how the UI changed.

## Source key

**Resource Center (RC)** — base `https://www.airbnb.com/resources/hosting-homes/a/`
- RC-738 `exploring-your-hosting-tools-738` (Dec 10 2025)
- RC-638 `introducing-the-listings-tab-638` (Nov 2023)
- RC-776 `new-tools-to-host-smarter-not-harder-776` (Sep 30 2026)
- RC-765 `reservations-redesigned-765` (May 20 2026)
- RC-770 `respond-faster-in-the-messages-tab-770` (May 20 2026)
- RC-768 `all-new-insights-to-help-your-listing-stand-out-768` (May 20 2026)
- RC-766 `the-right-price-for-every-season-766` (upd. Sep 2 2026)
- RC-777 `introducing-dynamic-pricing-777` (Oct 14 2026)
- RC-707 `using-airbnb-pricing-tools-707`
- RC-708 `updating-your-availability-708`
- RC-675 `get-valuable-insights-in-the-earnings-dashboard-675` (Oct 2024, upd. Jul 2025)
- RC-678 `getting-the-most-out-of-the-messages-tab-678` (Dec 5 2025)
- RC-73 `using-quick-replies-to-save-time-73` (Dec 8 2025)
- RC-21 `important-changes-to-house-rules-21` (Oct 20 2026, upd. Nov 3)
- RC-771 `simplifying-service-fees-on-airbnb-771` (Jul 7 2026)
- RC-649 `updating-settings-and-availability-649` (Jan 2024)
- RC-585 `upgrades-make-your-calendar-easier-to-manage-on-mobile-585` (May 2023)
- RC-582 `redesigned-pricing-tools-now-in-your-airbnb-calendar-582` (May 2023)
- RC-583 `how-to-compare-the-average-prices-of-similar-listings-583`
- RC-665 `use-guest-reviews-to-improve-665` (Sep 2025)

**Newsroom**
- NEWS-23W https://news.airbnb.com/airbnb-2023-winter-release
- NEWS-25S https://news.airbnb.com/airbnb-2025-summer-release
- NEWS-26S https://news.airbnb.com/airbnb-2026-summer-release
- NEWS-26F https://news.airbnb.com/airbnb-2026-fall-update

**Help Center (HC-n)** = `https://www.airbnb.com/help/article/n` (3546, 3037, 363, 50, 166, 447, 474, 1168, 476, 883, 249, 1244, 1534, 2898, 2899, 304, 2500, 2714, 2715, 2499, 2061, 2062, 1257, 13, 32, 3531, 280, 3872, 4168, 4084, 1336, 459, 2739, 2822, 2893, 14, 3329). HC-1183 and HC-3329 are from search-snippet or Luxe-host text.

**Community, Wayback, secondary**
- CC-1 https://communitycenter.airbnb.com/forum/2d51a5c2-16fb-4016-833b-8f987dae813c/post/bGVnYWN5X2Nj_2112208 (Jun 2 2025)
- CC-2 https://community.withairbnb.com/t5/Support-with-your-bookings/Ability-to-view-sort-All-Reservations-table-removed-from/m-p/2298513 (Sep 2026; seen only as a search-index snippet, the page now redirects)
- CC-3 https://community.withairbnb.com/t5/Help-with-your-business/Airbnb-Task-Tool-going-away/m-p/2180189
- WB-1 `web.archive.org/web/20230301000000/https://www.airbnb.com/help/article/1355`
- WB-2 `.../web/20250213025533/https://www.airbnb.com/help/article/3037`
- WB-3 `.../web/20250915000000/https://www.airbnb.com/help/article/3037`
- SEC-1 https://turno.com/blog/airbnb-task-tool-alternative/
- SEC-2 https://uxmagic.ai/references/Airbnb-iOS/Menu-from-Switching-to-hosting
- SEC-3 https://www.rentalrecon.com/airbnb-website-issues/airbnb-calendar-symbols-colors/ (search snippet only)
- SEC-4 https://www.itsnicethat.com/articles/airbnb-app-redesign-140525
- SEC-5 https://www.overmatter.design/blog/the-airbnb-update-when-ui-design-doubles-as-brand-and-business-strategy
- SEC-6 https://www.shadcn.io/design/airbnb (community-reconstructed guest-side tokens)

**CSS and PMS**
- CSS-1 inline CSS of https://www.airbnb.com/help/article/3546 and `https://a0.muscache.com/airbnb/static/packages/web/common/frontend/cep-help-center/entrypoints/client.e4860e3d3d.css`
- CSS-2 https://www.airbnb.com/resources/hosting-homes/a/exploring-your-hosting-tools-738 and `.../resource-center/entrypoints/client.5f9757a5af.css`
- HOSP-1 https://help.hospitable.com/en/articles/4598563-task-rules-how-to-create-a-task-rule
- HOSP-2 https://help.hospitable.com/en/articles/9651923-inbox-overview-guest-conversation-thread-video-tour

**Repo context** (glob of `David-0chieng/Amina_stays:frontend/src/app/host/*/page.tsx`): existing console routes are `/host` (Today), `inbox`, `messaging`, `calendar`, `reservations` (+ `[ref]`), `listings` (+ `[id]`), `tasks`, `kitchen`, `guests`, `reviews`, `insights`, `payments`, `safety`, `channels` and `settings`.
