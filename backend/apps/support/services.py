"""Support desk. Every guest request gets a reference (T12) and a reply-by time on whichever channel it arrived:
SMS, USSD, a voice message or the website. Amina answers from the console or by SMS ("T12 <text>"), or taps Call to
be connected to the guest through Africa's Talking Voice. A ticket nobody answers escalates: first an SMS to Amina
and her backup, then (for complaints and call-backs) a phone call she can press 1 on to reach the guest."""

import logging
import re
from datetime import timedelta

from django.db.models import Avg
from django.utils import timezone

from apps.core.activity import record
from apps.core.models import SiteSettings
from apps.core.utils import first_name, spoken_digits
from apps.messaging import services as messaging

from .models import Ticket, TicketEvent

log = logging.getLogger("amina.support")

SLA = {
    "urgent": timedelta(minutes=15),
    "high": timedelta(minutes=30),
    "normal": timedelta(hours=2),
    "low": timedelta(hours=8),
}
SLA_TEXT = {
    "en": {"urgent": "15 minutes", "high": "30 minutes", "normal": "2 hours", "low": "8 hours"},
    "sw": {"urgent": "dakika 15", "high": "dakika 30", "normal": "saa 2", "low": "saa 8"},
}
DEFAULT_PRIORITY = {
    "complaint": "high",
    "callback": "high",
    "issue": "normal",
    "billing": "normal",
    "booking": "normal",
    "feedback": "low",
    "other": "normal",
}
TASK_PRIORITY = {"urgent": "urgent", "high": "high", "normal": "normal", "low": "low"}
OPEN = ("open", "in_progress")
CALL_ESCALATE = ("urgent", "high")  # these ring Amina's phone once the SMS reminder has gone unanswered too
REF = re.compile(r"\bT-?(\d{1,7})\b", re.IGNORECASE)
DUPLICATE_WINDOW = timedelta(minutes=10)

TEXT = {
    "en": {
        "none": "You have no open requests. Reply COMPLAIN and tell us what went wrong, or CALL ME for a call-back.",
        "list": "Your requests: {items}. Reply the reference (e.g. {ref}) for details.",
        "detail": "{ref} {category}: {subject} - {status}.{last}",
        "last": " Latest: {text}",
        "unknown": "We couldn't find request {ref} for this number. Reply TICKETS to see yours.",
        "complaint_ask": "Sorry to hear that. Tell us what went wrong in one message and we'll pass it straight to {host}.",
    },
    "sw": {
        "none": "Huna ombi lililo wazi. Jibu COMPLAIN na utueleze tatizo, au CALL ME tukupigie.",
        "list": "Maombi yako: {items}. Jibu kumbukumbu (mf. {ref}) kwa maelezo.",
        "detail": "{ref} {category}: {subject} - {status}.{last}",
        "last": " Mpya: {text}",
        "unknown": "Hatukupata ombi {ref} kwa nambari hii. Jibu TICKETS kuona yako.",
        "complaint_ask": "Samahani kwa hilo. Tueleze tatizo kwa ujumbe mmoja na tutampa {host} moja kwa moja.",
    },
}
STATUS_SW = {
    "open": "Limepokelewa",
    "in_progress": "Linashughulikiwa",
    "resolved": "Limemalizika",
    "closed": "Limefungwa",
}
CATEGORY_SW = {
    "complaint": "Malalamiko",
    "issue": "Tatizo nyumbani",
    "callback": "Nipigie",
    "billing": "Malipo",
    "booking": "Nafasi",
    "feedback": "Maoni",
    "other": "Mengineyo",
}


def t_(key, lang, **kw):
    text = TEXT.get(lang, TEXT["en"]).get(key) or TEXT["en"][key]
    return text.format(**kw) if kw else text


def sentence(text, limit=140):
    """A guest's words inside our own message: trimmed, ending in exactly one full stop."""
    text = (text or "").strip()[:limit].rstrip()
    return text if text.endswith((".", "!", "?")) else f"{text}."


def parse_ref(text):
    m = REF.search(text or "")
    return int(m[1]) if m else None


def lang_of(t):
    return (t.guest.lang if t.guest_id else "") or (t.booking.lang if t.booking_id else "") or "en"


