"""Booking lifecycle shared by every channel (web, USSD, SMS, voice, host console):

hold → pay → confirm → pre-arrival → directions → door code → stay → checkout → review
"""

import logging
import re
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.activity import record
from apps.core.models import OnceMarker, SiteSettings
from apps.core.utils import at_local, daterange, first_name, is_kenyan, kes, nice_date, nice_time, today
from apps.messaging import services as messaging
from apps.properties.models import Unit
from apps.properties.services import from_price, is_available
from apps.properties.services import quote as price_quote

from . import locks
from .models import (
    ACTIVE_STATUSES,
    Addon,
    Booking,
    BookingAddon,
    BookingEvent,
    BookingGuest,
    ChangeRequest,
    Waitlist,
)

log = logging.getLogger("amina.bookings")

CHANNEL_LABEL = dict(Booking.CHANNELS)
BREAKFAST_STYLES = {
    "swahili": "Swahili (mahamri, chai, mbaazi, fruit)",
    "continental": "Continental",
    "english": "Full English",
    "vegetarian": "Vegetarian / vegan",
}
RISK_LABELS = {
    "one_night_weekend": "One-night weekend stay",
    "same_day": "Same-day booking",
    "last_minute": "Booked for tomorrow",
    "new_guest": "First stay with us",
    "full_occupancy": "At maximum occupancy",
    "previous_incident": "Previous incident on record",
}


class BookingError(Exception):
    def __init__(self, message="", code=None):
        super().__init__(message)
        self.code = code  # machine-readable reason where the caller needs one ("available", "unavailable")


# ---------- helpers ----------


def event(booking, kind, text, channel="", actor=None, **data):
    BookingEvent.objects.create(
        booking=booking,
        kind=kind,
        text=text[:300],
        channel=channel or "",
        actor=actor if getattr(actor, "pk", None) else None,
        data=data,
    )


def trip_link(booking):
    return f"{settings.FRONTEND_URL}/trips/{booking.ref}"


def dates_text(check_in, check_out, lang="en"):
    return f"{nice_date(check_in, lang)} - {nice_date(check_out, lang)}"


def _addon(booking, code, statuses=("confirmed", "fulfilled")):
    return booking.addons.filter(addon__code=code, status__in=statuses).select_related("addon").first()


HHMM = re.compile(r"([01]?\d|2[0-3]):[0-5]\d")


def _extra_time(ba):
    """The time an approved early check-in / late checkout gives: what the guest asked for, else the time the extra
    itself offers (Addon.options["time"], e.g. late checkout until 14:00) - a request left blank still counts."""
    if ba is None:
        return None
    options = ba.addon.options or {}
    for value in ((ba.details or {}).get("time"), options.get("time"), options.get("default_time")):
        value = str(value or "").strip()
        if HHMM.fullmatch(value):
            return value
    return None


def effective_checkin_time(booking):
    return _extra_time(_addon(booking, "early_checkin")) or booking.unit.effective_checkin()


def effective_checkout_time(booking):
    return _extra_time(_addon(booking, "late_checkout")) or booking.unit.effective_checkout()


REVEAL_BEFORE = timedelta(hours=48)
REVEAL_LATER = {  # what templates say instead, before the reveal
    "en": {
        "wifi": "shared 2 days before you arrive",
        "directions": "Full directions are shared 2 days before you arrive.",
    },
    "sw": {
        "wifi": "itatumwa siku 2 kabla ya kufika",
        "directions": "Maelekezo kamili yatatumwa siku 2 kabla ya kufika.",
    },
}


def details_reveal_at(booking):
    """When a confirmed stay's arrival details (Wi-Fi, directions, landmark, parking) open up: 48 hours before
    check-in. The trip page, SMS answers and every message template share this rule."""
    return at_local(booking.check_in, effective_checkin_time(booking)) - REVEAL_BEFORE


def details_visible(booking, now=None):
    if booking.status == "checked_in":
        return True
    return booking.status == "confirmed" and (now or timezone.now()) >= details_reveal_at(booking)


# How to pay, in the guest's words: an M-Pesa prompt only where one really goes out (M-Pesa on, a Kenyan number)
PAY_WORDS = {
    "en": {
        "both": "M-Pesa or card",
        "card": "card",
        "prompt": "Check your phone for an M-Pesa prompt or pay here",
        "link": "Pay by card here",
        "reply_prompt": "Reply PAY for an M-Pesa prompt or pay here",
        "reply_link": "Reply PAY for a card payment link or pay here",
    },
    "sw": {
        "both": "M-Pesa au kadi",
        "card": "kadi",
        "prompt": "Angalia ombi la M-Pesa au lipa hapa",
        "link": "Lipa kwa kadi hapa",
        "reply_prompt": "Jibu PAY kupata ombi la M-Pesa au lipa hapa",
        "reply_link": "Jibu PAY kupata kiungo cha kulipa kwa kadi au lipa hapa",
    },
}


def pay_words(phone, lang):
    from apps.payments.services import can_prompt

    w, prompt = PAY_WORDS.get(lang, PAY_WORDS["en"]), can_prompt(phone)
    return {
        "pay_by": w["both" if prompt else "card"],
        "pay_prompt": w["prompt" if prompt else "link"],
        "reply_pay": w["reply_prompt" if prompt else "reply_link"],
    }


def guest_context(booking, *, reveal=False):
    """Everything a message template or knowledge-base answer may mention about this stay. Wi-Fi, directions,
    landmark and parking follow the trip page's reveal (details_visible) unless `reveal` (Amina sending them)."""
    u, g, lang = booking.unit, booking.guest, booking.lang
    s = SiteSettings.load()
    code = booking.access_codes.filter(revoked_at__isnull=True, sent_at__isnull=False).first()
    breakfast = _addon(booking, "breakfast", ("requested", "confirmed", "fulfilled"))
    ctx = {
        "first_name": first_name(g.name),
        "name": g.name or "",
        "unit": u.name,
        "area": u.area.name,
        "ref": booking.ref,
        "dates": dates_text(booking.check_in, booking.check_out, lang),
        "check_in": nice_date(booking.check_in, lang),
        "check_out": nice_date(booking.check_out, lang),
        "nights": booking.nights,
        "s": "s" if booking.nights != 1 else "",
        "total": kes(booking.total),
        "paid": kes(booking.amount_paid),
        "balance": kes(booking.balance_due),
        "due_date": nice_date(booking.check_in - timedelta(days=s.balance_due_days), lang),
        "checkin_time": nice_time(effective_checkin_time(booking)),
        "checkout_time": nice_time(effective_checkout_time(booking)),
        "trip_link": trip_link(booking),
        "tips": u.local_tips or u.area.tips,
        "taxi": settings_taxi(),
        "status": booking.get_status_display(),
        "breakfast": breakfast_summary(breakfast) if breakfast else "",
        **pay_words(g.phone, lang),
    }
    if booking.status in ("confirmed", "checked_in"):
        ctx.update(map_link=u.map_link, address=u.address)  # on the trip page from confirmation
        if reveal or details_visible(booking):
            ctx.update(
                wifi=f"{u.wifi_name} / {u.wifi_password}" if u.wifi_name else "",
                directions=u.directions,
                landmark=u.landmark,
                parking=u.parking,
            )
        else:
            later = REVEAL_LATER.get(lang, REVEAL_LATER["en"])
            ctx.update(
                wifi=later["wifi"] if u.wifi_name else "",
                directions=later["directions"] if u.directions else "",
                landmark=u.area.name if u.landmark else "",
                parking=later["wifi"] if u.parking else "",
            )
    if code:
        ctx.update(
            code=code.code,
            valid_from=f"{nice_date(timezone.localtime(code.valid_from).date(), lang)} {nice_time(timezone.localtime(code.valid_from).strftime('%H:%M'))}",
            valid_until=f"{nice_date(timezone.localtime(code.valid_until).date(), lang)} {nice_time(timezone.localtime(code.valid_until).strftime('%H:%M'))}",
        )
    return ctx


def settings_taxi():
    import os

    return os.environ.get("TAXI_CONTACT") or "Uber, Bolt and Little work well - or ask us for Amina's trusted driver"


def breakfast_summary(ba):
    d = ba.details or {}
    parts = [f"{ba.quantity} x {BREAKFAST_STYLES.get(d.get('style'), d.get('style', 'breakfast'))}"]
    if d.get("dietary"):
        parts.append(d["dietary"])
    if d.get("time"):
        parts.append(f"at {d['time']}")
    return ", ".join(parts)


def notify_host(text, *, booking=None, kind="host_notice"):
    return messaging.send(SiteSettings.load().host_contact, text, booking=booking, kind=kind, sender="system")


def send_guest(booking, key, *, reveal=False, **extra):
    ctx = {**guest_context(booking, reveal=reveal), **extra}
    return messaging.send(booking.guest.phone, messaging.render(key, booking.lang, **ctx), booking=booking, kind=key)


# ---------- screening ----------


def screen(unit, guest, check_in, check_out, guests):
    """Reservation screening, in the spirit of Airbnb's anti-party system — neutral, behavioural signals only."""
    flags, score = [], 0
    n, lead = (check_out - check_in).days, (check_in - today()).days
    if n == 1 and check_in.weekday() in (4, 5):
        flags.append("one_night_weekend")
        score += 25
    if lead <= 0:
        flags.append("same_day")
        score += 15
    elif lead == 1:
        flags.append("last_minute")
        score += 10
    past = Booking.objects.filter(guest=guest, status="completed").count()
    if past == 0:
        flags.append("new_guest")
        score += 10
    else:
        score -= 10
    if guests >= unit.max_guests and unit.max_guests >= 4:
        flags.append("full_occupancy")
        score += 10
    from apps.safety.models import Alert

    if Alert.objects.filter(guest=guest, kind__in=("security", "sos")).exclude(source="sos").exists() or "incident" in (
        guest.tags or []
    ):
        flags.append("previous_incident")
        score += 30
    if "vip" in [t.lower() for t in (guest.tags or [])]:
        score -= 20
    return max(0, min(100, score)), flags


# ---------- holds ----------


