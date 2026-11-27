# 08 · End-to-end flows: industry gap analysis

> Research brief produced while verifying that every Amina Stays flow works end to end
> (web, USSD, SMS, voice, host console). It compares our flows with Airbnb, Hospitable and
> Hostaway, M-Pesa Daraja and Paystack behaviour, Africa's Talking edge cases and Kenyan
> compliance, and ranks the gaps MUST / SHOULD / NICE. Repo citations use the
> paths that were current when the brief was written. See the "What we built" section (just before the sources)
> for what was implemented from this brief.

## Summary

I checked the brief against the repo (about 15 files) and ran web research on platform docs, Daraja/Paystack, Africa's Talking (AT) and Kenyan rules. The payments and channel layers are already robust:
- Settlement is idempotent.
- A payment that arrives after its hold has lapsed is reinstated or marked refund_due.
- Pending STK pushes are reconciled by STK Query.
- Delivery reports, opt-outs and voice end-of-call are all handled.

The gaps that matter for a Kenyan direct-booking demo are:
1. Change and extend a booking with a price delta. This is entirely missing; SMS `EXTEND` only pings the host.
2. Web "notify me" waitlist. The backend exists; the web entry point doesn't.
3. Balance-payment failure handling. The reminder exists, but nothing happens after it.
4. M-Pesa failure mapping. Only 5 result codes are mapped, and there is no Paybill/Till fallback.
5. Special offer, deposit and damage claim, and a tax-invoice view.

I also found three production risks: the USSD request calls Daraja synchronously, card payments are never reconciled, and a guest's STOP can blacklist transactional SMS.

Confidence on sources:
- Airbnb and Hospitable help pages, Paystack and the Tourism Fund homepage were retrieved from primary pages or search snippets of them.
- Safaricom's Daraja docs and AT's docs are JavaScript apps that wouldn't render. I used AT Help Centre snippets and Safaricom's Reversal page, plus secondary Daraja summaries, and marked each use.
- Kenyan tax and TRA claims come mainly from secondary sources and are flagged.

Repo cites below are `backend/apps/<path>:<lines>` in David-0chieng/Amina_stays; `frontend/src/...` is the frontend.

---

## 0. Verified in code (corrections and risks)

- **M-Pesa failure map:** `FAILURE_TEXT` maps only 1032, 1037, 2001, 1 and 1025. These are fragments pushed into the SMS `payment_failed` template, and only for non-web channels (`payments/services.py:30-36`, `:228-241`).
- **Settlement is already strong:**
  - Duplicate callbacks are no-ops, and a late success reinstates the booking or marks it `refund_due` (`payments/services.py:134-226`).
  - A 60-second dedupe stops double STK pushes (`:65-76`).
  - A manual path records cash and bank payments (`:304-316`).
  - `reconcile_pending` runs STK Query after 2 minutes and expires after 30, **M-Pesa only** (`:318-331`).
- **Card payments are never reconciled:** `PaystackCard.query()` returns `None` (`payments/providers.py:235-236`).
- **Paystack webhook (`payments/views.py:94-111`):**
  - It verifies the legacy `x-paystack-signature` header and handles only `charge.success`.
  - It doesn't call Verify Transaction.
  - It doesn't check currency.
- **Daraja callback (`payments/views.py:68-91`):** it is authenticated only by a URL secret that reuses `AT_WEBHOOK_SECRET` and falls back to `"cb"`. If the secret is empty, `_secret_ok` passes everything (`:23-26`), so set it in production.
- **Refunds:** real refunds are queued for Amina to send by hand (`payments/services.py:244-301`).
- **Paybill/Till and C2B:** there is no C2B Paybill/Till support, no `registerurl`, and no "I've paid, here's my code" flow.
- **USSD and payment:**
  - `ussd.py:340-342` and `:406-409` call `start_remote_payment` synchronously inside the USSD request.
  - Inside that call, Daraja token and push use `httpx` timeouts of 15 and 20 seconds (`payments/providers.py:68-132`).
  - AT's Help Centre gives Airtel a 15-second application-response timeout.
- **USSD session events:** `ussd_events` only logs (`comms/views.py:117-120`).
- **SMS dispatch (`messaging/services.py:221-300`):**
  - Any status code other than 100/101/102 becomes `failed` and is not retried.
  - Only network exceptions are retried, up to 3 attempts.
  - The delivery-report map covers Success, Failed, Rejected, AbsentSubscriber and Expired.
  - There is no handling for 406 UserInBlacklist, no fallback channel, and no SLA timer for critical messages.