def category_in(t, lang):
    return CATEGORY_SW.get(t.category) if lang == "sw" else t.get_category_display()


def status_in(t, lang):
    return STATUS_SW.get(t.status) if lang == "sw" else t.get_status_display()


def sla_text(priority, lang="en"):
    return SLA_TEXT.get(lang, SLA_TEXT["en"])[priority]


def event(t, kind, text, channel="", actor=None):
    TicketEvent.objects.create(
        ticket=t, kind=kind, text=text[:2000], channel=channel, actor=actor if getattr(actor, "pk", None) else None
    )
    Ticket.objects.filter(pk=t.pk).update(updated_at=timezone.now())


def overdue(t, now=None):
    now = now or timezone.now()
    return bool(t.status in OPEN and not t.first_response_at and t.first_response_due and t.first_response_due <= now)


# ---------- opening ----------


def open_ticket(
    phone,
    *,
    category,
    subject,
    description="",
    channel="sms",
    booking=None,
    priority=None,
    recording_url="",
    task=None,
    ack=True,
    tell_host=True,
    actor=None,
    reply_channel=None,
):
    from apps.accounts.services import get_or_create_user
    from apps.bookings.services import current_booking, notify_host

    guest, _ = get_or_create_user(phone, channel=channel)
    phone = guest.phone
    booking = booking or current_booking(phone)
    now = timezone.now()
    repeat = Ticket.objects.filter(
        phone=phone,
        category=category,
        description=description or "",
        status__in=OPEN,
        created_at__gte=now - DUPLICATE_WINDOW,
    ).first()
    if repeat is not None and not recording_url:  # a double tap on USSD, the same SMS sent twice: one ticket
        if ack:
            _acknowledge(repeat, guest, reply_channel)
        return repeat
    priority = priority or DEFAULT_PRIORITY.get(category, "normal")
    t = Ticket.objects.create(
        phone=phone,
        guest=guest,
        booking=booking,
        unit=booking.unit if booking else None,
        task=task,
        channel=channel,
        category=category,
        priority=priority,
        subject=(subject or description or "Request")[:140],
        description=description or "",
        recording_url=recording_url,
        first_response_due=now + SLA[priority],
    )
    event(
        t,
        "created",
        f"{t.get_category_display()} via {t.get_channel_display()}: {description or t.subject}",
        channel,
        actor,
    )
    record(
        "message",
        f"Ticket {t.ref}: {t.get_category_display()} from {guest.display_name}",
        channel=channel if channel != "host" else "",
        booking=booking,
        phone=phone,
    )
    if ack:
        _acknowledge(t, guest, reply_channel)
    if tell_host:
        where = f" ({booking.ref} {booking.unit.name})" if booking else ""
        said = sentence(description or t.subject)
        verb = "wants a call back" if category == "callback" else f"- {t.get_category_display().lower()}"
        voice = f", CALL {t.ref} to be connected" if category in ("callback", "complaint") else ""
        notify_host(
            f"{t.ref}: {guest.display_name}{where} {verb}: {said} "
            f"Reply {t.ref} <text> to answer{voice}. Due in {sla_text(priority)}.",
            booking=booking,
            kind="ticket_new",
        )
    return t


def _acknowledge(t, guest, reply_channel=None):
    lang = guest.lang or "en"
    key = "ticket_callback" if t.category == "callback" else "ticket_opened"
    messaging.send(
        t.phone,
        messaging.render(key, lang, ref=t.ref, subject=t.subject[:60], sla=sla_text(t.priority, lang)),
        kind=key,
        booking=t.booking,
        channel=reply_channel,  # a question typed in the web chat is answered there
    )


def request_callback(phone, *, channel="sms", booking=None, note=""):
    return open_ticket(
        phone,
        category="callback",
        subject="Please call me back",
        description=note,
        channel=channel,
        booking=booking,
    )


def open_for_issue(task, booking, text, channel):
    """A problem in the home (operations.report_issue) is a ticket too, tied to its work order: no extra SMS (the
    guest already got 'issue logged'), and it closes when the work order does."""
    if booking is None:
        return None
    return open_ticket(
        booking.guest.phone,
        category="issue",
        subject=task.title,
        description=text,
        channel=channel if channel in dict(Ticket.CHANNELS) else "web",
        booking=booking,
        priority=TASK_PRIORITY.get(task.priority, "normal"),
        task=task,
        ack=False,
        tell_host=False,
    )


