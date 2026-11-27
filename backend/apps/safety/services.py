"""Safety & alerts. 'HELP' by SMS, 9 on a call, the SOS button on the web or USSD option 9 all
skip every queue: Amina's phone rings (Africa's Talking Voice) and she gets an SMS with who and
where. If nobody acknowledges within 3 minutes the backup contact is called."""

import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.activity import record
from apps.core.models import OnceMarker, SiteSettings
from apps.core.utils import mask_phone

from .models import Alert

log = logging.getLogger("amina.safety")


def _guest_and_booking(phone):
    from apps.accounts.models import User
    from apps.bookings.services import current_booking

    guest = User.objects.filter(phone=phone).first()
    booking = current_booking(phone) if phone else None
    return guest, booking


def describe(phone):
    guest, booking = _guest_and_booking(phone)
    who = f"{guest.name} ({phone})" if guest and guest.name else phone
    if booking:
        where = f"{'staying at' if booking.status == 'checked_in' else 'booked at'} {booking.unit.name}, {booking.unit.area.name} (ref {booking.ref})"
    else:
        where = "no active booking"
    return guest, booking, who, where


def raise_alert(
    kind, summary, *, severity="high", booking=None, phone="", source="system", details="", dedupe=None, notify=True
):
    if dedupe and not OnceMarker.mark(f"alert:{dedupe}"):
        return None
    guest = booking.guest if booking is not None else None
    alert = Alert.objects.create(
        kind=kind,
        severity=severity,
        source=source,
        phone=phone or (guest.phone if guest else ""),
        guest=guest,
        booking=booking,
        summary=summary[:300],
        details=details,
    )
    record("alert", summary, booking=booking, phone=alert.phone, severity=severity, alert_id=alert.pk)
    if notify and severity in ("critical", "high"):
        from apps.messaging import services as messaging

        messaging.send(
            SiteSettings.load().host_contact, f"ALERT: {summary} Reply OK when handled.", booking=booking, kind="alert"
        )
    return alert


def _call(number, alert):
    from apps.comms import at
    from apps.comms.voice import register_outbound

    try:
        res = at.voice_call(number, client_request_id=f"alert-{alert.pk}")
        register_outbound(res, "alert", alert_id=alert.pk)
        entry = (res.get("entries") or [{}])[0]
        return "dry_run" if res.get("dry_run") else entry.get("status", "requested")
    except Exception as e:
        log.error("safety call failed: %s", e)
        return "failed"


def escalate(phone, source, *, text="", call=True):
    """Guest asked for urgent help. Returns the Alert."""
    from apps.messaging import services as messaging

    s = SiteSettings.load()
    guest, booking, who, where = describe(phone)
    alert = Alert.objects.create(
        kind="sos",
        severity="critical",
        source=source,
        phone=phone,
        guest=guest,
        booking=booking,
        summary=f"SOS from {who}, {where}"[:300],
        details=text,
        call_status="pending",
    )
    status = _call(s.host_contact, alert) if call else "bridged"
    alert.call_status, alert.calls_made, alert.last_call_at = status, 1 if call else 0, timezone.now()
    alert.save(update_fields=["call_status", "calls_made", "last_call_at"])
    lead = (
        "Calling you now."
        if status in ("Queued", "dry_run")
        else "Connecting the caller to you now."
        if status == "bridged"
        else "Please call them now."
    )
    note = f' They said: "{text[:80]}"' if text else ""
    messaging.send(
        s.host_contact,
        f"URGENT HELP ({source}): {who}, {where}.{note} {lead} Reply OK when handled.",
        booking=booking,
        kind="sos",
    )
    if s.backup_phone:
        messaging.send(
            s.backup_phone,
            f"URGENT for {s.host_name}: guest {who}, {where} needs help ({source}). Please check in with {s.host_name}.",
            kind="sos",
        )
    record(
        "alert",
        f"SOS via {source}: {who}",
        channel=source,
        booking=booking,
        phone=phone,
        alert_id=alert.pk,
        call=status,
    )
    return alert


def acknowledge(alert, user=None):
    if alert.status == "open":
        alert.status, alert.acknowledged_at, alert.acknowledged_by = (
            "acknowledged",
            timezone.now(),
            user if getattr(user, "pk", None) else None,
        )
        alert.save(update_fields=["status", "acknowledged_at", "acknowledged_by"])
        record("alert", f"Alert #{alert.pk} acknowledged", actor=user)
    return alert


def resolve(alert, user=None, note=""):
    alert.status, alert.resolved_at = "resolved", timezone.now()
    alert.resolved_by = user if getattr(user, "pk", None) else None
    alert.resolution_note = note[:300]
    if not alert.acknowledged_at:
        alert.acknowledged_at = alert.resolved_at
    alert.save(update_fields=["status", "resolved_at", "resolved_by", "resolution_note", "acknowledged_at"])
    record("alert", f"Alert #{alert.pk} resolved{': ' + note if note else ''}", actor=user)
    return alert


def acknowledge_latest(user=None):
    open_alerts = Alert.objects.filter(status="open")
    alert = open_alerts.filter(kind="sos").order_by("-id").first() or open_alerts.order_by("-id").first()
    return acknowledge(alert, user) if alert else None


