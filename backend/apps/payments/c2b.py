"""Lipa na M-Pesa Paybill / Till (Daraja C2B): the fallback when an M-Pesa prompt can't reach the phone.

Guests pay into the Paybill with their booking ref as the account number. Daraja calls validation (only when
Safaricom has enabled external validation on the shortcode) and then confirmation. The account number is
normalised (upper case, spaces and hyphens stripped) and matched to a booking ref, and TransID is unique, so a
repeated confirmation is a no-op. A match becomes a Payment(provider "c2b") settled through the normal on_success
path: a hold confirms, a balance goes down, anything over the bill is queued for refund. A payment that matches
nothing - or is too short to confirm a hold - waits in the host's "Unmatched payments" queue, and "I've paid,
here's my code" (web, or SMS PAID <code>) either finds it or asks Amina to.
"""

import logging
import os
import re
import secrets
import string
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import httpx
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.bookings import services as bookings
from apps.bookings.models import Booking
from apps.core.activity import record
from apps.core.utils import kes, normalize_phone
from apps.messaging import services as messaging

from . import services
from .models import C2BTransaction, Payment
from .providers import DarajaMpesa, PaymentError, _callback_base, callback_secret, tunnel_host

log = logging.getLogger("amina.payments")

CODE = re.compile(r"^[A-Z0-9]{8,12}$")
BAD_CODE = (
    "That doesn't look like an M-Pesa code - it's the 10 letters and numbers at the start of your M-Pesa SMS, "
    "e.g. SKL3X7QW2P."
)
# Safaricom's production rules for C2B URLs: "Avoid keywords such as M-PESA, Safaricom, exe, exec, cmd, SQL, query"
BANNED_URL_WORDS = ("mpesa", "m-pesa", "safaricom", "exe", "exec", "cmd", "sql", "query")
# an STK prompt settled by STK Query (no receipt in the answer) and a Paybill notice this close are the same money
ECHO_WINDOW = timedelta(minutes=30)


def c2b_urls():
    """{"validation": url, "confirmation": url}: what Daraja must call (register them, list them for Amina)."""
    base, secret = f"{_callback_base()}/api/payments/daraja/c2b", callback_secret()
    return {"validation": f"{base}/validation/{secret}", "confirmation": f"{base}/confirmation/{secret}"}


def c2b_shortcode():
    """The Paybill/Till guests pay into: MPESA_SHORTCODE, else the shortcode the M-Pesa prompts use."""
    return str(
        getattr(settings, "MPESA_SHORTCODE", "") or os.environ.get("MPESA_SHORTCODE", "") or settings.DARAJA_SHORTCODE
    ).strip()


def register_c2b_urls(shortcode=None):
    """Register our validation and confirmation URLs for the shortcode with Daraja (POST /mpesa/c2b/v2/registerurl).
    Returns {"shortcode", "urls", "response"}. Raises PaymentError when Daraja isn't configured or says no."""
    shortcode = str(shortcode or c2b_shortcode()).strip()
    missing = [
        name
        for name, value in (
            ("DARAJA_CONSUMER_KEY", settings.DARAJA_CONSUMER_KEY),
            ("DARAJA_CONSUMER_SECRET", settings.DARAJA_CONSUMER_SECRET),
            ("MPESA_SHORTCODE (or DARAJA_SHORTCODE)", shortcode),
        )
        if not value
    ]
    if missing:
        raise PaymentError(f"Daraja isn't configured - set {', '.join(missing)}.")
    urls = c2b_urls()
    production = settings.DARAJA_ENV == "production"
    if not urls["confirmation"].startswith("https://"):
        example = "your site's own https:// domain" if production else "e.g. https://abc123.ngrok-free.app"
        raise PaymentError(f"Daraja only calls public HTTPS addresses - set PUBLIC_URL ({example}).")
    if production:
        for url in urls.values():
            _check_production_url(url)
    daraja = DarajaMpesa()
    body = {
        "ShortCode": shortcode,
        "ResponseType": "Completed",  # if our validation URL can't be reached, Safaricom completes the payment
        "ConfirmationURL": urls["confirmation"],
        "ValidationURL": urls["validation"],
    }
    try:
        r = daraja._post("/mpesa/c2b/v2/registerurl", body)
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise PaymentError(f"Daraja is unreachable ({e})") from e
    if not isinstance(data, dict) or str(data.get("ResponseCode", "")) not in ("0", "00000000"):
        detail = (data.get("errorMessage") or data.get("ResponseDescription")) if isinstance(data, dict) else data
        raise PaymentError(f"Daraja didn't register the URLs: {detail or f'HTTP {r.status_code}'}")
    return {"shortcode": shortcode, "urls": urls, "response": data}