# ---------- answering ----------


def _first_response(t, now=None):
    if t.first_response_at is None:
        t.first_response_at = now or timezone.now()
    if t.status == "open":
        t.status = "in_progress"


def reply(t, text, *, user=None, channel="sms"):
    """Amina's answer, by SMS to the guest with the reference, from the console or her phone."""
    s = SiteSettings.load()
    text = (text or "").strip()
    messaging.send(
        t.phone, f"{s.host_name} ({t.ref}): {text}", sender="host", user=user, booking=t.booking, kind="ticket_reply"
    )
    _first_response(t)
    t.save(update_fields=["first_response_at", "status", "updated_at"])
    event(t, "reply", text, "sms", user)
    return t


def _ask_rating(t):
    """Only ask for a 1-5 when the guest isn't in the middle of something else on SMS."""
    from apps.messaging.models import Conversation

    c = Conversation.objects.filter(phone=t.phone).first()
    busy = c is not None and c.state not in ("idle", "ticket_rating")  # a newer resolution may take over the rating
    if busy and c.updated_at > timezone.now() - timedelta(hours=24):
        return False
    Conversation.objects.update_or_create(phone=t.phone, defaults={"state": "ticket_rating", "data": {"ticket": t.pk}})
    return True


def resolve(t, *, note="", user=None, notify=True, channel=""):
    if t.status in ("resolved", "closed"):
        return t
    now = timezone.now()
    _first_response(t, now)
    t.status, t.resolved_at, t.resolution = "resolved", now, (note or "").strip()[:300]
    t.save(update_fields=["status", "resolved_at", "resolution", "first_response_at", "updated_at"])
    event(t, "status", f"Resolved{': ' + t.resolution if t.resolution else ''}", channel, user)
    if notify and t.category != "issue":  # a fixed problem in the home already gets 'issue fixed' from operations
        lang = lang_of(t)
        rate_line = " " + messaging.render("ticket_rate_line", lang) if _ask_rating(t) else ""
        messaging.send(
            t.phone,
            messaging.render(
                "ticket_resolved", lang, ref=t.ref, note=f" {t.resolution}" if t.resolution else "", rate_line=rate_line
            ),
            kind="ticket_resolved",
            booking=t.booking,
        )
    return t


def reopen(t, *, user=None):
    if t.status in OPEN:
        return t
    t.status = "in_progress" if t.first_response_at else "open"
    t.resolved_at = None
    t.save(update_fields=["status", "resolved_at", "updated_at"])
    event(t, "status", "Reopened", "", user)
    return t


def rate(t, rating, comment="", channel="sms"):
    from apps.bookings.services import notify_host

    t.rating, t.rating_comment = rating, (comment or "")[:300]
    t.save(update_fields=["rating", "rating_comment", "updated_at"])
    event(t, "rating", f"Rated {rating}/5{': ' + t.rating_comment if t.rating_comment else ''}", channel)
    if rating <= 2:
        notify_host(
            f"{t.ref} was rated {rating}/5 by {t.guest.display_name if t.guest_id else t.phone}"
            f"{': ' + t.rating_comment if t.rating_comment else ''}. Worth a call: CALL {t.ref}.",
            booking=t.booking,
            kind="ticket_low_rating",
        )
    return t


def task_started(task):
    for t in task.tickets.filter(status="open"):
        _first_response(t)
        t.save(update_fields=["first_response_at", "status", "updated_at"])
        event(t, "task", f"Work order #{task.pk} started{' by ' + task.assignee.display_name if task.assignee else ''}")


def task_done(task):
    for t in task.tickets.filter(status__in=OPEN):
        event(t, "task", f"Work order #{task.pk} done{': ' + task.completion_note if task.completion_note else ''}")
        resolve(t, note=task.completion_note, notify=False)


# ---------- calls (Africa's Talking Voice) ----------