def _resolve_addons(unit, items, guests):
    resolved = []
    for item in items or []:
        code = item.get("code") if isinstance(item, dict) else item
        addon = Addon.objects.filter(code=code, active=True).first()
        if not addon or (addon.units.exists() and not addon.units.filter(pk=unit.pk).exists()):
            continue
        if addon.category == "breakfast" and not unit.breakfast_available:
            continue
        qty = int(
            (item.get("quantity") if isinstance(item, dict) else 0)
            or (guests if addon.pricing in ("per_guest_night", "per_guest") else 1)
        )
        resolved.append(
            {
                "addon": addon,
                "quantity": max(1, min(qty, 20)),
                "details": (item.get("details") if isinstance(item, dict) else None) or {},
            }
        )
    return resolved


def taxes(taxable, s=None):
    """Tourism levy and VAT on a taxable amount: the one formula the quote, recalc and date changes share."""
    s = s or SiteSettings.load()
    levy = round(taxable * Decimal(s.tourism_levy_percent) / 100)
    vat = round(taxable * Decimal(s.vat_percent) / 100) if s.vat_registered and s.vat_percent else 0
    return levy, vat


AGREED_PRICE = "Agreed price"  # nightly label of a stay Amina priced herself


def _spread(amount, check_in, check_out, label):
    """An amount spread over the nights in whole shillings (any remainder on the last night)."""
    nights = list(daterange(check_in, check_out))
    each = amount // len(nights)
    out = [{"date": d.isoformat(), "price": each, "label": label} for d in nights]
    out[-1]["price"] += amount - each * len(nights)
    return out


