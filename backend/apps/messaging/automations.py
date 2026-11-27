"""The guest message timeline. Each Automation row (editable in the console) says what goes out and
when, relative to the stay; the guard functions below say *whether* it applies to a given booking.
Every send is claimed with a OnceMarker, so restarts and overlapping scheduler runs never double-send.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.models import OnceMarker, SiteSettings
from apps.core.utils import at_local, today

from .models import Automation

log = logging.getLogger("amina.automations")

OTA_CHANNELS = ("airbnb", "booking_com")  # their guests pay the platform and may not be solicited off it
HEADS_UP_DAYS = 7  # the balance ladder's early reminder, a week before arrival
PROMPT_GAP = timedelta(hours=23)  # one automatic M-Pesa prompt a day (an hour's slack for the daily run's start)

DEFAULT_AUTOMATIONS = [
    (
        "pre_arrival",
        "Pre-arrival: breakfast, ETA & travel",
        "Asks breakfast preference, arrival time and how they're travelling",
        "check_in",
        -3,
        "10:00",
    ),
    (
        "id_request",
        "Guest-register ID reminder",
        "Only if the guest hasn't registered an ID yet",
        "check_in",
        -2,
        "11:00",
    ),
    (
        "balance_due",
        "Balance due (deposit bookings)",
        "Sends an M-Pesa prompt for the balance on its due day (Settings: balance due days before arrival)",
        "check_in",
        -1,
        "09:00",
    ),
    (
        "directions",
        "Directions, landmark & Wi-Fi",
        "Exact location is only shared once a booking is confirmed",
        "check_in",
        -1,
        "16:00",
    ),
    ("welcome_check", "Settled in?", "Evening of arrival", "check_in", 0, "19:00"),
    ("mid_stay", "Mid-stay check-in & clean offer", "Stays of 4+ nights only", "check_in", 2, "10:00"),
    (
        "checkout_reminder",
        "Checkout reminder & late checkout offer",
        "Evening before departure",
        "check_out",
        -1,
        "19:00",
    ),
    (
        "rebook_offer",
        "Come-back offer",
        "Opted-in direct guests only, never Airbnb/Booking.com guests",
        "check_out",
        21,
        "10:00",
    ),
]


def ensure_defaults():
    for i, (key, name, desc, anchor, offset, at) in enumerate(DEFAULT_AUTOMATIONS):
        Automation.objects.get_or_create(
            key=key,
            defaults={
                "name": name,
                "description": desc,
                "anchor": anchor,
                "offset_days": offset,
                "send_time": at,
                "template_key": key,
                "sort_order": i,
            },
        )
    # the balance request follows Settings > balance due days: show the timeline that's really used
    days = SiteSettings.load().balance_due_days
    Automation.objects.filter(key="balance_due").exclude(anchor="check_in", offset_days=-days).update(
        anchor="check_in", offset_days=-days
    )


def _quiet(s):
    h = timezone.localtime().hour
    return h >= s.quiet_hours_start or h < s.quiet_hours_end


def _due_at(auto, b, s=None):
    if auto.key == "balance_due":  # the day guests are told the balance is due (quote, trip page, confirmation SMS)
        day = b.check_in - timedelta(days=(s or SiteSettings.load()).balance_due_days)
        return at_local(day, auto.send_time or "00:00"), day
    anchor = {"check_in": b.check_in, "check_out": b.check_out}.get(auto.anchor) or timezone.localtime(
        b.created_at
    ).date()
    day = anchor + timedelta(days=auto.offset_days)
    return at_local(day, auto.send_time or "00:00"), day


def _applies(key, b, s, due_day):
    t = today()
    if key == "pre_arrival":
        return b.status == "confirmed" and t < b.check_in
    if key == "id_request":
        return b.status == "confirmed" and t <= b.check_in and s.require_id_before_code and not b.guest.has_id
    if key == "balance_due":  # Airbnb / Booking.com guests pay the platform, never us
        return b.status == "confirmed" and b.balance_due > 0 and t <= b.check_in and b.channel not in OTA_CHANNELS
    if key == "directions":
        return b.status == "confirmed" and t <= b.check_in
    if key == "welcome_check":
        return b.status == "checked_in" and t == b.check_in
    if key == "mid_stay":
        return b.status == "checked_in" and b.nights >= 4 and t == due_day
    if key == "checkout_reminder":
        return b.status == "checked_in" and t < b.check_out
    if key == "rebook_offer":
        g = b.guest
        return (
            b.status == "completed"
            and t <= due_day + timedelta(days=3)
            and g.marketing_opt_in
            and not g.sms_opt_out_at
            and b.channel not in ("airbnb", "booking_com")
            and not b.guest.bookings.filter(created_at__gt=b.created_at).exists()
        )
    return False


def _send(auto, b):
    from apps.bookings.services import send_guest
    from apps.messaging import services as messaging
    from apps.payments import services as payments

    if auto.key == "balance_due" and payments.can_prompt(b.guest.phone):
        try:
            payments.start_payment(b, method="mpesa", purpose="balance")
        except Exception as e:  # the SMS still goes out with the pay link
            log.info("balance STK not sent for %s: %s", b.ref, e)
    extra = _extras(auto, b)
    if auto.key == "rebook_offer":
        msg = messaging.send(
            b.guest.phone,
            messaging.render(auto.template_key, b.lang, **{**_ctx(b), **extra}),
            booking=b,
            kind=auto.key,
            marketing=True,
        )
        return msg is not None
    send_guest(b, auto.template_key, **extra)
    return True


def _extras(auto, b):
    """Values some timeline messages need beyond the booking itself (shared by the send and the preview)."""
    from apps.bookings.models import Addon
    from apps.core.utils import kes

    if auto.key == "mid_stay":
        clean = Addon.objects.filter(code="mid_stay_clean", active=True).first()
        return {"clean_price": kes(clean.price) if clean else "on request"}
    if auto.key == "rebook_offer":
        return {"link": f"{_frontend()}/stays/{b.unit.slug}"}
    return {}


def _ctx(b):
    from apps.bookings.services import guest_context

    return guest_context(b)


def _frontend():
    from django.conf import settings

    return settings.FRONTEND_URL


def run_automations():
    from apps.bookings.models import Booking

    s = SiteSettings.load()
    if _quiet(s):
        return 0
    now, t = timezone.now(), today()
    autos = list(Automation.objects.filter(enabled=True))
    # far enough ahead for the earliest message before arrival (the balance goes out balance_due_days before)
    ahead = max([4, s.balance_due_days + 1] + [1 - a.offset_days for a in autos if a.anchor == "check_in"])
    candidates = Booking.objects.filter(
        status__in=("confirmed", "checked_in", "completed"),
        check_out__gte=t - timedelta(days=30),
        check_in__lte=t + timedelta(days=ahead),
    ).select_related("unit", "unit__area", "guest")
    sent = 0
    for b in candidates:
        for auto in autos:
            due, due_day = _due_at(auto, b, s)
            if due > now or not _applies(auto.key, b, s, due_day):
                continue
            if not OnceMarker.mark(f"auto:{auto.key}:{b.ref}"):
                continue
            try:
                if _send(auto, b):
                    sent += 1
            except Exception:
                log.exception("automation %s failed for %s", auto.key, b.ref)
    return sent


def skip_overdue(booking):
    """Count every timeline message already due for this booking as sent, without sending it: a stay entered after
    the fact (demo guests) shouldn't get days of messages at once. Later ones still go out on time."""
    s, now, t = SiteSettings.load(), timezone.now(), today()
    for auto in Automation.objects.filter(enabled=True):
        if _due_at(auto, booking, s)[0] <= now:
            OnceMarker.mark(f"auto:{auto.key}:{booking.ref}")
    if (booking.check_in - t).days <= HEADS_UP_DAYS:  # the balance ladder's reminders
        OnceMarker.mark(f"balance-soon:{booking.ref}")
    if t > booking.check_in - timedelta(days=s.balance_due_days):
        OnceMarker.mark(f"balance-overdue:{booking.ref}")