def call_guest(t, *, user=None):
    """Click-to-call: Africa's Talking rings Amina first; when she picks up, she hears who it is and the call is
    bridged to the guest. The guest's number never leaves the system."""
    from apps.comms import at, voice

    s = SiteSettings.load()
    host_phone = user.phone if getattr(user, "is_host", False) and user.phone else s.host_contact
    Ticket.objects.filter(pk=t.pk).update(call_requested_at=timezone.now())
    t.call_requested_at = timezone.now()
    try:
        res = at.voice_call(host_phone, client_request_id=f"bridge-{t.pk}")
    except Exception as e:
        log.warning("call-back for %s failed: %s", t.ref, e)
        event(t, "call", f"Couldn't start the call: {e}", "voice", user)
        return {"placed": False, "dry_run": False, "detail": f"Africa's Talking couldn't place the call: {e}"}
    if res.get("dry_run"):
        event(t, "call", "Call-back simulated: no Africa's Talking voice number is set up", "voice", user)
        return {
            "placed": False,
            "dry_run": True,
            "detail": "Simulated - set AT_VOICE_NUMBER for real calls. In the Demo Lab, answer it on Amina's phone.",
        }
    voice.register_outbound(res, "bridge", ticket_id=t.pk, lang="en")
    event(t, "call", f"Calling {s.host_name} on {host_phone}; the guest is connected when she picks up", "voice", user)
    return {
        "placed": True,
        "dry_run": False,
        "detail": f"Your phone ({host_phone}) is ringing - pick up to be connected.",
    }


def bridge_answered(t):
    """Amina picked up (a call-back she asked for, or the escalation call): she's about to talk to the guest."""
    _first_response(t)
    t.save(update_fields=["first_response_at", "status", "updated_at"])
    event(t, "call", "Amina answered - connecting the guest", "voice")


def call_finished(t, *, answered, talked_seconds=0, purpose="bridge"):
    if not answered:
        event(
            t,
            "call",
            "Amina didn't pick up the call" if purpose == "bridge" else "Escalation call not answered",
            "voice",
        )
    elif talked_seconds > 0:
        event(t, "call", f"Talked to the guest for {talked_seconds // 60} min {talked_seconds % 60} s", "voice")
    elif purpose == "bridge":
        event(t, "call", "The guest didn't answer", "voice")


def bridge_prompt(t):
    who = t.guest.display_name if t.guest_id and t.guest.name else spoken_digits(t.phone)
    return f"Amina Stays call-back for ticket T {t.pk}, {who}: {t.subject}. Connecting you now."