def _with_agreed_price(q, price, check_in, check_out, s):
    """The quote with Amina's agreed accommodation price instead of the listed one (no stay discount on top);
    cleaning, extras, levy and VAT follow the normal rules."""
    taxable = price + q["cleaning_fee"] + q["addons"]
    levy, vat = taxes(taxable, s)
    total = taxable + levy + vat
    deposit = -(-total * s.deposit_percent // 100)
    return {
        **q,
        "nightly": _spread(price, check_in, check_out, AGREED_PRICE),
        "accommodation": price,
        "discount": 0,
        "levy": levy,
        "vat": vat,
        "total": total,
        "deposit": deposit,
        "due_now": deposit if q["due_now"] < q["total"] else total,
    }


def _expire(qs):
    from apps.payments.models import Payment

    expired = []
    for b in qs.select_related("unit", "guest"):
        if Booking.objects.filter(pk=b.pk, status="held").update(status="expired"):
            Payment.objects.filter(booking=b, status="pending").update(status="expired")
            event(b, "expired", "Hold expired - payment not completed, unit released")
            if b.channel != "web" and OnceMarker.mark(f"hold-expired:{b.ref}"):
                send_guest(b, "hold_expired")
            expired.append(b)
    return expired


def expire_stale_holds():
    expired = _expire(Booking.objects.filter(status="held", hold_expires_at__lt=timezone.now()))
    for unit_id in {b.unit_id for b in expired}:
        notify_waitlist(Unit.objects.get(pk=unit_id))
    return expired


def create_hold(
    *,
    unit,
    guest,
    check_in,
    check_out,
    channel,
    adults=1,
    children=0,
    infants=0,
    addons=None,
    payment_plan="full",
    lang=None,
    arrival_eta="",
    arrival_mode="",
    special_requests="",
    purpose="",
    vehicle_plate="",
    occupants=None,
    actor=None,
    price_override=None,
    override_reason="",
):
    """Hold a unit while the guest pays. `price_override` (host bookings only) replaces the accommodation price
    for the whole stay - cleaning, extras, levy and VAT are added on top as usual - and needs a reason."""
    s = SiteSettings.load()
    if price_override is not None:
        if not isinstance(price_override, int) or isinstance(price_override, bool) or price_override <= 0:
            raise BookingError("Enter the price for the whole stay in KES.")
        if not (override_reason or "").strip():
            raise BookingError("Say why the price was changed - it goes on the booking's timeline.")
    if not check_in or not check_out or check_out <= check_in:
        raise BookingError("Check-out must be after check-in.")
    if check_in < today():
        raise BookingError("That check-in date has already passed.")
    if (check_in - today()).days > 540:
        raise BookingError("We take bookings up to 18 months ahead.")
    n = (check_out - check_in).days
    if n < unit.min_nights:
        raise BookingError(f"{unit.name} has a minimum stay of {unit.min_nights} nights.")
    if n > unit.max_nights:
        raise BookingError(f"{unit.name} takes stays of up to {unit.max_nights} nights.")
    guests = max(1, adults + children)
    if guests > unit.max_guests:
        raise BookingError(f"{unit.name} sleeps up to {unit.max_guests} guests.")
    if unit.status != "active":
        raise BookingError("This home isn't taking bookings right now.")
    if guest.is_blocked:
        raise BookingError("We're unable to accept this booking. Please contact us.")

    resolved = _resolve_addons(unit, addons, guests)
    try:
        with transaction.atomic():
            Unit.objects.select_for_update().filter(pk=unit.pk).first()  # serialise holds on this unit
            _expire(Booking.objects.filter(unit=unit, status="held", hold_expires_at__lt=timezone.now()))
            if not is_available(unit, check_in, check_out):
                raise BookingError("Sorry - those dates were just taken.")
            q = price_quote(unit, check_in, check_out, guests=guests, addons=resolved, payment_plan=payment_plan)
            plan = "deposit" if payment_plan == "deposit" and q["deposit_available"] else "full"
            listed = q["accommodation"] - q["discount"]
            if price_override is not None:
                q = _with_agreed_price(q, price_override, check_in, check_out, s)
            score, flags = screen(unit, guest, check_in, check_out, guests)
            booking = Booking.objects.create(
                ref=Booking.new_ref(),
                unit=unit,
                guest=guest,
                check_in=check_in,
                check_out=check_out,
                adults=max(1, adults),
                children=children,
                infants=infants,
                status="held",
                channel=channel,
                lang=lang or guest.lang,
                hold_expires_at=timezone.now() + timedelta(minutes=s.hold_minutes),
                nightly=q["nightly"],
                accommodation_amount=q["accommodation"],
                discount_amount=q["discount"],
                cleaning_fee=q["cleaning_fee"],
                addons_amount=q["addons"],
                levy_amount=q["levy"],
                vat_amount=q["vat"],
                total=q["total"],
                payment_plan=plan,
                amount_due_now=q["due_now"] if plan == "deposit" else q["total"],
                cancellation_policy=unit.cancellation_policy,
                arrival_eta=arrival_eta[:40],
                arrival_mode=arrival_mode[:10],
                special_requests=special_requests[:1000],
                purpose=purpose[:20],
                vehicle_plate=vehicle_plate.upper()[:12],
                risk_score=score,
                risk_flags=flags,
            )
            for item in resolved:
                a, qty = item["addon"], item["quantity"]
                BookingAddon.objects.create(
                    booking=booking,
                    addon=a,
                    quantity=qty,
                    unit_price=a.price,
                    total=a.price_for(n, guests, qty),
                    status="requested" if a.requires_approval else "confirmed",
                    details=item["details"],
                )
            BookingGuest.objects.create(
                booking=booking,
                full_name=guest.name or guest.phone,
                id_type=guest.id_type,
                id_number_enc=guest.id_number_enc,
                id_last4=guest.id_last4,
                nationality=guest.nationality,
                is_lead=True,
            )
            for o in occupants or []:
                if not o.get("full_name"):
                    continue
                bg = BookingGuest(
                    booking=booking,
                    full_name=o["full_name"][:80],
                    id_type=o.get("id_type", "")[:20],
                    nationality=(o.get("nationality") or "")[:2].upper(),
                    is_minor=bool(o.get("is_minor")),
                )
                if o.get("id_number"):
                    bg.set_id_number(o["id_number"])
                bg.save()
            event(
                booking,
                "held",
                f"Held via {CHANNEL_LABEL.get(channel, channel)} for {s.hold_minutes} minutes",
                channel,
                actor,
            )
            if price_override is not None:
                reason = override_reason.strip()[:120]
                event(
                    booking,
                    "price_override",
                    f"Price set to {kes(price_override)} for {n} night{'s' if n != 1 else ''} "
                    f"(listed {kes(listed)}): {reason}",
                    channel,
                    actor,
                    listed=listed,
                    price=price_override,
                    reason=reason,
                )
    except IntegrityError as e:  # the exclusion constraint caught a race between two channels
        log.info("overlap rejected by database: %s", e)
        raise BookingError("Sorry - those dates were just taken.") from e

    changed = []
    if not guest.first_channel:
        guest.first_channel = channel
        changed.append("first_channel")
    guest.last_area, guest.last_guests = unit.area.name, guests
    guest.save(update_fields=changed + ["last_area", "last_guests"])
    record(
        "booking",
        f"Hold {booking.ref}: {unit.name}, {check_in:%d %b}-{check_out:%d %b} via {CHANNEL_LABEL.get(channel, channel)}",
        channel=channel,
        booking=booking,
        actor=actor,
        total=booking.total,
    )
    return booking


# ---------- confirmation ----------


def confirm(booking, *, actor=None):
    with transaction.atomic():
        b = Booking.objects.select_for_update().select_related("unit", "guest", "unit__area").get(pk=booking.pk)
        if b.status != "held":
            return b
        b.status, b.hold_expires_at = "confirmed", None
        b.save(update_fields=["status", "hold_expires_at", "updated_at"])
        locks.create_code(b)
        event(b, "confirmed", "Booking confirmed - door code generated (sent on arrival day)", actor=actor)
        _waitlist_booked(b)
    balance_note = messaging.render("balance_note", b.lang, **guest_context(b)) if b.balance_due else ""
    send_guest(b, "booking_confirmed", balance_note=" " + balance_note if balance_note else "")
    risk = f" Screening: {', '.join(RISK_LABELS.get(f, f) for f in b.risk_flags)}." if b.risk_score >= 40 else ""
    notify_host(
        f"New booking {b.ref} via {CHANNEL_LABEL.get(b.channel, b.channel)}: {b.unit.name}, {dates_text(b.check_in, b.check_out)}, "
        f"{kes(b.total)} ({kes(b.amount_paid)} paid). Guest {b.guest.name or ''} {b.guest.phone}.{risk}",
        booking=b,
    )
    record(
        "booking",
        f"Confirmed {b.ref}: {b.unit.name} for {b.guest.display_name}",
        channel=b.channel,
        booking=b,
        actor=actor,
        total=b.total,
    )
    if b.risk_score >= 60:
        from apps.safety.services import raise_alert

        raise_alert(
            "security",
            f"High-risk reservation {b.ref} ({', '.join(RISK_LABELS.get(f, f) for f in b.risk_flags)})",
            severity="medium",
            booking=b,
            dedupe=f"risk:{b.ref}",
        )
    return b


COUNTED_ADDON_STATUSES = ("confirmed", "fulfilled")  # requested extras wait for Amina's yes before they cost anything


def _retotal(b, s=None):
    """Add the bill up again from its parts: counted extras, then levy and VAT on the gross."""
    addons_total = sum(a.total for a in b.addons.filter(status__in=COUNTED_ADDON_STATUSES))
    taxable = b.accommodation_amount - b.discount_amount + b.cleaning_fee + addons_total
    b.addons_amount = addons_total
    b.levy_amount, b.vat_amount = taxes(taxable, s)
    b.total = taxable + b.levy_amount + b.vat_amount
    update_payment_status(b, save=False)


def recalc(booking, *, reason="", actor=None):
    """Re-total after add-ons change (levy follows the gross). If the bill drops below what the guest
    has paid, the difference is queued as a refund."""
    b = booking
    _retotal(b)
    b.save(update_fields=["addons_amount", "levy_amount", "vat_amount", "total", "payment_status", "updated_at"])
    refund_overpayment(b, reason=reason or "Bill reduced after payment", actor=actor)
    return b


def update_payment_status(b, save=True):
    net = b.amount_paid - b.amount_refunded
    if b.amount_refunded and net <= 0:
        b.payment_status = "refunded"
    elif b.amount_refunded and b.status not in (*ACTIVE_STATUSES, "completed"):
        b.payment_status = "partially_refunded"  # a cancelled stay with part of the money back
    elif net >= b.total and b.total > 0:
        b.payment_status = "paid"
    elif net > 0:
        b.payment_status = "deposit_paid"
    else:
        b.payment_status = "unpaid"
    if save:
        b.save(update_fields=["payment_status", "updated_at"])


def owed(b):
    """What the guest still owes on this booking; negative when we hold more than the bill.
    Refunds already queued for Amina to send count as money handed back."""
    pending = b.refunds.filter(status="pending").aggregate(s=Sum("amount"))["s"] or 0
    return b.total - (b.amount_paid - b.amount_refunded - pending)


REFUND_QUEUED = {
    "en": "{ref}: your bill is now {total}. {amount} will be refunded to {dest}.",
    "sw": "{ref}: bili yako sasa ni {total}. {amount} zitarudishwa {dest}.",
}
REFUND_DEST = {
    "en": {"mpesa_b2c": "your M-Pesa", "card": "your card", "manual": "you"},
    "sw": {"mpesa_b2c": "kwenye M-Pesa yako", "card": "kwenye kadi yako", "manual": "kwako"},
}


def refund_overpayment(b, *, reason="", actor=None, notify=True):
    """Queue a refund (for Amina to send and mark as sent) for whatever the guest paid beyond the bill.
    Idempotent: only the part not already covered by pending refunds is added. Money that has just paid for
    a date change not applied yet is not an overpayment."""
    from apps.payments import services as payments

    if b.status not in ACTIVE_STATUSES:
        return None
    excess = -owed(b)
    if excess > 0:
        excess -= _paid_for_pending_changes(b)
    if excess <= 0:
        return None
    r = payments.refund(b, excess, reason=reason, actor=actor, queue=True)
    if not notify:
        return r
    lang = b.lang if b.lang in REFUND_QUEUED else "en"
    dest = REFUND_DEST[lang].get(r.method, REFUND_DEST[lang]["manual"])
    messaging.send(
        b.guest.phone,
        REFUND_QUEUED[lang].format(ref=b.ref, total=kes(b.total), amount=kes(excess), dest=dest),
        booking=b,
        kind="refund_queued",
    )
    return r


# ---------- cancellation ----------

POLICY_TEXT = {
    "flexible": "Full refund until 24 hours before check-in.",
    "moderate": "Full refund until 5 days before check-in, then 50%.",
    "firm": "Full refund until 30 days before check-in, 50% until 7 days before, then non-refundable.",
    "strict": "50% refund until 7 days before check-in, then non-refundable.",
}


def policy_percent(b, at=None):
    """Share of the money paid for a stay (or for nights taken off it) that the cancellation policy refunds now."""
    now = at or timezone.now()
    hours = (at_local(b.check_in, effective_checkin_time(b)) - now).total_seconds() / 3600
    policy = b.cancellation_policy
    if policy == "flexible":
        return 100 if hours >= 24 else 0
    if policy == "moderate":
        return 100 if hours >= 5 * 24 else 50 if hours > 0 else 0
    if policy == "firm":
        return 100 if hours >= 30 * 24 else 50 if hours >= 7 * 24 else 0
    return 50 if hours >= 7 * 24 else 0


def refund_quote(b, at=None):
    paid = b.amount_paid - b.amount_refunded
    if paid <= 0:
        return {
            "refund": 0,
            "percent": 0,
            "paid": 0,
            "policy": b.cancellation_policy,
            "text": "Nothing has been charged, so there's nothing to refund.",
        }
    policy = b.cancellation_policy
    pct = policy_percent(b, at)
    refund = round(paid * pct / 100)
    text = (
        f"You'll get {kes(refund)} back ({pct}% of what you paid)."
        if refund
        else "Under the cancellation policy this booking is no longer refundable."
    )
    return {
        "refund": refund,
        "percent": pct,
        "paid": paid,
        "policy": policy,
        "policy_text": POLICY_TEXT.get(policy, ""),
        "text": text,
    }


def cancel(booking, *, by, reason="", actor=None, refund_amount=None, notify=True):
    from apps.payments import services as payments

    b = Booking.objects.select_related("unit", "guest", "unit__area").get(pk=booking.pk)
    if b.status not in ("held", "confirmed"):
        raise BookingError("This booking can't be cancelled now.")
    was_paid = b.amount_paid - b.amount_refunded
    if refund_amount is not None:
        refund = max(0, min(int(refund_amount), was_paid))
    elif by == "host":
        refund = was_paid  # Amina cancelling always refunds in full
    else:
        refund = refund_quote(b)["refund"]
    with transaction.atomic():
        b.status, b.cancelled_at, b.cancelled_by, b.cancel_reason = "cancelled", timezone.now(), by, reason[:200]
        b.save(update_fields=["status", "cancelled_at", "cancelled_by", "cancel_reason", "updated_at"])
        b.addons.filter(status="requested").update(status="cancelled", decided_at=b.cancelled_at)
        locks.revoke_all(b, "cancelled")
        event(b, "cancelled", f"Cancelled by {by}{': ' + reason if reason else ''}", actor=actor)
        for c in b.changes.filter(status__in=ChangeRequest.PENDING):
            _close_change(c, "cancelled", "withdrawn - the booking was cancelled")
    if refund:
        payments.refund(b, refund, reason=f"Cancelled by {by}", actor=actor)
    airtime = 0
    if by == "host" and was_paid:
        airtime = send_goodwill(b)
    if notify:
        lang = b.lang
        refund_line = messaging.render("refund_line", lang, amount=kes(refund)) if refund else ""
        goodwill_line = messaging.render("goodwill_line", lang, airtime=airtime) if airtime else ""
        key = "cancelled_by_host" if by == "host" else "cancelled_by_guest"
        send_guest(
            b,
            key,
            refund_line=" " + refund_line if refund_line else "",
            goodwill_line=" " + goodwill_line if goodwill_line else "",
        )
        if by != "host":
            notify_host(
                f"{b.ref} ({b.unit.name}, {dates_text(b.check_in, b.check_out)}) was cancelled by the guest. Refund {kes(refund)}.",
                booking=b,
            )
    record("booking", f"Cancelled {b.ref} by {by} (refund {kes(refund)})", booking=b, actor=actor)
    notify_waitlist(b.unit)
    return {"cancelled": b.ref, "refund": refund, "goodwill_airtime": airtime}


def send_goodwill(b):
    """Airtime apology when Amina cancels a paid stay (Africa's Talking Airtime, Kenyan numbers)."""
    from apps.comms import at

    amount = SiteSettings.load().goodwill_airtime_kes
    if not amount or not is_kenyan(b.guest.phone) or not OnceMarker.mark(f"goodwill:{b.ref}"):
        return 0
    try:
        res = at.send_airtime(b.guest.phone, amount, idempotency_key=f"goodwill-{b.ref}", metadata={"ref": b.ref})
        failed = not res.get("dry_run") and int(res.get("numSent") or 0) == 0
        event(b, "airtime", f"Goodwill airtime KES {amount} {'failed' if failed else 'sent'}")
        record("system", f"Goodwill airtime KES {amount} to {b.guest.phone} for {b.ref}", booking=b)
        return 0 if failed else amount
    except Exception as e:
        log.error("airtime failed: %s", e)
        event(b, "airtime", f"Goodwill airtime failed: {e}"[:300])
        return 0


# ---------- arrival: door code ----------


def release_code(booking, *, force=False, actor=None, allow_early=False):
    """Arrival morning. Returns released | too_early | waiting_balance | waiting_id | checking_sim | security_hold
    | not_confirmed. `force` (Amina's override) skips the balance, ID and SIM checks but never the date: a code
    only goes out from check-in day (Kenya time). `allow_early` exists for the Demo Lab's time machine alone."""
    from apps.comms import simswap
    from apps.payments import services as payments

    b = Booking.objects.select_related("unit", "guest", "unit__area").get(pk=booking.pk)
    if b.status != "confirmed":
        return "not_confirmed"
    if today() < b.check_in and not allow_early:
        return "too_early"
    s = SiteSettings.load()
    if b.balance_due > 0 and not force:
        if OnceMarker.mark(f"code-wait-balance:{b.ref}"):
            send_guest(b, "code_waiting_balance")
            if payments.can_prompt(b.guest.phone):  # everyone else pays through the link in that SMS
                payments.start_payment(b, method="mpesa", purpose="balance")
        return "waiting_balance"
    if s.require_id_before_code and not b.guest.has_id and not force:
        if OnceMarker.mark(f"code-wait-id:{b.ref}"):
            send_guest(b, "code_waiting_id")
        return "waiting_id"
    if s.sim_swap_check and is_kenyan(b.guest.phone) and not force:
        state = simswap.status_for(b)
        if state == "pending":
            return "checking_sim"
        if state == "swapped":
            if OnceMarker.mark(f"simswap-hold:{b.ref}"):
                from apps.safety.services import raise_alert

                send_guest(b, "code_security_hold")
                raise_alert(
                    "security",
                    f"SIM swap detected on {b.guest.phone} before releasing the door code for {b.ref}. Call the guest to verify.",
                    severity="high",
                    booking=b,
                    dedupe=f"simswap:{b.ref}",
                )
            return "security_hold"

    code = locks.create_code(b)
    now = timezone.now()
    with transaction.atomic():
        b.status, b.code_released_at, b.checked_in_at = "checked_in", now, now
        b.save(update_fields=["status", "code_released_at", "checked_in_at", "updated_at"])
        code.sent_at = now
        code.save(update_fields=["sent_at"])
        event(b, "code_released", f"Door code released by SMS{' (released manually)' if force else ''}", actor=actor)
    send_guest(b, "checkin_code")
    if OnceMarker.mark(f"tips:{b.ref}"):
        send_guest(b, "local_tips")
    _welcome_data(b, s)
    if s.voice_welcome_call and is_kenyan(b.guest.phone) and OnceMarker.mark(f"welcome-call:{b.ref}"):
        from apps.comms.voice import place_welcome_call

        place_welcome_call(b)
    record("lock", f"Door code released for {b.ref} at {b.unit.name}", booking=b, actor=actor)
    return "released"


def _welcome_data(b, s):
    from apps.comms import at

    if not s.welcome_data_mb or not is_kenyan(b.guest.phone) or not OnceMarker.mark(f"data:{b.ref}"):
        return
    try:
        at.send_mobile_data(
            b.guest.phone, s.welcome_data_mb, metadata={"ref": b.ref}, idempotency_key=f"welcome-{b.ref}"
        )
        event(b, "data", f"Welcome data bundle {s.welcome_data_mb}MB sent")
    except Exception as e:
        log.error("mobile data failed: %s", e)


def check_out(booking, *, by="guest", channel="", auto=False, actor=None):
    from apps.operations.services import create_turnover_task

    b = Booking.objects.select_related("unit", "guest", "unit__area").get(pk=booking.pk)
    if b.status != "checked_in":
        raise BookingError("There's no active stay to check out of.")
    with transaction.atomic():
        b.status, b.checked_out_at = "completed", timezone.now()
        b.save(update_fields=["status", "checked_out_at", "updated_at"])
        locks.revoke_all(b, "checked_out")
        Unit.objects.filter(pk=b.unit_id).update(housekeeping="dirty")
        event(
            b,
            "checked_out",
            "Auto check-out at checkout time - code deactivated"
            if auto
            else f"Checked out via {channel or by} - code deactivated",
            channel,
            actor,
        )
        for c in b.changes.filter(status__in=ChangeRequest.PENDING):
            _close_change(c, "cancelled", "closed - the guest checked out")
    create_turnover_task(b)
    send_guest(b, "auto_checkout" if auto else "checkout_thanks")
    record(
        "booking",
        f"{'Auto ' if auto else ''}check-out {b.ref} from {b.unit.name}",
        channel=channel,
        booking=b,
        actor=actor,
    )
    notify_waitlist(b.unit)
    return b


def active_stay(phone):
    return (
        Booking.objects.filter(guest__phone=phone, status="checked_in")
        .select_related("unit", "guest", "unit__area")
        .order_by("check_in")
        .first()
    )


def current_booking(phone):
    """The stay a guest most likely means: in-house first, then the next upcoming one, then a pending hold."""
    qs = Booking.objects.filter(guest__phone=phone).select_related("unit", "guest", "unit__area")
    return (
        qs.filter(status="checked_in").order_by("check_in").first()
        or qs.filter(status="confirmed", check_out__gte=today()).order_by("check_in").first()
        or qs.filter(status="held", hold_expires_at__gt=timezone.now()).order_by("-created_at").first()
    )


# ---------- waitlist ----------


def add_to_waitlist(guest, check_in, check_out, *, area=None, unit=None, guests=0, channel="sms"):
    w, _ = Waitlist.objects.get_or_create(
        guest=guest,
        check_in=check_in,
        check_out=check_out,
        area=area,
        unit=unit,
        status="waiting",
        defaults={"guests": guests or 0, "channel": channel},
    )
    record(
        "booking",
        f"Waitlist: {guest.phone} for {check_in:%d %b}-{check_out:%d %b}{' in ' + area.name if area else ''}",
        channel=channel,
    )
    return w


def join_waitlist(guest, unit, check_in, check_out, *, adults=1, children=0, channel="web"):
    """A guest asks to be told when taken dates at one home free up. Returns (entry, created);
    asking again for the same home and dates returns the entry they already have."""
    t = today()
    if not check_in or not check_out:
        raise BookingError("Choose your dates.")
    if check_in < t:
        raise BookingError("That check-in date has already passed.")
    if check_out <= check_in:
        raise BookingError("Check-out must be after check-in.")
    if (check_in - t).days > 540:
        raise BookingError("We take bookings up to 18 months ahead.")
    n = (check_out - check_in).days
    if n < unit.min_nights:
        raise BookingError(f"{unit.name} has a minimum stay of {unit.min_nights} nights.")
    if n > unit.max_nights:
        raise BookingError(f"{unit.name} takes stays of up to {unit.max_nights} nights.")
    adults, children = max(1, adults), max(0, children)
    if adults + children > unit.max_guests:
        raise BookingError(f"{unit.name} sleeps up to {unit.max_guests} guests.")
    w = (
        Waitlist.objects.filter(
            guest=guest, unit=unit, check_in=check_in, check_out=check_out, status__in=("waiting", "offered")
        )
        .order_by("-id")
        .first()
    )
    if is_available(unit, check_in, check_out):
        raise BookingError("Good news - those dates are free. You can book them now.", code="available")
    if w:
        if w.status == "offered":  # the opening was taken again: back in the queue
            w.status = "waiting"
            w.save(update_fields=["status"])
        return w, False
    w = Waitlist.objects.create(
        guest=guest,
        unit=unit,
        area=unit.area,
        check_in=check_in,
        check_out=check_out,
        guests=adults + children,
        adults=adults,
        children=children,
        channel=channel,
    )
    lang = guest.lang
    messaging.send(
        guest.phone,
        messaging.render("waitlist_joined", lang, unit=unit.name, dates=dates_text(check_in, check_out, lang)),
        kind="waitlist_joined",
    )
    record("booking", f"Waitlist: {guest.phone} for {unit.name}, {check_in:%d %b}-{check_out:%d %b}", channel=channel)
    return w, True


def waitlist_unit(w):
    """The home this entry is about: the one offered once dates opened up, else the one asked for."""
    return (w.offered_unit if w.status == "offered" else None) or w.unit


def guest_waitlist(guest):
    """A guest's live waitlist entries, newest first. Past dates lapse; an offer whose dates were taken again goes
    back to waiting, so the next opening is offered again."""
    Waitlist.objects.filter(guest=guest, status__in=("waiting", "offered"), check_in__lt=today()).update(
        status="expired"
    )
    entries = list(
        Waitlist.objects.filter(guest=guest, status__in=("waiting", "offered"))
        .select_related("unit__area", "offered_unit__area", "area")
        .order_by("-created_at", "-id")
    )
    for w in entries:
        unit = waitlist_unit(w)
        if w.status == "offered" and (unit is None or not is_available(unit, w.check_in, w.check_out)):
            w.status = "waiting"
            w.save(update_fields=["status"])
    return entries


def book_url(w):
    """Deep link into checkout with the waitlisted dates and party (offered entries only)."""
    unit = waitlist_unit(w)
    if w.status != "offered" or unit is None:
        return None
    params = {
        "check_in": w.check_in.isoformat(),
        "check_out": w.check_out.isoformat(),
        "adults": w.adults or w.guests or 1,
    }
    if w.children:
        params["children"] = w.children
    return f"/book/{unit.slug}?{urlencode(params)}"


def _waitlist_booked(b):
    """The guest booked what they were waiting for: their matching waitlist entries are done."""
    Waitlist.objects.filter(
        guest_id=b.guest_id, status__in=("waiting", "offered"), check_in__lt=b.check_out, check_out__gt=b.check_in
    ).filter(
        Q(unit_id=b.unit_id)
        | Q(offered_unit_id=b.unit_id)
        | Q(unit__isnull=True, area_id=b.unit.area_id)
        | Q(unit__isnull=True, area__isnull=True)
    ).update(status="booked")


def notify_waitlist(unit):
    from apps.messaging.models import Conversation

    if unit.status != "active":
        return 0
    offered = 0
    for w in (
        Waitlist.objects.filter(status="waiting", check_out__gt=today())
        .select_related("guest", "area")
        .order_by("created_at")
    ):
        if w.check_in < today():
            w.status = "expired"
            w.save(update_fields=["status"])
            continue
        if (
            (w.unit_id and w.unit_id != unit.pk)
            or (w.area_id and w.area_id != unit.area_id)
            or (w.guests and unit.max_guests < w.guests)
            or (w.check_out - w.check_in).days < unit.min_nights
        ):
            continue
        if not is_available(unit, w.check_in, w.check_out):
            continue
        w.status, w.offered_unit, w.offered_at = "offered", unit, timezone.now()
        w.save(update_fields=["status", "offered_unit", "offered_at"])
        Conversation.objects.update_or_create(
            phone=w.guest.phone,
            defaults={
                "state": "offer",
                "data": {
                    "unit_id": unit.pk,
                    "check_in": w.check_in.isoformat(),
                    "check_out": w.check_out.isoformat(),
                    "guests": w.guests,
                },
            },
        )
        link = f"{settings.FRONTEND_URL}{book_url(w)}"
        body = messaging.render(
            "waitlist_offer",
            w.guest.lang,
            unit=unit.name,
            price=kes(from_price(unit)),
            dates=dates_text(w.check_in, w.check_out, w.guest.lang),
            link=link,
        )
        if link not in body:  # a console-edited wording without {link} still carries the booking link
            body = f"{body} {link}"
        messaging.send(w.guest.phone, body, kind="waitlist_offer")
        offered += 1
    if offered:
        record("broadcast", f"{unit.name} opened up - offered to {offered} waitlisted guest(s)")
    return offered


# ---------- add-ons, breakfast, requests ----------


def add_addon(booking, code, *, quantity=None, details=None, channel="web", actor=None):
    addon = Addon.objects.filter(code=code, active=True).first()
    if not addon:
        raise BookingError("That extra isn't available.")
    b = booking
    if b.status not in ("held", "confirmed", "checked_in"):
        raise BookingError("Extras can only be added to an active booking.")
    if addon.units.exists() and not addon.units.filter(pk=b.unit_id).exists():
        raise BookingError(f"{addon.name} isn't offered at {b.unit.name}.")
    if addon.category == "breakfast" and not b.unit.breakfast_available:
        raise BookingError(f"{addon.name} isn't offered at {b.unit.name}.")
    existing = b.addons.filter(addon=addon).exclude(status__in=("declined", "cancelled")).first()
    if existing and addon.category in ("flexibility", "breakfast"):
        raise BookingError(f"{addon.name} is already on this booking.")
    qty = max(1, int(quantity or (b.guests_count if addon.pricing in ("per_guest_night", "per_guest") else 1)))
    ba = BookingAddon.objects.create(
        booking=b,
        addon=addon,
        quantity=qty,
        unit_price=addon.price,
        total=addon.price_for(b.nights, b.guests_count, qty),
        status="requested" if addon.requires_approval else "confirmed",
        details=details or {},
    )
    recalc(b)
    event(
        b,
        "addon",
        f"{addon.name} {'requested' if addon.requires_approval else 'added'} ({kes(ba.total)})",
        channel,
        actor,
    )
    if addon.requires_approval:
        notify_host(
            f"REQUEST #{ba.pk}: {b.guest.display_name} ({b.ref}, {b.unit.name}) asks for {addon.name}"
            f"{' at ' + ba.details['time'] if ba.details.get('time') else ''}. Reply YES {ba.pk} or NO {ba.pk}.",
            booking=b,
            kind="addon_request",
        )
    record(
        "booking",
        f"{addon.name} {'requested' if addon.requires_approval else 'added'} on {b.ref}",
        channel=channel,
        booking=b,
        actor=actor,
    )
    return ba


def decide_addon(ba, approve, *, actor=None):
    from apps.payments import services as payments
    from apps.payments.providers import PaymentError

    if ba.status != "requested":
        return ba
    b = ba.booking
    b.refresh_from_db()
    before = b.total
    ba.status, ba.decided_at = ("confirmed" if approve else "declined"), timezone.now()
    ba.save(update_fields=["status", "decided_at"])
    recalc(b, reason=f"{ba.addon.name} {'approved' if approve else 'declined'}", actor=actor)
    if ba.addon.code in ("late_checkout", "early_checkin"):
        locks.refresh_window(b)
    event(b, "addon", f"{ba.addon.name} {'approved' if approve else 'declined'}", actor=actor)
    what = ba.addon.name.lower()
    if approve:
        added = b.total - before  # the extra plus the levy/VAT it attracts
        price_line = f" {kes(added)} has been added to your bill." if added > 0 else ""
        send_guest(b, "request_approved", what=what, price_line=price_line)
        due = min(added, owed(b))  # never ask again for money the guest has already paid
        if due > 0 and payments.can_prompt(b.guest.phone) and b.status in ("confirmed", "checked_in"):
            try:
                payments.start_payment(b, method="mpesa", purpose="addon", amount=due)
            except PaymentError:  # already on the timeline; the guest can still pay from the trip page
                log.warning("add-on payment request failed for %s", b.ref)
    else:
        send_guest(b, "request_declined", what=what)
    return ba


def set_breakfast(booking, style, *, people=None, dietary="", time="", notes="", channel="sms", actor=None):
    b = booking
    current = b.addons.filter(addon__code="breakfast").exclude(status__in=("declined", "cancelled")).first()
    if b.status not in ACTIVE_STATUSES:
        if not style or style == "none":
            return None  # nothing to take off a past or cancelled stay
        raise BookingError("Breakfast can only be changed on an active booking.")
    if not style or style == "none":
        if current:
            current.status = "cancelled"
            current.save(update_fields=["status"])
            event(b, "breakfast", "Breakfast removed", channel, actor)
            recalc(b, reason="Breakfast removed", actor=actor)
        return None
    if style not in BREAKFAST_STYLES:
        raise BookingError("Unknown breakfast choice.")
    addon = Addon.objects.filter(code="breakfast", active=True).first()
    if not addon or not b.unit.breakfast_available:
        raise BookingError("Breakfast isn't available at this home.")
    qty = max(1, min(int(people or b.guests_count), b.unit.max_guests))
    details = {
        "style": style,
        "dietary": dietary[:120],
        "time": time[:10] or addon.options.get("default_time", "08:00"),
        "notes": notes[:200],
    }
    if current:
        current.quantity, current.details, current.unit_price = qty, details, addon.price
        current.total = addon.price_for(b.nights, b.guests_count, qty)
        current.save(update_fields=["quantity", "details", "unit_price", "total"])
        ba = current
    else:
        ba = BookingAddon.objects.create(
            booking=b,
            addon=addon,
            quantity=qty,
            unit_price=addon.price,
            total=addon.price_for(b.nights, b.guests_count, qty),
            status="confirmed",
            details=details,
        )
    event(b, "breakfast", f"Breakfast: {breakfast_summary(ba)}", channel, actor)
    recalc(b, reason="Breakfast changed", actor=actor)
    record("booking", f"Breakfast set for {b.ref}: {breakfast_summary(ba)}", channel=channel, booking=b)
    return ba


def set_eta(booking, eta, channel="sms"):
    booking.arrival_eta = eta[:40]
    booking.save(update_fields=["arrival_eta", "updated_at"])
    event(booking, "eta", f"Arrival time: {eta}", channel)


ARRIVAL_TIPS = {
    "flight": "From Moi International Airport it's about 30-45 min to Nyali/Old Town; taxis cost around KES 1,500 - agree the fare first, or book Uber/Bolt.",
    "sgr": "The SGR terminus is at Miritini, about 12 km from town - allow 30-60 min by taxi or Uber/Bolt.",
    "car": "For Diani use the Dongo Kundu bypass to avoid Likoni ferry queues.",
    "bus": "Most buses stop near Mwembe Tayari / Buxton - take a registered taxi, Uber or Bolt from there.",
    "local": "Great - see you soon!",
}


def set_arrival_mode(booking, mode, channel="sms"):
    booking.arrival_mode = mode
    booking.save(update_fields=["arrival_mode", "updated_at"])
    event(booking, "arrival", f"Arriving by {mode}", channel)
    tip = ARRIVAL_TIPS.get(mode, "")
    if booking.unit.area.slug == "diani" and mode in ("flight", "sgr"):
        tip += " Diani is south of the Likoni channel - the Dongo Kundu bypass saves ferry queues."
    return tip


def checkout_reply(phone, channel="sms"):
    b = active_stay(phone)
    if not b:
        return messaging.render("no_booking", _lang(phone))
    check_out(b, channel=channel)
    return None  # the thank-you SMS has already been sent


def _lang(phone):
    from apps.accounts.models import User

    u = User.objects.filter(phone=phone).only("lang").first()
    return u.lang if u else "en"


# ---------- changing a stay: other dates, a longer stay, more or fewer guests ----------

CHANGE_WINDOW = timedelta(hours=48)
OTA_CHANNELS = ("airbnb", "booking_com")
KEPT_LABEL = "Kept under the cancellation policy"
SAME_PRICE = {"en": "same price", "sw": "bei ile ile"}
NEXT_STEP = {
    "en": {
        "host": "Amina will confirm by SMS shortly.",
        "mpesa": "Pay {amount} to confirm - check your phone for the M-Pesa prompt.",
        "card": "Pay {amount} by card to confirm: {link}",
        "pay": "Pay {amount} to confirm: {link}",
    },
    "sw": {
        "host": "Amina atathibitisha kwa SMS hivi karibuni.",
        "mpesa": "Lipa {amount} kuthibitisha - angalia simu yako kwa ombi la M-Pesa.",
        "card": "Lipa {amount} kwa kadi kuthibitisha: {link}",
        "pay": "Lipa {amount} kuthibitisha: {link}",
    },
}


class _BookedExtra:
    """A booked extra re-priced for new dates at the unit price the guest agreed; already approved, so it counts."""

    requires_approval = False
    price_for = Addon.price_for

    def __init__(self, ba):
        self.name, self.code, self.pricing, self.price = ba.addon.name, ba.addon.code, ba.addon.pricing, ba.unit_price


def _extra_quantity(ba, guests):
    # breakfast is booked per person eating: never more people than are staying
    return min(ba.quantity, guests) if ba.addon.pricing == "per_guest_night" else ba.quantity


def can_change(b):
    """Guests change confirmed stays before they end, and extend a stay they're in. OTA bookings change on the OTA."""
    if b.channel in OTA_CHANNELS:
        return False
    if b.status == "checked_in":
        return b.check_out >= today()
    return b.status == "confirmed" and b.check_out > today()


def kept_amount(b):
    """Money kept on the bill from nights an earlier change took off (accommodation not tied to a night)."""
    nights = b.nightly or []
    return max(0, b.accommodation_amount - sum(int(n.get("price") or 0) for n in nights)) if nights else 0


def _agreed_rate(b):
    nights = b.nightly or []
    if nights and all(n.get("label") == AGREED_PRICE for n in nights):
        return sum(int(n.get("price") or 0) for n in nights) / len(nights)
    return None


def _held(b):
    """Money we hold for the stay: paid, less refunds sent or queued."""
    pending = b.refunds.filter(status="pending").aggregate(s=Sum("amount"))["s"] or 0
    return b.amount_paid - b.amount_refunded - pending


def _paid_for_pending_changes(b):
    return (
        ChangeRequest.objects.filter(booking_id=b.pk, status="pending_payment", payment__status="success").aggregate(
            s=Sum("payment__amount")
        )["s"]
        or 0
    )


def _party(adults, children):
    n = adults + children
    return f"{n} guest{'s' if n != 1 else ''}"


def _money(delta):
    return f"+{kes(delta)}" if delta > 0 else f"-{kes(-delta)}" if delta < 0 else "same price"


def _change_summary(c):
    party = (
        f", {_party(c.old_adults, c.old_children)} -> {_party(c.new_adults, c.new_children)}"
        if (c.old_adults, c.old_children) != (c.new_adults, c.new_children)
        else f", {_party(c.new_adults, c.new_children)}"
    )
    old, new = dates_text(c.old_check_in, c.old_check_out), dates_text(c.new_check_in, c.new_check_out)
    return f"{old} -> {new}{party} ({_money(c.delta)})"


def _change_problem(b, check_in, check_out, adults, children):
    """Why this change can't be made, as (code, sentence) - or None when it can."""
    unit = b.unit
    if b.channel in OTA_CHANNELS:
        return "channel", f"This booking came through {b.get_channel_display()} - please change it there."
    if not can_change(b):
        return "status", "This booking can't be changed any more."
    if not check_in or not check_out or check_out <= check_in:
        return "dates", "Check-out must be after check-in."
    if adults < 1:
        return "guests", "At least one adult needs to be on the booking."
    if (check_in, check_out, adults, children) == (b.check_in, b.check_out, b.adults, b.children):
        return "same", "That's the same as your current booking."
    if b.status == "checked_in":
        if check_in != b.check_in:
            return "checked_in", "You're already checked in - you can extend your stay, but not move it."
        if (adults, children) != (b.adults, b.children):
            return "checked_in", "To change the number of guests during your stay, message Amina."
        if check_out <= b.check_out:
            return "checked_in", "Leaving early? Just check out, or message Amina."
    elif check_in != b.check_in and check_in < today():
        return "dates", "That check-in date has already passed."
    if (check_in - today()).days > 540:
        return "dates", "We take bookings up to 18 months ahead."
    n = (check_out - check_in).days
    if n < unit.min_nights:
        return "nights", f"{unit.name} has a minimum stay of {unit.min_nights} nights."
    if n > unit.max_nights:
        return "nights", f"{unit.name} takes stays of up to {unit.max_nights} nights."
    if adults + children > unit.max_guests and (adults, children) != (b.adults, b.children):
        return "guests", f"{unit.name} sleeps up to {unit.max_guests} guests."
    if not is_available(unit, check_in, check_out, exclude_booking_id=b.pk):
        if b.status == "checked_in":
            return (
                "unavailable",
                f"Sorry - {unit.name} is booked after your stay, so it can't run to {nice_date(check_out)}.",
            )
        return "unavailable", f"Sorry - {unit.name} isn't free for all of those nights."
    return None


def _price_change(b, check_in, check_out, adults, children, s):
    """The stay re-priced by the normal quote (stay discounts judged from the day it was booked, extras at the
    price agreed, Amina's agreed rate kept), plus anything earlier changes kept. Taking nights off refunds what
    the guest paid for them under the cancellation policy; the rest of that money stays on the bill."""
    guests = max(1, adults + children)
    n = (check_out - check_in).days
    extras = [
        {"addon": _BookedExtra(ba), "quantity": _extra_quantity(ba, guests)}
        for ba in b.addons.filter(status__in=COUNTED_ADDON_STATUSES).select_related("addon")
    ]
    booked_on = timezone.localtime(b.created_at).date() if b.created_at else today()
    q = price_quote(b.unit, check_in, check_out, guests=guests, addons=extras, ref_today=booked_on)
    nightly, accommodation, discount = q["nightly"], q["accommodation"], q["discount"]
    lines = [
        {"label": ln["label"], "amount": ln["amount"]} for ln in q["lines"] if ln["kind"] in ("nights", "discount")
    ]
    rate = _agreed_rate(b)
    if rate is not None:
        accommodation, discount = round(rate * n), 0
        nightly = _spread(accommodation, check_in, check_out, AGREED_PRICE)
        lines = [
            {"label": f"{kes(round(accommodation / n))} x {n} night{'s' if n != 1 else ''}", "amount": accommodation}
        ]
    carried = kept = kept_amount(b)
    base = accommodation - discount + q["cleaning_fee"] + q["addons"] + kept
    before = base + sum(taxes(base, s))
    held = _held(b)
    pct = policy_percent(b)
    paid_for_removed = max(0, min(b.total - before, held - before))
    keep_now = paid_for_removed - round(paid_for_removed * pct / 100)
    if keep_now > 0:  # kept as accommodation, so levy and VAT still add up on the bill
        tax_rate = Decimal(s.tourism_levy_percent) + (Decimal(s.vat_percent) if s.vat_registered else 0)
        kept += round(Decimal(keep_now) / (1 + tax_rate / 100))
    taxable = accommodation - discount + q["cleaning_fee"] + q["addons"] + kept
    levy, vat = taxes(taxable, s)
    total = taxable + levy + vat
    if kept:
        lines.append({"label": KEPT_LABEL, "amount": kept})
    if q["cleaning_fee"]:
        lines.append({"label": "Cleaning fee", "amount": q["cleaning_fee"]})
    lines += [{"label": ln["label"], "amount": ln["amount"]} for ln in q["lines"] if ln["kind"] == "addon"]
    if levy:
        lines.append({"label": f"Tourism levy ({Decimal(s.tourism_levy_percent).normalize()}%)", "amount": levy})
    if vat:
        lines.append({"label": f"VAT ({Decimal(s.vat_percent).normalize()}%)", "amount": vat})
    return {
        "nights": n,
        "nightly": nightly,
        "accommodation": accommodation + kept,
        "discount": discount,
        "cleaning_fee": q["cleaning_fee"],
        "addons": q["addons"],
        "levy": levy,
        "vat": vat,
        "total": total,
        "kept": kept,
        "kept_now": kept - carried,
        "percent": pct,
        "refund": max(0, held - total),
        "lines": lines,
    }


def _quote_change(b, check_in, check_out, adults, children):
    s = SiteSettings.load()
    quote = {
        "available": False,
        "reason": None,
        "nights": max(0, (check_out - check_in).days) if check_in and check_out else 0,
        "old_total": b.total,
        "new_total": b.total,
        "delta": 0,
        "pay_now": 0,
        "refund": 0,
        "policy_text": POLICY_TEXT.get(b.cancellation_policy, ""),
        "instant": bool(getattr(s, "instant_changes", True)),
        "lines": [],
    }
    problem = _change_problem(b, check_in, check_out, adults, children)
    if problem:
        quote["reason"] = problem[1]
        return quote, None, problem[0]
    p = _price_change(b, check_in, check_out, adults, children, s)
    delta = p["total"] - b.total
    if p["kept_now"]:
        quote["policy_text"] += f" Nights taken off now are {p['percent']}% refundable."
    quote.update(
        available=True,
        new_total=p["total"],
        delta=delta,
        pay_now=max(0, delta),
        refund=p["refund"],
        lines=p["lines"],
    )
    return quote, p, None


def change_quote(b, check_in, check_out, adults=None, children=None):
    """What a change would cost: {available, reason, nights, old_total, new_total, delta, pay_now, refund,
    policy_text, instant, lines}. Availability ignores the booking itself."""
    adults = b.adults if adults is None else adults
    children = b.children if children is None else children
    return _quote_change(b, check_in, check_out, adults, children)[0]


def _change_expiry(b, new_check_in):
    """A pending change lapses after 48 hours - sooner when the stay it touches begins (or ends, when extending)."""
    now = timezone.now()
    if b.status == "checked_in":
        edge = at_local(b.check_out, effective_checkout_time(b))
    else:
        edge = at_local(min(b.check_in, new_check_in), effective_checkin_time(b))
    return max(now + timedelta(hours=1), min(now + CHANGE_WINDOW, edge))


def request_change(
    b,
    *,
    check_in,
    check_out,
    adults=None,
    children=None,
    note="",
    channel="web",
    requested_by="guest",
    method=None,
    actor=None,
    notify=True,
):
    """Ask for - and where possible make - a change to a confirmed stay. Returns (change, payment): payment is the
    start_payment result (or its error) when the guest pays the difference now, else None. Raises BookingError.

    Instant changes (SiteSettings.instant_changes, default on): a dearer change waits for the guest's payment and
    applies when it lands; a cheaper or equal one applies at once. Otherwise Amina is asked first by SMS."""
    b = Booking.objects.select_related("unit", "guest", "unit__area").get(pk=b.pk)
    adults = b.adults if adults is None else adults
    children = b.children if children is None else children
    quote, pricing, code = _quote_change(b, check_in, check_out, adults, children)
    if not quote["available"]:
        raise BookingError(quote["reason"], code=code)
    instant = requested_by == "host" or quote["instant"]
    delta = quote["delta"]
    with transaction.atomic():
        Booking.objects.select_for_update().filter(pk=b.pk).first()  # one change request at a time per booking
        for older in b.changes.select_for_update().filter(status__in=ChangeRequest.PENDING):
            _close_change(older, "cancelled", "replaced by a newer request", actor)
        c = ChangeRequest.objects.create(
            booking=b,
            requested_by=requested_by,
            channel=(channel or "")[:12],
            old_check_in=b.check_in,
            old_check_out=b.check_out,
            old_adults=b.adults,
            old_children=b.children,
            new_check_in=check_in,
            new_check_out=check_out,
            new_adults=adults,
            new_children=children,
            old_total=b.total,
            new_total=quote["new_total"],
            delta=delta,
            refund_amount=quote["refund"],
            pricing=pricing,
            status="pending_payment" if instant and delta > 0 else "pending_host",
            note=(note or "").strip()[:300],
            created_by=actor if getattr(actor, "pk", None) else None,
            expires_at=_change_expiry(b, check_in),
        )
        event(b, "change", f"Change requested: {_change_summary(c)}", channel, actor, change=c.pk)
        if instant and delta <= 0 and not _apply_change(c, actor=actor):
            raise BookingError("Sorry - those dates were just taken.", code="unavailable")
    payment = None
    if c.status == "applied":
        _announce_change(c, notify_guest=notify)
    elif c.status == "pending_payment":
        payment = _start_change_payment(c, method)
        if notify and channel != "web":  # on the web the guest is looking at the page (and the M-Pesa prompt)
            _send_change_text(c, payment)
    else:
        _ask_host(c)
        if notify:
            _send_change_text(c)
    record(
        "booking",
        f"Change C{c.pk} on {b.ref}: {_change_summary(c)} - {c.get_status_display().lower()}",
        channel=channel,
        booking=b,
        actor=actor,
    )
    return c, payment


def _close_change(c, status, why, actor=None):
    """End a change that won't happen (withdrawn, replaced, declined, expired); its payment request is called off."""
    from apps.payments.models import Payment

    c.status, c.decided_at, c.refund_amount = status, timezone.now(), 0  # nothing was refunded for it (yet)
    c.save(update_fields=["status", "decided_at", "refund_amount"])
    Payment.objects.filter(booking_id=c.booking_id, purpose="change", status="pending").update(status="cancelled")
    event(c.booking, "change", f"Change C{c.pk} {why}", actor=actor, change=c.pk)


def _move_tasks(b, old_in, old_out):
    """Open housekeeping tasks pinned to the stay's arrival or departure day move with it."""
    from apps.operations.models import Task

    shift = {old_in: (b.check_in - old_in).days, old_out: (b.check_out - old_out).days}
    for t in Task.objects.filter(booking=b, status__in=("open", "in_progress"), due_at__isnull=False):
        days = shift.get(timezone.localtime(t.due_at).date())
        if days:
            t.due_at += timedelta(days=days)
            t.save(update_fields=["due_at"])


def _apply_change(c, *, actor=None):
    """Move the booking to the change's dates, party and quoted price, inside the caller's transaction. Availability
    is checked again under the unit lock and the exclusion constraint has the final word: returns False (nothing
    changed) when the new dates are no longer free."""
    b = Booking.objects.select_for_update().select_related("unit", "guest", "unit__area").get(pk=c.booking_id)
    Unit.objects.select_for_update().filter(pk=b.unit_id).first()
    _expire(Booking.objects.filter(unit_id=b.unit_id, status="held", hold_expires_at__lt=timezone.now()))
    if b.status not in ("confirmed", "checked_in") or not is_available(
        b.unit, c.new_check_in, c.new_check_out, exclude_booking_id=b.pk
    ):
        return False
    old_in, old_out = b.check_in, b.check_out
    p = c.pricing or {}
    nights = (c.new_check_out - c.new_check_in).days
    guests = max(1, c.new_adults + c.new_children)
    try:
        with transaction.atomic():
            b.check_in, b.check_out, b.adults, b.children = (
                c.new_check_in,
                c.new_check_out,
                c.new_adults,
                c.new_children,
            )
            b.nightly = p.get("nightly") or b.nightly
            b.accommodation_amount = p.get("accommodation", b.accommodation_amount)
            b.discount_amount = p.get("discount", b.discount_amount)
            b.cleaning_fee = p.get("cleaning_fee", b.cleaning_fee)
            for ba in b.addons.exclude(status__in=("declined", "cancelled")).select_related("addon"):
                qty = _extra_quantity(ba, guests)
                total = _BookedExtra(ba).price_for(nights, guests, qty)
                if (qty, total) != (ba.quantity, ba.total):
                    ba.quantity, ba.total = qty, total
                    ba.save(update_fields=["quantity", "total"])
            _retotal(b)
            b.save(
                update_fields=[
                    "check_in",
                    "check_out",
                    "adults",
                    "children",
                    "nightly",
                    "accommodation_amount",
                    "discount_amount",
                    "cleaning_fee",
                    "addons_amount",
                    "levy_amount",
                    "vat_amount",
                    "total",
                    "payment_status",
                    "updated_at",
                ]
            )
    except IntegrityError as e:  # another channel took the nights between the check and the write
        log.info("change C%s rejected by the database: %s", c.pk, e)
        return False
    locks.refresh_window(b)
    _move_tasks(b, old_in, old_out)
    now = timezone.now()
    c.status, c.applied_at, c.decided_at = "applied", now, c.decided_at or now
    c.save(update_fields=["status", "applied_at", "decided_at"])
    event(b, "change", f"Stay changed: {_change_summary(c)}. New total {kes(b.total)}", c.channel, actor, change=c.pk)
    r = refund_overpayment(b, reason=f"Date change C{c.pk}: bill reduced", actor=actor, notify=False)
    c.refund_amount = r.amount if r else 0
    c.save(update_fields=["refund_amount"])
    return True


def _announce_change(c, *, notify_guest=True, tell_host=True):
    """After a change is applied: the guest's SMS, Amina's heads-up and the waitlist for any nights given back."""
    b = Booking.objects.select_related("unit", "guest", "unit__area").get(pk=c.booking_id)
    if notify_guest:
        _send_change_text(c)
    if tell_host:
        notify_host(
            f"{b.ref} ({b.unit.name}) changed by {'the guest' if c.requested_by == 'guest' else 'you'}: "
            f"{_change_summary(c)}. New total {kes(b.total)}"
            f"{', refund ' + kes(c.refund_amount) + ' queued' if c.refund_amount else ''}.",
            booking=b,
            kind="change_notice",
        )
    if c.new_check_in > c.old_check_in or c.new_check_out < c.old_check_out:
        notify_waitlist(b.unit)


def _ask_host(c):
    b = c.booking
    note = f' Note: "{c.note[:120]}"' if c.note else ""
    notify_host(
        f"CHANGE C{c.pk}: {b.guest.display_name} ({b.ref}, {b.unit.name}) asks to change {_change_summary(c)}. "
        f"New total {kes(c.new_total)}.{note} Reply YES C{c.pk} or NO C{c.pk}.",
        booking=b,
        kind="change_request",
    )


def _start_change_payment(c, method=None):
    """Ask for the difference (M-Pesa for Kenyan numbers when it's on, else card) and link the payment to it."""
    from apps.payments import services as payments
    from apps.payments.providers import PaymentError

    b = c.booking
    method = method or payments.default_method(b.guest.phone)
    try:
        r = payments.start_payment(b, method=method, purpose="change", amount=c.delta)
    except PaymentError as e:
        as_dict = getattr(e, "as_dict", None)
        return as_dict() if callable(as_dict) else {"error": str(e)}
    if r.get("payment_id") and r["payment_id"] != c.payment_id:
        c.payment_id = r["payment_id"]
        ChangeRequest.objects.filter(pk=c.pk).update(payment_id=r["payment_id"])
    return r


def change_text(c, payment=None):
    """The guest's message for a change in its current state (also the Ask Amina reply to EXTEND)."""
    b = Booking.objects.select_related("unit", "guest", "unit__area").get(pk=c.booking_id)
    lang = b.lang
    nights, guests = (c.new_check_out - c.new_check_in).days, c.new_adults + c.new_children
    ctx = {
        **guest_context(b),
        "new_dates": dates_text(c.new_check_in, c.new_check_out, lang),
        "nights": nights,
        "s": "s" if nights != 1 else "",
        "guests": guests,
        "gs": "s" if guests != 1 else "",
    }
    refund = messaging.render("refund_line", lang, amount=kes(c.refund_amount)) if c.refund_amount else ""
    if c.status == "applied":
        balance = messaging.render("balance_note", lang, **ctx) if b.balance_due and b.status == "confirmed" else ""
        return messaging.render(
            "change_applied",
            lang,
            **{**ctx, "refund_line": f" {refund}" if refund else "", "balance_note": f" {balance}" if balance else ""},
        )
    if c.status not in ChangeRequest.PENDING:
        return messaging.render("change_declined", lang, **{**ctx, "refund_line": f" {refund}" if refund else ""})
    step = NEXT_STEP.get(lang, NEXT_STEP["en"])
    amount = kes(c.delta)
    payment = payment or {}
    if c.status == "pending_host":
        next_step = step["host"]
    elif payment.get("pay_link") or payment.get("checkout_url"):
        next_step = step["card"].format(amount=amount, link=payment.get("pay_link") or payment["checkout_url"])
    elif payment.get("method") == "mpesa" and not payment.get("error"):
        next_step = step["mpesa"].format(amount=amount)
    else:
        next_step = step["pay"].format(amount=amount, link=trip_link(b))
    difference = _money(c.delta) if c.delta else SAME_PRICE.get(lang, SAME_PRICE["en"])
    return messaging.render(
        "change_requested",
        lang,
        **{**ctx, "new_total": kes(c.new_total), "difference": difference, "next_step": next_step},
    )


def _send_change_text(c, payment=None):
    b = c.booking
    kind = (
        "change_applied"
        if c.status == "applied"
        else "change_requested"
        if c.status in ChangeRequest.PENDING
        else "change_declined"
    )
    return messaging.send(b.guest.phone, change_text(c, payment), booking=b, kind=kind)


def pay_change(c, method=None):
    """(Re)send the payment request for a change waiting on the guest's money."""
    if c.status != "pending_payment":
        raise BookingError("This change isn't waiting for a payment.")
    return _start_change_payment(c, method)


def cancel_change(c, *, actor=None):
    """The guest withdraws a change that hasn't happened yet; the booking stays as it was."""
    with transaction.atomic():
        c = ChangeRequest.objects.select_for_update().select_related("booking").get(pk=c.pk)
        if c.status not in ChangeRequest.PENDING:
            raise BookingError("This change can't be withdrawn any more.")
        _close_change(c, "cancelled", "withdrawn by the guest", actor)
    return c


def decide_change(c, approve, *, actor=None):
    """Amina's yes/no to a change waiting for her. A dearer change then waits for the guest's payment; a cheaper one
    applies at once. Raises BookingError if it was already dealt with - or, after declining it and telling the
    guest, when the new dates have been taken in the meantime."""
    with transaction.atomic():
        c = ChangeRequest.objects.select_for_update().select_related("booking", "booking__unit").get(pk=c.pk)
        if c.status != "pending_host":
            raise BookingError("This change has already been dealt with.")
        b = c.booking
        free = b.status in ("confirmed", "checked_in") and is_available(
            b.unit, c.new_check_in, c.new_check_out, exclude_booking_id=b.pk
        )
        if not approve:
            _close_change(c, "declined", "declined by Amina", actor)
            outcome = "declined"
        elif not free:
            _close_change(c, "declined", "declined - the new dates are no longer free", actor)
            outcome = "unavailable"
        elif c.delta > 0:
            c.status, c.decided_at, c.expires_at = "pending_payment", timezone.now(), _change_expiry(b, c.new_check_in)
            c.save(update_fields=["status", "decided_at", "expires_at"])
            event(b, "change", f"Change C{c.pk} approved - waiting for the guest's payment", actor=actor, change=c.pk)
            outcome = "pending_payment"
        elif _apply_change(c, actor=actor):
            outcome = "applied"
        else:
            _close_change(c, "declined", "declined - the new dates are no longer free", actor)
            outcome = "unavailable"
    c.refresh_from_db()
    if outcome == "pending_payment":
        _send_change_text(c, _start_change_payment(c))
    elif outcome == "applied":
        _announce_change(c, tell_host=False)
    else:
        _send_change_text(c)
    record(
        "booking",
        f"Change C{c.pk} on {c.booking.ref} {'approved' if approve else 'declined'}",
        booking=c.booking,
        actor=actor,
    )
    if outcome == "unavailable":
        raise BookingError(
            "Those dates aren't free any more, so the change was declined and the guest told.", code="unavailable"
        )
    return c


def decide_change_by_sms(pk, approve, *, actor=None):
    """Amina's 'YES C12' / 'NO C12' text. Returns the reply for her."""
    c = ChangeRequest.objects.select_related("booking").filter(pk=pk).first()
    if c is None:
        return f"No change request C{pk}."
    try:
        c = decide_change(c, approve, actor=actor)
    except BookingError as e:
        return f"C{pk}: {e}"
    verdict = {
        "applied": "Approved and done",
        "pending_payment": "Approved - waiting for the guest's payment",
    }.get(c.status, "Declined")
    return f"{verdict}: change C{pk} for {c.booking.ref}. Guest told."


def attach_change_payment(booking, payment):
    """Payments offers this first any money that didn't come from a change's own prompt: a Paybill / C2B payment,
    a matched "PAID <code>" claim, Amina's manual match. When the booking has a change waiting for payment and the
    money is plainly for it - exactly what the change costs, or at least that with nothing else owed - the payment
    becomes the change's (purpose "change") and is settled here: payments.on_success counts it once and applies the
    change through on_change_paid; anything beyond the change's price is then a plain overpayment, queued for
    refund. A payment that is already settled is counted already, so it only applies the change.
    Returns True when the payment was taken (and settled) for the change, else False with nothing changed."""
    from apps.payments import services as payments
    from apps.payments.models import Payment

    with transaction.atomic():
        p = Payment.objects.select_for_update().get(pk=payment.pk)
        linked = ChangeRequest.objects.filter(payment_id=p.pk).first()
        if linked is None:
            c = (
                ChangeRequest.objects.select_for_update()
                .filter(booking_id=booking.pk, status="pending_payment")
                .order_by("-id")
                .first()
            )
            if c is None or c.pay_now <= 0:
                return False
            b = Booking.objects.get(pk=booking.pk)
            other_due = owed(b) + (p.amount if p.status == "success" else 0)  # what was owed without this money
            if not (p.amount == c.pay_now or (other_due <= 0 and p.amount >= c.pay_now)):
                return False
            # the change's own M-Pesa prompt, if still open, isn't needed any more
            Payment.objects.filter(booking_id=b.pk, purpose="change", status="pending").exclude(pk=p.pk).update(
                status="cancelled"
            )
            c.payment = p
            c.save(update_fields=["payment"])
            if p.purpose != "change" and "change" in dict(Payment.PURPOSES):
                p.purpose = "change"
                p.save(update_fields=["purpose", "updated_at"])
            event(
                b, "change", f"{kes(p.amount)} {p.get_method_display()} payment taken for change C{c.pk}", change=c.pk
            )
        elif p.status == "success" and linked.status != "pending_payment":
            return True  # taken for a change and settled already (a repeated hook)
    if p.status == "success":
        on_change_paid(p)  # counted already: just apply the change (once)
    else:
        payments.on_success(p)  # counts the money once, then payments calls on_change_paid
    return True


def on_change_paid(payment):
    """Payments calls this once a purpose="change" payment has succeeded (booking.amount_paid already includes it),
    inside the transaction that settles it, so the money and the change it paid for commit together. Applies the
    change, exactly once per payment. When that's no longer possible - the dates went in the meantime, or the
    change was withdrawn or replaced - the money is queued for refund and Amina alerted."""
    from apps.payments.models import Payment
    from apps.safety.services import raise_alert

    with transaction.atomic():
        if not Payment.objects.filter(pk=payment.pk, status="success").exists():
            return None
        if not OnceMarker.mark(f"change-paid:{payment.pk}"):
            return None
        c = ChangeRequest.objects.select_for_update().filter(payment_id=payment.pk).first()
        if c is None:  # paid an earlier prompt for the same change (a re-sent request moved the link)
            c = (
                ChangeRequest.objects.select_for_update()
                .filter(booking_id=payment.booking_id, status="pending_payment", delta=payment.amount)
                .order_by("-id")
                .first()
            )
        b = Booking.objects.select_related("unit", "guest", "unit__area").get(pk=payment.booking_id)
        if b.status not in ("confirmed", "checked_in"):
            # a stay that's over or cancelled: payments' late-payment handling deals with the money
            if c is not None and c.status in ChangeRequest.PENDING:
                _close_change(c, "cancelled", "closed - the booking is no longer active")
            return c
        outcome = "orphan"
        if c is not None and c.status == "pending_payment":
            if c.payment_id != payment.pk:
                c.payment_id = payment.pk
                c.save(update_fields=["payment"])
            if _apply_change(c):
                outcome = "applied"
            else:
                _close_change(c, "declined", f"paid, but the new dates were taken - refunding {kes(payment.amount)}")
                outcome = "declined"
        if outcome != "applied":
            b.refresh_from_db()
            r = refund_overpayment(b, reason="Paid for a date change that couldn't be made", notify=outcome == "orphan")
            if c is not None and (outcome == "declined" or c.payment_id == payment.pk) and c.status != "applied":
                c.refund_amount = r.amount if r else 0
                c.save(update_fields=["refund_amount"])
            if r is None:  # the money simply went towards what's still owed
                event(
                    b, "change", f"{kes(payment.amount)} paid for a change that wasn't made - kept towards the balance"
                )
            else:
                raise_alert(
                    "payment",
                    f"{kes(payment.amount)} paid for a date change on {b.ref} that couldn't be made - "
                    f"refund {kes(r.amount)} queued",
                    severity="high",
                    booking=b,
                    dedupe=f"change-refund:{payment.pk}",
                )
    if outcome == "applied":
        _announce_change(c)
    elif outcome == "declined":
        _send_change_text(c)
    return c


def expire_stale_changes():
    """Scheduler hook: pending changes past expires_at lapse and their payment request is called off. A change
    whose payment did arrive is applied first, in case the payment hook was missed. Returns how many lapsed."""
    for c in ChangeRequest.objects.filter(status="pending_payment", payment__status="success").select_related(
        "payment"
    ):
        on_change_paid(c.payment)
    n = 0
    for pk in ChangeRequest.objects.filter(status__in=ChangeRequest.PENDING, expires_at__lt=timezone.now()).values_list(
        "pk", flat=True
    ):
        with transaction.atomic():
            c = ChangeRequest.objects.select_for_update().filter(pk=pk, status__in=ChangeRequest.PENDING).first()
            if c is None:
                continue
            was = c.status
            _close_change(
                c,
                "expired",
                "expired - Amina didn't answer in time" if was == "pending_host" else "expired - no payment came in",
            )
        if was == "pending_host":
            _send_change_text(c)
        n += 1
    return n


def extend_by_sms(b, nights, *, thread_id=None):
    """SMS 'EXTEND n': ask for n more nights. Returns (reply, handled) for the Ask Amina bot. When the home is taken
    after the stay, Amina hears about it (she may have another home) and the guest is told she will reply."""
    n = max(1, min(int(nights or 1), 60))
    new_out = b.check_out + timedelta(days=n)
    try:
        c, payment = request_change(
            b, check_in=b.check_in, check_out=new_out, channel="sms", actor=b.guest, notify=False
        )
    except BookingError as e:
        if e.code != "unavailable":
            return str(e), "auto"
        notify_host(
            f"EXTEND: {b.guest.display_name} ({b.ref}, {b.unit.name}) wants {n} more night(s) to {new_out}. "
            f"Unit is NOT free - reply #{thread_id} to answer.",
            booking=b,
        )
        return messaging.render("request_sent", b.lang, what=f"{n} more night{'s' if n > 1 else ''}"), "relayed"
    return change_text(c, payment), "auto"