- **Voice:** `call_ended` handles inbound calls where the host isn't reached (`comms/voice.py:465-505`). Outbound failures are not handled: the welcome call, and SOS calls to Amina that go unanswered (`:424-445`).
- **Reservation change:** there is no change or alter endpoint in `bookings/views.py`. "Change dates" exists only before booking (`frontend/src/components/site/checkout-view.tsx:278`).
- **Extend by SMS:** it only checks availability and notifies the host (`comms/smsbot.py:363-377`).
- **Waitlist (web):**
  - The backend exists at `bookings/services.py:693-762`, and `waitlist_offer` is at `messaging/templates_default.py:175`.
  - The website shows only "Change dates" when dates are taken (`frontend/src/components/site/listing-view.tsx:572`).
- **Balance reminder (`messaging/automations.py:107-141`):** it fires STK and an SMS. Code release is blocked while unpaid (`bookings/services.py:579`). There is no follow-up ladder, no deadline enforcement and no "overdue" list.
- **Manual host booking:** `_host_create` offers payment none, cash, mpesa or card for the **full** `b.total` only, with no deposit plan or price override (`bookings/views.py:304-345`).
- **CSV exports:** only two exist, the guest register and the TRA return (`safety/views.py:98-100`, `insights/views.py:80-82`). The ledger has none (`payments/views.py:161`).
- **Compliance already modelled:** levy and VAT lines (`properties/services.py:182-190`, `bookings/serializers.py:48-51`), `kra_pin` and `vat_registered` (`core/models.py:32,41`), and a levy reminder saying "due by the 10th" (`core/scheduler.py:124-135`). The 10th matches the Tourism Fund secondary sources below.

---

## (a) Flow gap table

| # | Flow | Best-in-class reference | Ours | Priority |
|---|---|---|---|---|
| G1 | Change dates/guests after booking, with price delta | Airbnb: guest or host proposes a change, the new total is shown, the original method is charged or refunded, and a change unpaid within 48 h auto-declines; max 3 changes/day, 10/reservation (help 50, 1363) | **Missing** | **MUST** (lite) |
| G2 | Extend stay | Same primitive as G1 | **Partial**: SMS `EXTEND` pings the host only | **MUST** |
| G3 | Request-to-book vs instant book | Airbnb: host replies in 24 h, charge only on accept; Instant Book falls back to a request if booked within 2 days and arriving outside the check-in window (help 85) | **Missing**: stays are always instant-hold; only add-ons have `requires_approval` (`bookings/models.py:215`) | NICE |
| G4 | Waitlist / "notify me" on web | I found no primary doc for Airbnb or Booking.com; treat as a differentiator | **Partial**: SMS, USSD and voice only | **MUST** (cheap) |
| G5 | Co-guests / share itinerary | Airbnb group-reservation invite: invitees see the reservation, group messages and, for homes, address and check-in instructions (help 1175) | **Partial**: ID register for adults only | NICE |
| G6 | Receipt → tax invoice (eTIMS) | KRA eTIMS tax invoices (secondary sources) | **Partial**: receipt only; no invoice number, buyer PIN, credit note or eTIMS status | SHOULD |
| G7 | Balance failure / pay-later edge | Airbnb: notify, 72 h to pay, then cancel per policy (help 3783). Hospitable: booking stays pending, guest retries via portal, link expires, auto-cancel; hosts can't retry or see the failure reason | **Partial** | **MUST** (lite) |
| G8 | Message host before booking | Airbnb (help 85) | **Present** (`frontend/src/components/host/biz/messaging-kb.tsx:256`) | – |
| G9 | Check-in instructions / house manual | Airbnb: code 48 h before, details on Trips page (help 41) | **Present** (`frontend/src/components/site/trip-view.tsx:346-352`); guidebook is partial | NICE |
| G10 | Security deposit / damage | See H4 and the guidance below | **Missing** | SHOULD |
| G11 | M-Pesa failure UX | Table (b) | **Partial** (5 codes) | **MUST** |
| G12 | Paybill/Till fallback + "I've paid" code | C2B URLs, below | **Missing** | SHOULD |
| G13 | Card verify + reconcile | Paystack verify + webhook | **Partial** | SHOULD (MUST before live) |
| G14 | Automated refunds | Reversal API / B2C / Paystack refund | **Partial**: manual queue | NICE for demo |
| H1 | Special offer / custom quote | Airbnb special offer and pre-approval; price is recalculated on later changes (help 50). Hostaway "sending a quote" | **Missing** | SHOULD |
| H2 | Manual booking with deposit / custom price | Hostaway payment link | **Partial** | SHOULD (small) |
| H3 | Host-initiated change request | Airbnb | **Missing** (same as G1) | SHOULD |
| H4 | Damage claim with evidence | Airbnb: file within 14 days of checkout, guest has 24 h to respond, then escalate (help 279). Hospitable: separate deposit collected about 2 days before check-in, failed authorizations auto-released (help 14803560) | **Missing** | SHOULD |
| H5 | Cleaning checklist with photos | Hostaway checklist templates and mobile app | **Partial**: checklist JSON, no photos (`operations/models.py:53`, `operations/services.py:20-33`) | NICE (SHOULD with H4) |
| H6 | Maintenance tickets | – | **Partial**: type exists, auto-created from issues (`operations/services.py:188`); no cost or vendor | NICE |
| H7 | Payout / accounting export | Hostaway owner statements and accounting sync (third-party summary) | **Partial** | SHOULD (30 min) |
| H8 | Host reviews guest / do-not-rent | – | **Partial** (CRM, not confirmed) | NICE |
| H9 | Block/unblock with reasons | – | **Present** (`properties/models.py:293`) | – |
| H10 | Bulk pricing across homes | – | Unverified | NICE |
| C1 | Tourism levy calc + reminder | Tourism Fund eLevy portal | **Present** | – |
| C2 | TRA licence renewal reminder | Licences expire 31 Dec; renew at least 2 months ahead (secondary) | **Missing** | SHOULD (cheap) |
| C3 | Data-subject request log and SLA | 7-day response (see below) | **Partial**: export and erase exist, no register | NICE |

