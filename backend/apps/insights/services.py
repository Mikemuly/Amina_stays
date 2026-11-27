"""Host KPIs, defined the way the industry does (AirDNA / Key Data conventions):

occupancy = booked nights / available nights (owner & maintenance blocks are not available;
            nights sold on Airbnb/Booking.com via iCal count as booked)
ADR       = room revenue / booked nights          RevPAR = room revenue / available nights
"""

import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

from django.db.models import Q, Sum
from django.utils import timezone

from apps.bookings.models import LIVE_STATUSES, Booking
from apps.core.utils import daterange, today
from apps.properties.models import CalendarBlock, Unit


def _overlap(a_start, a_end, b_start, b_end):
    return max(0, (min(a_end, b_end) - max(a_start, b_start)).days)


def occupancy(start, end, unit_ids=None):
    units = Unit.objects.filter(status="active")
    if unit_ids:
        units = units.filter(pk__in=unit_ids)
    ids = list(units.values_list("pk", flat=True))
    days = (end - start).days
    available = len(ids) * days
    booked = 0
    for b in Booking.objects.filter(
        unit_id__in=ids, status__in=LIVE_STATUSES, check_in__lt=end, check_out__gt=start
    ).only("check_in", "check_out"):
        booked += _overlap(b.check_in, b.check_out, start, end)
    for blk in CalendarBlock.objects.filter(unit_id__in=ids, start_date__lt=end, end_date__gt=start):
        n = _overlap(blk.start_date, blk.end_date, start, end)
        if blk.reason == "external":
            booked += n
        else:
            available -= n
    return {
        "occupancy": round(100 * booked / available) if available > 0 else 0,
        "booked_nights": booked,
        "available_nights": max(available, 0),
    }


def room_revenue(start, end, unit_ids=None):
    """Accommodation revenue earned on nights inside [start, end) (nightly breakdown, net of stay discounts)."""
    total, nights = 0, 0
    qs = Booking.objects.filter(status__in=LIVE_STATUSES, check_in__lt=end, check_out__gt=start)
    if unit_ids:
        qs = qs.filter(unit_id__in=unit_ids)
    for b in qs.only("nightly", "accommodation_amount", "discount_amount", "check_in", "check_out"):
        factor = (b.accommodation_amount - b.discount_amount) / b.accommodation_amount if b.accommodation_amount else 1
        for n in b.nightly or []:
            d = date.fromisoformat(n["date"])
            if start <= d < end:
                total += n["price"] * factor
                nights += 1
    return round(total), nights


def kpis(start, end):
    from apps.messaging.models import Message
    from apps.payments.models import Payment, Refund
    from apps.reviews.models import Review

    occ = occupancy(start, end)
    revenue, sold = room_revenue(start, end)
    created = Booking.objects.filter(created_at__date__gte=start, created_at__date__lt=end).exclude(status="expired")
    live = created.filter(status__in=LIVE_STATUSES)
    by_channel = defaultdict(lambda: {"bookings": 0, "revenue": 0})
    for b in live.only("channel", "total"):
        by_channel[b.channel]["bookings"] += 1
        by_channel[b.channel]["revenue"] += b.total
    leads = [(b.check_in - timezone.localtime(b.created_at).date()).days for b in live.only("check_in", "created_at")]
    stays = [b.nights for b in live.only("check_in", "check_out")]
    cancelled = created.filter(status__in=("cancelled", "refund_due")).count()
    ota = live.filter(channel__in=("airbnb", "booking_com")).count()

    collected = (
        Payment.objects.filter(status="success", completed_at__date__gte=start, completed_at__date__lt=end).aggregate(
            s=Sum("amount")
        )["s"]
        or 0
    )
    refunded = (
        Refund.objects.filter(status="success", completed_at__date__gte=start, completed_at__date__lt=end).aggregate(
            s=Sum("amount")
        )["s"]
        or 0
    )
    by_method = {
        r["method"]: r["s"]
        for r in Payment.objects.filter(status="success", completed_at__date__gte=start, completed_at__date__lt=end)
        .values("method")
        .annotate(s=Sum("amount"))
    }
    stays_in_period = Booking.objects.filter(status__in=LIVE_STATUSES, check_in__lt=end, check_out__gt=start)
    addons = stays_in_period.aggregate(s=Sum("addons_amount"))["s"] or 0
    levy = stays_in_period.aggregate(s=Sum("levy_amount"))["s"] or 0

    # responsiveness: how fast a relayed question got a human answer, and how much the bot handled alone
    inbound = Message.objects.filter(
        direction="in", sender="guest", created_at__date__gte=start, created_at__date__lt=end
    )
    auto = inbound.filter(handled="auto").count()
    total_in = inbound.exclude(handled="na").count()
    waits = []
    for m in inbound.filter(handled__in=("answered", "relayed")).only("thread_id", "created_at")[:300]:
        reply = (
            Message.objects.filter(
                thread_id=m.thread_id, direction="out", sender__in=("host", "staff"), created_at__gt=m.created_at
            )
            .order_by("id")
            .first()
        )
        if reply:
            waits.append((reply.created_at - m.created_at).total_seconds() / 60)
    reviews = Review.objects.filter(created_at__date__gte=start, created_at__date__lt=end)
    rating = reviews.aggregate(s=Sum("rating"))["s"]

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        **occ,
        "room_revenue": revenue,
        "adr": round(revenue / sold) if sold else 0,
        "revpar": round(revenue / occ["available_nights"]) if occ["available_nights"] else 0,
        "collected": collected - refunded,
        "refunded": refunded,
        "by_method": by_method,
        "bookings": live.count(),
        "by_channel": dict(by_channel),
        "lead_time_days": round(statistics.mean(leads), 1) if leads else 0,
        "avg_stay_nights": round(statistics.mean(stays), 1) if stays else 0,
        "cancellation_rate": round(100 * cancelled / created.count()) if created.count() else 0,
        "direct_share": round(100 * (live.count() - ota) / live.count()) if live.count() else 0,
        "addon_revenue": addons,
        "levy_due": levy,
        "response_minutes": round(statistics.median(waits)) if waits else None,
        "auto_answer_rate": round(100 * auto / total_in) if total_in else 0,
        "messages_in": total_in,
        "reviews": reviews.count(),
        "rating": round(rating / reviews.count(), 2) if reviews.count() else None,
    }


