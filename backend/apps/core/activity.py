import logging

log = logging.getLogger("amina")


def record(kind, title, *, channel="", detail="", booking=None, phone="", actor=None, **data):
    """Write one line to the activity feed / audit trail. Never raises."""
    from .models import Activity

    try:
        ref = getattr(booking, "ref", booking) or ""
        Activity.objects.create(
            kind=kind,
            channel=channel or "",
            title=title[:200],
            detail=detail or "",
            booking_ref=ref,
            phone=phone
            or (getattr(booking, "guest_phone", "") if booking is not None and not isinstance(booking, str) else ""),
            actor=actor if getattr(actor, "pk", None) else None,
            data=data,
        )
    except Exception:  # the feed must never break a booking or a webhook
        log.exception("activity record failed: %s", title)
