# Africa's Talking (AT) capabilities and limits for Amina Stays: SMS, USSD, Voice, Payments, Airtime, newer products, Python SDK, callbacks, simulator

Research date: 2026-11-25. Several answers change for a Django/Python 3.14 backend. In particular, I recommend a thin REST client over the SDK.

**Source key**
- **D:x** = `https://developers.africastalking.com/docs/x`. The site is a JS SPA behind Cloudflare, so I read its backing JSON (`…/content/api/v1/files/tree` lists the 54 current pages; `…/files/file?name=x.md` gives each page verbatim).
- **HC:n** = `https://help.africastalking.com/en/articles/n`.
- **PRICE** = `https://africastalking.com/pricing`.
- **PyPI** = `https://pypi.org/project/africastalking/` plus wheel contents, cited as `File.py:line`.
- **GH:py** = `github.com/AfricasTalkingLtd/africastalking-python`.
- **GH:node** = `github.com/AfricasTalkingLtd/africastalking-node.js`.
- **P** = my unauthenticated DNS/HTTP probes today.
- **RUN** = I executed the SDK wheel on Python 3.14.4 with HTTP mocked.
- `github/get_me` was not exposed in this environment, so I skipped it.

## Headline findings
- **Payments is gone from AT's public surface.**
  - The 54-page docs tree has no `payments/` section, and `payments/mobile/checkout.md` returns 404 (P).
  - `africastalking.com/payments` returns 404, and the homepage products are SMS, Airtime, USSD, Voice, Mobile Data, WhatsApp (`https://africastalking.com/`).
  - Both SDKs dropped it (see Python SDK and Node sections below).
  - M-Pesa checkout survives only as an onboarding-gated service (see Payments).
- **The sandbox has no new bulk SMS route.** `api.sandbox…/version1/messaging/bulk` returns 404 (P), while live returns 400 "missing username" (P).
- **There is no usable Voice sandbox.** `voice.sandbox.africastalking.com` has no DNS record (P).
- **WhatsApp is "Preview"** and needs Meta verification plus fees.
- **No webhook signatures or AT source-IP list are documented.**

## 1. SMS
- **Legacy send** (form POST):
  - Live: `https://api.africastalking.com/version1/messaging`. Sandbox: `https://api.sandbox.africastalking.com/version1/messaging`.
  - Fields: `username`, `to` (comma-separated), `message`, `from` (optional, defaults to AFRICASTKNG), `bulkSMSMode` (must be 1 for bulk), `enqueue`, `keyword`, `linkId`, `retryDurationInHours` [D:sms/sending/bulk_(legacy)].
- **New JSON bulk:**
  - Live: `https://api.africastalking.com/version1/messaging/bulk`. Fields: `username`, `phoneNumbers[]`, `message`, `senderId` (marked required), `enqueue` (default 1).
  - Sandbox is "coming soon" and returns 404 [D:sms/sending/bulk][P]. The Node SDK has a TODO for the same reason (`GH:node lib/sms.js:90-92`).
- **Hashed Safaricom numbers:** same bulk endpoint with `maskedNumber`, `telco`, `phoneNumbers: []` [D:sms/sending/bulk].
- **Premium:** Live `https://content.africastalking.com/version1/messaging`; sandbox uses the api.sandbox host. Adds `from` (required), `keyword`, `linkId`, `retryDurationInHours`, `requestId` [D:sms/sending/premium].
- **Fetch inbox:** `GET /version1/messaging?username&lastReceivedId`, 100 messages per call. Callbacks are preferred [D:sms/fetch_messages].
- **Send response:**
  - `statusCode` values: 100/101/102, 401 RiskHold, 402 InvalidSenderId, 403, 404, 405, 406 UserInBlacklist, 407, 409, 500–502.
  - Each recipient has `number`, `cost` (e.g. "KES 0.8000"), `messageId`.
  - 101 "Sent" is not delivered [D:sms/sending/bulk][HC:16150386].
