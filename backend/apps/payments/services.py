"""Payments: start a collection, then settle it exactly once when the provider calls back.

Lessons from Airbnb's payments engineering (Orpheus): no network call inside a DB transaction,
a duplicate callback is a no-op, and async methods move pending → confirmed. A payment that
arrives after its hold lapsed re-confirms the booking only if the unit is still free;
otherwise the booking becomes refund_due and Amina is alerted.

A failed M-Pesa prompt keeps its Daraja result code; results.MPESA_RESULTS turns it into the stored reason,
the guest's message and the next step (public_failure). Paybill (C2B) payments live in c2b.py and tax
invoices in invoices.py.
"""

import logging
import math
import os
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.bookings import services as bookings
from apps.bookings.models import Booking
from apps.core.activity import record
from apps.core.models import SiteSettings
from apps.core.utils import is_kenyan, kes, today
from apps.messaging import services as messaging
from apps.properties.models import Unit
from apps.properties.services import is_available

from .models import Payment, Refund
from .providers import (
    PaymentError,
    PaystackCard,
    StripeCard,
    card_provider,
    mpesa_provider,
    setup_alert,
)
from .results import MPESA_RESULTS, result_for, sms_reason

log = logging.getLogger("amina.payments")

OPEN_PUSH_WINDOW = timedelta(minutes=2)
OPEN_PUSH_MESSAGE = (
    "An M-Pesa request is already waiting on your phone - enter your PIN there, or wait a minute and try again."
)
NO_CONFIRMATION = "no confirmation received"
CARD_FAILED = "Your card payment didn't go through. Try again, or pay with M-Pesa."
CARD_FAILED_NO_MPESA = "Your card payment didn't go through. Please try again, or use another card."
MISMATCH = (
    "We received a different amount than expected, so this payment is on hold. Amina has been alerted and will "
    "sort it out - please don't pay again."
)


# ---------- which methods are on ----------


def mpesa_on():
    """M-Pesa is offered at all (MPESA_PROVIDER isn't "off"). When it's off every payment is a card payment."""
    return settings.MPESA_PROVIDER != "off"


def can_prompt(phone):
    """Whether this phone gets M-Pesa prompts: M-Pesa is on and the number is Kenyan. Everyone else pays by card,
    through a link sent by SMS when they aren't on the website."""
    return mpesa_on() and is_kenyan(phone)


def default_method(phone):
    return "mpesa" if can_prompt(phone) else "card"


# ---------- Paybill / deposit options ----------


def paybill_number():
    """The Paybill guests can pay into with their booking ref as the account number (None = not offered). A Till
    (CustomerBuyGoodsOnline) takes no account number, so DARAJA_SHORTCODE only counts for a Paybill."""
    if not mpesa_on():
        return None
    paybill = settings.MPESA_PROVIDER == "daraja" and settings.DARAJA_TRANSACTION_TYPE == "CustomerPayBillOnline"
    number = (
        getattr(settings, "MPESA_SHORTCODE", "")
        or os.environ.get("MPESA_SHORTCODE", "")
        or (settings.DARAJA_SHORTCODE if paybill else "")
        or ("174379" if settings.DEMO else "")  # Daraja's sandbox shortcode
    )
    return str(number).strip() or None


def paybill_config():
    number = paybill_number()
    return {"number": number, "account_hint": "Your booking ref, e.g. AMS-1234"} if number else None


