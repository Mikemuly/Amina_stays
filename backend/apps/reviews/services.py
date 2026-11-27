"""Verified-stay reviews: requested by SMS after checkout, with Airbnb-style category ratings on the web."""

from django.db.models import Avg, Count
from django.utils import timezone

from apps.core.activity import record
from apps.core.models import OnceMarker

from .models import CATEGORIES, Review


def request_review(booking):
    from apps.bookings.services import send_guest
    from apps.messaging.models import Conversation

    if Review.objects.filter(booking=booking).exists() or not OnceMarker.mark(f"review-request:{booking.ref}"):
        return False
    Conversation.objects.update_or_create(
        phone=booking.guest.phone, defaults={"state": "review", "data": {"ref": booking.ref}}
    )
    send_guest(booking, "review_request")
    return True


def record_rating(booking, rating, *, channel="sms", comment="", categories=None):
    from apps.safety.services import raise_alert

    rating = max(1, min(5, int(rating)))
    review, created = Review.objects.get_or_create(
        booking=booking,
        defaults={
            "unit": booking.unit,
            "guest": booking.guest,
            "rating": rating,
            "channel": channel,
            "comment": comment,
        },
    )
    if not created:
        review.rating = rating
        if comment:
            review.comment = comment
    for c in CATEGORIES:
        if categories and categories.get(c):
            setattr(review, c, max(1, min(5, int(categories[c]))))
    review.save()
    record("review", f"{rating}/5 review for {booking.unit.name} ({booking.ref})", booking=booking)
    if rating <= 2:
        raise_alert(
            "low_review",
            f"Low review ({rating}/5) from {booking.guest.display_name} for {booking.ref} at {booking.unit.name} - worth a call.",
            severity="medium",
            booking=booking,
            dedupe=f"low-review:{booking.ref}",
            notify=False,
        )
        from apps.bookings.services import notify_host

        notify_host(
            f"Low review ({rating}/5) from {booking.guest.display_name} ({booking.guest.phone}) for {booking.ref}. Worth a call.",
            booking=booking,
        )
    return review


def add_comment(review, comment):
    review.comment = comment[:2000]
    review.save(update_fields=["comment"])
    return review


def respond(review, text, user=None):
    review.host_response, review.responded_at = text[:2000], timezone.now()
    review.save(update_fields=["host_response", "responded_at"])
    record("review", f"Amina replied to a review for {review.unit.name}", actor=user)
    return review


def unit_stats(unit=None):
    qs = Review.objects.filter(is_public=True)
    if unit is not None:
        qs = qs.filter(unit=unit)
    agg = qs.aggregate(avg=Avg("rating"), n=Count("id"), **{c: Avg(c) for c in CATEGORIES})
    avg = round(agg["avg"], 2) if agg["avg"] else None
    return {
        "rating": avg,
        "count": agg["n"],
        "categories": {c: round(agg[c], 1) for c in CATEGORIES if agg[c]},
        # Airbnb's Guest Favourite needs ≥5 reviews; we use a ≥4.8 average across our own stays
        "guest_favourite": bool(avg and avg >= 4.8 and agg["n"] >= 5),
    }