def _check_production_url(url):
    """Safaricom's production rules: your own domain (URL testers such as ngrok are blocked) and none of the words
    its filter rejects."""
    if tunnel_host(url):
        raise PaymentError(
            f"Safaricom blocks tunnel hosts like {urlsplit(url).hostname} in production - set PUBLIC_URL to your own "
            "https:// domain."
        )
    banned = [word for word in BANNED_URL_WORDS if word in url.lower()]
    if banned:
        raise PaymentError(
            f"Safaricom rejects C2B URLs containing {' or '.join(repr(w) for w in banned)}: {url} - change PUBLIC_URL "
            "or DARAJA_CALLBACK_SECRET (a hex secret is always safe)."
        )


def normalise_ref(text):
    """'ams 4821', 'AMS-4821', '4821' -> 'AMS-4821'."""
    s = re.sub(r"[^A-Z0-9]", "", str(text or "").upper()).removeprefix("AMS")
    return f"AMS-{s}" if s else ""


def find_booking(bill_ref):
    ref = normalise_ref(bill_ref)
    return Booking.objects.filter(ref=ref).select_related("guest", "unit").first() if ref else None


def due_now(b):
    """What the guest needs to pay now: the rest of the deposit (or total) on a hold, otherwise the balance."""
    if b.status in ("held", "expired"):
        return max(0, b.amount_due_now - b.amount_paid)
    return b.balance_due


def _amount(value):
    try:
        return round(float(str(value).replace(",", "")))
    except (TypeError, ValueError, OverflowError):
        return 0


def _when(value):
    """Daraja's TransTime, e.g. '20261125223000' (Kenya time)."""
    try:
        return timezone.make_aware(datetime.strptime(str(value), "%Y%m%d%H%M%S"))
    except (TypeError, ValueError):
        return None


def _problem(b, amount):
    """Why a payment shouldn't be applied to this booking without Amina looking at it (None = apply it)."""
    if b.status in ("held", "expired"):  # an expired hold follows the usual late-payment rules
        due = due_now(b)
        return f"Short payment for {b.ref}: {kes(amount)} received, {kes(due)} due" if amount < due else None
    if b.status in ("confirmed", "checked_in") or (b.status == "completed" and b.balance_due > 0):
        return None
    return f"{b.ref} is {b.get_status_display().lower()} - nothing to pay"


def _purpose(b, amount):
    if b.status in ("held", "expired"):
        return "deposit" if b.payment_plan == "deposit" and b.amount_paid + amount < b.total else "full"
    return "balance"


# ---------- Daraja callbacks ----------


def validate(payload):
    """Daraja validation: '0' accepts; C2B00012 (invalid account) / C2B00013 (invalid amount) reject the payment
    before the guest's money moves."""
    amount = _amount(payload.get("TransAmount"))
    if amount <= 0:
        return "C2B00013"
    b = find_booking(payload.get("BillRefNumber"))
    if b is None or b.status == "expired" or (b.status == "held" and not b.hold_active):
        return "C2B00012"
    if b.status == "held":
        return "C2B00013" if amount < due_now(b) else "0"
    return "C2B00012" if _problem(b, amount) else "0"