### Implementation guidance (MUST/SHOULD)

**G1, G2, H3: `ReservationChange`.**
- **Model.** `ReservationChange(booking, kind: extend|shorten|move|guests, requested_by, new_check_in/out, new_adults/children, old_total, new_total, delta, status: pending_host|pending_payment|accepted|declined|expired, expires_at=+48h, payment)`.
- **Pricing and locking.** Price with `properties/services.py:quote` (`:120`) and re-total with the existing helper at `bookings/services.py:425-437`. Lock dates through the same exclusion-constraint path as holds.
- **Payment.** If delta > 0, call `start_payment(amount=delta, purpose="change")` and branch on that purpose in `on_success`. If delta < 0, call `refund()` using `refund_quote` (`bookings/services.py:467`). If zero, apply it immediately.
- **API.** `GET/POST /api/bookings/<ref>/changes` and host accept/decline, reusing the request cards at `bookings/views.py:410`.
- **UI.** A "Change or extend" button in the trip hub, a date picker, a price-diff card, then "Send request".
- **Messages.** `change_requested` (host "reply YES/NO"), `change_accepted` (with STK or link), `change_declined`, `change_expired`, plus SMS `CHANGE`/`EXTEND n` completing the loop.
- **Side effects.** Shift the housekeeping task, code window and iCal.
- **Demo cut.** Ship extend and shorten first.

**G4: web waitlist.**
- Add `POST /api/waitlist` (OTP-authenticated) that calls `add_to_waitlist` (`bookings/services.py:696`).
- Show "Notify me if these dates open" where the listing is `taken` (`listing-view.tsx:572`) and on zero-result searches.
- Show an "On waitlist" chip in the account.
- Make the offer SMS carry a deep link `/book/<slug>?ci=&co=&offer=<token>` with a 30–60 minute soft hold.
- Demo path: cancel a booking in the host console, and the waitlisted phone gets the SMS.