def deposit_amount(b):
    """The deposit a held, pay-in-full booking could pay now instead (None when a deposit isn't allowed)."""
    s = SiteSettings.load()
    if b.status != "held" or b.payment_plan != "full" or not 0 < s.deposit_percent < 100:
        return None
    if (b.check_in - today()).days <= s.balance_due_days:
        return None
    deposit = -(-b.total * s.deposit_percent // 100)  # ceil, as in the quote
    return deposit if deposit > b.amount_paid else None


def switch_to_deposit(booking, *, actor=None):
    """Pay only the deposit now (e.g. after 'insufficient balance'); the balance falls due before arrival."""
    b = booking
    if b.payment_plan == "deposit":
        return b
    deposit = deposit_amount(b)
    if not deposit:
        raise PaymentError("A deposit isn't available for this stay.", suggest="card")
    if not Booking.objects.filter(pk=b.pk, status="held", payment_plan="full").update(
        payment_plan="deposit", amount_due_now=deposit, updated_at=timezone.now()
    ):
        raise PaymentError("This booking can't switch to a deposit now.")
    b.refresh_from_db()
    bookings.event(b, "plan", f"Switched to a deposit: {kes(deposit)} now, the balance before arrival", actor=actor)
    return b


# ---------- starting a payment ----------


def _amount_for(b, purpose):
    if b.status == "held":
        due = max(0, b.amount_due_now - b.amount_paid)
        return due, ("deposit" if b.payment_plan == "deposit" else "full")
    return b.balance_due, purpose or "balance"


def _open_push(b, phone, purpose, amount):
    """The same prompt sent under 2 minutes ago and still unanswered (a different amount is a new request:
    if the phone is still showing the first one, Daraja answers 1001 and we hand that one back instead)."""
    return (
        Payment.objects.filter(
            booking=b,
            method="mpesa",
            purpose=purpose,
            amount=amount,
            phone=phone,
            status="pending",
            created_at__gt=timezone.now() - OPEN_PUSH_WINDOW,
        )
        .order_by("-id")
        .first()
    )


def start_payment(booking, *, method=None, purpose=None, amount=None, phone=None, actor=None, plan=None):
    """Returns {payment_id, method, status, amount, purpose, checkout_url?, simulated, message}.
    Raises PaymentError (with .failure_code and .suggest, see PaymentError.as_dict) when it can't start.
    plan="deposit" first switches a held pay-in-full booking to paying its deposit now.
    purpose="change" with amount=X charges exactly X (a reservation change applied once it's paid)."""
    b = Booking.objects.select_related("guest", "unit").get(pk=booking.pk)
    phone = phone or b.guest.phone
    method = method or default_method(phone)
    if method not in ("mpesa", "card"):
        raise PaymentError("Choose M-Pesa or card.")
    if method == "mpesa" and not mpesa_on():
        raise PaymentError("M-Pesa isn't available here - please pay by card.", suggest="card")
    if method == "mpesa" and not is_kenyan(phone):
        raise PaymentError("M-Pesa needs a Kenyan (+254) number - please pay by card.", suggest="card")
    if b.status not in ("held", "confirmed", "checked_in"):
        raise PaymentError("This booking can't take payments.")
    if b.status == "held" and not b.hold_active:
        raise PaymentError("The hold on this home has expired - please book again.")
    if plan == "deposit":
        switch_to_deposit(b, actor=actor)
    default_amount, default_purpose = _amount_for(b, purpose)
    amount = int(amount if amount is not None else default_amount)
    purpose = purpose or default_purpose
    if amount <= 0:
        raise PaymentError("There's nothing left to pay.")

    if method == "mpesa":
        # One prompt at a time: Safaricom answers a second push to a phone still showing one with 1001
        open_push = _open_push(b, phone, purpose, amount)
        if open_push:
            return _result(open_push, {"status": "pending", "message": OPEN_PUSH_MESSAGE})
    else:
        # "Guest taps Pay twice": reuse the card page made in the last minute instead of opening a second one
        recent = Payment.objects.filter(
            booking=b,
            method="card",
            amount=amount,
            status="pending",
            created_at__gt=timezone.now() - timedelta(seconds=60),
        ).first()
        if recent:
            return _result(recent, {"status": "pending", "message": "A payment request is already waiting."})

    provider = mpesa_provider() if method == "mpesa" else card_provider()
    p = Payment.objects.create(
        booking=b, amount=amount, method=method, purpose=purpose, phone=phone, provider=provider.name, created_by=actor
    )
    try:
        res = provider.request(p)
    except PaymentError as e:
        code = e.failure_code or ""
        if code == "1001":  # the phone is busy with a prompt we already sent: keep that one
            other = (
                Payment.objects.filter(booking=b, method="mpesa", status="pending").exclude(pk=p.pk).order_by("-id")
            ).first()
            if other:
                p.delete()
                return _result(other, {"status": "pending", "message": OPEN_PUSH_MESSAGE})
        p.status, p.failure_code, p.failure_reason = "failed", code, str(e)[:200]
        p.save(update_fields=["status", "failure_code", "failure_reason", "raw", "updated_at"])
        bookings.event(b, "payment_failed", f"{p.get_method_display()} request failed: {e}", code=code)
        info = public_failure(p)
        e.failure_code, e.suggest = info["failure_code"], e.suggest or info["suggest"]
        raise
    bookings.event(b, "payment_requested", f"{p.get_method_display()} request for {kes(amount)} sent ({purpose})")
    # Providers answer in their own words ("Success. Request accepted for processing"); guests get ours.
    guest_msg = (
        f"Check your phone for the M-Pesa prompt of {kes(amount)} and enter your PIN."
        if method == "mpesa"
        else f"Finish paying {kes(amount)} on the secure card page."
    )
    return _result(
        p, {**res, "message": guest_msg, "provider_message": res.get("message", "")}, simulated=provider.simulated
    )


def checkout_url(p):
    """The provider's own payment page for a card payment: where the website sends the guest straight away."""
    if p.method != "card" or not p.checkout_token:
        return None
    if p.provider == "simulate":
        return pay_link(p)
    for entry in reversed(p.raw or []):
        request = entry.get("request") or {}
        url = request.get("url") or (request.get("data") or {}).get("authorization_url")  # Stripe, Paystack
        if url:
            return url
    return None


def pay_link(p):
    """The short link for a card payment that goes out by SMS: our /pay/card/<token> page opens the provider's page
    (a Stripe Checkout URL runs to hundreds of characters), and is where Stripe brings the guest back."""
    if p.method != "card" or not p.checkout_token:
        return None
    return f"{settings.FRONTEND_URL.rstrip('/')}/pay/card/{p.checkout_token}"


def _result(p, res, simulated=None):
    return {
        "payment_id": p.pk,
        "method": p.method,
        "status": p.status,
        "amount": p.amount,
        "purpose": p.purpose,
        "checkout_url": res.get("checkout_url") or checkout_url(p),
        "pay_link": pay_link(p),
        "message": res.get("message", ""),
        "provider_message": res.get("provider_message", ""),
        "simulated": simulated if simulated is not None else p.provider == "simulate",
    }


def start_remote_payment(booking):
    """For SMS / USSD / voice: start payment and return wording for the guest; card links go out by SMS."""
    b = booking
    try:
        r = start_payment(b)
    except PaymentError as e:
        return {
            "error": str(e),
            "text": f"We couldn't start payment ({e}). Your hold lasts a few minutes - reply PAY to try again.",
        }
    ctx = {
        **bookings.guest_context(b),
        "amount": kes(r["amount"]),
        "minutes": SiteSettings.load().hold_minutes,
        "link": r.get("pay_link") or r.get("checkout_url") or "",
    }
    if r["method"] == "card":
        messaging.send(b.guest.phone, messaging.render("hold_card", b.lang, **ctx), booking=b, kind="hold_card")
        return {**r, "text": f"We've texted you a secure card payment link for {kes(r['amount'])}."}
    return {**r, "text": f"Check your phone for an M-Pesa prompt for {kes(r['amount'])}."}


# ---------- settling ----------


def on_success(payment, *, transaction_id=None, provider_ref="", raw=None, amount=None):
    """Settle a payment exactly once. Safe to call repeatedly (duplicate callbacks, retries, the simulator).
    Money for a date change applies the change in the same transaction: nobody ever sees it counted while the
    change it paid for is still pending."""
    outcome = None
    try:
        with transaction.atomic():
            p = Payment.objects.select_for_update().get(pk=payment.pk)
            if p.status == "success":
                if provider_ref and not p.provider_ref:  # the M-Pesa code arriving after STK Query settled it
                    p.provider_ref = provider_ref[:80]
                    p.save(update_fields=["provider_ref", "updated_at"])
                return p.booking
            if amount is not None and int(float(amount)) < p.amount:
                p.status, p.failure_code = "failed", ""
                p.failure_reason = f"Amount mismatch: got {amount}, expected {p.amount}"
                p.raw = [*p.raw, {"callback": raw or {}}]
                p.save(update_fields=["status", "failure_code", "failure_reason", "raw", "updated_at"])
                outcome = "mismatch"
            else:
                p.status, p.completed_at = "success", timezone.now()
                p.failure_code = p.failure_reason = ""  # a late success outranks an earlier failure
                if transaction_id and not p.transaction_id:
                    p.transaction_id = transaction_id
                p.provider_ref = (provider_ref or p.provider_ref or "")[:80]
                if raw:
                    p.raw = [*p.raw, {"callback": raw}]
                p.save()
                Unit.objects.select_for_update().filter(pk=p.booking.unit_id).first()
                b = Booking.objects.select_for_update().get(pk=p.booking_id)
                b.amount_paid += p.amount
                bookings.update_payment_status(b, save=False)
                b.save(update_fields=["amount_paid", "payment_status", "updated_at"])
                bookings.event(
                    b,
                    "payment",
                    f"{p.get_method_display()} payment received: {kes(p.amount)}{' (' + p.provider_ref + ')' if p.provider_ref else ''}",
                )
                if b.status == "held":
                    outcome = "confirm"
                elif b.status in ("expired", "cancelled"):
                    if b.status == "expired" and is_available(b.unit, b.check_in, b.check_out, exclude_booking_id=b.pk):
                        b.status, b.hold_expires_at = "held", timezone.now() + timedelta(minutes=5)
                        b.save(update_fields=["status", "hold_expires_at", "updated_at"])
                        bookings.event(
                            b, "reinstated", "Paid after the hold lapsed - unit still free, booking reinstated"
                        )
                        outcome = "confirm"
                    else:
                        b.status = "refund_due"
                        b.save(update_fields=["status", "updated_at"])
                        outcome = "refund_due"
                elif p.purpose == "change" and b.status in ("confirmed", "checked_in"):
                    outcome = "change"  # pays for the new total, not an overpayment
                else:
                    outcome = "extra"
            if outcome == "change":
                _apply_change(p)
    except IntegrityError:
        # the reinstated dates were taken in the meantime (exclusion constraint)
        Booking.objects.filter(pk=payment.booking_id).update(status="refund_due")
        outcome = "refund_due"

    p = Payment.objects.select_related("booking", "booking__guest", "booking__unit", "booking__unit__area").get(
        pk=payment.pk
    )
    b = p.booking
    if outcome == "confirm":
        bookings.confirm(b)
        b.refresh_from_db()
        bookings.refund_overpayment(b, reason="Paid more than the bill")  # a Paybill payment can be any amount
        _invoice_quietly(b)
    elif outcome == "refund_due":
        from apps.safety.services import raise_alert

        bookings.send_guest(b, "late_payment_refund", amount=kes(p.amount))
        raise_alert(
            "payment",
            f"Refund due: {kes(p.amount)} to {b.guest.phone} for {b.ref} (paid after the unit was re-let)",
            severity="high",
            booking=b,
            dedupe=f"refund-due:{p.pk}",
        )
        if p.status == "success":  # a ledger entry Amina can mark as sent, which then closes the booking
            refund(b, p.amount, reason="Paid after the hold lapsed and the dates were re-let", queue=True)
    elif outcome == "extra":
        b.refresh_from_db()
        balance_line = f"Balance due: {kes(b.balance_due)}." if b.balance_due else "You're fully paid - thank you!"
        bookings.send_guest(b, "payment_received", amount=kes(p.amount), balance_line=balance_line)
        bookings.refund_overpayment(b, reason="Paid more than the bill (duplicate payment)")
    elif outcome == "mismatch":
        from apps.safety.services import raise_alert

        raise_alert(
            "payment",
            f"Payment amount mismatch on {b.ref}: {p.failure_reason}",
            severity="high",
            booking=b,
            dedupe=f"mismatch:{p.pk}",
        )
    if outcome in ("confirm", "extra", "refund_due", "change"):
        record(
            "payment",
            f"{p.get_method_display()} {kes(p.amount)} received for {b.ref}",
            booking=b,
            method=p.method,
            amount=p.amount,
        )
    return b


def _apply_change(p):
    """A paid reservation change, inside the transaction that counts the money: bookings applies the change (or
    declines it and refunds when the dates have gone). Should that fail, its savepoint is rolled back on its own:
    the money stays counted, Amina is alerted and the scheduler applies the change later."""
    hook = getattr(bookings, "on_change_paid", None)
    if hook is None:
        log.warning("change payment %s settled but bookings.on_change_paid isn't available", p.pk)
        return
    try:
        with transaction.atomic():
            hook(p)
    except Exception:
        log.exception("applying the change paid by payment %s failed", p.pk)
        from apps.safety.services import raise_alert

        raise_alert(
            "payment",
            f"{kes(p.amount)} received for a change to {p.booking.ref}, but the change couldn't be applied - "
            "check the reservation.",
            severity="high",
            booking=p.booking,
            dedupe=f"change-paid:{p.pk}",
        )


def _invoice_quietly(b):
    """Issue the tax invoice once a stay is confirmed; invoicing never gets in the way of settling a payment."""
    from .invoices import get_or_issue

    try:
        get_or_issue(b)
    except Exception:
        log.exception("issuing the invoice for %s failed", b.ref)


def on_mpesa_result(payment, code, *, desc="", raw=None, amount=None, receipt=""):
    """The single path for an STK prompt's final answer: the Daraja callback, STK Query reconciliation and the
    Demo Lab's simulated result codes all land here. ResultCode 0 settles; anything else fails it with the
    code kept for the guest's message."""
    code = "" if code is None else str(code).strip()
    if code == "0":
        receipt = str(receipt or "")
        paybill = (
            Payment.objects.filter(provider="c2b", transaction_id=receipt).exclude(pk=payment.pk).first()
            if receipt
            else None
        )
        if paybill:  # the same M-Pesa transaction already arrived as a Paybill confirmation and was credited
            Payment.objects.filter(pk=payment.pk, status__in=("pending", "failed", "expired")).update(
                status="cancelled",
                failure_reason=f"Same M-Pesa payment as Paybill {receipt}",
                updated_at=timezone.now(),
            )
            return paybill.booking
        twin = None if receipt else _paybill_twin(payment)
        if twin:  # STK Query (no M-Pesa code) settled it after a Paybill payment of the same money was counted
            cancelled = Payment.objects.filter(pk=payment.pk, status__in=("pending", "failed", "expired")).update(
                status="cancelled",
                failure_reason=f"Paid with no M-Pesa code: counted once, with Paybill {twin.transaction_id}",
                updated_at=timezone.now(),
            )
            if cancelled:
                flag_same_money(twin.booking, payment, twin.transaction_id)
            return twin.booking
        return on_success(payment, provider_ref=receipt, raw=raw, amount=amount)
    entry = MPESA_RESULTS.get(code)
    failed = on_failure(payment, entry["reason"] if entry else (desc or "failed"), raw=raw, code=code)
    if entry and entry.get("host_alert"):
        setup_alert(failed.booking, entry["host_alert"])
    return failed


def _paybill_twin(payment):
    """A Paybill payment already counted for the same booking and amount around this prompt's time: what a prompt
    settled without an M-Pesa code may be the same money as."""
    from .c2b import ECHO_WINDOW

    window = (payment.created_at - ECHO_WINDOW, payment.created_at + ECHO_WINDOW)
    return (
        Payment.objects.filter(
            booking_id=payment.booking_id,
            provider="c2b",
            status="success",
            amount=payment.amount,
            created_at__range=window,
        )
        .order_by("created_at")
        .first()
    )


def flag_same_money(booking, prompt, paybill_code):
    """A prompt and a Paybill payment matched by amount and time, not by M-Pesa code: one payment reported twice
    (a prompt echoed to the Paybill) or a guest who paid twice. It is counted once, and nobody is promised a
    refund; Amina's M-Pesa statement settles which it was, and the alert says what to do if it was two."""
    from apps.safety.services import raise_alert

    b = Booking.objects.select_related("guest").get(pk=booking.pk)
    amount = kes(prompt.amount)
    if b.balance_due >= prompt.amount:  # the stay still needs the money: a second payment counts towards it
        action = "record the second one on the reservation (Record cash or bank payment, M-Pesa)"
    else:
        action = f"refund {amount} to {prompt.phone or b.guest.phone}"
    raise_alert(
        "payment",
        f"Check M-Pesa for {b.ref}: an M-Pesa prompt and Paybill {paybill_code} ({amount}) were counted as one "
        f"payment. If your statement shows two, {action}.",
        severity="high",
        booking=b,
        dedupe=f"same-money:{prompt.pk}",
    )
    record(
        "payment",
        f"Prompt payment and Paybill {paybill_code} ({amount}) counted once for {b.ref}",
        booking=b,
        amount=prompt.amount,
        trans_id=paybill_code,
    )


def on_failure(payment, reason="", raw=None, code=""):
    code = str(code or "").strip()[:12]
    with transaction.atomic():
        p = Payment.objects.select_for_update().get(pk=payment.pk)
        if p.status != "pending":
            return p
        p.status, p.failure_code = "failed", code
        p.failure_reason = (reason or (MPESA_RESULTS.get(code) or {}).get("reason") or "declined")[:200]
        if raw:
            p.raw = [*p.raw, {"callback": raw}]
        p.save(update_fields=["status", "failure_code", "failure_reason", "raw", "updated_at"])
    b = Booking.objects.select_related("guest", "unit", "unit__area").get(pk=p.booking_id)
    bookings.event(b, "payment_failed", f"{p.get_method_display()} payment failed: {p.failure_reason}", code=code)
    if b.status == "held" and b.channel != "web":
        _tell_remote_guest(b, p)
    return p


def _tell_remote_guest(b, p):
    """SMS for guests who booked by SMS / USSD / voice: the reason in their language, plus Paybill when the
    prompt couldn't reach their phone."""
    body = messaging.render("payment_failed", b.lang, **bookings.guest_context(b), reason=sms_reason(p, b.lang))
    number = paybill_number()
    if number and public_failure(p)["suggest"] == "paybill":
        body += " " + messaging.render("paybill_hint", b.lang, amount=kes(p.amount), paybill=number, ref=b.ref)
    messaging.send(b.guest.phone, body, booking=b, kind="payment_failed")


# ---------- what the guest sees about a failed payment ----------

NOT_FAILED = {"failure_code": None, "failure_message": None, "retryable": False, "suggest": None}


def public_failure(payment):
    """{failure_code, failure_message, retryable, suggest} for the trip page's payments list."""
    p = payment
    if p.status != "failed":
        return dict(NOT_FAILED)
    b = p.booking
    code = p.failure_code or None
    if p.failure_reason.startswith("Amount mismatch"):
        return {"failure_code": code, "failure_message": MISMATCH, "retryable": False, "suggest": None}
    card_failed = CARD_FAILED if mpesa_on() else CARD_FAILED_NO_MPESA
    entry = result_for(code) if p.method == "mpesa" else {"retryable": True, "suggest": "retry", "message": card_failed}
    suggest = _suggest(p, b, code, entry["suggest"])
    ctx = {"amount": kes(p.amount), "deposit_option": "", "or_deposit": "", "hold_note": ""}
    if suggest == "deposit":
        deposit, pct = deposit_amount(b), SiteSettings.load().deposit_percent
        ctx["deposit_option"] = f", pay only the {pct}% deposit ({kes(deposit)})"
        ctx["or_deposit"] = f", or pay only the {pct}% deposit ({kes(deposit)}) by M-Pesa"
    if b.status == "held" and b.hold_active:
        minutes = max(1, math.ceil((b.hold_expires_at - timezone.now()).total_seconds() / 60))
        ctx["hold_note"] = f" Your home is still held for {minutes} more minute{'s' if minutes != 1 else ''}."
    return {
        "failure_code": code,
        "failure_message": entry["message"].format_map(ctx),
        "retryable": bool(entry["retryable"]) and _can_retry(p, b),
        "suggest": suggest,
    }


def _suggest(p, b, code, default):
    if p.method != "mpesa":
        return default
    if code in ("1", "3", "4", "8"):  # too much for this M-Pesa account now: pay less now, or by card
        return "deposit" if p.purpose != "change" and deposit_amount(b) else "card"
    if code in ("1025", "1037"):  # the prompt can't reach the phone: Paybill doesn't need it to
        return "paybill" if paybill_number() and p.purpose != "change" else "retry"
    if code == "2001":  # a second wrong PIN in a row: stop before M-Pesa locks the account
        previous = (
            Payment.objects.filter(booking_id=p.booking_id, method="mpesa", pk__lt=p.pk)
            .order_by("-pk")
            .values_list("failure_code", flat=True)
            .first()
        )
        return "card" if previous == "2001" else "retry"
    return default


def _can_retry(p, b):
    if p.purpose == "change":
        return b.status in ("confirmed", "checked_in")
    if b.status == "held":
        return bool(b.hold_active)
    return b.status in ("confirmed", "checked_in") and b.balance_due > 0


# ---------- refunds ----------


def refund(booking, amount, *, reason="", actor=None, method=None, queue=False):
    """Simulated payments refund instantly. A refund the stay's Stripe card payments can cover goes back through Stripe
    by itself once the transaction commits, split across them (newest first) when one isn't enough. Any other refund -
    and any queue=True one - waits for Amina to send it (M-Pesa B2C / card reversal) and mark it as sent."""
    b = booking
    last = b.payments.filter(status="success").order_by("-id").first()
    method = method or (
        "card" if last and last.method == "card" else "mpesa_b2c" if last and last.method == "mpesa" else "manual"
    )
    simulated = last is not None and last.provider == "simulate" and not queue
    parts = None if simulated or queue else _stripe_parts(b, amount)
    if parts:
        from apps.comms import deferred

        rows = [
            Refund.objects.create(
                booking=b, payment=p, amount=part, method="card", reason=reason[:200], created_by=actor
            )
            for p, part in parts
        ]
        bookings.event(b, "refund", f"Refund {kes(amount)} going back to the card through Stripe", actor=actor)
        for r in rows:
            deferred.after_response(refund_by_stripe, r.pk)  # never call Stripe inside a transaction that may roll back
        return rows[0]
    r = Refund.objects.create(
        booking=b,
        payment=last,
        amount=amount,
        method=method,
        reason=reason[:200],
        created_by=actor,
        status="success" if simulated else "pending",
        completed_at=timezone.now() if simulated else None,
    )
    bookings.event(
        b, "refund", f"Refund {kes(amount)} {'sent' if simulated else 'queued'} ({r.get_method_display()})", actor=actor
    )
    if simulated:
        _refund_sent(r)
    else:
        _refund_to_send(r)
    return r


def _refund_to_send(r, note=""):
    from apps.safety.services import raise_alert

    raise_alert(
        "payment",
        f"Refund to send: {kes(r.amount)} to {r.booking.guest.phone} for {r.booking.ref} ({r.get_method_display()})"
        f"{note}",
        severity="medium",
        booking=r.booking,
        dedupe=f"refund:{r.pk}",
    )


def _stripe_parts(b, amount):
    """How a refund goes back through Stripe: from the stay's Stripe card payments, newest first, each within what it
    has left. None when they can't cover all of it (some of the money came as cash or M-Pesa): Amina sends that one."""
    if not settings.STRIPE_SECRET_KEY or amount <= 0:
        return None
    left, parts = amount, []
    for p in b.payments.filter(status="success", method="card", provider="stripe").order_by("-id"):
        room = p.amount - sum(r.amount for r in p.refunds.exclude(status="failed"))
        if room > 0:
            part = min(left, room)
            parts.append((p, part))
            left -= part
            if not left:
                return parts
    return None


def refund_by_stripe(refund_id):
    """Send a queued card refund through Stripe; if Stripe won't take it, Amina is asked to send it herself."""
    r = Refund.objects.select_related("payment", "booking", "booking__guest").get(pk=refund_id)
    if r.status != "pending":
        return r
    key = f"amina-refund-{r.pk}-{int(r.created_at.timestamp())}"  # the same refund is never sent twice
    try:
        res = StripeCard().refund(r.payment, r.amount, key=key, note=r.reason)
    except PaymentError as e:
        log.warning("Stripe refund %s failed: %s", r.pk, e)
        _refund_to_send(r, f" - Stripe couldn't send it: {str(e)[:120]}")
        return r
    state = res.get("status")
    Refund.objects.filter(pk=r.pk).update(raw=[*r.raw, {"stripe": {"id": res.get("id"), "status": state}}])
    if state not in ("succeeded", "pending"):  # failed, canceled or requires_action: a person has to look
        _refund_to_send(r, f" - Stripe answered '{state}'")
        return r
    r.refresh_from_db()
    return mark_refund_sent(r, provider_ref=str(res.get("id") or ""))


def mark_refund_sent(r, provider_ref="", actor=None):
    if r.status == "success":
        return r
    r.status, r.provider_ref, r.completed_at = "success", provider_ref[:80], timezone.now()
    r.save(update_fields=["status", "provider_ref", "completed_at"])
    _refund_sent(r)
    bookings.event(
        r.booking,
        "refund",
        f"Refund {kes(r.amount)} marked as sent{' (' + provider_ref + ')' if provider_ref else ''}",
        actor=actor,
    )
    from apps.safety.models import Alert
    from apps.safety.services import resolve

    for alert in Alert.objects.filter(
        kind="payment",
        booking=r.booking,
        status__in=("open", "acknowledged"),
        summary__startswith=f"Refund to send: {kes(r.amount)} ",
    ):
        resolve(alert, actor, f"Refund sent{' (' + provider_ref + ')' if provider_ref else ''}")
    # Instant refunds were already announced in the cancellation SMS; a manual one gets its own receipt.
    sw = r.booking.lang == "sw"
    destination = {
        "mpesa_b2c": "M-Pesa yako" if sw else "your M-Pesa",
        "card": "kadi yako" if sw else "your card",
    }.get(r.method, "akaunti yako" if sw else "you")
    reference = f" (ref {provider_ref})" if provider_ref else ""
    bookings.send_guest(
        r.booking, "refund_sent", amount=kes(r.amount), destination=destination, reference_line=reference
    )
    return r


def _refund_sent(r):
    _apply_refund(r.booking, r.amount)
    from .invoices import sync_credit_notes

    try:
        sync_credit_notes(r.booking, refund=r)
    except Exception:
        log.exception("credit note for refund %s failed", r.pk)


def _apply_refund(b, amount):
    b = Booking.objects.get(pk=b.pk)
    b.amount_refunded += amount
    bookings.update_payment_status(b, save=False)
    if b.status == "refund_due" and b.amount_refunded >= b.amount_paid:
        b.status = "cancelled"
    b.save(update_fields=["amount_refunded", "payment_status", "status", "updated_at"])


def record_manual_payment(booking, amount, method="cash", reference="", actor=None):
    """Amina took cash / a bank transfer at the door."""
    p = Payment.objects.create(
        booking=booking,
        amount=int(amount),
        method=method,
        purpose="balance" if booking.amount_paid else "full",
        phone=booking.guest.phone,
        provider="manual",
        created_by=actor,
    )
    return on_success(p, provider_ref=reference or f"{method.upper()}-{p.pk}")


# ---------- reconciliation ----------


def reconcile_pending():
    """Ask the provider about prompts and card checkouts with no callback after 2 minutes; expire old ones."""
    cutoff = timezone.now() - timedelta(minutes=2)
    mpesa = Payment.objects.filter(status="pending", method="mpesa", created_at__lt=cutoff).exclude(
        provider__in=("c2b", "manual")
    )
    for p in mpesa.order_by("created_at")[:20]:
        reconcile_payment(p)
    if settings.PAYSTACK_SECRET_KEY:
        cards = Payment.objects.filter(status="pending", method="card", provider="paystack", created_at__lt=cutoff)
        for p in cards.order_by("created_at")[:20]:
            reconcile_payment(p)
    if settings.STRIPE_SECRET_KEY:
        _reconcile_stripe()


def _reconcile_stripe(limit=20):
    """Stripe Checkout payments nobody has confirmed yet: every run for their first quarter hour, then every
    15 minutes until the session's day is over (newest first, at most `limit` lookups a run)."""
    now = timezone.now()
    pending = Payment.objects.filter(
        status="pending", method="card", provider="stripe", created_at__lt=now - timedelta(minutes=1)
    )
    asked = 0
    for p in pending.order_by("-created_at")[:200]:
        age = now - p.created_at
        if age > timedelta(hours=26):  # sessions last 24 hours at most: it was never paid
            on_failure(p, NO_CONFIRMATION)
            continue
        if asked >= limit:
            continue
        every = 100 if age < timedelta(minutes=15) else 15 * 60
        if cache.add(f"stripe-poll:{p.pk}", 1, every):
            settle_stripe(p, StripeCard().query(p))
            asked += 1


def reconcile_payment(p):
    """Ask the provider about one pending payment and settle it if the answer is final."""
    if p.method == "card":
        if p.provider == "paystack":
            settle_card(p, PaystackCard().query(p))
        elif p.provider == "stripe":
            settle_stripe(p, StripeCard().query(p))
        return
    res = mpesa_provider().query(p) if p.transaction_id else None
    code = str((res or {}).get("ResultCode", "")).strip()
    if code and code != "None":  # still processing: Daraja answers with an errorCode and no ResultCode
        on_mpesa_result(p, code, desc=(res or {}).get("ResultDesc", ""), raw=res)
    elif p.created_at < timezone.now() - timedelta(minutes=30):
        on_failure(p, NO_CONFIRMATION)


def _wrong_currency(p, currency, provider, raw):
    from apps.safety.services import raise_alert

    on_failure(p, f"Paid in {currency}, expected KES", raw=raw)
    raise_alert(
        "payment",
        f"Card payment for {p.booking.ref} was made in {currency}, not KES - check it in {provider}.",
        severity="high",
        booking=p.booking,
        dedupe=f"currency:{p.pk}",
    )


def settle_card(p, res):
    """Apply Paystack's Verify Transaction answer: only a verified success, in KES, for the full amount counts."""
    data = res.get("data") if isinstance(res, dict) and res.get("status") else None
    if not isinstance(data, dict):
        if p.created_at < timezone.now() - timedelta(hours=24):
            on_failure(p, NO_CONFIRMATION)
        return p
    state = data.get("status")
    if state == "success":
        currency = str(data.get("currency") or "KES").upper()
        if currency != "KES":
            _wrong_currency(p, currency, "Paystack", data)
            return p
        on_success(
            p,
            transaction_id=str(data.get("id") or "") or None,
            provider_ref=str(data.get("reference") or p.checkout_token or ""),
            raw=data,
            amount=int(data.get("amount") or 0) / 100,
        )
    elif state in ("failed", "reversed"):
        on_failure(p, str(data.get("gateway_response") or f"card payment {state}"), raw=data)
    elif state == "abandoned" and p.created_at < timezone.now() - timedelta(minutes=30):
        on_failure(p, "card checkout not completed", raw=data)
    return p


STRIPE_FIELDS = ("id", "status", "payment_status", "amount_total", "currency", "payment_intent")


def settle_stripe(p, session):
    """Apply a Stripe Checkout Session, whether from the webhook, the guest coming back or the scheduler: only a
    complete, paid session for this payment, in KES and for the full amount counts; an expired one ends the attempt.
    on_success settles once, so it doesn't matter which of the three gets here first."""
    s = session
    if not isinstance(s, dict) or s.get("object") != "checkout.session":
        if p.created_at < timezone.now() - timedelta(hours=26):  # a session lasts 24 hours at most
            on_failure(p, NO_CONFIRMATION)
        return p
    if s.get("client_reference_id") != p.checkout_token:
        log.warning("Stripe session %s doesn't belong to payment %s", s.get("id"), p.pk)
        return p
    intent = s.get("payment_intent")
    intent = str((intent.get("id") if isinstance(intent, dict) else intent) or "")
    summary = {**{k: s.get(k) for k in STRIPE_FIELDS}, "payment_intent": intent or None}
    state, paid = s.get("status"), s.get("payment_status")
    if state == "complete" and paid in ("paid", "no_payment_required"):
        currency = str(s.get("currency") or "").upper()
        if currency != "KES":
            _wrong_currency(p, currency or "an unknown currency", "Stripe", summary)
            return p
        on_success(
            p,
            transaction_id=intent or None,
            provider_ref=(intent or str(s.get("id") or ""))[:80],
            raw=summary,
            amount=int(s.get("amount_total") or 0) / 100,
        )
    elif state == "expired":
        on_failure(p, "card checkout not completed", raw=summary)
    return p


def check_stripe(p, every=3):
    """Ask Stripe about a pending Checkout payment right now (the guest is back on our page), at most once every
    `every` seconds per payment however often the page asks, and settle it if it's done."""
    if p.provider != "stripe" or p.status != "pending" or not cache.add(f"stripe-check:{p.pk}", 1, every):
        return p
    settle_stripe(p, StripeCard().query(p))
    p.refresh_from_db()
    return p


# ---------- host ledger ----------


def outstanding_balances():
    """Confirmed and in-house stays that still owe money, the soonest due first (due = the balance due date)."""
    s, t = SiteSettings.load(), today()
    qs = Booking.objects.filter(
        status__in=("confirmed", "checked_in"), total__gt=F("amount_paid") - F("amount_refunded")
    ).select_related("guest", "unit")
    rows = []
    for b in qs:
        if b.balance_due <= 0:
            continue
        due_on = b.check_in - timedelta(days=s.balance_due_days)
        rows.append(
            {
                "ref": b.ref,
                "guest": b.guest.display_name,
                "phone": b.guest.phone,
                "unit": b.unit.name,
                "check_in": b.check_in,
                "balance_due": b.balance_due,
                "due_on": due_on,
                "overdue": t > due_on,
            }
        )
    rows.sort(key=lambda r: (r["due_on"], r["check_in"], r["ref"]))
    return rows


def month_bounds(month):
    """'2026-11' -> (start, end) as aware Kenya-time datetimes. Raises ValueError for anything else."""
    year, mon = (int(x) for x in str(month).split("-"))
    start = timezone.make_aware(datetime(year, mon, 1))
    return start, timezone.make_aware(datetime(year + mon // 12, mon % 12 + 1, 1))


LEDGER_COLUMNS = ["date", "ref", "guest", "phone", "method", "purpose", "receipt", "gross", "refunded", "net", "status"]


def ledger_rows(start, end):
    """Money in (payments received) and out (refunds sent) between start and end, by the day it moved."""
    when = Q(completed_at__gte=start, completed_at__lt=end) | Q(
        completed_at__isnull=True, created_at__gte=start, created_at__lt=end
    )
    rows = []
    for p in Payment.objects.filter(when, status="success").select_related("booking", "booking__guest"):
        g, at = p.booking.guest, p.completed_at or p.created_at
        method = p.get_method_display() + (" Paybill" if p.provider == "c2b" else "")
        rows.append(
            (
                at,
                [
                    timezone.localtime(at).date().isoformat(),
                    p.booking.ref,
                    g.display_name,
                    p.phone or g.phone,
                    method,
                    p.get_purpose_display(),
                    p.provider_ref,
                    p.amount,
                    0,
                    p.amount,
                    "paid",
                ],
            )
        )
    for r in Refund.objects.filter(when, status="success").select_related("booking", "booking__guest"):
        g, at = r.booking.guest, r.completed_at or r.created_at
        rows.append(
            (
                at,
                [
                    timezone.localtime(at).date().isoformat(),
                    r.booking.ref,
                    g.display_name,
                    g.phone,
                    r.get_method_display(),
                    "Refund",
                    r.provider_ref,
                    0,
                    r.amount,
                    -r.amount,
                    "refunded",
                ],
            )
        )
    return [row for _, row in sorted(rows, key=lambda x: x[0])]
