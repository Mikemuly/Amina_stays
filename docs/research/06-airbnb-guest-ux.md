# Airbnb guest UI/UX as of 25 Nov 2026: measured anatomy for the Amina Stays guest site

## Summary

- **Most numbers below were measured on the live site.** I read computed styles and bounding boxes on airbnb.com (logged out, Japan-geolocated, JPY) at 1440×1000 and a 375×812 mobile emulation. I also read Airbnb's served CSS variables, its SSR JSON and its CSS bundle.
- **Primary sources confirm the timeline.**
  - 2025 Summer Release (13 May 2025): rebuilt app, Homes/Experiences/Services, "dimensional" design system.
  - 2025 Winter Release (21 Oct 2025): flexible carousels, improved maps, Reserve Now Pay Later.
  - 2026 Summer Release (20 May 2026): "All" tab, boutique hotels, new homepage, AI review highlights.
  - 2026 fall update (30 Sep 2026): AI search with text and voice, AI filters, AI listing descriptions, AI-powered wishlist comparison, AI support in 50+ languages, connections and travel map.
- **The product has moved on from your brief in several ways.**
  - **Home tabs:** the tab bar is now All / Homes / Hotels / Experiences / Services. Results and listing pages show only Homes / Experiences / Services.
  - **Category icon bar:** gone from the homepage and from search results. Search has a "Filters" button plus amenity quick-filter chips.
  - **Date picker:** two tabs, Dates and Flexible. I saw no "Months" tab on the All tab.
  - **Listing prices:** the card and booking price headline is the total ("¥50,000 JPY for 2 nights"). The booking card has no inline fee rows; the breakdown opens in a popover.
  - **Reserve button:** a 999px pill with a gradient. Secondary buttons are #F2F2F2 with 12px radius.
  - **Secondary text:** #6C6C6C, not #6A6A6A.
  - **Guest favorite caption:** "One of the most loved homes on Airbnb, according to guests" is still live in the banner. The delegated reader reported it as not found; that is wrong.
  - **Engineering blog:** Airbnb engineering moved from Medium to https://airbnb.tech/. airbnb.design redirects to airbnb.com (Wayback, 9 Jan 2026) and returned no usable posts.
- **Mobile search results open map-first** with a draggable bottom sheet, not a list with a "Show map" toggle.
- **Checkout is reachable logged out** at `/book/stays/{id}`, so §7 is measured, not recalled. Steps 2 and 3 are login-gated and unseen.

**Legend**
- **(M)** measured live.
- **(C)** read from Airbnb's CSS variables or CSS bundle.
- **(E)** estimated from a screenshot.
- **(S)** secondary source.
- **⚠** unverified.

**Environment caveats**
- IP was in Japan, so currency, rows and promos reflect that.
- Some features (AI search, Compare) are US-only and were not visible.
- Hover and animation timings were mostly not captured.

---

## Sources

**Primary**
- https://news.airbnb.com/airbnb-2025-summer-release/ (13 May 2025)
- https://news.airbnb.com/product-releases/airbnb-2025-winter-release (21 Oct 2025)
- https://news.airbnb.com/airbnb-2026-summer-release/ (20 May 2026)
- https://news.airbnb.com/airbnb-2026-fall-update (30 Sep 2026)
- Airbnb Help articles, via the delegated reader: 85, 125, 475, 1236, 2143, 3495, 3558, 3598, 3610, 4274, 4280.
- Live airbnb.com pages: `/`, `/rooms/7311241`, `/rooms/1569736908867710237`, `/s/Kamakura--Japan/homes`, `/book/stays/7311241`.
- Airbnb CSS bundle: `a0.muscache.com/airbnb/static/packages/web/common/frontend/core-guest-spa/entrypoints/client.43fa3288d0.css`.

**Secondary**
- Design Week (14 May 2025), with the VP Design interview: https://www.designweek.co.uk/it-was-a-bit-nuts-teo-connor-on-designing-the-new-airbnb-app/
- It's Nice That: https://www.itsnicethat.com/articles/airbnb-app-redesign-140525
- Overmatter: https://www.overmatter.design/blog/the-airbnb-update-when-ui-design-doubles-as-brand-and-business-strategy
- TYPENORM teardown (Sep 2026): https://typenorm.com/articles/airbnb-ux-teardown
- OpenLava spec for the 3D icon format: https://github.com/OpenLavaFormat/OpenLava/blob/main/Docs/format.md
- Airbnb engineering, now at https://airbnb.tech/:
  - Pay as a Local (Feb 2026) lists M-Pesa as a supported method.
  - Flexible Authentication (Aug 2026).

**Design intent (S)**
- ~18 months, ~200 designers.
- "Softer… more curved edges" and "fun, alive, simple."
- Experiences and Services are top-level tabs.
- 3D icons are in-house and animate on press: the balloon emits fire and the bell shakes.
- Itinerary check-in uses an open-door icon and check-out a closed-door icon.

---

## 1. Global header

### Desktop (≥1128px; measured at 1440 → 1425px usable)