- **Incoming-message callback** (form-encoded): `date`, `from`, `id`, `linkId` (optional), `text`, `to`, `cost`, `networkCode`.
  - Kenya network codes: 63902 Safaricom, 63903 Airtel, 63907 Orange, 63999 Equitel; 99999 = sandbox [D:sms/notifications].
- **Delivery-report callback:**
  - Fields: `id`, `status`, `phoneNumber`, `networkCode`, `failureReason` (only for Rejected/Failed), `retryCount` (premium only).
  - `status` values: Sent, Submitted, Buffered, Rejected (final), Success (final), Failed (final), AbsentSubscriber, Expired.
  - `failureReason` values: InsufficientCredit, InvalidLinkId, UserIsInactive, UserInBlackList, UserAccountSuspended, NotNetworkSubcriber (sic), UserNotSubscribedToProduct, UserDoesNotExist, DeliveryFailure, DoNotDisturbRejection (Nigeria only) [D:sms/notifications].
- **Opt-out:**
  - A "Bulk SMS Opt Out" callback sends `senderId` and `phoneNumber`. Opt-out instructions are auto-appended to the first message sent to a subscriber [D:sms/notifications].
  - Blocked recipients return 406 or `UserInBlackList`. A Safaricom user re-enables via `*456*9#` → 5 → 5 (secondary: `https://community.africastalking.com/forum/help-18238/topic/at-help-comprehensive-94/`).
  - I found no API to list or manage bulk opt-outs (UNVERIFIED negative).
  - Premium subscription callback fields: `phoneNumber`, `shortCode`, `keyword`, `updateType` (addition|deletion).
  - The Node SDK has create/fetch/delete at `content…/version1/subscription/{create,delete}` and GET `/subscription` (`GH:node lib/sms.js:218-354`). Those pages are no longer in the docs tree.
  - Safaricom consent/header-enrichment endpoints: `/version1/subscription/safaricom/{consent,token}` [D:sms/premium_subscriptions/consent_gateway].
- **Encoding:**
  - GSM-7 gives 160 characters. One non-GSM character drops it to 70 per segment. AT calls this "GSM 8-bit"; technically it is UCS-2.
  - The extension characters `^{}\[~]|€` count as 2 [HC:2964644].
  - The 153/67 concatenation sizes are not in AT docs (3GPP general knowledge, UNVERIFIED here). A maximum recipient count per request is also undocumented.
- **Sender IDs (Kenya):**
  - At most 11 characters, no spaces, not generic, with trademark or registration proof and an authorisation letter. They start as promotional; moving to transactional takes about 2 days [HC:407085][HC:12381163].
  - Default-sender test SMS works only on Airtel Kenya numbers [D:sms/overview]. Safaricom needs a registered ID.
  - Safaricom IDs are raised before 12:30 on Mondays and Thursdays only [HC:2206521].
  - Table from a community mirror (secondary): Safaricom 2 working days, Airtel 5, Telkom 2, Equitel 7–14.
- **Shortcodes and keywords:**
  - A shared shortcode with keyword types (toll-free, premium-rated, standard-rated) goes through order form, invoice, keyword confirmation, testing, activation [HC:11087337].
  - The 2019 price was KES 5,000 setup plus 2,000/month plus VAT (stale) [HC:1139328].
- **Kenya bulk SMS price per SMS (2025 rate card PDF [HC:12381163]):**

| Monthly spend (KES) | Safaricom | Airtel and other Kenyan telcos |
|---|---|---|
| 0–19,999 | 0.8 | 0.8 |
| 20,000–99,999 | 0.7 | 0.8 |
| 100,000–399,999 | 0.6 | 0.7 |
| 400,000+ | 0.4 | 0.6 |

  - Sender ID setup: Safaricom-only 8,700, Airtel-only 8,700, bundled 14,100, Telkom 4,500, Equitel 9,000. The PDF says "VAT exclusive", while HC:407085 says 7,500 + 16% VAT = 8,700, so this is ambiguous.