**G7: balance ladder.**
- Add `Booking.balance_due_on` (the context already derives it, `bookings/services.py:103`) and a daily `balance_dunning` job:
  - **T0:** STK + SMS (exists).
  - **+1 day:** SMS with card/Paybill link.
  - **+2 days:** "pay within 72 h or the booking cancels under {policy}" (Airbnb's 72-hour rule).
  - **Then:** an Alert "Balance overdue" with one-tap Extend 24 h / Cancel under policy / Waive, plus an optional `auto_cancel_unpaid` toggle.
- Send at most one auto STK per 24 hours. Code release is already blocked while unpaid.
- Add a red "Balance overdue" banner in the trip hub.

**G11: M-Pesa failure UX.**
- Replace `FAILURE_TEXT` with `MPESA_RESULT = {code: {reason, retryable, action, msg_key}}` and add `Payment.failure_code`.
- Wait screen:
  - 0 s: "check your phone".
  - 30 s: Resend / Card / Paybill.
  - 90 s: server STK Query.
  - 3 min: "still checking, don't pay twice".
- On code 1, offer to switch to the 30% deposit.
- Reuse the open Payment on 1001 or a synchronous `500.001.1001`, and raise the dedupe window.
- Add `payment_failed_<code>` templates in 5 languages.

**H1, H2: Offer.**
- **Model.** `Offer(token, unit, dates, guests, nightly_override|discount_pct|total_override, deposit_pct, expires_at, status, note, booking)`.
- **UI.** "Send offer" from the reservation detail, the inbox thread or a calendar selection, with a preview that recalculates levy and VAT.
- **Delivery.** SMS and WhatsApp link `/o/<token>`.
- **Checkout.** The guest lands on a pre-filled checkout with a "Special offer from Amina, valid until…" banner and locked pricing.
- **Manual booking.** Extend `_host_create` (`bookings/views.py:304`) with `payment_plan`, `deposit_pct` and `price_override`+`reason`.

**G10, H4, H5: deposit and damage.**
- M-Pesa can't pre-authorize a hold, so pick one of three options:
  - **(1) Refundable deposit.** Collect by STK about 48 h before arrival, as Hospitable does, and refund via the queue after inspection.
  - **(2) Non-refundable damage waiver.** An add-on; the cheapest to build.
  - **(3) Cash at the door.** Record it with `record_manual_payment`.
- **Model.** `DamageClaim(booking, amount, description, photos[], status, due_by=checkout+14d)`.
- **Inspection.** Add an Inspection step with photo upload on the turnover task.
- **Claim flow.** The SMS reads "KES X for <item>, reply AGREE/DISPUTE within 72 h". It then deducts from the deposit via `refund(deposit − claim)` or via `request-payment`.
- **Demo cut.** Waiver add-on + claim form + refund-queue entry.

**G6 (+C3): tax invoice.**
- **Model.** `Invoice(number sequential, seller_pin=SiteSettings.kra_pin, buyer_name, buyer_pin?, lines incl. VAT and levy, etims_status: not_submitted|pending|synced|failed, etims_invoice_no)`.
- **Output.** Issue it on payment, and issue a credit note on refund. Provide a printable view at `/trips/<ref>/invoice` and a "sales register" CSV.
- **Positioning.** Label it "eTIMS-ready"; don't claim live integration. Keep `vat_registered` host-configurable, because sources disagree on the VAT threshold (see compliance notes).

**G12: Paybill/Till fallback.**
- Add `/api/payments/daraja/c2b/{validation,confirmation}/<secret>` and call `POST /mpesa/c2b/v1/registerurl`.
- Use the booking ref as the account number, normalised (upper-case, spaces and hyphens stripped).
- Validation can reject with `C2B00012` (invalid account) and `C2B00013` (invalid amount), per a Laravel Daraja guide. Check whether external validation is enabled for your shortcode.
- The payloads carry `TransID`, `TransTime`, `TransAmount`, `BusinessShortCode`, `BillRefNumber`, `MSISDN`.
- On confirmation, make `TransID` unique, create `Payment(provider="c2b")` and call `on_success`. Unmatched payments go to a host "Unmatched payments" queue.
- Show the Paybill instructions on the wait screen after 1037 or 1025, plus an "I've paid, enter code" box (SMS `PAID <code>`). Add a Demo Lab button that simulates a C2B confirmation.

**G13: Paystack.**
- Implement `PaystackCard.query` as `GET /transaction/verify/<reference>`. Call it in the webhook before `on_success`, in `reconcile_pending` for cards pending over 2 minutes, and on `?paid=1` return.
- Check `status`, `currency=="KES"` and `amount`.
- Also verify the new timestamped `Paystack-Signature` (`whsec_…`); the legacy header is deprecated but still sent while a secret key exists.

**H7: exports.** Add `ledger.csv?month=` with date, ref, guest, method, M-Pesa receipt, gross, VAT, levy, refunded and net columns (the `ledger` view already exists).

**C2: TRA licence.** Add `tra_licence_no` and `tra_licence_expiry` to settings, with reminders at 90, 60 and 30 days, and a licence badge on listings.

### Suggested 2-day cut (my estimates)

| Day | Items |
|---|---|
| Day 1 | G11 (1.5 h), G4 (2 h), G7 (3 h), G13 (1.5 h), H7 and C2 (1 h) |
| Day 2 | G1/G2 extend and shorten (6–8 h), G6 (2 h), then H1/H2 (3 h) and G12 simulated (3 h) if time remains |

Demo storyline: cancel on the M-Pesa prompt → friendly message → Paybill → C2B confirmation → confirmed → host cancels another booking → waitlist SMS → extend the stay → pay the delta → tax invoice.

---

## (b) M-Pesa handling

**Source caveat.** Safaricom's Daraja page didn't render. The code meanings below come from secondary sources that agree with each other; the Reversal API facts come from Safaricom's own Reversal page. Confirm them in your Daraja sandbox.

| Code | Meaning | Retry | System action | Guest message (EN) | Kiswahili (draft) |
|---|---|---|---|---|---|
| 0 | Success. Callback metadata includes Amount, MpesaReceiptNumber, PhoneNumber | – | Settle idempotently on CheckoutRequestID, store the receipt, check the amount | "Payment received - KES {amt}, M-Pesa ref {receipt}." | "Malipo yamepokelewa - KES {amt}, kumbukumbu {receipt}." |
| 1 | Insufficient balance | After top-up | Fail soft, keep hold, offer 30% deposit or card | "M-Pesa balance too low for KES {amt}. Top up or use Fuliza and resend, pay only the 30% deposit (KES {dep}), or pay by card." | "Salio halitoshi. Weka pesa utume tena, lipa amana ya 30% au tumia kadi." |
| 1001 | Unable to lock subscriber, another transaction in progress | After 1–2 min | Don't create a new Payment; keep polling the open one | "An M-Pesa request is already open on your phone. Finish or cancel it, wait a minute, then Resend." | "Una ombi lingine wazi la M-Pesa. Likamilishe au ulighairi, subiri dakika moja, kisha utume tena." |
| 1019 | Transaction expired | Yes | Mark expired; new push on demand | "The M-Pesa prompt expired. Tap Resend." | "Ombi limeisha muda. Bonyeza Tuma tena." |
| 1025 | Error sending the push | Auto-retry once after about 10 s | Retry once; on repeat show Paybill/card | "We couldn't reach your phone. Check your signal and try again, or use Paybill/card." | "Hatukuweza kufikia simu yako. Angalia mtandao au tumia Paybill/kadi." |
| 1032 | Cancelled by user | Yes, user-driven | Stop polling, no auto-retry, hold continues | "You cancelled the M-Pesa request. Your home is held for {n} more minutes. Tap Pay to retry or choose card." | "Umeghairi ombi. Nyumba imeshikiliwa dakika {n} - bonyeza Lipa au tumia kadi." |
| 1037 | DS timeout, user unreachable or no PIN entered (about 25–30 s; some reports say 1–3 min) | Yes | Wait about 5 s, then STK Query to rule out late success; then fail and offer resend and Paybill | "We couldn't reach your phone in time. Keep it unlocked, then resend, or pay via Paybill." | "Hatukufikia simu kwa wakati. Iweke wazi kisha utume tena, au tumia Paybill." |
| 2001 | Wrong PIN on consumer STK. On B2C/reversal, 2001 means invalid initiator or SecurityCredential | Carefully | After 2 consecutive 2001s, suggest card or Paybill | "Wrong M-Pesa PIN. Try once more carefully; repeated wrong PINs can lock M-Pesa. Or pay by card." | "PIN si sahihi. Jaribu tena kwa makini au tumia kadi." |
| Other / missing | Unknown | – | Store ResultCode and ResultDesc verbatim; alert if frequent | "We couldn't complete the payment. If M-Pesa took your money, don't pay again - text us the M-Pesa code and we'll match it." | – |

Lifecycle rules a production system needs:
- **Initiation.** `ResponseCode 0` on initiation only means accepted for processing. The final result comes from the callback or STK Query.
- **Query while pending.** STK Query returns an error object instead of a `ResultCode` while the transaction is still being processed. A field report says the same `500.001.1001` code is used for "being processed" and for "unable to lock subscriber", so tell them apart by the message. Your absence-of-code check already handles this (`payments/services.py:324-331`).
- **Late and duplicate callbacks.** Already handled, including reinstating the booking after a lapsed hold.
- **Underpay and overpay.** Underpay is treated as a mismatch (`:142`). Overpay is silently accepted; record `amount_received` and flag it.
- **Callback security.** Callbacks are unsigned. Use a dedicated `DARAJA_CALLBACK_SECRET` over HTTPS (Daraja rejects HTTP callback URLs, per a field guide). Optionally re-confirm each success with STK Query before crediting. An IP allowlist is also possible, but I couldn't verify Safaricom's list.
- **Refunds.**
  - Safaricom's Reversal API is asynchronous. `CommandID=TransactionReversal` takes `TransactionID`, `Amount`, `ReceiverParty`, `ResultURL` and `QueueTimeOutURL`. It returns R000001 if the transaction was already reversed.
  - The portal states that B2C reversals are done manually on the M-PESA portal.
  - Your queue plus `mark_refund_sent` is a sound hackathon scope. Add an SMS to the guest when the refund is marked sent.
- **Paybill/Till fallback.** See G12.
- **Paystack essentials.**
  - Verify the signature on the raw body. The legacy `x-paystack-signature` is HMAC-SHA512 with the secret key and is deprecated.
  - Return 200 quickly, then verify the transaction.
  - Retries: live mode every 3 minutes for 4 tries, then hourly for up to 72 hours. Test mode retries hourly for 10 hours, with a 30-second timeout per attempt.
  - Resending isn't idempotent, so ignore repeats. Your `on_success` already does.

---

## (c) Africa's Talking edge cases

| Channel | Edge case | Evidence | Recommended handling |
|---|---|---|---|
| USSD | Session limits | AT Help Centre: Safaricom sessions last 180 s and time out after 30 s of customer silence. Airtel: 180 s, application response 15 s, connection-to-app 10 s, customer idle 60 s | Don't call Daraja synchronously in the USSD request (`ussd.py:340-342`). Enqueue the push, then `END "Check your phone for the M-Pesa prompt of KES X"`. Pre-warm the token (cache exists). Cap screens at about 160 characters (AT's Nigeria page cites 160; assume the same). |
| USSD | Drop mid-booking | `ussd_events` only logs (`comms/views.py:117-120`) | Persist `UssdSession(session_id, phone, status, duration, hops, last_input, error)`. On `Incomplete` with a draft hold, send a "finish your booking" SMS, and offer "Continue {ref}" on the next dial. From memory of the docs (not re-fetched): the notification carries sessionId, status (Success/Incomplete/Failed), durationInMillis, hopsCount, input, lastAppResponse and errorMessage. |
| USSD | Non-Safaricom user | STK is M-Pesa only | Detect by network or prefix and send a card/Paybill link by SMS. |
| USSD | Repeats / exceptions | `process_ussd` returns "END Sorry…" (`comms/views.py:96-105`) | Good. Make hold creation idempotent per (phone, unit, dates). |
| SMS | DLR states | AT Help Centre: Sent, Submitted, Buffered, Success, Rejected, Failed, Expired | You map the terminal states. Add an SLA timer: if a critical message (code, pay link, OTP) has no Success in N minutes, fall back to WhatsApp (`at.send_whatsapp`) or a "call guest" task, and alert the host. Don't resend while Buffered or AbsentSubscriber; wait for Expired. |
| SMS | API status codes | AT: 405 InsufficientBalance, 406 UserInBlacklist (opted out or blacklisted). Others from memory: 402 InvalidSenderId, 403 InvalidPhoneNumber, 404 UnsupportedNumberType, 407 CouldNotRoute, 500/501/502 gateway | **Transient** (5xx, 407, network): retry with 1, 5 and 30 minute backoff, 3 attempts. **Terminal** (402, 403, 404, 406): no retry, mark `undeliverable` and flag the guest. **405**: host alert, pause marketing, keep transactional (`at.balance()` exists). |
| SMS | STOP / opt-out | `sms_optout` and `marketing_opt_in=False` (`comms/views.py:82-92`); marketing is suppressed in `messaging.send` | AT or the telco may blacklist the recipient per sender, so later *transactional* sends can return 406. Use separate sender IDs for promo and transactional, include "Reply STOP to opt out" in every promo (Noria, Devotel), honour STOP at once, and add a START re-consent path. |
| SMS | Sender ID | Devotel (secondary): the Communications Authority regulates sender-ID registration | Register the alphanumeric sender ID per operator; unregistered IDs risk `Rejected`. |
| SMS | Inbound duplicates | `record_inbound(provider_id)` (`messaging/services.py:111`) | Add a unique constraint on provider_id for inbound messages. |
| Voice | Callback states | AT Help Centre: `callSessionState` Active, Dialing, Ringing, Bridged, Completed, NotAnswered, Enqueued, Dequeued, Expired. `hangupCause` is sent when an outbound call isn't answered (e.g. NORMAL_CLEARING, NORMAL_TEMPORARY_FAILURE) | Inbound bridging is handled (`voice.py:465-505`). **Add** event-driven handling for outbound calls: an unanswered welcome call triggers an SMS; an unanswered SOS call to Amina triggers the next escalation tier and an SMS immediately, instead of waiting for the timer. |
| Voice | Retries | AT retries an outbound call and sends `Expired` if unreachable after 6 hours | Don't re-dial. Correlate with `clientRequestId` (you already use `welcome-` and `alert-`). |