def preview(auto, booking):
    from apps.bookings.services import guest_context
    from apps.messaging import services as messaging

    # Amina sees the real wording (e.g. the day-before directions with the Wi-Fi), not the before-reveal placeholders
    ctx = {**guest_context(booking, reveal=True), **_extras(auto, booking)}
    return messaging.render(auto.template_key, booking.lang, **ctx)


# ---------- the balance ladder (confirmed stays that still owe money) ----------
#   a week before arrival   balance_reminder_soon: amount and due date (only stays booked more than a week ahead)
#   the due day             the balance_due automation above: M-Pesa prompt + SMS at its send time
#   after the due day       balance_overdue once (card, Paybill), and at most one automatic M-Pesa prompt a day
#   arrival morning         release_code keeps the door code back, and Amina gets a payment alert


def run_balance_ladder():
    """The daily job. Returns how many reminders and M-Pesa prompts went out."""
    from django.db.models import F

    from apps.bookings.models import Booking

    s = SiteSettings.load()
    if _quiet(s):
        return 0
    t = today()
    owing = (
        Booking.objects.filter(
            status="confirmed",
            check_in__gt=t,
            check_in__lte=t + timedelta(days=max(HEADS_UP_DAYS, s.balance_due_days)),
            total__gt=F("amount_paid") - F("amount_refunded"),
        )
        .exclude(channel__in=OTA_CHANNELS)
        .select_related("guest", "unit", "unit__area")
    )
    done = 0
    for b in owing:
        if b.balance_due <= 0:
            continue
        due = b.check_in - timedelta(days=s.balance_due_days)
        try:
            if t < due:
                done += _balance_heads_up(b, t, due)
            elif t > due:
                done += _balance_overdue(b, t)
        except Exception:
            log.exception("balance ladder failed for %s", b.ref)
    return done