def receive(payload):
    """Daraja confirmation: record it once (TransID is unique), then match and settle it. Returns the
    C2BTransaction, or None for a payload without a transaction id or amount."""
    trans_id = re.sub(r"[^A-Z0-9]", "", str(payload.get("TransID") or "").upper())[:32]
    amount = _amount(payload.get("TransAmount"))
    if not trans_id or amount <= 0:
        return None
    existing = C2BTransaction.objects.filter(trans_id=trans_id).first()
    if existing:
        return existing
    names = (payload.get(k) for k in ("FirstName", "MiddleName", "LastName"))
    try:
        with transaction.atomic():
            t = C2BTransaction.objects.create(
                trans_id=trans_id,
                amount=amount,
                phone=(normalize_phone(payload.get("MSISDN")) or str(payload.get("MSISDN") or ""))[
                    :80
                ],  # may be masked
                payer_name=" ".join(str(n).strip() for n in names if n)[:120],
                bill_ref=str(payload.get("BillRefNumber") or "").strip()[:40],
                shortcode=str(payload.get("BusinessShortCode") or "")[:12],
                trans_time=_when(payload.get("TransTime")),
                raw=payload,
            )
    except IntegrityError:  # the same confirmation delivered twice at once
        return C2BTransaction.objects.get(trans_id=trans_id)
    # an M-Pesa prompt paid into the same shortcode can be echoed here too: never count the money twice
    prompt = Payment.objects.filter(provider_ref=trans_id, status="success").exclude(provider="c2b").first()
    b = find_booking(t.bill_ref)
    guessed = False
    if prompt is None and b is not None:
        prompt = _settled_without_receipt(b, t)
        guessed = prompt is not None  # matched by amount and time, not by M-Pesa code
    if prompt:
        C2BTransaction.objects.filter(pk=t.pk).update(
            status="matched",
            booking_id=prompt.booking_id,
            payment_id=prompt.pk,
            matched_at=timezone.now(),
            note="Counted once with an M-Pesa prompt of the same amount and time"
            if guessed
            else "Already received as an M-Pesa prompt payment",
        )
        if guessed:
            services.flag_same_money(prompt.booking, prompt, trans_id)
    elif b is None:
        _hold_for_review(t, f"No booking matches account '{t.bill_ref}'" if t.bill_ref else "No account number")
    else:
        apply(t, b, strict=True)
    t.refresh_from_db()
    return t


def _settled_without_receipt(b, t):
    """The prompt this Paybill notice echoes when STK Query settled it (Query answers carry no M-Pesa receipt): a
    Daraja prompt for the same booking and amount, sent within ECHO_WINDOW of the payment and still without a
    receipt. Its receipt is filled in here; the claim is atomic, so one notice completes one prompt."""
    when = t.trans_time or timezone.now()
    candidates = Payment.objects.filter(
        booking=b,
        provider="daraja",
        status="success",
        provider_ref="",
        amount=t.amount,
        created_at__range=(when - ECHO_WINDOW, when + ECHO_WINDOW),
    )
    for p in candidates.order_by("-id"):
        if Payment.objects.filter(pk=p.pk, provider_ref="").update(provider_ref=t.trans_id, updated_at=timezone.now()):
            return p
    return None