---

## Kenyan compliance notes

- **Tourism levy:**
  - The Tourism Fund's homepage confirms the 2% levy and the eLevy portal at https://levy.tourismfund.co.ke/.
  - Secondary sources say it is due by the 10th of the following month, with a late penalty of KSh 5,000 plus 3% (BusinessRadar). One source says the base is sales before taxes and charges, computed as gross × 2 ÷ 123, 118 or 102 depending on which taxes apply.
  - Check that your `levy = taxable × 2%` matches the Tourism Fund's formula for your invoicing.
- **TRA licence:**
  - A secondary source says serviced apartments, villas, holiday cottages, homestays and guest houses need a TRA licence (Tourism Act s.98).
  - It also says licences expire on 31 December and renewals are due at least 2 months earlier.
  - I found no primary text for a "monthly TRA return" or the guest-register format. Verify these with TRA.
- **VAT and eTIMS:**
  - Accommodation is standard-rated at 16%.
  - Sources conflict on the VAT registration threshold: KES 5m (MyBillDash) versus KES 8m "raised by the Finance Act 2025" (Veira). Your `vat_registered` help text says KES 5m (`core/models.py:32`).
  - Tax invoices must go through eTIMS (MyBillDash).
  - A claim that KRA validates income and expenses against invoices from January 2026 comes from one low-quality source. I did not find a KRA primary page.
  - A host with 6 homes likely exceeds both thresholds. That is my inference, not a sourced figure.
