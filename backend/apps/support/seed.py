"""Demo data for the support desk: an overdue complaint, a fresh call-back request, a billing question Amina has
answered, and resolved tickets with ratings - so the console, the guests' phones and the escalation job all have
something real to show."""

from datetime import timedelta

from django.utils import timezone


def _backdate(t, minutes):
    from .models import Ticket, TicketEvent
    from .services import SLA

    at = timezone.now() - timedelta(minutes=minutes)
    Ticket.objects.filter(pk=t.pk).update(created_at=at, first_response_due=at + SLA[t.priority])
    TicketEvent.objects.filter(ticket=t, kind="created").update(created_at=at)
    t.refresh_from_db()
    return t


def seed():
    from apps.bookings.models import Booking

    from . import services
    from .models import Ticket, TicketEvent

    stays = list(Booking.objects.filter(status="checked_in").select_related("guest", "unit").order_by("check_in"))
    upcoming = list(Booking.objects.filter(status="confirmed").select_related("guest", "unit").order_by("check_in"))
    past = list(
        Booking.objects.filter(status="completed").select_related("guest", "unit").order_by("-checked_out_at")[:6]
    )
    made = 0

    if stays:
        b = stays[0]
        t = services.open_ticket(
            b.guest.phone,
            category="complaint",
            subject="Loud music next door until 1am",
            description="Loud music next door until 1am two nights running. We couldn't sleep.",
            channel="sms",
            booking=b,
        )
        _backdate(t, 42)  # past its 30-minute reply-by time: the escalation job reminds Amina
        made += 1
    if len(stays) > 1:
        b = stays[1]
        services.request_callback(b.guest.phone, channel="ussd", booking=b, note="Asked by USSD")
        made += 1
    if upcoming:
        b = upcoming[0]
        t = services.open_ticket(
            b.guest.phone,
            category="billing",
            subject="Was the deposit received?",
            description="I paid the deposit yesterday - was it received? The trip page still shows a balance.",
            channel="web",
            booking=b,
            ack=False,
            tell_host=False,
        )
        _backdate(t, 95)
        services.reply(
            t,
            "Yes - your deposit is in. The balance shown is what's due 1 day before arrival; we'll send a reminder.",
            user=None,
        )
        made += 1

    lines = [
        (
            "complaint",
            "Hot water took ages in the morning",
            "Fixed the timer on the geyser and left an extra kettle. Pole sana!",
            5,
        ),
        ("booking", "Can we arrive at 10am?", "Early check-in from 11am arranged - see you then.", 4),
        (
            "feedback",
            "Lovely breakfast, could we have more fruit?",
            "Mama Zawadi now adds a fruit platter for every booking.",
            5,
        ),
    ]
    for b, (category, subject, resolution, rating) in zip(past, lines, strict=False):
        when = (b.checked_out_at or timezone.now()) - timedelta(days=1, hours=3)
        t = Ticket.objects.create(
            phone=b.guest.phone,
            guest=b.guest,
            booking=b,
            unit=b.unit,
            channel="sms",
            category=category,
            priority=services.DEFAULT_PRIORITY[category],
            status="resolved",
            subject=subject,
            description=subject,
            first_response_due=when + services.SLA[services.DEFAULT_PRIORITY[category]],
            first_response_at=when + timedelta(minutes=11),
            resolved_at=when + timedelta(hours=2),
            resolution=resolution,
            rating=rating,
        )
        Ticket.objects.filter(pk=t.pk).update(created_at=when)
        for minutes, kind, text in (
            (0, "created", f"{t.get_category_display()} via SMS: {subject}"),
            (11, "reply", "Thanks for telling us - we're on it."),
            (120, "status", f"Resolved: {resolution}"),
            (150, "rating", f"Rated {rating}/5"),
        ):
            e = TicketEvent.objects.create(ticket=t, kind=kind, text=text, channel="sms")
            TicketEvent.objects.filter(pk=e.pk).update(created_at=when + timedelta(minutes=minutes))
        made += 1
    return made