def apply(t, booking, *, actor=None, strict=False):
    """Credit a Paybill payment to a booking through on_success. strict (automatic matching and guest claims)
    leaves a short payment on a hold - or money for a booking that can't take it - for Amina to review.
    Returns the Payment, or None when it wasn't applied."""
    actor = actor if getattr(actor, "pk", None) else None
    with transaction.atomic():
        t = C2BTransaction.objects.select_for_update().get(pk=t.pk)
        if t.status == "matched":
            return t.payment if t.booking_id == booking.pk else None
        b = Booking.objects.select_related("guest").get(pk=booking.pk)
        problem = _problem(b, t.amount) if strict else None
        if problem:
            t.booking, t.note = b, problem[:200]
            t.save(update_fields=["booking", "note"])
        else:
            p = Payment.objects.create(
                booking=b,
                amount=t.amount,
                method="mpesa",
                purpose=_purpose(b, t.amount),
                phone=(normalize_phone(t.phone) or "")[:20],
                provider="c2b",
                transaction_id=t.trans_id,
                provider_ref=t.trans_id,  # the M-Pesa code stays on the payment whoever settles it
                created_by=actor,
            )
            t.status, t.booking, t.payment, t.matched_by, t.matched_at, t.note = (
                "matched",
                b,
                p,
                actor,
                timezone.now(),
                "",
            )
            t.save()
    if problem:
        _hold_for_review(t, problem, booking=b)
        return None
    _close_alerts(t.trans_id, b, actor)
    if _pays_for_a_change(b, p):
        return p
    services.on_success(p, provider_ref=t.trans_id, raw={"c2b": t.raw})
    return p


def _close_alerts(code, booking, actor=None):
    """Once a Paybill payment is applied, the "needs matching" / "guest says they paid" alerts about it are done."""
    from apps.safety.models import Alert
    from apps.safety.services import resolve

    for alert in Alert.objects.filter(kind="payment", status__in=("open", "acknowledged"), summary__contains=code):
        resolve(alert, actor, f"M-Pesa {code} matched to {booking.ref}")


def _pays_for_a_change(b, p):
    """A pending date change gets first call on the money: bookings.attach_change_payment(booking, payment) links
    the payment to the change and applies it, returning True. If it can't (or fails), the normal allocation runs,
    so the money is never left unsettled."""
    hook = getattr(bookings, "attach_change_payment", None)
    if hook is None:
        return False
    try:
        return bool(hook(b, p))
    except Exception:
        log.exception("attach_change_payment failed for payment %s on %s", p.pk, b.ref)
        return False


def _hold_for_review(t, note, booking=None):
    from apps.safety.services import raise_alert

    C2BTransaction.objects.filter(pk=t.pk).update(note=note[:200])
    record(
        "payment",
        f"Unmatched Paybill payment {kes(t.amount)} ({t.trans_id}): {note}",
        booking=booking,
        amount=t.amount,
        trans_id=t.trans_id,
    )
    raise_alert(
        "payment",
        f"Paybill payment {kes(t.amount)} ({t.trans_id}, account '{t.bill_ref or '-'}') needs matching: {note}. "
        "See Payments.",
        severity="high",
        booking=booking,
        dedupe=f"c2b:{t.trans_id}",
    )


# ---------- the host's queue ----------


def unmatched_rows(limit=100):
    return [
        {
            "id": t.pk,
            "trans_id": t.trans_id,
            "amount": t.amount,
            "phone": t.phone,
            "bill_ref": t.bill_ref,
            "received_at": t.trans_time or t.received_at,
            "payer": t.payer_name,
            "note": t.note,
            "booking": t.booking.ref if t.booking_id else None,
        }
        for t in C2BTransaction.objects.filter(status="unmatched").select_related("booking")[:limit]
    ]


def match(t, ref, *, actor=None):
    """Amina applies a queued payment to the booking it was meant for (no amount checks: her call)."""
    b = find_booking(ref)
    if b is None:
        raise PaymentError("No booking has that ref - check it and try again.")
    if t.status == "matched":
        raise PaymentError(f"That payment is already matched to {t.booking.ref if t.booking_id else 'a booking'}.")
    p = apply(t, b, actor=actor)
    if p is None:
        raise PaymentError("That payment has just been matched to another booking.")
    record("payment", f"Paybill payment {t.trans_id} ({kes(t.amount)}) matched to {b.ref}", booking=b, actor=actor)
    return p