- **Data Protection (DSR deadlines):**
  - The Cliffe Dekker Hofmeyr summary of the 2021 Regulations gives access in 7 days; erasure, rectification and restriction in 14 days; and portability in 30 days.
  - A Dira blog says 7 days for most requests.
  - Use 7 days as your internal SLA for all request types, and log `received_at`, `due_at` and `status`.

---

## Gaps and uncertainties

- **Official docs not retrieved.** Safaricom Daraja's STK docs, AT's USSD and SMS-status docs, Paystack's page (403 to my fetch; I used search snippets of it), KRA, TRA and ODPC. Secondary sources and Help Centre snippets stand in, and the marked items above should be checked before relying on them.
- **No competitor evidence for web waitlist or Booking.com behaviour.** I found no Booking.com sources and no primary doc for waitlists on Airbnb or Booking.com.
- **Unverified product behaviour.** Bulk pricing across homes, guest ratings in the CRM, and whether the wait screen shows the failure reason were not confirmed. Voice and USSD logic are as read, not exercised.
- **No code or tests changed by the brief itself.** The implementation followed; see the next section.

---

## What we built

Every MUST and most SHOULD items were implemented, and every guest and host flow was then walked end to end in the browser and covered by API flow tests (`backend/tests/test_flows_*.py`, `test_feature_*.py`).

