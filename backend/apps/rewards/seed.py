"""Demo data for rewards: points for past stays (awarded silently, so the job never texts seeded guests about old
stays), invite codes, one completed and one pending referral, and a redeemed airtime top-up."""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.core.models import OnceMarker


def seed():
    from apps.bookings.models import Booking
    from apps.reviews.models import Review

    from . import services
    from .models import Member, Payout, PointsEntry, Program

    now = timezone.now()
    prog = Program.load()
    prog.started_at = now - timedelta(days=200)
    prog.save(update_fields=["started_at"])

    done = (
        Booking.objects.filter(status="completed")
        .exclude(channel__in=services.OTA)
        .filter(guest__role="guest")
        .select_related("guest", "unit")
        .order_by("checked_out_at")
    )
    for b in done:
        e = services.award(
            b.guest,
            services.stay_points(b, prog),
            "stay",
            booking=b,
            note=f"{b.ref} {b.unit.name}",
            key=f"rewards:stay:{b.ref}",
        )
        if e is not None and b.checked_out_at:
            PointsEntry.objects.filter(pk=e.pk).update(created_at=b.checked_out_at)
    for r in Review.objects.filter(booking__in=done).select_related("booking", "guest"):
        e = services.award(
            r.guest,
            prog.review_points,
            "review",
            booking=r.booking,
            note=r.booking.ref,
            key=f"rewards:review:{r.booking.ref}",
        )
        if e is not None:
            PointsEntry.objects.filter(pk=e.pk).update(created_at=r.created_at)
    # bookings already in progress or upcoming get members too, so every seeded guest has an invite code
    guests = {b.guest for b in Booking.objects.filter(guest__role="guest").select_related("guest")}
    for g in guests:
        services.member(g)

    kenyan = sorted((g for g in guests if g.phone.startswith("+254")), key=lambda g: g.pk)
    if len(kenyan) >= 3:
        # an old referral that has paid out, and a new one waiting for the friend's first stay
        stayed = [g for g in kenyan if services.has_stayed(g)]
        fresh = [g for g in kenyan if not services.has_stayed(g)]
        if len(stayed) >= 2:
            referrer, friend = stayed[0], stayed[1]
            m = Member.objects.get(user=friend)
            first = friend.bookings.filter(status="completed").order_by("check_in").first()
            m.referred_by, m.referred_at, m.referral_status, m.referral_booking = (
                referrer,
                (first.created_at if first else now) - timedelta(days=3),
                "rewarded",
                first,
            )
            m.save()
            for who, amount, reason in (
                (friend, prog.referee_airtime, "referee"),
                (referrer, prog.referral_airtime, "referral"),
            ):
                p = Payout.objects.create(
                    user=who,
                    phone=who.phone,
                    kind="airtime",
                    amount=amount,
                    reason=reason,
                    booking=first,
                    status="simulated",
                    idempotency_key=f"{reason}-seed-{who.pk}",
                    completed_at=first.checked_out_at if first else now,
                )
                Payout.objects.filter(pk=p.pk).update(
                    created_at=(first.checked_out_at if first and first.checked_out_at else now)
                )
        if fresh and stayed:
            m = Member.objects.get(user=fresh[0])
            if not m.referred_by_id:
                m.referred_by, m.referred_at, m.referral_status = stayed[-1], now - timedelta(days=2), "pending"
                m.save()

    # someone who already swapped points for airtime
    rich = sorted(kenyan, key=lambda g: -services.balance(g))
    if rich and services.balance(rich[0]) >= prog.redeem_points:
        g = rich[0]
        p = Payout.objects.create(
            user=g,
            phone=g.phone,
            kind="airtime",
            amount=prog.redeem_airtime,
            reason="redeem",
            status="simulated",
            note=f"{prog.redeem_points} points",
            idempotency_key=f"redeem-seed-{g.pk}",
            completed_at=now - timedelta(days=12),
        )
        Payout.objects.filter(pk=p.pk).update(created_at=now - timedelta(days=12))
        e = PointsEntry.objects.create(
            user=g, points=-prog.redeem_points, reason="redeem", payout=p, note=p.amount_text
        )
        PointsEntry.objects.filter(pk=e.pk).update(created_at=now - timedelta(days=12))
    OnceMarker.mark("rewards:seeded")
    return Member.objects.filter(~Q(code="")).count()