def daily_series(start, end):
    """Per-day occupancy %, room revenue and new bookings by channel — for the insights charts."""
    units = Unit.objects.filter(status="active").count() or 1
    nightly = defaultdict(float)
    occupied = Counter()
    for b in Booking.objects.filter(status__in=LIVE_STATUSES, check_in__lt=end, check_out__gt=start).only(
        "nightly", "accommodation_amount", "discount_amount"
    ):
        factor = (b.accommodation_amount - b.discount_amount) / b.accommodation_amount if b.accommodation_amount else 1
        for n in b.nightly or []:
            d = date.fromisoformat(n["date"])
            if start <= d < end:
                nightly[d] += n["price"] * factor
                occupied[d] += 1
    for blk in CalendarBlock.objects.filter(reason="external", start_date__lt=end, end_date__gt=start):
        for d in daterange(max(blk.start_date, start), min(blk.end_date, end)):
            occupied[d] += 1
    created = defaultdict(Counter)
    for b in Booking.objects.filter(
        created_at__date__gte=start, created_at__date__lt=end, status__in=LIVE_STATUSES
    ).only("created_at", "channel"):
        created[timezone.localtime(b.created_at).date()][b.channel] += 1
    return [
        {
            "date": d.isoformat(),
            "occupancy": round(100 * min(occupied[d], units) / units),
            "revenue": round(nightly[d]),
            "bookings": dict(created[d]),
        }
        for d in daterange(start, end)
    ]


def forward_bookings(days=60):
    """On-the-books occupancy for the coming weeks (pace)."""
    t = today()
    return [
        {
            "week_start": (t + timedelta(days=7 * i)).isoformat(),
            **occupancy(t + timedelta(days=7 * i), t + timedelta(days=7 * (i + 1))),
        }
        for i in range(days // 7)
    ]


def tra_return(year, month):
    """Monthly return to the Tourism Regulatory Authority (Tourism Enterprises Regulations 2025, r.27):
    bed occupancy, visitors by country of origin, and revenue."""
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    occ = occupancy(start, end)
    revenue, _nights = room_revenue(start, end)
    stays = (
        Booking.objects.filter(status__in=LIVE_STATUSES, check_in__lt=end, check_out__gt=start)
        .select_related("guest")
        .prefetch_related("occupants")
    )
    countries = Counter()
    guest_nights = 0
    for b in stays:
        n = _overlap(b.check_in, b.check_out, start, end)
        occupants = list(b.occupants.all()) or [None]
        for o in occupants:
            country = (o.nationality if o else "") or b.guest.nationality or "Unknown"
            countries[country] += 1
            guest_nights += n
    levy = stays.aggregate(s=Sum("levy_amount"))["s"] or 0
    return {
        "month": f"{year}-{month:02d}",
        "units": Unit.objects.filter(status="active").count(),
        "occupancy": occ["occupancy"],
        "room_nights_sold": occ["booked_nights"],
        "room_nights_available": occ["available_nights"],
        "guest_nights": guest_nights,
        "arrivals": stays.filter(check_in__gte=start, check_in__lt=end).count(),
        "visitors_by_country": dict(countries.most_common()),
        "room_revenue": revenue,
        "tourism_levy": levy,
    }


def host_today():
    """Everything the 'Today' screen needs in one query batch."""
    from apps.messaging.models import Thread
    from apps.operations.models import Task
    from apps.operations.services import kitchen_sheet
    from apps.safety.models import Alert

    t = today()
    base = Booking.objects.select_related("unit", "guest", "unit__area")
    return {
        "date": t.isoformat(),
        "arrivals": list(base.filter(check_in=t, status__in=("confirmed", "checked_in")).order_by("unit__name")),
        "departures": list(base.filter(check_out=t, status__in=("checked_in", "completed")).order_by("unit__name")),
        "in_house": list(base.filter(status="checked_in").order_by("check_out")),
        "upcoming": list(
            base.filter(status="confirmed", check_in__gt=t, check_in__lte=t + timedelta(days=7)).order_by("check_in")
        ),
        "holds": list(base.filter(status="held", hold_expires_at__gt=timezone.now()).order_by("-created_at")),
        "tasks": list(
            Task.objects.filter(status__in=("open", "in_progress"))
            .select_related("unit", "assignee")
            .order_by("due_at")[:20]
        ),
        "alerts": list(Alert.objects.filter(~Q(status="resolved")).select_related("booking").order_by("-id")[:20]),
        "threads": list(Thread.objects.filter(needs_reply=True).select_related("guest").order_by("waiting_since")[:20]),
        "breakfasts": kitchen_sheet(t + timedelta(days=1 if timezone.localtime().hour >= 11 else 0)),
    }