def _balance_heads_up(b, t, due):
    from apps.bookings import services as bookings
    from apps.core.utils import kes, nice_date

    booked_on = timezone.localtime(b.created_at).date()
    if (b.check_in - t).days > HEADS_UP_DAYS or (b.check_in - booked_on).days <= HEADS_UP_DAYS:
        return 0
    if not OnceMarker.mark(f"balance-soon:{b.ref}"):
        return 0
    bookings.send_guest(b, "balance_reminder_soon")
    bookings.event(b, "balance_reminder", f"Balance reminder sent: {kes(b.balance_due)} due {nice_date(due)}")
    return 1


def _balance_overdue(b, t):
    from apps.bookings import services as bookings
    from apps.core.activity import record
    from apps.core.utils import kes

    from .models import Message

    done = 0
    # the due-day request caught up late (scheduler down): don't send a second balance SMS within the day
    asked = Message.objects.filter(
        booking=b, direction="out", kind="balance_due", created_at__gte=timezone.now() - PROMPT_GAP
    ).exists()
    if not asked and OnceMarker.mark(f"balance-overdue:{b.ref}"):
        bookings.send_guest(b, "balance_overdue", paybill_line=_paybill_line(b))
        bookings.event(b, "balance_overdue", f"Balance {kes(b.balance_due)} overdue - reminder sent")
        record("payment", f"Balance overdue: {b.ref} still owes {kes(b.balance_due)}", booking=b)
        done += 1
    return done + _auto_prompt(b, t)


def _auto_prompt(b, t):
    """At most one automatic M-Pesa prompt per booking a day (Kenyan numbers, when M-Pesa is on), never on top of
    a recent prompt (the due-day one, or one the guest asked for)."""
    from apps.payments import services as payments
    from apps.payments.models import Payment

    if not payments.can_prompt(b.guest.phone):
        return 0
    if Payment.objects.filter(booking=b, method="mpesa", created_at__gte=timezone.now() - PROMPT_GAP).exists():
        return 0
    if not OnceMarker.mark(f"balance-prompt:{b.ref}:{t}"):
        return 0
    try:
        payments.start_payment(b, method="mpesa", purpose="balance")
    except Exception as e:  # the overdue SMS already carries the card and Paybill options
        log.info("overdue balance prompt not sent for %s: %s", b.ref, e)
        return 0
    return 1


def _paybill_line(b):
    from apps.core.utils import kes
    from apps.messaging import services as messaging
    from apps.payments.services import paybill_number

    number = paybill_number()
    if not number:
        return ""
    return " " + messaging.render("paybill_hint", b.lang, amount=kes(b.balance_due), paybill=number, ref=b.ref)