| Gap | What shipped | Where |
|---|---|---|
| G1, G2, H3 change / extend | `ChangeRequest`: the guest (trip page "Change trip", SMS `EXTEND`) or Amina proposes new dates or guests. The whole stay is re-priced at current rates, availability is re-checked in one transaction, a higher price waits for payment (M-Pesa or card) for up to 48 hours, less close to arrival, then lapses, and a lower one applies at once with the refund set by the cancellation policy. With **Instant changes** off in Settings, Amina approves first (Today and the reservation page). | `bookings/models.py::ChangeRequest`, `bookings/services.py` (change section), `changes_expire` job, `trip-change.tsx`, host `today.tsx` / `reservation-detail.tsx` |
| G4 web waitlist | "Notify me" on a listing when the dates are taken; the guest manages entries under Account; the existing waitlist SMS fires when the dates free up. | `POST /api/waitlist`, `/api/me/waitlist`, `listing-view.tsx`, `account-view.tsx` |
| G7 balance failure | A balance ladder (a reminder a week ahead, the due-day prompt, then an overdue SMS with the Paybill details), an "overdue" state on the trip page, an Outstanding balances card for Amina, and an arrival-morning alert when a door code is held for payment. | `messaging/automations.py::run_balance_ladder` (daily 10:00), host Payments |
| G11 M-Pesa failure UX | Result codes 0, 1, 1001, 1019, 1025, 1032, 1037 and 2001 map to a plain-language message on the web and an SMS fragment in English or Kiswahili, each with the right next step (resend, wait, pay the 30% deposit, card or Paybill). The reason is stored on the payment for Amina. The Demo Lab can simulate each failure. | `payments/results.py`, `payment-help.tsx`, checkout |
| G12 Paybill / C2B | Validation and confirmation callbacks under a secret path. A payment whose account number is the booking reference settles the booking and sends a PAID SMS; anything else lands in an Unmatched queue that Amina matches in one click. `manage.py register_c2b` registers the URLs with Daraja. The checkout offers the Paybill after a failure or 30 s. | `payments/c2b.py`, `register_c2b`, host Payments, Demo Lab "Simulate Paybill" |
| G13 card verify + reconcile | Paystack webhooks are verified with Verify Transaction (amount and currency), and pending card payments are reconciled like STK pushes. | `payments/providers.py`, `payments/services.py` |
| G6 tax invoice | Numbered invoices (`AMS-INV-YYYY-NNNNN`) and credit notes (`AMS-CN-…`) for refunds and reductions, a printable invoice page for guests and Amina, and a sales-register CSV. eTIMS transmission is not built (status `not_submitted`). | `payments/invoices.py`, `/trips/[ref]/invoice`, Safety → Compliance |
| H2 manual booking | A deposit plan and a custom price with a reason on host-created reservations. | `new-reservation.tsx`, `bookings/views.py` |
| H7 exports | Payments ledger CSV (`?export=csv`). | host Payments |
| C2 licence renewal | Reminders to Amina 45, 30, 14, 7 and 1 days before the TRA licence expiry date in Settings, plus a compliance alert that closes when the licence is renewed. | `safety/services.py::licence_reminder` (daily 09:00) |
| Overpayment | The surplus (a Paybill payment can be any amount) is queued as a refund and the guest is told by SMS; when Amina marks it sent, a `refund_sent` SMS follows. | `bookings/services.py::refund_overpayment`, `payments/services.py::mark_refund_sent` |
| Callback security | A dedicated `DARAJA_CALLBACK_SECRET` for the Paybill callbacks; callbacks for unknown or garbled transactions are ignored. | `payments/c2b.py`, `payments/views.py` |
| USSD / voice M-Pesa | The STK push is deferred until after the USSD or voice response, so Daraja latency can't time out the session. | `comms/deferred.py` |
| SMS status codes | 402, 403 and 404 are final (no retry); 406 also marks the number as opted out (START opts back in); 405 alerts Amina to top up while booking messages wait it out (every 30 minutes, for up to a day); 5xx, 407 and network errors retry after 1 and 5 minutes, 3 sends in all. Inbound messages are de-duplicated by a database constraint. | `messaging/services.py`, migration `messaging/0002` |
| Unanswered outbound calls | An unanswered welcome call falls back to SMS; an unanswered SOS call escalates at once. | `comms/voice.py` |