## 2. USSD
- **Callback** (form-encoded POST): `sessionId`, `serviceCode`, `phoneNumber`, `networkCode`, `text` (empty on the first hit, then inputs joined with `*`) [D:ussd/handle_sessions].
- **Reply rules:**
  - Reply `text/plain` starting `CON ` or `END `.
  - A 40x or a reply without CON/END makes AT end the session. Avoid special characters.
  - AT expects a response within 10 seconds [D:ussd/overview].
  - The optional response header `at-ussd-hop-metadata` is at most 99 characters with no `|`, and shows in dashboard session details.
- **Length and timeouts** (Help Center, March 2020, dated):
  - Menu limit: Safaricom 160, Airtel 184 characters; telcos auto-paginate with "98:More 00:Back". User input limit: 80 / 90 [HC:1284096].
  - Session: 180 s total. Safaricom and Equitel time out if the user takes more than 30 s to reply. Airtel's limits are 15 s app response, 10 s connect, 60 s user response [HC:1284071].
  - The "182 chars" figure is not in AT sources.
- **End-of-session Events URL callback:**
  - Fields: `date` (UTC), `sessionId`, `serviceCode`, `networkCode`, `phoneNumber`, `status` (Incomplete|Success|Failed), `cost`, `durationInMillis`, `hopsCount`, `hopsMetadata`, `input`, `lastAppResponse`, `errorMessage` [D:ussd/notifications][HC:9915125].
- **Shared vs dedicated:**
  - Shared codes are `*384*channel#` (Safaricom postpaid) and `*483*channel#` or `*789*…#` (prepaid). Dedicated codes are 2XX/4XX/8XX [HC:1162965].
  - A shared code is raised "immediate" on Safaricom, Airtel and Telkom [HC:8165894].
  - Dedicated lead time (community mirror, secondary): Safaricom 3–4 weeks, Airtel 2 weeks, Equitel 3 weeks.
- **Pricing [PRICE]:**
  - Shared: free setup, maintenance KES 10k–40k/month depending on channel length.
  - Prepaid per session: KES 1 (user) + 0.25 (AT), KES 5,000 deposit.
  - Safaricom postpaid: KES 1.5 down to 1.25, KES 10,000 deposit.
  - Dedicated Safaricom: setup 145,000, test bed 17,400, monthly 58–70k.

## 3. Voice
- **Callback fields:**
  - All requests: `isActive` (1, then 0 on the final), `sessionId`, `direction`, `callerNumber`, `destinationNumber`, `callerCountryCode`, `callStartTime`.
  - Conditional: `dtmfDigits` (after GetDigits), `recordingUrl`.
  - Final notification only: `durationInSeconds`, `currencyCode`, `amount`, `callSessionState`, `dialDestinationNumber`, `dialDurationInSeconds`, `dialStartTime`, `hangupCause`.
  - `hangupCause` values: NORMAL_CLEARING, CALL_REJECTED, NORMAL_TEMPORARY_FAILURE, RECOVERY_ON_TIMER_EXPIRE, ORIGINATOR_CANCEL, LOSE_RACE, USER_BUSY, NO_ANSWER, NO_USER_RESPONSE, SUBSCRIBER_ABSENT, SERVICE_UNAVAILABLE, USER_NOT_REGISTERED, UNALLOCATED_NUMBER, UNSPECIFIED [D:voice/notifications][D:voice/handle_calls].
  - The final notification needs no XML reply.
  - `clientRequestId` is only described as "sent to your Events Callback URL" [D:voice/make_call]. I could not confirm the exact callback field name (UNVERIFIED).
- **Outbound call:**
  - `POST https://voice.africastalking.com/call` (form or multipart): `username`, `from`, `to` (comma-separated), `clientRequestId`.
  - Response `entries[{phoneNumber, status, sessionId}]`. Status values: Queued, InvalidPhoneNumber, DestinationNotSupported, InsufficientCredit. Header `X-Current-Queue-Size`.
  - Also `/callTransfer` (`sessionId`, `phoneNumber`, `callLeg`, `holdMusicUrl`), `/queueStatus`, `/mediaUpload` [D:voice/call_transfer][GH:node lib/voice.js:104-209].