| Item | Spec |
|---|---|
| Sticky wrapper | `position: sticky; top: 0; z-index: 100; height: 96px`; inner `<header>` padding `0 48px` (M) |
| Logo | Link box 102×80 at x=48. Colour `logo-brand` #FF385C (M) |
| Tab bar (home only) | `<a role=tab>` ×5: All `/`, Homes `/homes`, Hotels `/hotels`, Experiences `/experiences`, Services `/services`. Tab box 36px tall. Label 14px/20px, 400, #222 (M) |
| Tab icons | `<video muted>` boxes of 72×72 at y=12, positioned inline left of the label. Artwork visible ≈ 36–40px (E). Sources `a0.muscache.com/videos/search-bar-icons/webm/house-selected.webm`, `balloon-selected.webm`, `consierge-selected.webm`, `unified/webm/Globe_Selected_180px_01.webm`, `Hotel_Selected_180px_02.webm`. Not autoplay and paused at rest, so the "selected" clip plays on select (M). Non-selected icons are static 3D PNGs (`search-bar-icons/original/<uuid>.png?im_w=240`, 48px in the compact pill) (M). |
| Selected indicator | Three spans, 3px tall, #222: two 3×3 rounded caps (radius 1.5px) and a 60px bar. It sits at y=74, 8px below the label (M) |
| Unselected labels | The visible label is an `aria-hidden` span at 14/18, 500: #222 when selected, #6C6C6C otherwise. The computed #222/400 text is a visually hidden screen-reader copy (M, re-measured 25 Nov) |
| Icon animation | Press animation per Design Week (S). Hover produced no DOM change in my test ⚠ |
| While search is active | The icons disappear and tabs show text only (M, screenshot) |
| Right cluster | "Become a host": 121×40, radius 20px, 14px/500, transparent. "Log in or sign up": 40×40 circle, bg #F2F2F2. "Main navigation menu": 40×40 circle (M) |
| Icon-button states | 40×40, bg grey200 #F2F2F2, hover grey300 #EBEBEB, active `scale(38/40)`, radius 50% (C) |
| Globe icon | No globe in the header. "Languages & currency" (16px globe) is the first item of the main menu, and the footer has the same buttons ("English (US)", "¥ JPY") (M) |
| Logged-out menu (M) | Order: Languages & currency, Help Center · Become a host ("It's easy to start hosting and earn extra income.", 48px art at right) · Refer a Host, Find a co-host, Gift cards · Log in or sign up (400, not bold). Panel 265px wide, radius 12px, `0 2px 16px rgba(0,0,0,.12)`, padding 12px 0, top ≈3px above the header row's bottom edge. Rows 36px: padding 9px 24px, 14/18 400 #222, 16px icons 10px before the text. Dividers 1px #DDD inset 24px with 8px above and below. Promo row padding 4px 24px: title 14/18 500, text 12/16 #6C6C6C |
| Expanded pill row | Pill at y=102 (6px below the 96px row). The band is 200px, `linear-gradient(#fff 39.9%, #f8f8f8 100%)`, with a hairline at y=200 (M) |
| Collapsed on scroll | The tab bar disappears and a compact pill replaces it: 375.8×46, radius 40px, centred at x≈712, y=25–71. Segments: [48×48 3D icon + "Anywhere"] 141px, "Anytime" 90px, "Add guests" 109px, then a search circle. Each segment is 48px tall (M). A soft bottom shadow appears under the header (E). Transition timing not captured ⚠ (use 250–350ms on `cubic-bezier(.2,0,0,1)`). |
| Results header | Tabs reduce to Homes / Experiences / Services. The compact pill reads "Homes in Kamakura · Jan 8 – 10, 2027 · 2 guests" (M). Total sticky header 152px: 96px row + 54px filter row (M) |
| Listing header | Same 96px row. The compact pill reads "Anywhere / Anytime / Add guests" (M). A fixed 80px white bar with `0 1px 0 rgba(0,0,0,.1)` appears after scrolling past the hero; its contents were not captured ⚠ |
| Checkout header | 80px, logo only (M) |
| Tab layout vs width | At 860 and 1024: icons (36px) stacked above 14px labels, tabs 60px tall at ≈100px pitch, and the right cluster is only the two circles. At 1280–1366: inline icon+label in an 80px row (tabs y=22, indicator y=66, pill y=94, 32px padding), "Become a host" back. From 1440: the 96px row with 48px padding (M). The switch between 1024 and 1280 is presumably the 1128px media query (Airbnb's CSS uses 744/950/1128/1440) |
| "Continue your search" (desktop) | A full-width row under the band: a centred link 86px tall (padding 15px 48px, gap 16px) with a 56px deck of three stacked photos (2px white borders, radius 11–12px, small shadow, two tilted), "Continue your search" 16/20 500, then "Kamakura · Jan 8 – 10, 2027" 16/26 #6C6C6C and a 10px arrow. A 1px #DDD rule sits under it (M) |

### Mobile web (375px)
- **App banner (M):** 83px tall, white, 1px bottom border #E2E2E2. It contains ×, a 40px app-icon tile, "Get the app" (14/18, 500), "The fastest, easiest way to Airbnb", and a blue "USE APP" pill.
- **Search pill (M):** "Start your search" is 312×56 (page padding 24px). Radius 9999px, border 1px #DDD, shadow `0 6px 20px rgba(0,0,0,.1)`, text 14/18 500, magnifier icon.
- **Category chips (M):**
  - All, Homes, Hotels, Experiences, Services, in a horizontally scrolling row.
  - Each chip is 40px tall, radius 40px, padding 10px 14px, gap 8px.
  - Each has a 28×28 3D icon and a 14px/400 label.
  - Each has a layered "pillow" shadow: `0 3px 2.5px rgba(0,0,0,.1), 0 1px 1px rgba(0,0,0,.15), 0 .8px .4px rgba(0,0,0,.15)` plus an inner white highlight.
- **Bottom tab bar (M):**
  - Fixed, white, border-top 1px #EBEBEB, no shadow, ≈65px plus safe-area.
  - Inner row 352×44. Items are 70.4×44: a 24px icon with a 10px/12px label.
  - Active "Explore" is 500 and #DA1249. Inactive items are 400 and #6C6C6C.
  - Logged out the tabs are Explore, Wishlists, Log in. Logged in it is Explore, Wishlists, Trips, Messages, Profile (⚠ visually; the tab names come from the 2025 release).
- **Search sheet (M, screenshot):**
  - Full screen. Icon tabs Homes / Hotels / Experiences / Services (no All), a circular × at top-right, and a blurred pastel gradient backdrop.
  - Stacked cards: "Where?" with a ~54px input and recent/suggested rows with tinted 56px tiles, then collapsed "When — Add dates" and "Who — Add guests" cards, then a gradient Search button.
- **Listing page (M):** no site header. A back button plus Share and Save buttons float over the hero.

---

## 2. Search

### Expanded pill (desktop, M)
- Pill is 850×66 at x=287.5, y=102 (centred).
- Outer container radius 32px; inner layers radius 100px. White fill, border 1px #DDD.
- Shadow `0 0 0 1px rgba(0,0,0,.02), 0 8px 24px rgba(0,0,0,.10)` (elevation 3).
- Segment widths: Where 278.3, When 283.3, Who 278.3.
- Dividers are 1×32 #DDD at x=567.8 and 856.2.
- Left padding is 32px. Label x=319.5 against pill x=287.5.
- Labels (Where, When, Who): 12/16, 500, #222.
- Values: 14/18, 400, #6C6C6C when empty. The input measured 14/18, 500, #222 when filled.
- Search button is a 48×48 circle at 9px top/bottom and 10px right inset. Background is a flat `rausch700` #DA1249 (M), not the old gradient. Icon is 16px.
- When any segment is active the button expands to a 99.7×48 pill (radius 24px) with the icon plus a "Search" label (16/20, 500, white) (M).
- Active state:
  - The bar fills #EBEBEB (radius 100px).
  - The active segment is a white card (radius 32px) with shadow `rgba(0,0,0,.1) 0 3px 12px, rgba(0,0,0,.08) 0 1px 2px`.
  - Inactive-segment hover looks ≈#DDD (E).

### Where panel
- Opens below the pill, ≈425px wide with ≈32px radius, with an internal scroll (E).
- Heading "Suggested destinations". Rows are ≈72px with 56px pastel rounded-square tiles holding line icons, a title (16/20, 500) and a subtitle (14/18, #6C6C6C).
- Live copy: "Nearby — Find what's around you", "Osaka, Japan — For sights like Osaka Castle", "Tokyo, Japan — For its bustling nightlife", "For its stunning architecture", "For nature-lovers", "For a trip abroad", "Near you", "Popular beach destination".
- Mobile also shows "Recent searches: Kamakura · Jan 8 – 10, 2027 · 2 guests" (M).

### Date picker (M, All tab)
- Panel width matches the pill (850px), radius ≈32px, opening at y≈180.
- Segmented control "Dates | Flexible": track 311×44, radius 100px, bg #EBEBEB; selected segment 149.5×36, white, 14/18, 500.
- Two months side by side. Month title 16/20, 500. Weekday header S M T W T F S at 12px/17px, 500, #6C6C6C.
- Day cell is a 51.5×51.5 square. Digits ≈16px/500 (E). Past days #C1C1C1. Prev chevron is disabled at the current month.
- Bottom chips: "Exact dates" (selected, border 1px #222), "± 1 day", "± 2 days", "± 3 days", "± 7 days", "± 14 days".
- Chips are 34px tall, radius 24px, padding 8px 14px, 12/16, border 1px #DDD.
- Listing-page calendar (M) uses the same cells. Header "Select check-in date" with sub-copy "Add your travel dates for exact pricing", and a "Clear dates" button (88×32, radius 8px).
- Day buttons carry labels like "25, Wednesday, November 2026, Today. Unavailable".

### Guest picker (M)
- Four rows at a 91px pitch:
  - Adults ("Ages 13 or above")
  - Children ("Ages 2 – 12")
  - Infants ("Under 2")
  - Pets (link "Bringing a service animal?")
- Title 16/20, 500. Sub-line 14/18, #6C6C6C.
- Steppers are 32×32 circles, bg #F2F2F2 (disabled #C1C1C1). The count sits centred at 16/20, 400.

### AI search (fall 2026, US) ⚠
- A toggle at the top of the search page and a microphone icon in the search bar (Help article 4280).
- Example prompts "beachfront property in Mallorca with a pool" and "I want a hotel or condo to stay in for a week within a 30-minute drive to San Francisco". Help says English and desktop web only (the page may have changed since).
- The newsroom says it works with "your own words or voice with our new search bar". TechCrunch quotes Chesky avoiding a "chatbot-like interface".
- Typing "baby" in filters surfaces cribs, playgrounds, and children's books and toys.
- I could not see the bar's placeholder, position or style.

---

## 3. Home feed (All tab, M)

- **Page padding:** 48px at 1440, giving a 1329px content width. Mobile padding is 24px.
- **Row title:** 20/24, 600, letter-spacing −0.18px, #222. Mobile is 18/24. Some rows add a 28px circular arrow chip after the title. Prev/next circles sit at the row's right end.
- **Arrows:** 28×28 circles, bg #F2F2F2, no border, 4px apart. Disabled uses #C1C1C1 at 0.5 opacity. Aria label: "Previous in Places to stay in Kamakura, showing 1–7 of 9 items".
- **Scroller:** `display: grid` with `grid-auto-flow: column`, column-gap 12px, padding `4px 4px 8px`, `scroll-snap-type: x mandatory`, `scroll-padding-left: 4px`. Its box starts 4px outside the content edge so cards align at 48px.
- **Cards per row at 1440:** 7 for stays and experiences (card 179.56px wide; 7×179.56 + 6×12 = 1329). Destination and category tiles show 10 per row (10 items per page; (1329 − 9×12)/10 ≈ 122px).
- **Row titles seen:**
  - Destinations for you
  - Explore experiences nearby ›
  - Popular experiences in Tokyo
  - Places to stay in Kamakura ›
  - Popular homes in Shibuya ›
  - Stay in Sapporo ›
  - Stay near Mt. Fuji ›
  - Based on your Kamakura search ›
  - Popular homes in Minato-ku ›
  - Great hotels in Paris (subtitle "Plus, get Airbnb credit when you stay at a featured hotel.")
  - "Available in Kyoto this weekend" (section id `HOMES_DESTINATION_WITH_TIME_GROUPINGS:Kyoto:NEXT_WEEKEND`)
- **Category-icon bar:** not present on the home page. Search shows amenity chips (§5).
- **Mobile extras:** a "Continue your search" card (312×110, radius 24px, shadow elevation 3, stacked photo at right) and a floating "Prices include all fees" toast pill.
- **Footer inspiration block:** "Inspiration for future getaways" with tabs Popular, Arts & culture, Beach, Mountains, Outdoors, Things to do, Travel tips & inspiration, Airbnb-friendly apartments (14/18, 500; active #222, inactive #6C6C6C).
- **Footer:**
  - Support: Help Center, Get help with a safety issue, AirCover, Travel insurance, Anti-discrimination, Disability support, Cancellation options, Report neighborhood concern.
  - Hosting: Airbnb your home, hotel, experience, service; AirCover for Hosts; Earnings Protection; Hosting resources; Community Center; Hosting responsibly; Airbnb-friendly apartments; Join a free hosting class; Find a co-host; Refer a host.
  - Airbnb: 2026 Summer Release, Newsroom, Careers, Investors, Gift cards, Airbnb.org emergency stays.
  - Bottom bar: "© 2026 Airbnb, Inc. · Privacy · Terms · Your Privacy Choices", language and currency buttons, and Facebook/Twitter/Instagram.
  - Column headings are 14/18, 500.
- **Skeleton (E, screenshot):**
  - Shapes in #EBEBEB mirror the final layout: 36px circles with pill labels for the tabs, the pill with label blocks, a 162×28 title bar, 180×171 rounded image blocks, and two text bars (128×16 and 85×16).
  - Token `--dls-shimmer-animation-end-color` is `bg-loading-tinted`, black at 8% (C).

---

## 4. Listing card anatomy

### Home-feed card (compact, M)
- Card 179.56×228.6. Radius 20px on the card and image. No shadow, no hover lift (no transform on hover).
- Image 179.56×170.6, which is 20:19 (padding-bottom ≈95%), `object-fit: cover`.
- Heart button 32×32 at top 8 / right 8, holding a 24px icon (SVG viewBox 32).
- Text sits 8px below the image with 4px side padding:
  - Title 13px/16px, 500, #222.
  - Price line 12/16, 400, #6C6C6C: "¥50,000 JPY for 2 nights".
  - The "·" separator is 700, #C1C1C1.
  - Rating "★ 4.89" with an 8px star. On narrow cards it wraps to its own line.
- Experience cards: "Trending" pill, title, "★ 4.94 · 320 ratings", "From ¥15,130 JPY / guest" (E).

### Search-result card (M, 1440)
- Card 303.4×353.5. Image 303.4×227.5, which is 4:3, radius 20px.
- Mobile result card is a 312×380 tile with radius 28px. The image sits inset 8px (296×222).
- **Badges:**
  - "Superhost" is a 95.9×32 pill, radius 16px, bg `rgba(34,34,34,.5)`, `backdrop-filter: blur(16px) saturate(1.6)`, padding 7px 14px, 14/18, 500, white. Position: left 12 / top 14.
  - "Guest favorite" is a white pill with dark text (E). Its data style is `LOUD_ROUNDED_PILL`, `badgeType: GUEST_FAVORITE` (SSR JSON).
  - There is no laurel on cards. The laurels appear on the listing-page banner (§6).
- **Heart:** 32×32 at right 12 / top 12. Path fill `rgba(0,0,0,.5)`, stroke #FFF 2px. Saved state is Rausch fill ⚠.
- **Photo arrows:** 32×32 circles, bg `rgba(255,255,255,.9)`, 12px chevrons, at left 12 and right 12. Transition `transform .25s cubic-bezier(.2,0,0,1)`. Visible on hover.
- **Dots:** active dot is a 16×6 pill (radius 12px, `rgba(255,255,255,.925)`). Inactive dots are 6×6 at `rgba(250,250,250,.72)`, 12px pitch, tapering to 4px at the edges (windowed). They sit ≈17px above the image bottom.
- **Text rows (padding-left 4px, 21px line pitch):**
  1. Title "Hut in Kamakura" at 15/19, 500, #222, with "★ 4.89 (826)" right-aligned at 15/19, 500.
  2. Listing name at 15/19, 500, #6C6C6C, ellipsised.
  3. "1 bedroom · 4 futons · 1 bath" at 15/19, 500, #6C6C6C.
  4. "¥50,000 JPY" at 15px, 500, #222, underlined (a button "Show price breakdown"), then " for 2 nights" at 15/19, 500, #6C6C6C.
  5. Two chips, "Pay ¥0 today" and "Free cancellation". Each is 20px tall, radius 6px, bg `rgba(242,242,242,.75)`, padding 2.5px 4px, 11/15, 500, #6C6C6C.
- **Declared sizes (C):** `--listing-card-content-font-size` is 15px on large and 14px on small; line height is 19px and 18px.
- **Price display:** `displayPriceStyle: TOTAL_ONLY`, `primaryLine { price: "¥118,000 JPY", qualifier: "for 2 nights" }`, `secondaryLine: null` (SSR JSON). Total price is standard worldwide (newsroom, 21 Apr 2025). Taxes are shown before checkout. US guests cannot turn it off (Help 3610).
- **Result pages (M):** a "Prices include all fees" label with a 3D tag icon sits to the right of the results heading (E).

---

## 5. Search results page (desktop M; mobile M)

### Desktop at 1440
- Heading "504 homes in Kamakura": 20/24, 600.
- Filter row (54px): a "Filters" button (83.6×34, radius 24px, border 1px #DDD, sliders icon), a divider, then chips. Chips are 34px tall, radius 24px, border 1px #DDD, white.
- Chip copy: "Free parking", "Guest favorite", "Free cancellation", "Kitchen", "Allows pets", "Self check-in", "Wifi", "TV", "Hair dryer".
- Circular prev/next arrows (50%, border 1px `rgba(0,0,0,.08)`) scroll the row.
- List: two columns of 303.4px cards at x=48 and 375.4 (24px column gap). Row pitch is 393.5px (card 353.5 + 40px).
- Map pane: x=726.8, 650×784, sticky, top 192. A Google map with white price pills ("¥32,270 JPY"). Radius is ≈24px (E).
- Pagination is numbered: Previous, 1 2 3 4 … 15, Next. 18 results per page; aria "Page 1 of 15"; query uses `cursor`.
- Loading state: ten "Fake title" chips plus a loading region. Heading text is "Search results; Over 1,000 stays" until results arrive.
- I could not measure column counts at other breakpoints ⚠. The browser tab degraded after the 1440 pass.

### Mobile (375)
- Map first, full viewport. Header: back arrow, a centred two-line pill ("Homes in Kamakura / Jan 8 – 10, 2027 · 2 guests"), and a sliders filter button. A chip row sits below (Free parking, Allows pets, Free cancellation…).
- A draggable white bottom sheet (rounded top, grip handle) opens with the "Prices include all fees" row, then stacked tile cards. Bottom tab bar stays visible.
- Whether this map-first default is an A/B variant ⚠.

---

## 6. Listing detail page

**Layout (M):** content container 1120px (x=152.5 at 1425). 12-column grid with no gutter: left column 653.3 (7 cols), one empty column, right column 372.3 (4 cols).

**Order (`data-section-id`):**
1. TITLE (84px tall)
2. HERO (560px)
3. NAV (sticky) and BOOK_IT_NAV
4. OVERVIEW
5. GUEST_FAVORITE_BANNER (when applicable)
6. HIGHLIGHTS
7. UGC_TRANSLATION
8. DESCRIPTION
9. SLEEPING_ARRANGEMENT
10. AMENITIES
11. AVAILABILITY_CALENDAR (inline)
12. BOOK_IT_SIDEBAR (right column)
13. REPORT_TO_AIRBNB
14. REVIEWS
15. LOCATION
16. MEET_YOUR_HOST
17. HOST_LEGAL_DETAILS
18. POLICIES
19. SEO_LINKS (breadcrumbs)
20. Footer

On mobile, Location comes before the calendar. Modals are URL-driven (`?modal=PHOTO_TOUR_SCROLLABLE`, `?modal=DESCRIPTION`).

| Module | Measured spec |
|---|---|
| Title row | h1 26/30, 500, up to two lines. Share and Save are text buttons 34px tall, radius 8px, 14/18, 500, 16px icons, right-aligned. A translate icon appears for auto-translated titles. |
| Hero grid | 1120×560 (24px top padding). Large photo 560×536 (50%). Four photos 272×268 / 272×260. Gap 8px. Outer-corner radius ≈12px, per-corner, not found on `img` ancestors via computed style ⚠. Images served at `im_w=1200` (main) and `im_w=720` (small). |
| "Show all photos" | 140×32, radius 8px, bg #F2F2F2, 12/16, 500 plus 16px icon; 24px from the bottom-right corner. |
| Photo tour modal | Full viewport, white, radius 0. Close ✕ at (24,24); Share and Save at right. Title "Photo tour" 22/26, 500. A row of 146.3×96.2 room thumbnails (3:2) with 14/18 labels (Floor plan, Living room, Full kitchen, Dining area, Bedroom, Full bathroom, Backyard, Exterior, Additional photos). Sections per room (22/26, 500), then a sticky "Reserve" button. |
| Overview | H2 "Hut in Kamakura, Japan" is 22/26, 500, letter-spacing −0.44px. US pattern: "Entire condo in Chandler, Arizona, United States". Meta line 16/20, 400: "4 guests · 1 bedroom · 4 futons · 1 bath". Rating line: 8px star, "4.89" 17/20 500, "826 reviews" 16/20 500 (link). |
| Guest favorite banner | Section 653×101. Left: laurel SVGs (22.5×36) around "Guest favorite" (18px, 500) with a caption "One of the most loved homes on Airbnb, according to guests" (16/20, 500). Middle: "4.75" (22/26, 500) over five 10px stars. Right: "8" (22/26, 500) over "Reviews" (12/16, 500). A 1px #DDD divider separates the last two. Help copy: "This home is a guest favorite based on ratings, reviews, and reliability." Threshold (Help 3495 per the reader): ≥5 reviews in the past 4 years with ≥1 in the past 2. |
| Host mini-card | Inside "Listing highlights" ("Hosted by Kensuke — Superhost · 11 years hosting", 40px avatar with a 20px badge). |
| Highlights | AI-generated rows with 36–40px 3D icons, titles 14/20 500, body 14/20 #6C6C6C, 66px pitch, caption "Learn more about summaries" (12/16). Disclaimer: "These summaries were generated with AI, based on reviews and details hosts provide. Please verify important details on the listing or contact the host." |
| Translation bar | "Some info has been automatically translated. Show original" on a grey block. |
| Description | 16/22, 400, clamped. "Show more" is a link `?modal=DESCRIPTION`, rendered as a 132×48 grey button (radius 12px, bg #F2F2F2). |
| Where you'll sleep | Cards 318.7×270 (two per row, 16px gap), radius 8px (image 212px tall). "Bedroom" 16/20 500, "4 futons" 14/18 #6C6C6C. |
| Amenities | Two columns, 24px line icons, 16/20, 400, 48px row pitch. Unavailable items are struck through with "Unavailable:" prefix. Button "Show all 50 amenities" is 208×48, padding 14px 24px, radius 12px, bg #F2F2F2, 16/20, 500, no border. The amenities modal was not opened ⚠. |
| Section titles | 22/26, 500 ("Things to know" measured 600), 48px top padding. Hairline dividers between sections. |
| Booking card | `<aside aria-label="Booking Information">`, 372.3 wide, padding 24px, radius 12px, shadow `0 6px 16px rgba(0,0,0,.12)` with a 1px `rgba(0,0,0,.04)` border; wrapper `position: sticky; top: 80px`. A 372×52 tip card (radius 12px) sits above it: promo ("Get ¥3,000 JPY off your getaway. Terms apply [Claim]") or the animated "Prices include all fees" tip. |
| Booking price line | With dates: "¥50,000 JPY" 22px, 500, underlined (opens "Price details"), then "for 2 nights" 16/20. Without dates: "Add dates for prices" and a "Check availability" button. |
| Booking date box | 324×116. Labels CHECK-IN / CHECKOUT / GUESTS at 10/12, 700, uppercase. Values 14/18, 400 (M/D/YYYY, "2 guests"). Border 1px #8C8C8C; top row radius 12 12 0 0 (57px), bottom row 0 0 12 12 (61px). |
| Pay-later pill | 32px tall, radius 8px, bg #F2F2F2, padding 8px 12px: "¥0 today · Free cancellation before **January 3**" (12/16; date 500). |
| Reserve button | 324×48, radius 999px, padding 14px 24px, `linear-gradient(to right,#E61E4D 0%,#E31C5F 50%,#D70466 100%)`, text 16/20, 500, white. An inner `<span>` carries `radial-gradient(circle,#FF385C 0%,#E61E4D 27.5%,#E31C5F 40%,#D70466 57.5%,#BD1E59 75%,#BD1E59 100%)`. Transitions: `box-shadow .2s`, `transform .25s`, `border-color .3s`, all `cubic-bezier(.2,0,0,1)`. Pointer-tracking is inferred from the DOM ⚠. |
| Under the button | "You won't be charged yet" 14/18, 400, centred. "Report this listing" sits 24px below the card. |
| Price popover | "Price details" 369×148, radius 24px, bg `rgba(255,255,255,.925)`, elevation-4 shadow. Rows 14/18: "2 nights x ¥25,000 JPY — ¥50,000 JPY". Caption "Pay ¥0 today with no extra fees." (12/16, #6C6C6C). |
| Reviews header | "★ 4.89 · 826 reviews" at 26/30, 500. Left: a 5→1 histogram with 10/12 labels. Then six category columns (109px wide, 158px pitch): label 12/16 500 over score 12/16 500. Order: Cleanliness, Accuracy, Check-in, Communication, Location, Value. |
| "Guests mention" | 18/24, 600. Chip carousel: chips 56px tall, radius 16px, border 1px #F2F2F2, 20px icon, label 14/18 500 plus count 14/18 400 #8C8C8C ("Beach 267"). Prev/next are 40×40 grey circles. |
| Review cards | Two columns, 568px pitch. Avatar 48px circle. Name 14/18 500; location and meta 14/18 #6C6C6C ("2 weeks ago · Stayed with kids"). Body 16/24, clamped, "Show more" 16/24 500. "Show all 826 reviews" button is 202×48, radius 12px, bg #F2F2F2. The reviews modal and its search were not opened ⚠. |
| Location | Map, then "Kamakura, Kanagawa Prefecture, Japan" (16/20, 500), description 16/24, "Show more". |
| Meet your host | Card 395×212 with an 88px avatar and a 32px "Identity verified" badge. Name 31.5/36, 600. Stats 22/26, 600 over 10/14, 500 labels. Right column: "Kensuke is a Superhost" 18/24, 500; "Co-hosts"; "Host details" ("Response rate: 100%", "Responds within an hour"); "Message host" button 151×48, radius 12px, bg #F2F2F2. Legal line: "To help protect your payment, always use Airbnb to send money and communicate with hosts." |
| Things to know | Three columns of 309px with 56px gaps. Headings 14/18, 500; body 14/18, #6C6C6C; "Show more" 14/18. Content: check-in and checkout times, House rules, Safety & property, "Free cancellation before January 3". |
| Footer | As in §3. |

**Mobile listing (M, 360 usable width)**
- Hero is full-bleed 360×343 (≈20:19). The photo list is a scroll-snap row of 27 slides.
- A "1 / 27" counter pill (49×22, radius 4px, bg `rgba(34,34,34,.66)`, white 12/500) sits at bottom-right.
- Back, Share and Save are 40px circles.
- A fixed bottom bar is 175px tall (white, border-top 1px #DDD):
  - "¥50,000 JPY" at 16/24, 700, underlined.
  - "For 2 nights · Jan 8 – 10" at 12/16.
  - The pay-later chip.
  - A 312×48 gradient Reserve pill.
  - "You won't be charged yet".
- Secondary grey button: 40px tall, radius 12px, padding 11px 20px, 14/18, 500.

---

## 7. Checkout ("Confirm and pay", desktop M)

- **Header:** 80px, logo only. A 40px circular Back button sits left of the title. The h1 "Confirm and pay" is 32/36, 600.
- **Layout:** 976px container with a 524px main column, 80px gap and a 372px sidebar. Left edge at x=224.5 on 1425.
- **Steps (accordion):**
  1. "1. Choose when to pay" (Step 1 of 3)
  2. "2. Add a payment method" (Step 2 of 3)
  3. "3. Review your reservation" (Step 3 of 3)
  - Headings are 18/24, 600.
  - The active card is 524×268, radius 24px, padding 24px, shadow elevation 2. Inactive cards are 74px tall, radius 20px, border 1px #DDD, no shadow.
- **Step 1 options:** radio rows, 22px circles, a hairline between rows.
  - "Pay ¥50,000 JPY now" (16/20).
  - "Pay ¥0 JPY now — ¥50,000 JPY charged on Dec 26. No extra fees. **More info**" (14/18, #6C6C6C, underlined link at 500; aria "Learn more about Pay Less Up Front").
- **Next button:** 112×48, radius 12px, bg #222, white 16/20, 500. Clicking it logged out opens the login modal.
- **Summary card:** 372×572, radius 24px, border 1px #DDD, padding 24px, no shadow.
  - 96.7px thumbnail, title 18/24 600, "★ 4.89 (826)" and "Superhost" at 12/16 500.
  - Sections separated by hairlines: "Free cancellation" (14/18, 600) / "Cancel before January 3 for a full refund. Full policy"; Dates with a "Change" button (75.9×32, radius 8px, bg #F2F2F2, 12/16 500); Guests ("2 adults") with "Change"; "Price details" (14/18, 600) / "2 nights x ¥25,000 JPY — ¥50,000 JPY"; "Total [JPY] ¥50,000 JPY" (14/18 600, "JPY" is an underlined currency switcher); "Price breakdown" link.
  - Below the card: "Rare find! This place is usually booked" with a 32px icon (14/18, 500).
- **Footer:** "Privacy · Terms · Your Privacy Choices".
- **Login modal (M):** 480×488 centred, radius 32px, white, shadow elevation 3, scrim 30% black. Content: 40px logo mark, h1 "Log in or sign up" (26/30, 600), a 432×55 input (floating label "Phone number or email"), a "Continue" button (432×48, radius 12px, Rausch gradient, 16/20 500), an "or" divider, and 60×60 Google and Apple buttons (radius 12px, border 1px #DDD).
- **Unseen (login-gated):** step 2 payment forms, step 3 review (ground rules, message the host, "Request to book" vs "Confirm and pay") and the confirmation screen ⚠. Help article 85 says Instant Book shows "Confirm and pay" and request-to-book shows "Request to book". The ground-rules copy is reported as "Treat your host's home like your own" and "Follow the host's house rules" (article 2894, by the reader). Airbnb engineering says M-Pesa is supported via redirect, async QR and direct flows (Pay as a Local, Feb 2026).
- **Reserve Now, Pay Later / Pay Part Now, Part Later (Help 2143):**
  - Offered if check-in is ≥14 days away, the stay is under 28 nights, and ≥$50 remains after credits.
  - Experiences and Services are not eligible.
  - A reminder email goes out 3 days before the second charge.
  - A failed second payment gives 72 hours before cancellation.
  - Worldwide since 17 Feb 2026.
- **Cancellation policies (Help 475):** Flexible (full refund until 24h before), Moderate (5 days), Limited (new, for bookings from 1 Oct 2025: 14 days, 50% for 7–14), Firm (30 days, 50% for 7–30), plus Strict, Super strict 30/60, and Long-term Firm/Strict. A 24-hour grace applies if booked ≥7 days before check-in. "Extenuating Circumstances" is now "Major Disruptive Event".

---

## 8. Trips, Wishlists, Messages, Profile, Settings, Help

Everything here is ⚠ unless noted. These screens are login-gated and no accessible source shows pixel layouts.

- **Trips:**
  - An "advanced travel itinerary" with a schedule, home details and booked services and experiences (newsroom).
  - Hour-level timelines and door icons for check-in and check-out (Design Week, S).
  - A shared-itinerary map in the Trips tab (2026 Summer).
  - Host phone, address, check-in method and house manual appear once booked (Help 4116 and 4192, by the reader).
  - Receipts are labelled "Get receipt" under Payment info. Reservation actions include "Cancel reservation".
- **Wishlists:**
  - Logged-out page (M): "Wishlists — Log in to view your wishlists — You can create, view, or edit wishlists once you've logged in. [Log in]".
  - Behaviour from Help (reader): 100 listings per list, collaborators vote and add notes, "Share as view only", an auto "From your connections" list.
  - Compare ("Compare places to stay", Help 4274): needs ≥2 saved homes; up to 16 listings. Rows: "What stands out", "Reviews", "Location", "Map", "Amenities and other details". Disclaimer "Remember, AI can make mistakes…". US home listings only.
  - I found no "Recently viewed" collection in Help.
- **Messages (Help 3558):**
  - Default "All" with quick filters Hosting, Support, Traveling.
  - Sections "Priority", "Recent", "Past conversations".
  - Dec 2025 added category filters Homes, Experiences, Services, Traveling, Support, Direct Messages, and a "Details" button for the reservation panel.
  - Edit for 15 minutes, unsend for 24 hours, reactions and threaded replies.
- **Profile:** 2025 profile shows stats such as "24 trips, 22 reviews, 8 years on Airbnb", a Connections list ("Cory — 3 trips together") with passport-stamp icons, and from Sep 2026 a travel map based on connections.
- **Account settings (Help 280, reader):** Personal information, Login and security, Privacy and sharing, Notifications, Payments and payouts, Translation, Taxes, Professional hosting tools, Accessibility. There is no "Global preferences" or "Travel for work" card. Layout is unverified.
- **Help Center home (reader, logged out 25 Nov 2026):** "Hi, how can we help?" with a search input ("Search how-tos and more"), "Log in or sign up", a "We're here for you" card, "Guides for getting started", "Top articles", "Explore more", "Need to get in touch? [Contact us]". Role tabs Guest / Home host / Experience host / Service host / Travel admin; body 14px/1.43; container ≈1176px (reader).

---

## 9. Design language and tokens

### Colour (C, from `:root` custom properties, 25 Nov 2026)

| Token | Value |
|---|---|
| Rausch (brand, logo) | #FF385C; `rausch100`–`900` = #FFF5F6, #FFEEF0, #FEE5E7, #FFD2D7, #FFABB6, #FF385C, #DA1249, #A21039, #732139 |
| `product-rausch` | #E00B41 |
| Search button, `text-brand`, `border-brand` | #DA1249 |
| Rausch gradient | `linear-gradient(to right,#E61E4D 0%,#E31C5F 50%,#D70466 100%)` |
| Radial hover gradient | `radial-gradient(circle at center,#FF385C 0%,#E61E4D 27.5%,#E31C5F 40%,#D70466 57.5%,#BD1E59 75%,#BD1E59 100%)` |
| Text | primary #222222; secondary #6C6C6C (legacy `foggy` #6A6A6A); tertiary #8C8C8C; quaternary #515151; placeholder #8C8C8C; disabled #C1C1C1 |
| Link / legal | #0D4DAA |
| Status | error #C13515; invalid #D7251C; success #038026; warning #EB6100 |
| Greys | #FFF, #F7F7F7, #F2F2F2, #EBEBEB, #DDDDDD, #C1C1C1, #8C8C8C, #6C6C6C, #515151, #3F3F3F, #222, #000 (`grey0`–`1100`) |
| Surfaces | `bg-secondary` #F7F7F7; `bg-interactive` #F2F2F2; `bg-tertiary` #EBEBEB; `bg-loading` #EBEBEB; tooltip #111111 |
| Beige (warm modal) | #F7F6F2, #F4F2EC, #EEEBE5, #DFDCD6; dark button #232221 |
| Borders | `border-primary` #222; `border-secondary` and `border-tertiary` #DDD; `bg-divider` #EBEBEB |
| Overlays | scrim primary 30% black, secondary 20%; pagination dots on media white 60% |

### Type
- **Font stack (C):** `"Airbnb Cereal VF", Circular, -apple-system, BlinkMacSystemFont, Roboto, "Helvetica Neue", sans-serif`. Weights 400/500/600/700.
- **Scale (C):** body 11/15, 12/16, 14/18, 16/20, 18/24. Paragraph 14/20, 16/22, 16/24, 18/28. Title-medium (500): 14/18, 16/20, 18/24. Title-semibold (600): 14/18, 16/20, 18/24, 22/26, 26/30, 32/36. Display (600): 40/44, 48/54, 60/68, 72/74. Wide tracking 0.04em.
- **In use (M):** row titles 20/24 600 (mobile 18/24), ls −0.18px; card titles 13/16 500 (compact) and 15/19 500 (search); listing h1 26/30 500; section titles 22/26 500; body 16/20, 16/22, 16/24; captions 12/16; booking labels 10/12 700 uppercase; checkout h1 32/36 600.

### Closest free fonts (measured proxy; ⚠ judgement for letterforms)
I measured average advance-width ratio against Cereal at 500 weight and 16px (four UI strings; Cereal measured in-browser via canvas, candidates via PIL without kerning). x-height and cap-height are per em; Cereal ≈ 0.53 and 0.72.

| Font | Width ratio | x-height / cap |
|---|---|---|
| Manrope | 0.997 | 0.54 / 0.72 |
| Instrument Sans | 1.001 | 0.51 / 0.72 |
| Outfit | 0.988 | 0.48 / 0.70 |
| Albert Sans | 1.014 | 0.50 / 0.70 |
| Figtree | 1.015 | 0.50 / 0.70 |
| Inter | 1.024 | 0.546 / 0.728 |
| Plus Jakarta Sans | 1.030 | 0.539 / 0.745 |
| DM Sans | 1.031 | 0.526 / 0.70 |
| Geist | 1.032 | 0.532 / 0.71 |
| Nunito Sans | 0.966 | 0.487 / 0.705 |
| Onest | 1.051 | not recorded |
| Sora | 1.105 | not recorded |

**Recommendation:**
1. **Manrope** for the closest metrics, so wrapping and truncation match.
2. **Figtree** for the most Cereal-like friendly geometry. Raise the size about 3% to offset its lower x-height.
3. Keep **Plus Jakarta Sans** (the project's current font) if brand continuity matters. Use `letter-spacing: -0.01em` to cancel its +3% width.
4. **Inter** is the neutral fallback.

### Radii (C and M)
- 4, 8, 12, 16, 20, 24, 28, 32px tokens.
- In use: card and image 20px; mobile result tile 28px; booking card 12px; checkout steps 24 / 20px; summary card 24px; login modal 32px; price popover 24px; promo dialog 16px; photo-tour modal 0; Reserve 999px; grey secondary button 12px; small text buttons 8px; chips 24px (desktop) and 40px (mobile); search pill 32 / 100px; badge 14–16px; hero outer corners ≈12px ⚠.

### Elevation (C; corrected alpha)
- **E1:** `0 0 0 1px rgba(0,0,0,.02), 0 2px 4px rgba(0,0,0,.16)`
- **E2:** `0 0 0 1px rgba(0,0,0,.02), 0 2px 6px rgba(0,0,0,.04), 0 4px 8px rgba(0,0,0,.10)`
- **E3 (search pill, login modal, mobile cards):** `0 0 0 1px rgba(0,0,0,.02), 0 8px 24px rgba(0,0,0,.10)`
- **E4:** `0 0 0 1px rgba(0,0,0,.02), 0 4px 8px rgba(0,0,0,.08), 0 12px 30px rgba(0,0,0,.18)`
- **E5:** `0 0 0 1px rgba(0,0,0,.02), 0 6px 8px rgba(0,0,0,.08), 0 16px 56px rgba(0,0,0,.18)`
- **Legacy:** primary `0 6px 20px rgba(0,0,0,.2)`; secondary `0 6px 16px rgba(0,0,0,.12)` (booking card); tertiary `0 2px 4px rgba(0,0,0,.18)`; high `0 8px 28px rgba(0,0,0,.28)`.
- E0 is `0 0 0 1px #DDD inset`. Brand glow is `0 2px 2px rgba(205,13,75,.2)`.

### Spacing, widths, breakpoints
- **Micro scale (C):** 2, 4, 8, 12, 16, 24, 32px. **Macro scale (C):** 16, 24, 32, 40, 48, 64, 80px.
- **Widths (M):** page padding 48px (desktop) and 24px (mobile). Listing container 1120px. Checkout 976px. Search pill 850px.
- **Breakpoints (C):** `min-width` queries 550, 744, 950, 1128, 1440, 1760, 2120 (rule counts, reader's spot check).

### Motion (C)
- **Curves:** standard `cubic-bezier(.2,0,0,1)`; enter `cubic-bezier(.1,.9,.2,1)`; exit `cubic-bezier(.4,0,1,1)`; "next" standard `cubic-bezier(.4,0,.2,1)`; "next" enter `cubic-bezier(0,0,0,1)`; plus linear.
- **Spring tokens** (via CSS `linear()` easing): snappy ≈294ms; fast ≈452ms; standard ≈584ms; slow and gentle ≈746ms. Bounce variants are 264–1421ms.
- **Mobile slide-up (M):** `--slide-up-from-bottom` 667ms with a spring easing, from y=100% and opacity 0.
- **Interaction timings (M):** photo arrows `transform .25s`; Reserve `box-shadow .2s`, `transform .25s`, `border-color .3s`.

### Other conventions
- **Iconography:** 24px line icons; heart is a 32-grid SVG shown at 24px (fill `rgba(0,0,0,.5)`, stroke #FFF 2px). Amenity-icon stroke weight not captured ⚠.
- **3D icons and illustration:** icons are in-house 3D renders (Airbnb's "Lava" format on apps (S); transparent WebM on web (M)). Do not reuse Airbnb's assets (the OpenLava README warns against it). Destination and category tiles are pastel rounded squares with line art. Highlight icons are 3D emoji-style.
- **Focus rings:** the arrow buttons carry a layered `box-shadow` with transparent 1px and 4px rings, activated on `:focus-visible` ⚠ (colours not captured).
- **Accessibility strings (M):** "Skip to content", tablist semantics, "Previous in {title}, showing 1–7 of 9 items", "Rated 4.89 out of 5 stars", day buttons with full dates and status, "Search results pagination".
- **Skeletons:** see §3.
- **Toasts:** "Prices include all fees" is a `region` with marquee text; on desktop a 372×52 white pill with elevation 2; on mobile a floating pill above the tab bar (E).
- **First-visit modal (M):** "Now you'll see one price for your trip, all fees included. [Got it]" on a warm beige surface (#F4F2EC range) with a 3D pink tag icon and a #232221 button.
- **Promo modal (M):** "Get ¥3,000 JPY off your getaway / For new guests in selected countries only. Terms apply / [Log in to claim offer]".

### Tailwind v4 starter (values as measured)

```css
@theme {
  --font-sans: "Manrope", system-ui, sans-serif;
  --color-rausch: #FF385C;
  --color-rausch-700: #DA1249;
  --color-ink: #222222;
  --color-ink-2: #6C6C6C;
  --color-ink-3: #8C8C8C;
  --color-line: #DDDDDD;
  --color-line-2: #EBEBEB;
  --color-fill: #F2F2F2;
  --color-fill-2: #F7F7F7;
  --color-link: #0D4DAA;
  --color-error: #C13515;
  --radius-sm: 8px;  --radius-md: 12px;  --radius-xl: 20px;  --radius-2xl: 24px;  --radius-3xl: 32px;
  --shadow-search: 0 0 0 1px rgb(0 0 0/.02), 0 8px 24px rgb(0 0 0/.10);
  --shadow-booking: 0 6px 16px rgb(0 0 0/.12);
  --ease-standard: cubic-bezier(.2,0,0,1);
  --ease-enter: cubic-bezier(.1,.9,.2,1);
  --ease-exit: cubic-bezier(.4,0,1,1);
}
```

---

## 10. Microcopy conventions (all M unless noted)

- Sentence case everywhere. Short imperative buttons: "Reserve", "Show more", "Show all 50 amenities", "Show all 826 reviews", "Message host", "Show original", "Clear dates", "Next", "Continue", "Got it", "Claim".
- **Money:** price first, qualifier after: "¥50,000 JPY for 2 nights". No tax or fee rows in the headline; "Prices include all fees"; "Pay ¥0 today"; "Free cancellation before January 3".
- **Booking:** "You won't be charged yet"; "Add dates for prices"; "Check availability"; "Rare find! This place is usually booked".
- **Badges:** "Guest favorite" (with the "One of the most loved homes on Airbnb, according to guests" caption), "Superhost", "Trending".
- **Ratings:** "★ 4.89 (826)" on cards; "4.89 · 826 reviews" on listings; aria "Rated 4.89 out of 5 stars."
- **Overview:** "{Type} in {City}, {Country}" with "4 guests · 1 bedroom · 4 futons · 1 bath".
- **Search:** "Where / Search destinations", "When / Add dates", "Who / Add guests", "Start your search". Result count: "504 homes in Kamakura".
- **Hosts:** "Hosted by Kensuke — Superhost · 11 years hosting".
- **Legal and safety:** "To help protect your payment, always use Airbnb to send money and communicate with hosts."
- **Wishlist empty state:** "Log in to view your wishlists".
- **Strings no longer seen live:** "Show receipt" (now "Get receipt"); a "Display total price" toggle.

---

## Top 30 details to replicate (most impact first)

| # | Detail | Implementation note (basis) |
|---|---|---|
| 1 | Borderless listing cards with rounded images | Image radius 20px, no shadow, no hover lift. Home rows 20:19 (`aspect-ratio: 20/19`); search results 4:3 (M). |
| 2 | Total-price-first display | "KES X for N nights", underlined price in 15px 500, qualifier in #6C6C6C; no fee rows on the card (M). |
| 3 | Search pill geometry | 850×66, radius 32px, border 1px #DDD, shadow E3, 1×32 #DDD dividers, labels 12/16 500, values 14/18 (M). |
| 4 | Pill collapse on scroll | Header stays 96px; tabs hide; compact pill 376×46, radius 40px, 48px segments (M). Animate over ≈250–350ms ⚠. |
| 5 | Listing booking card | 372px (4 of 12 cols), `sticky top:80px`, padding 24px, radius 12px, shadow `0 6px 16px rgba(0,0,0,.12)` (M). |
| 6 | Reserve pill | 48px, radius 999px, linear gradient plus a radial overlay span that tracks the pointer (M; tracking ⚠). |
| 7 | Hero grid | 1120×560 with 8px gaps: 50% large photo plus a 2×2 of 272px photos; grey "Show all photos" button 140×32, radius 8px (M). |
| 8 | 1120px listing container on a 12-col grid | Left 7 cols, empty 1 col, right 4 cols (M). |
| 9 | Type system | Cereal-like font; section titles 22/26 500; body 16/20–16/22; captions 12/16 (M). Use Manrope or Figtree. |
| 10 | Colour tokens | #222, #6C6C6C, #DDD, #F2F2F2, Rausch #FF385C (search button #DA1249) (C). |
| 11 | Home rows | 7-up at 1440, 12px gap, snap-x mandatory, 28px grey arrows top-right, title 20/24 600 (M). |
| 12 | Header tabs | Five tabs with 72px icon slots and a 3px #222 underline; icons vanish when search is active (M). Make your own icons. |
| 13 | Mobile entry points | 56px "Start your search" pill, 40px pillow chips, 3- or 5-tab bottom bar with Rausch-active "Explore" (M). |
| 14 | Mobile listing | Full-bleed 20:19 hero with 40px overlay buttons and a "1 / N" counter; fixed 175px bottom bar with a 312×48 Reserve (M). |
| 15 | Secondary button | bg #F2F2F2, radius 12px, 48px tall, padding 14px 24px for "Show more / Show all / Message host"; radius 8px for small text buttons (M). |
| 16 | Checkout | 3-step accordion; active card radius 24px (E2), inactive 20px with 1px #DDD; 372px summary card; black "Next" 48px radius 12px (M). |
| 17 | Date picker | "Dates | Flexible" segmented control; two months; 51.5px cells; ±1/2/3/7/14-day chips of 34px (M). |
| 18 | Guest picker | Four steppers (Adults, Children, Infants, Pets), 32px grey circles, 91px row pitch (M). |
| 19 | Loading states | #EBEBEB skeletons mirroring the final layout; shimmer to 8% black (C/E). |
| 20 | Review summary | Histogram plus six category columns plus "Guests mention" chips (56px, radius 16px); two-column review cards (M). |
| 21 | Guest favorite banner | Three zones: laurel plus title and caption, rating with stars, review count; 1px #DDD divider (M). |
| 22 | Photo dots | Windowed: 16×6 active pill, 6px dots tapering to 4px, `rgba(250,250,250,.72)` (M). |
| 23 | Badges | Superhost dark glass (`blur(16px) saturate(1.6)`); Guest favorite white pill (M/E). |
| 24 | Pay-later cues | Grey pill "¥0 today · Free cancellation before {date}" on the booking card, mini chips on cards, "Pay ¥0 JPY now" in checkout (M). |
| 25 | Mobile search sheet | Full-screen, icon tabs, stacked "Where? / When / Who" cards, 54px input (M/E). |
| 26 | Mobile results | Map-first with a draggable bottom sheet; tile cards radius 28px with an 8px image inset (M). |
| 27 | Elevation and modals | E3 for pills and modals, E4 for popovers, scrim 30% black, login modal radius 32px (C/M). |
| 28 | Motion | Standard `cubic-bezier(.2,0,0,1)` at 200–300ms; springs for overlays; mobile slide-up ≈667ms (C). |
| 29 | URL-driven modals and numbered pagination | `?modal=PHOTO_TOUR_SCROLLABLE` and `?modal=DESCRIPTION`; 18 results per page (M). |
| 30 | Microcopy | Sentence case; "Reserve", "You won't be charged yet", "Prices include all fees", "Free cancellation before {date}" (M). |

---

## Gaps and uncertainties

- Tab-icon hover and press animations and header collapse timing were not captured. The tab-layout switch lies between 1024px (stacked) and 1280px (inline).
- I could not open the amenities modal, the reviews modal (with search) or the logged-in account menu. The logged-out main menu is measured in §1.
- Checkout steps 2 and 3, the booking confirmation screen, Trips, Messages, Profile, account settings and the AI search bar are not measured. The reader found no accessible pixel-level sources for them; Mobbin, Page Flows, Refero and Medium were gated or JS-only.
- Search-results column counts at other breakpoints are not captured.
- Hero outer-corner radius is estimated; per-corner clipping is not visible in computed style.
- US-only features (AI search, AI filters, Compare, AI listing descriptions) could not be observed from Japan.
- Hotels-in-results behaviour is described only by TYPENORM (S); the "All" tab may vary by region or experiment.
- **Legal note:** match layout, spacing and behaviour, but do not copy Airbnb's logo, Cereal font files, 3D icon animations or imagery.

---

## How Amina Stays applies this

The patterns, scale, spacing and interactions above were rebuilt under Amina's own brand. Rausch, the Bélo logo, Cereal and Airbnb's 3D assets were not copied: Amina keeps its name, sail-and-wave mark and coral. Where Airbnb's mechanics don't fit a direct-booking host in Mombasa, the adaptation is noted.

| Airbnb pattern | Amina Stays implementation |
|---|---|
| Tokens: #222 / #6C6C6C / #8C8C8C / #C1C1C1, #DDD/#EBEBEB hairlines, #F2F2F2 fills, weights ≤600, E2/E3 shadows | `frontend/src/app/globals.css` (`ink`, `ink-2`, `ink-3`, `ink-disabled`, `line`, `line-soft`, `chip`; `shadow-badge` = E2, `shadow-search` = E3; `font-bold` mapped to 600) |
| Buttons: 8px radius at 32px, 12px at 40–56px, pill primary, #F2F2F2 secondary, press shrink | `ui/button.tsx` (radius per size, brand pill via `compoundVariants`, `soft` = #F2F2F2) |
| Font: Cereal | **Figtree**, the report's #2 pick, chosen for the closest friendly geometry. Manrope matches metrics more closely; changing the font is a one-line edit in `app/layout.tsx`. |
| 3D tab and highlight icons | Microsoft Fluent Emoji 3D (MIT) via `ui/icon3d.tsx`; laurels drawn in SVG |
| Header: All / Homes / Hotels / Experiences / Services tabs (stacked below 1128px, 96px row from 1440px), collapse into compact pill, expanding search over a scrim, flat deeper-brand search button | `site/header.tsx`, `site/search-bar.tsx`. "All" (`/`) mixes homes with Amina's experiences and services; "Homes" (`/homes`) adds tag rows. Amina has no hotels, so "Hotels" (`/hotels`, `site/hotels-view.tsx`) gathers the serviced apartments and studios with the hotel-style services (breakfast, mid-stay cleaning, pickups, early/late times). |
| Main menu: 265px panel, 36px rows, 16px icons, inset #DDD dividers, promo row with 48px art | `UserMenu` in `site/header.tsx`. "Book without data" (USSD, SMS, voice) takes the "Become a host" slot. |
| "Continue your search" row with a photo deck | `ContinueSearch` in `site/home-view.tsx`. The last search submitted from the header is kept in this browser (`useLastSearch`), and dates that have passed are dropped. |
| Languages & currency (menu item and footer buttons) | `site/locale.tsx`. Currency is a display preference (KES, USD, EUR, GBP at the rates in `/api/config`) for cards, map pins, extras and the listing's headline price; guests always pay in KES, so checkout and trips stay in shillings. Language is the guest's language for Amina's texts and WhatsApps, saved to their account; the website itself is English. |
| Where / When / Who panels | Same structure. When adds quick ranges (this/next weekend, 1–2 weeks) instead of ± flexibility, because the search API takes exact dates. Who has no Pets row, because most homes don't allow pets. |
| Mobile: "Start your search" pill, pillow chips, full-screen search sheet, bottom bar with brand-coloured Explore | `MobileSearch`, `MobileTabs`, `MobileTabBar` |
| Home rows: 7-up at 1440, 6-up from 1128, 10 destination tiles, 28px grey arrows, 20:19 cards | `site/carousel.tsx`, `site/home-view.tsx` (Destinations, Popular, Available this weekend, Experiences & services) |
| Search results: filter chips, Filters modal, 4:3 cards with 15/19 500 text, grey perk chips, price pills on a sticky map | `site/search-view.tsx`, `site/maps.tsx`. Chips include Free cancellation and Guest favourite (API `?free_cancellation=1`, `?guest_favourite=1`). Mobile keeps the list-first layout with a Map button rather than the map-first sheet, which the report flags as a possible A/B test. |
| Listing anatomy: 1+4 hero, photo tour by room, Guest-favourite banner, 3D highlights, 12px secondary buttons, 48px section rhythm, reviews histogram plus "Guests mention" | `site/listing-view.tsx` |
| Booking card: total-first, "Price details" popover, pay-later pill, Reserve pill, "You won't be charged yet", tip card | `BookingCard`, `PriceDetails`, `TipCard`. The pill reads "KES {30% deposit} today · Free cancellation before {date}", since Amina takes a deposit rather than KES 0. |
| Mobile listing: 20:19 full-bleed hero, "1 / N" counter, 40px floating buttons, bottom reserve bar | `PhotoCarousel counter`, `MobileReserveBar` |
| Checkout: logo-only header, numbered accordion (active radius 24 + E2; inactive radius 20 + hairline), 372px summary card with "Change" buttons and free-cancellation line | `site/checkout-view.tsx`. Steps are Log in → When to pay → Make it yours (extras) → Guest details (the guest register Kenyan law requires) → Pay with M-Pesa or card. |
| Account hub of cards; Trips list | `site/account-view.tsx`, `site/trips-view.tsx` |