def alert_prompt(t):
    waited = max(1, int((timezone.now() - t.created_at).total_seconds() // 60))
    who = first_name(t.guest.name) if t.guest_id and t.guest.name else "A guest"
    return f"{who} has waited {waited} minutes for a reply on ticket T {t.pk}: {t.subject}. Press 1 to call them now."


# ---------- escalation (scheduler) ----------


def escalate_overdue(now=None):
    """Nobody has answered by the reply-by time: SMS Amina (and her backup). Still nothing after the same time again,
    for a complaint or call-back: ring her phone. Low-priority tickets wait for the morning."""
    from apps.bookings.services import notify_host
    from apps.comms import at, voice

    now = now or timezone.now()
    s = SiteSettings.load()
    hour = timezone.localtime(now).hour
    quiet = hour >= s.quiet_hours_start or hour < s.quiet_hours_end
    done = 0
    qs = Ticket.objects.filter(status__in=OPEN, first_response_at__isnull=True, first_response_due__lte=now)
    for t in qs.select_related("guest", "booking", "unit"):
        if quiet and t.priority not in CALL_ESCALATE:
            continue
        waited = int((now - t.created_at).total_seconds() // 60)
        who = t.guest.display_name if t.guest_id else t.phone
        if t.escalation_level == 0:
            text = (
                f"Waiting {waited} min: {t.ref} {t.get_category_display().lower()} from {who}"
                f"{' (' + t.unit.name + ')' if t.unit_id else ''}: {sentence(t.description or t.subject, 120)} "
                f"Reply {t.ref} <text> or CALL {t.ref}."
            )
            notify_host(text, booking=t.booking, kind="ticket_overdue")
            if s.backup_phone:
                messaging.send(s.backup_phone, text, kind="ticket_overdue")
            t.escalation_level, t.last_escalated_at = 1, now
            t.save(update_fields=["escalation_level", "last_escalated_at"])
            event(t, "escalated", f"No reply after {waited} min - Amina reminded by SMS")
            done += 1
        elif (
            t.escalation_level == 1
            and t.priority in CALL_ESCALATE
            and t.category != "issue"
            and now >= t.first_response_due + SLA[t.priority]
        ):
            try:
                res = at.voice_call(s.host_contact, client_request_id=f"ticket-{t.pk}")
                voice.register_outbound(res, "ticket", ticket_id=t.pk, lang="en")
                how = "simulated (no voice number)" if res.get("dry_run") else "ringing"
            except Exception as e:
                how = f"failed: {e}"
            t.escalation_level, t.last_escalated_at = 2, now
            t.save(update_fields=["escalation_level", "last_escalated_at"])
            event(t, "escalated", f"Still no reply after {waited} min - calling Amina ({how})", "voice")
            done += 1
    return done


# ---------- what the guest sees on SMS ----------


def guest_tickets(phone):
    return Ticket.objects.filter(phone=phone).select_related("guest", "booking").order_by("-id")


def list_text(phone, lang="en"):
    recent = list(guest_tickets(phone).exclude(status="closed")[:4])
    if not recent:
        return t_("none", lang)
    items = "; ".join(f"{t.ref} {category_in(t, lang)} - {status_in(t, lang)}" for t in recent)
    return t_("list", lang, items=items, ref=recent[0].ref)


def detail_text(phone, pk, lang="en"):
    t = guest_tickets(phone).filter(pk=pk).first()
    if t is None:
        return t_("unknown", lang, ref=f"T{pk}")
    last = t.events.filter(kind__in=("reply", "status")).order_by("-id").first()
    return t_(
        "detail",
        lang,
        ref=t.ref,
        category=category_in(t, lang),
        subject=t.subject[:60],
        status=status_in(t, lang),
        last=t_("last", lang, text=last.text[:140]) if last else "",
    )


def host_list_text():
    now = timezone.now()
    open_ = list(
        Ticket.objects.filter(status__in=OPEN).select_related("guest", "unit").order_by("first_response_due")[:5]
    )
    if not open_:
        return "No open tickets. Nice!"
    items = "; ".join(
        f"{t.ref} {t.get_category_display()} {first_name(t.guest.name) if t.guest_id and t.guest.name else t.phone}"
        f"{' (' + t.unit.name + ')' if t.unit_id else ''} {'OVERDUE' if overdue(t, now) else ''}".strip()
        for t in open_
    )
    return f"Open: {items}. Reply T<n> <text>, CALL T<n> or RESOLVE T<n>."


def host_detail_text(pk):
    t = Ticket.objects.filter(pk=pk).select_related("guest", "unit", "booking").first()
    if t is None:
        return f"No ticket T{pk}."
    who = t.guest.display_name if t.guest_id else t.phone
    last = t.events.order_by("-id").first()
    return (
        f"{t.ref} {t.get_category_display()} from {who} {t.phone}{' (' + t.unit.name + ')' if t.unit_id else ''}, "
        f"{t.get_status_display().lower()}: {sentence(t.description or t.subject, 160)}"
        f"{' Last: ' + sentence(last.text, 120) if last and last.kind != 'created' else ''} "
        f"Reply {t.ref} <text>, CALL {t.ref} or RESOLVE {t.ref}."
    )


# ---------- console numbers ----------


def stats():
    now = timezone.now()
    answered = Ticket.objects.filter(first_response_at__isnull=False, created_at__gte=now - timedelta(days=30))
    minutes = [
        (t.first_response_at - t.created_at).total_seconds() / 60
        for t in answered.only("created_at", "first_response_at")
    ]
    rated = Ticket.objects.filter(rating__isnull=False, created_at__gte=now - timedelta(days=90))
    return {
        "open": Ticket.objects.filter(status__in=OPEN).count(),
        "overdue": Ticket.objects.filter(
            status__in=OPEN, first_response_at__isnull=True, first_response_due__lte=now
        ).count(),
        "resolved_7d": Ticket.objects.filter(resolved_at__gte=now - timedelta(days=7)).count(),
        "avg_first_response_min": round(sum(minutes) / len(minutes)) if minutes else None,
        "csat": round(rated.aggregate(a=Avg("rating"))["a"], 1) if rated.exists() else None,
        "csat_count": rated.count(),
    }