- **XML actions** [D:voice/actions/*]:
  - **Say:** `voice`, `playBeep`; supports SSML.
  - **Play:** `url` (required).
  - **GetDigits:** `callbackUrl`, `numDigits`, `timeout` (30), `finishOnKey`. If the caller gives no input it moves to the next action silently.
  - **Dial:** `phoneNumbers` (required), `record`, `sequential`, `callerId`, `ringbackTone`, `maxDuration`.
  - **Record:** `finishOnKey`, `maxLength`, `timeout` (3600), `trimSilence`, `playBeep`, `callbackUrl`. Terminal `<Record/>` takes no attributes and returns an mp3 URL.
  - **Enqueue:** `name`, `holdMusic`, `maxQueueTime`. **Dequeue:** `phoneNumber` (required), `name`.
  - **Conference:** `maxParticipants` (max 50), `record`, `beep`, `startOnEnter`, `endOnExit`, `waitUrl`, `muted`, `flags`, `statusEvents`, `statusEventsCallbackUrl`; plus a REST room API (mute, unmute, tmute, play).
  - **Redirect:** URL as element text. **Reject:** must be the only element.
- **TTS:** Google Cloud TTS voices (e.g. `en-US-Standard-C`, `en-US-Wavenet-C`) and `voice="swahili"` for Kiswahili [D:voice/actions/say].
- **Sandbox:** none usable (P; `GH:node` commit `7ef091eaaa` "Undoing voice tests, due to lack of voice sandbox"). The Help Center and a community post still mention a voice sandbox URL, which conflicts with the DNS result.
- **WebRTC:**
  - `POST https://webrtc.africastalking.com/capability-token/request` (`apiKey` header; body `username`, `clientName`, `phoneNumber`, `incoming`, `outgoing`, `expire` default 86400) [D:voice/webRTC_client/usage].
  - Browser library `africastalking-client`: npm latest 1.0.8 (2026-09-23); docs cite CDN 1.0.5.
  - A browser call makes AT POST to your callback with `clientDialedNumber`.
- **Kenya Voice pricing (2025 PDF [HC:12318754]):**
  - Numbers: KES 5,000 setup + 2,000/month, plus VAT.
  - Per minute: inbound 0.50, outbound 2.50, SIP out 0.25, conference 0.50. The PDF also lists Google TTS Standard, Wavenet and Chirp 3 rates.
  - Live numbers require KYC.

## 4. Payments
- **Status:**
  - Mobile checkout still routes: `payments.africastalking.com/mobile/checkout/request` returns 400 "missing 'username'" (P).
  - B2C, B2B, bank and card routes return 404 (P). `payments.sandbox…` has no DNS (P).
  - A Help Center article dated 2026-09-24 says to activate mobile checkout on your own paybill by filling the LNM form, emailing API Support, and sharing Safaricom Daraja Go-Live consumer key and secret with AT [HC:2295507].
  - So it is by-request, not self-serve, and undocumented. Not feasible for a 27 Nov demo.
  - `D:authentication` still links to the deleted payments page.
- **Historical endpoints and fields** (last SDK with Payment, Python 1.2.7 `Payment.py:65-394`):
  - `/mobile/checkout/request`: `username`, `productName`, `phoneNumber`, `currencyCode`, `amount`, `metadata`, `providerChannel?`.
  - `/mobile/b2c/request` (`recipients[]`), `/mobile/b2b/request`, `/bank/checkout/charge|validate`, `/card/checkout/charge|validate`, `/bank/transfer`, `/query/transaction/find|fetch`, `/query/wallet/balance|fetch`.
  - Callback fields (category, status, transactionId, value, providerRefId, requestMetadata, clientAccount…) are UNVERIFIED: the docs are deleted and my Wayback attempt hit 429.
- **AT recommendation:** none found. The practical alternative is integrating Safaricom Daraja directly (not researched here).

## 5. Airtime
- **Send:** `POST https://api.africastalking.com/version1/airtime/send` (sandbox: api.sandbox host).
  - Fields: `username`, `recipients[{phoneNumber, amount:"KES 100"}]` (max 1,000), `maxNumRetry` (default window 8 h, retries every 60 s), `requestMetadata` (string map).
  - Response: `numSent`, `totalAmount`, `totalDiscount`, `responses[{phoneNumber, amount, discount, status Sent|Failed, requestId, errorMessage}]`.
  - Kenya limits: min KES 5; max 10,000 (Safaricom, Airtel, Telkom) or 5,000 (Equitel, JTL).
  - Similar requests within 5 minutes are rejected unless you send an `Idempotency-Key` header. Limit: 500 simultaneous connections per IP, no per-second limit [D:airtime/sending][D:idempotent_requests].
- **Status callback:** `phoneNumber`, `description`, `status` (Success|Failed), `requestId`, `discount`, `value` [D:airtime/notifications/status].
- **Validation callback** (optional): `transactionId`, `phoneNumber`, `sourceIpAddress`, `currencyCode`, `amount`. Reply `{"status":"Validated"|"Failed"}` [D:airtime/notifications/validation].
- **Find:** `GET https://api.africastalking.com/query/transaction/find?username&transactionId` (live only) returns Queued|Sent|Success|Failed [D:airtime/query/find_transaction_status].

## 6. Newer products
- **WhatsApp ("Preview"):**
  - `POST https://chat.africastalking.com/whatsapp/message/send` with `username`, `waNumber`, `phoneNumber`, `body`.
  - `body` is one of: text, media (Image|Video|Audio|Sticker|Document|Voice), interactive list or buttons, or template (`templateId`, `headerValue`, `bodyValues`).
  - Response: `messageId`, `status` (SENT|DELIVERED|FAILED|READ|DELETED). Sandbox is "coming soon" (chat.sandbox has no DNS) [D:whatsapp/send_message][P].
  - Template creation exists [D:whatsapp/create_template]. Inbound and status webhook payloads are not publicly documented (UNVERIFIED).
  - Onboarding (March 2026): verified Meta Business, a dedicated number, USD 85 setup plus USD 50/month, up to 96 h verification [HC:12381100].
  - Per message in the rest of Africa: marketing USD 0.032, utility 0.008, authentication 0.008, service 0.002 (`https://africastalking.com/chat/whatsapp`).
  - "AT Chat" is this product (`GH:node lib/common.js`, `CHAT_URL=https://chat.africastalking.com`).
- **Mobile Data:**
  - `POST https://bundles.africastalking.com/mobile/data/request` (sandbox bundles.sandbox resolves): `username`, `productName`, `recipients[{phoneNumber, quantity, unit MB|GB, validity Day|Week|BiWeek|Month|Quarterly, metadata}]`. Response `entries[{…, status Queued, transactionId, value}]`.
  - `GET /query/transaction/find` and `/query/wallet/balance`; validation and status callbacks [D:data/sending].
  - The doc's curl sample uses "Monthly", which contradicts its own field list.
- **Insights ("Preview"):**
  - SIM swap: `POST https://insights.africastalking.com/v1/sim-swap` (sandbox host resolves, routes untested). Body: `username`, `phoneNumbers[]`.
  - Per-number status: Queued|Swapped|NoSwapDate|Failed|InvalidPhoneNumber|UnsupportedPhoneNumber|InsufficientBalance. Sample cost KES 1.
  - Async callback: `status`, `lastSimSwapDate`, `providerRefId`, `requestId`, `transactionId` [D:insights/simswap][D:insights/notifications/status].
- **CAMARA / GSMA Open Gateway / Number Verification:** no AT docs page, SDK module or announcement found (searches plus org code grep). Treat as not offered (UNVERIFIED negative). AT's SIM swap is proprietary, not CAMARA-shaped.
- **Balance:** `GET /version1/user?username` returns `UserData.balance` [D:application].

## 7. SDKs and REST

**Python SDK (`africastalking` on PyPI)**
- **Version and history:**
  - Latest 2.0.3 (2026-07-31). Releases: 1.2.7 (2023-11-07), 1.2.8 (2024-07-10), 1.2.9 (2024-10-04), 2.0 (2025-08-25), 2.0.1, 2.0.2 (2026-01-08), 2.0.3 [PyPI].
  - `requires_python >=3.8`, no Python classifiers. Dependencies: `requests>=2.30`, `schema>=0.6.7`, `responses>=0.25.8` (a test-mocking library, never imported).
- **Services:** SMS, Airtime, Voice, Application, Token, MobileData, Insights, Whatsapp. USSD is commented out (`__init__.py:1-30`).
- **Payments:** present through 1.2.7, removed in GH:py commit `1f5d934b1e` (2023-11-07), first absent in 1.2.8.
- **Python 3.12–3.14 compatibility (RUN, 3.14.4):**
  - All 10 files compile with zero warnings. No removed stdlib imports.
  - Imports and initialises with the real `schema` 0.7.8.
  - `requests` 2.34.2 lists Python 3.10–3.15 [PyPI]. `schema` classifiers stop at 3.11 but it ran fine. `responses` classifiers stop at 3.13.
  - Real `pip install` on 3.14 was not tested (no pip here). Django 6.1.3 supports 3.12–3.15 [PyPI].
- **Defects found in 2.0.3:**
  - `Voice.call` has no `clientRequestId` (`Voice.py:15-37`); a string `callTo` raises ValueError (`Voice.py:16`) (RUN).
  - `Airtime.send` stores `Idempotency-Key` on a shared headers dict (`Airtime.py:90`). In my run the next call without a key re-sent the old key (RUN). `requestMetadata` is not exposed.
  - `SMS.send` uses the legacy form endpoint with `bulkSMSMode=1` (`SMS.py:28-34`). `send_hashed` is broken: open issue #76 and PR #77 (`SMS.py:182-189`).
  - `Whatsapp.send_template` builds `https://chat.africastalking.comwhatsapp/template/send` (`Whatsapp.py:181`) (RUN).
  - Sync `requests` only; the `callback` argument spawns raw threads (`Service.py:178`); timeout (3.05, 9.05) s (`Service.py:8`); hard-coded User-Agent "2.0.0" (`Service.py:66`).
  - JSON is parsed only if the content-type equals exactly `application/json` (`Service.py:152,164`). Non-2xx raises with the body text only; the status code is lost (`Service.py:157`).
  - Phone regex requires a leading `+` (`Service.py:22-24`). Data validity allows only Day/Week/Month (`Service.py:35-37`).
- **Recommendation:** call REST directly. Each endpoint is a single POST, and the SDK adds mostly validation plus the defects above. Use `requests` (explicit 3.14 classifier) or `httpx` (0.28.1 classifiers stop at 3.12; 3.14 untested by me). Pass `Idempotency-Key`, `clientRequestId`, the new bulk JSON and hashed-number bodies yourself.

**Node SDK (for reference):** latest 0.8.4 (2026-10-09). Modules: SMS, TOKEN, VOICE, AIRTIME, INSIGHTS, WHATSAPP, MOBILE_DATA, APPLICATION, plus a USSD helper (`GH:node lib/index.js:5-44`). Payments was removed in 0.6.4 (2023-11-09; checked across every npm tarball; last commit `aa3e6518cc`).

**Exact base URLs** (the SDK treats `username == "sandbox"` as sandbox mode, `Service.py:75`)

| Product | Live | Sandbox |
|---|---|---|
| SMS (legacy) | `https://api.africastalking.com/version1/messaging` | `https://api.sandbox.africastalking.com/version1/messaging` |
| SMS bulk JSON | `https://api.africastalking.com/version1/messaging/bulk` | none (404) |
| Premium SMS | `https://content.africastalking.com/version1/messaging` | api.sandbox host |
| Voice call | `https://voice.africastalking.com/call` | none (SDK builds `voice.sandbox…`, no DNS) |
| Airtime | `https://api.africastalking.com/version1/airtime/send` | `https://api.sandbox.africastalking.com/version1/airtime/send` |
| Mobile Data | `https://bundles.africastalking.com/mobile/data/request` | bundles.sandbox host |
| SIM swap | `https://insights.africastalking.com/v1/sim-swap` | insights.sandbox host |
| WhatsApp | `https://chat.africastalking.com/whatsapp/message/send` | none |
| Payments (legacy) | `https://payments.africastalking.com/mobile/checkout/request` (undocumented) | none |

## 8. Callback security
- **No signing or IP allowlist is documented.**
  - Auth is the `apiKey` header plus username; a new key invalidates the old one [D:authentication].
  - `D:notifications` mentions no signature. My grep of `org:AfricasTalkingLtd` for whitelist/allowlist/hmac/signature found nothing.
  - The Help Center only says to ask your host to whitelist "our IP address" on a 403 and publishes no list [HC:2219978, 2018].
  - UNVERIFIED that AT never signs; ask techsupport@africastalking.com for IP ranges.
- **Practices:**
  - Use a secret path token per callback (`/cb/<random>/sms`) over HTTPS.
  - Match `id` / `sessionId` / `requestId` against what you sent.
  - Handle callbacks idempotently.
  - Keep keys server-side.
  - Airtime validation can approve or deny a transaction, but `sourceIpAddress` there is your caller's IP, not AT's.

## 9. Simulator and sandbox
- **Setup:** the sandbox app (`https://account.africastalking.com/apps/sandbox`) uses username `sandbox`. You create free shortcodes, USSD channels, voice numbers, airtime and payments resources, then interact with them in `https://simulator.africastalking.com:1517/` rather than on a handset [HC:1170660].
- **Callbacks:** your callback must be publicly reachable (the article suggests ngrok). Register numbers in separate browser sessions to simulate several users, and check server logs and the dashboard inbox.
- **Sandbox facts:** the network code is 99999, balance is N/A [D:sms/notifications], and Voice has no API sandbox (P).
- **Third-party claims, UNVERIFIED:** channels dialed as `*384*<channel>#`, and a cap of two USSD channels.
- **Inferred, not documented:** callback payloads match live shapes.

## Gotchas and recommendations for a hackathon demo
1. **Lead times kill live setups.**
   - Today is 25 Nov and the event is 27 Nov. The Safaricom sender ID cut-off is Mon/Thu 12:30 (today is Wednesday).
   - A live voice number needs KYC. WhatsApp needs up to 96 h plus USD 135. Dedicated USSD takes weeks. Demo on sandbox and simulator, and mock WhatsApp, Voice and Payments.
2. **AT's own hackathon pages list eligible products:** USSD, Voice, Airtime, Insights, Bulk SMS, Premium SMS, Mobile Data. WhatsApp and Payments are absent. These are Nigeria events (`https://community.africastalking.com/events/`); confirm the rules for yours.
3. **Use the legacy `/version1/messaging` endpoint in sandbox.** Go live on the bulk JSON endpoint only with real credentials.
4. **Voice demo:** POST sample callbacks (`isActive`, `sessionId`, `callerNumber`, `dtmfDigits`) to your own XML endpoint, since there is no sandbox. Return `application/xml` with HTTP 200.
5. **Django callback wiring:**
   - Exempt callback views from CSRF.
   - Read form-encoded `request.POST`.
   - Return `text/plain` for USSD within 10 s.
   - Add the ngrok host to `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`.
   - Keep USSD menus at 160 characters or fewer for Safaricom.
6. **Treat 101 as accepted, not delivered.** Drive guest-facing status from the delivery report (Success, Failed, Buffered, Expired, AbsentSubscriber).
7. **Keep SMS GSM-7 clean.** Smart quotes or emoji force 70-character segments and extra cost (about KES 0.8 per segment).
8. **Always send a unique `Idempotency-Key` per airtime request.** Otherwise similar airtime within 5 minutes is blocked.
9. **For Safaricom hashed numbers, bypass the SDK** and send `phoneNumbers: []` in the JSON body yourself.
10. **Payments:** don't plan on AT STK push. Mock it, or use Daraja directly with your own credentials.

**Unverified items:**
- Payment callback payloads.
- WhatsApp webhooks.
- `clientRequestId` field name on voice callbacks.
- Maximum recipients per SMS request.
- Multipart segment sizes at AT.
- `pip install` on 3.14.
- httpx on 3.14.
- CAMARA / Number Verification (assumed not offered).