Not built in this round: request-to-book (G3), co-guest invites (G5), security deposits and damage claims (G10, H4), the special offer / custom quote link (H1), cleaning photos (H5), vendor costs on maintenance (H6), host-reviews-guest (H8), a data-subject request log (C3), eTIMS submission and automated M-Pesa reversals (G14).

---

## Sources

**Airbnb**
- Host modifies a reservation: https://www.airbnb.com.au/help/article/50
- Guest changes during a trip: https://www.airbnb.com/help/article/1363
- Instant Book vs request: https://www.airbnb.ca/help/article/85
- Payment plans: https://www.airbnb.com.sg/help/article/3783
- Host damage protection: https://www.airbnb.ae/help/article/279
- Invite guests: https://www.airbnb.com.mt/help/article/1175
- Check-in: https://www.airbnb.co.uk/help/article/41

**PMS tools**
- Hospitable, payment failures: https://help.hospitable.com/en/articles/14631405-direct-booking-payment-failures
- Hospitable, direct-booking payments and deposit: https://help.hospitable.com/en/articles/14803560-how-payments-work-for-direct-bookings
- Hostaway help index (quotes, checklists): https://support.hostaway.com/hc/en-us/categories/360000589513-Using-Hostaway
- Hostaway automation summary (third party): https://pushbuild.com/tools/hostaway.html

**M-Pesa / Daraja**
- Safaricom Reversal API: https://developer.safaricom.co.ke/apis/Reversal
- M-Pesa Express page (didn't render): https://developer.safaricom.co.ke/apis/MpesaExpress
- Result codes, secondary: https://www.kenzobe.com/blog/mpesa-daraja-api-errors, https://www.domaintechhubs.com/insights/daraja-api-error-codes-reference-resultcode-1032-1037-2001, https://learn.elitesamttech.co.ke/lesson/transaction-lifecycle, https://fyberpay.com/tools/daraja-stk-debugger
- C2B: https://daraja-local.chanansystems.co.ke/docs/c2b/, https://laraveldaraja.com/apis/c2b/

**Paystack**
- Webhooks: https://paystack.com/docs/payments/webhooks/ and https://paystack.com/docs/v2/developer-tools/integration/webhooks

**Africa's Talking**
- SMS error codes: https://help.africastalking.com/en/articles/16150386-messaging-error-codes
- USSD session duration: https://help.africastalking.com/en/articles/1284071-what-is-the-duration-of-a-ussd-session-for-kenyan-telcos
- Hang-up causes: https://help.africastalking.com/en/articles/2948431-what-are-the-parameters-for-hang-up-cause
- Call parameters: https://help.africastalking.com/en/articles/2948521-understanding-parameters-used-in-a-call

**Kenya SMS rules** (secondary)
- https://noria.co.ke/insights/bulk-sms-kenya-consent-opt-out
- https://docs.orbit.devotel.io/compliance/kenya-ca-sender-rules

**Kenya compliance**
- Tourism Fund, primary: https://www.tourismfund.go.ke/ (eLevy: https://levy.tourismfund.co.ke/)
- Tourism levy, secondary: https://eliacc.co.ke/catering-levy-in-kenya-2-tourism-levy-deadlines-compliance-restaurant-guide-2026/, https://businessradar.co.ke/tourism-levy-in-kenya/, https://paybillke.com/guides/tourism-levy-kenya-2026
- TRA licensing, secondary: https://streamlinefeed.co.ke/news/running-an-airbnb-in-kenya-licences-levies-taxes-bylaws
- VAT/eTIMS, secondary: https://mybilldash.com/blog/kenya-vat-invoicing-etims-guide/, https://veirahq.com/vat, https://veirahq.com/statistics/etims-tax-statistics-kenya
- Data protection: https://www.cliffedekkerhofmeyr.com/en/news/publications/2022/Practice/TMT/tmt-alert-31-january-Unpacking-the-Data-Protection-General-Regulations-2021-of-the-Data-Protection-Act-24-of-2019, https://compliancedira.com/blog/managing-dsr-kenya-dpa-2019