# ---------- "I've paid - here's my M-Pesa code" ----------


def claim(booking, code, *, channel="web", actor=None):
    """Returns {"status": "matched" | "pending_review", "message"}. Raises PaymentError for a malformed code."""
    code = re.sub(r"[^A-Za-z0-9]", "", str(code or "")).upper()
    if not CODE.match(code):
        raise PaymentError(BAD_CODE)
    b = Booking.objects.select_related("guest", "unit").get(pk=booking.pk)
    lang = "en" if channel == "web" else b.lang
    found = b.payments.filter(status="success").filter(Q(provider_ref=code) | Q(transaction_id=code)).first()
    t = C2BTransaction.objects.filter(trans_id=code).select_related("booking").first()
    if not found and t and t.status == "unmatched" and t.booking_id in (None, b.pk):
        found = apply(t, b, actor=actor, strict=True)
    if not found and not t:
        found = _ask_about_open_prompts(b)
    if found:
        bookings.event(b, "payment_claim", f"M-Pesa code {code} from the guest matched a payment", channel)
        return {
            "status": "matched",
            "message": messaging.render("payment_claim_matched", lang, code=code, amount=kes(found.amount), ref=b.ref),
        }
    from apps.safety.services import raise_alert

    detail = ""
    if t and t.booking_id and t.booking_id != b.pk:
        detail = f" That code was paid to account '{t.bill_ref}' ({t.booking.ref})."
    elif t and t.note:
        detail = f" {t.note}."
    bookings.event(b, "payment_claim", f"Guest says they paid with M-Pesa code {code} - waiting to be matched", channel)
    raise_alert(
        "payment",
        f"{b.guest.display_name} says {b.ref} was paid with M-Pesa code {code}, but it isn't matched yet.{detail} "
        "Check the M-Pesa statement and match it under Payments.",
        severity="high" if b.status == "held" else "medium",
        booking=b,
        source=channel,
        dedupe=f"claim:{b.ref}:{code}",
    )
    return {"status": "pending_review", "message": messaging.render("payment_claim_review", lang, code=code, ref=b.ref)}


def _ask_about_open_prompts(b):
    """A prompt the guest paid whose callback never arrived: ask M-Pesa now rather than wait for the scheduler."""
    for p in b.payments.filter(status="pending", method="mpesa").exclude(transaction_id=None)[:2]:
        services.reconcile_payment(p)
        p.refresh_from_db()
        if p.status == "success":
            return p
    return None


# ---------- Demo Lab ----------


def _new_code():
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "S" + "".join(secrets.choice(alphabet) for _ in range(9))
        if not C2BTransaction.objects.filter(trans_id=code).exists():
            return code


def simulate(ref, *, amount=None, phone=None):
    """A Paybill confirmation exactly as Daraja would send it (amount defaults to what's due now)."""
    b = find_booking(ref)
    if amount in (None, ""):
        if b is None:
            raise PaymentError("Give an amount for a payment that doesn't match a booking.")
        amount = due_now(b)
    amount = _amount(amount)
    if amount <= 0:
        raise PaymentError("There's nothing left to pay." if b else "Enter the amount paid.")
    msisdn = normalize_phone(phone) if phone else (b.guest.phone if b else "+254700000000")
    if not msisdn:
        raise PaymentError("Enter a valid phone number.")
    first, _, last = ((b.guest.name if b else "") or "Demo Guest").partition(" ")
    return receive(
        {
            "TransactionType": "Pay Bill",
            "TransID": _new_code(),
            "TransTime": timezone.localtime().strftime("%Y%m%d%H%M%S"),
            "TransAmount": f"{amount}.00",
            "BusinessShortCode": services.paybill_number() or "174379",
            "BillRefNumber": ref,
            "MSISDN": msisdn.lstrip("+"),
            "FirstName": first,
            "LastName": last,
        }
    )
