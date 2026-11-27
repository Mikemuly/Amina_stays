"""Demo data for service alerts: a Wi-Fi outage happening now where a guest is staying (so the data bundle shows), a
water-tank clean planned for tomorrow, and last week's power cut, long fixed."""

from datetime import timedelta

from django.utils import timezone


def seed():
    from apps.bookings.models import Booking
    from apps.properties.models import Unit

    from . import services
    from .models import Notice

    now = timezone.now()
    made = 0
    # an international guest's home: the Demo Lab keeps the Kenyan guests' homes free to post an outage live
    staying = (
        Booking.objects.filter(status="checked_in")
        .exclude(guest__phone__startswith="+254")
        .select_related("unit")
        .first()
        or Booking.objects.filter(status="checked_in").select_related("unit").order_by("-check_in").first()
    )
    if staying is not None:
        services.create(
            kind="outage",
            service="wifi",
            message="The fibre provider has a fault on our street and is fixing it. Mobile data works fine.",
            units=[staying.unit],
            expected_end=now + timedelta(hours=3),
            data_mb=100,
            source="demo",
        )
        made += 1
    later = (
        Booking.objects.filter(status__in=("confirmed", "checked_in"), check_out__gt=now.date() + timedelta(days=1))
        .exclude(unit=staying.unit if staying else None)
        .select_related("unit")
        .order_by("check_in")
        .first()
    )
    if later is not None:
        start = timezone.localtime(now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        services.create(
            kind="maintenance",
            service="water",
            title="Water tank cleaning",
            message="Water will be off for about two hours while the tank is cleaned. We'll fill buckets for you first.",
            units=[later.unit],
            starts_at=start,
            expected_end=start + timedelta(hours=2),
            source="demo",
        )
        made += 1
    unit = Unit.objects.filter(status="active").order_by("id").first()
    if unit is not None:
        start = now - timedelta(days=6, hours=4)
        n = Notice.objects.create(
            kind="outage",
            service="power",
            status="resolved",
            title="Power outage",
            message="Kenya Power is repairing a transformer. The backup generator runs lights, fans and the fridge.",
            starts_at=start,
            expected_end=start + timedelta(hours=3),
            resolved_at=start + timedelta(hours=2, minutes=20),
            resolution="Power is back - Kenya Power replaced the fuse on the transformer.",
            notified=3,
            source="host",
        )
        Notice.objects.filter(pk=n.pk).update(created_at=start)
        made += 1
    return made