def recall(alert):
    """The call bridged to Amina wasn't answered: ring her again now on the same alert (follow-ups carry on
    from this attempt, and one OK still settles the whole emergency)."""
    from apps.messaging import services as messaging

    s = SiteSettings.load()
    status = _call(s.host_contact, alert)
    alert.calls_made += 1
    alert.last_call_at, alert.call_status = timezone.now(), status
    alert.save(update_fields=["calls_made", "last_call_at", "call_status"])
    _, _, who, where = describe(alert.phone)
    messaging.send(
        s.host_contact,
        f"URGENT HELP ({alert.source}): {who}, {where}. The call to you wasn't answered. Calling you now. "
        "Reply OK when handled.",
        booking=alert.booking,
        kind="sos",
    )
    record(
        "alert", f"SOS #{alert.pk} bridge not answered - calling {mask_phone(s.host_contact)} again", alert_id=alert.pk
    )
    return alert


FOLLOW_UP_AFTER = timedelta(minutes=3)
MAX_CALLS = 3


def call_next(alert, why="still open"):
    """The escalation ladder for an open SOS: Amina, her backup contact, then Amina again (3 calls at most).
    The timer climbs it 3 minutes after the last call; an outbound call that ends unanswered climbs it at once.
    Returns the number rung, or None (settled, ladder done, or the step was just taken elsewhere)."""
    s = SiteSettings.load()
    n = alert.calls_made
    if alert.kind != "sos" or alert.status != "open" or n >= MAX_CALLS:
        return None
    number = s.backup_phone if (n % 2 == 1 and s.backup_phone) else s.host_contact
    # claim the step first: the timer and an 'unanswered' callback must never both ring the next person
    if not Alert.objects.filter(pk=alert.pk, status="open", calls_made=n).update(
        calls_made=n + 1, last_call_at=timezone.now()
    ):
        return None
    status = _call(number, alert)
    alert.calls_made, alert.last_call_at, alert.call_status = n + 1, timezone.now(), status
    alert.save(update_fields=["calls_made", "last_call_at", "call_status"])
    record("alert", f"SOS #{alert.pk} {why} - calling {mask_phone(number)} (attempt {n + 1})", alert_id=alert.pk)
    return number


def followups():
    """Unacknowledged SOS: ring the backup contact, then Amina again (max 3 calls)."""
    cutoff = timezone.now() - FOLLOW_UP_AFTER
    for alert in Alert.objects.filter(kind="sos", status="open", calls_made__lt=MAX_CALLS, last_call_at__lt=cutoff):
        call_next(alert)


def balance_unpaid_on_arrival(booking):
    """Arrival morning with money still owed: release_code keeps the door code back, and Amina needs to know now."""
    from apps.core.utils import kes, nice_date, today

    b = booking
    when = "arrives today" if b.check_in >= today() else f"was due in on {nice_date(b.check_in)}"
    return raise_alert(
        "payment",
        f"Balance {kes(b.balance_due)} unpaid - {b.ref} ({b.guest.display_name}) {when}; door code withheld.",
        severity="high",
        booking=b,
        source="system",
        dedupe=f"code-withheld-balance:{b.ref}",
    )


# ---------- TRA licence (Tourism Act: licences run to 31 December) ----------

LICENCE_STEPS = (45, 30, 14, 7, 1)  # days before the expiry date in Settings; once more on/after the day


def licence_reminder():
    """The daily job: an SMS to Amina and a compliance alert at each step, once per step and expiry date. A newer
    reminder replaces the open one, and a renewed licence (a later expiry date) closes the old ones."""
    from apps.bookings.services import notify_host
    from apps.core.utils import today

    s = SiteSettings.load()
    expiry = s.tra_licence_expiry
    if not expiry:
        return 0
    tag = f"tra_licence:{expiry.isoformat()}"
    left = (expiry - today()).days
    if left > LICENCE_STEPS[0]:
        _settle_licence_alerts(f"Licence renewed - valid to {expiry.day} {expiry:%b %Y}", keep=tag)
        return 0
    step = 0 if left <= 0 else min(d for d in LICENCE_STEPS if left <= d)
    if not OnceMarker.mark(f"licence-reminder:{expiry.isoformat()}:{step}"):
        return 0
    text = licence_text(s.tra_licence_number, expiry, left)
    notify_host(text, kind="licence_reminder")
    _settle_licence_alerts("Replaced by a newer reminder")
    raise_alert(
        "compliance", text, severity="medium" if step >= 30 else "high", source="system", details=tag, notify=False
    )
    return 1


def licence_text(number, expiry, left):
    licence = f"Your TRA licence {number}" if number else "Your TRA licence"
    date = f"{expiry.day} {expiry:%b %Y}"
    if left > 0:
        when = f"expires on {date} ({left} day{'s' if left != 1 else ''})"
    elif left == 0:
        when = f"expires today ({date})"
    else:
        when = f"expired on {date} ({-left} day{'s' if left != -1 else ''} ago)"
    return f"{licence} {when}. Renew on the TRA portal - licences run to 31 December."


def _settle_licence_alerts(note, keep=None):
    open_alerts = Alert.objects.filter(kind="compliance", details__startswith="tra_licence:").exclude(status="resolved")
    for a in open_alerts.exclude(details=keep) if keep else open_alerts:
        resolve(a, note=note)
