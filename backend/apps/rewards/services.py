"""Rewards paid in airtime and mobile data (Africa's Talking Airtime + Mobile Data).

Guests earn points for completed stays and for sharing feedback, swap them for airtime or a data bundle by SMS, USSD
or the website, and earn airtime when a friend they invited finishes a first stay. Every top-up - rewards, the
outage data bundle, a goodwill gift from Amina - goes through one ledger (Payout): one idempotency key each, a monthly
airtime budget, and Africa's Talking's status callbacks to confirm delivery."""

import logging
import random
import re
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.activity import record
from apps.core.models import OnceMarker, SiteSettings
from apps.core.utils import first_name, is_kenyan, mask_phone
from apps.messaging import services as messaging

from .models import Member, Payout, PointsEntry, Program

log = logging.getLogger("amina.rewards")

OTA = ("airbnb", "booking_com")  # platform guests: no points, and no soliciting them off-platform
LOOKBACK = timedelta(days=30)
SPENT = ("queued", "sent", "success", "simulated")
REASONS = {
    "en": {
        "unknown": "we don't have that code - check the spelling.",
        "own": "that's your own code - share it with friends instead.",
        "used": "you've already used a friend's code.",
        "stayed": "invite codes are for guests before their first stay.",
    },
    "sw": {
        "unknown": "hatuna nambari hiyo - angalia herufi.",
        "own": "hiyo ni nambari yako - washirikishe marafiki.",
        "used": "tayari umetumia nambari ya rafiki.",
        "stayed": "nambari za mwaliko ni za wageni kabla ya safari yao ya kwanza.",
    },
}


def program():
    return Program.load()


def _lang(user):
    return getattr(user, "lang", "") or "en"


def _is_guest(user):
    return user is not None and user.role == "guest"


def _seeded(user):
    return user is not None and "seed" in (user.tags or [])


# ---------- members, codes and points ----------


def member(user):
    m = Member.objects.filter(user=user).first()
    if m is not None:
        return m
    letters = re.sub(r"[^A-Z]", "", first_name(user.name).upper())[:8]
    base = letters if len(letters) >= 3 else "KARIBU"
    rng = random.SystemRandom()
    for digits in (2, 2, 2, 2, 3, 3, 4, 4, 5, 6):
        code = f"{base}{rng.randint(10 ** (digits - 1), 10**digits - 1)}"
        try:
            with transaction.atomic():
                return Member.objects.create(user=user, code=code)
        except IntegrityError:
            m = Member.objects.filter(user=user).first()
            if m is not None:  # created by a parallel request
                return m
    raise RuntimeError("could not allocate a referral code")


def balance(user):
    return PointsEntry.objects.filter(user=user).aggregate(s=Sum("points"))["s"] or 0


def award(user, points, reason, *, booking=None, note="", key=None):
    """Add points once (the key makes a re-run of the job harmless)."""
    if points <= 0 or (key and not OnceMarker.mark(key)):
        return None
    member(user)
    return PointsEntry.objects.create(user=user, points=points, reason=reason, booking=booking, note=note[:160])


def stay_points(b, prog=None):
    prog = prog or program()
    paid = max(0, min(b.total, b.amount_paid) - b.amount_refunded)
    return (paid // 100) * prog.points_per_100


# ---------- the ledger: airtime and data through Africa's Talking ----------


def month_spent(kind="airtime", exclude=None):
    start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    qs = Payout.objects.filter(kind=kind, status__in=SPENT, created_at__gte=start)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.aggregate(s=Sum("amount"))["s"] or 0


def _over_budget(p, prog):
    return bool(
        p.kind == "airtime"
        and prog.monthly_airtime_budget
        and month_spent("airtime", exclude=p) + p.amount > prog.monthly_airtime_budget
    )


def can_send(kind):
    """Live keys without a Mobile Data product would only pretend to send data: say it's unavailable instead."""
    from apps.comms import at

    return kind != "data" or not at.configured() or bool(settings.AT_DATA_PRODUCT)


def send_payout(user, kind, amount, reason, *, booking=None, note="", key=None, actor=None, phone=None, budget=True):
    """Queue one top-up and send it. A key that was used before returns that payout instead of paying twice.
    Kenyan lines only: Africa's Talking airtime is sent in the recipient's currency."""
    phone = phone or (user.phone if user else "")
    if not phone or not is_kenyan(phone) or amount <= 0 or not can_send(kind):
        return None
    key = key or f"{reason}-{uuid.uuid4().hex}"
    try:
        with transaction.atomic():
            p = Payout.objects.create(
                user=user,
                phone=phone,
                kind=kind,
                amount=amount,
                reason=reason,
                booking=booking,
                note=note[:160],
                idempotency_key=key[:80],
                created_by=actor if getattr(actor, "pk", None) else None,
            )
    except IntegrityError:
        return Payout.objects.filter(idempotency_key=key[:80]).first()
    if budget and _over_budget(p, program()):
        p.status = "held"
        p.save(update_fields=["status"])
        _budget_alert()
        return p
    return dispatch(p)


def _budget_alert():
    from apps.bookings.services import notify_host

    if OnceMarker.mark(f"rewards-budget:{timezone.localdate()}"):
        notify_host(
            "Rewards: this month's airtime budget is used up, so new airtime rewards are waiting for your approval "
            "in Host > Rewards & airtime.",
            kind="rewards_budget",
        )


def _first(res):
    entries = res.get("responses") or res.get("entries") or []
    return entries[0] if entries and isinstance(entries[0], dict) else {}


def dispatch(p):
    """Send a queued payout through Africa's Talking (a dry run without an API key, or for seeded demo people)."""
    from apps.comms import at

    if p.user is not None and _seeded(p.user):
        res = {"dry_run": True}
    else:
        try:
            if p.kind == "airtime":
                res = at.send_airtime(
                    p.phone,
                    p.amount,
                    idempotency_key=p.idempotency_key,
                    metadata={"payout": str(p.pk), "reason": p.reason},
                )
            else:
                res = at.send_mobile_data(
                    p.phone,
                    p.amount,
                    metadata={"payout": str(p.pk), "reason": p.reason},
                    idempotency_key=p.idempotency_key,
                )
        except Exception as e:  # network, rejected request, product not set up
            log.warning("payout %s failed: %s", p.pk, e)
            return fail(p, str(e))
    now = timezone.now()
    if res.get("dry_run"):
        p.status, p.completed_at = "simulated", now
    else:
        first = _first(res)
        status = str(first.get("status") or "")
        err = str(first.get("errorMessage") or res.get("errorMessage") or "")
        accepted = ("Sent", "Success", "Queued", "Pending") if p.kind == "data" else ("Sent", "Success")
        ok = status in accepted or (p.kind == "airtime" and not status and int(res.get("numSent") or 0) > 0)
        p.provider_ref = str(first.get("requestId") or first.get("transactionId") or "")[:80]
        if not ok:
            p.save(update_fields=["provider_ref"])
            return fail(p, err if err and err != "None" else status or "rejected by Africa's Talking")
        p.status = "sent"
    p.save(update_fields=["status", "provider_ref", "completed_at"])
    record(
        "system",
        f"{p.get_kind_display()} {p.amount_text} {p.get_status_display().lower()} to {mask_phone(p.phone)} "
        f"({p.get_reason_display()})",
        phone=p.phone,
        booking=p.booking,
    )
    return p


def fail(p, error):
    p.status, p.error, p.completed_at = "failed", (error or "failed")[:240], timezone.now()
    p.save(update_fields=["status", "error", "completed_at"])
    _return_points(p, "the top-up failed")
    record(
        "system", f"{p.get_kind_display()} {p.amount_text} to {mask_phone(p.phone)} failed: {p.error}", phone=p.phone
    )
    return p


def _return_points(p, note):
    if p.reason != "redeem" or not OnceMarker.mark(f"payout-refund:{p.pk}"):
        return
    spent = PointsEntry.objects.filter(payout=p, reason="redeem").aggregate(s=Sum("points"))["s"] or 0
    if spent < 0 and p.user is not None:
        PointsEntry.objects.create(user=p.user, points=-spent, reason="refund", payout=p, note=note)


def on_status(data, kind):
    """Africa's Talking's delivery callback for an airtime top-up or a data bundle."""
    ref = str(data.get("requestId") or data.get("transactionId") or "")
    p = Payout.objects.filter(provider_ref=ref, kind=kind).first() if ref else None
    if p is None:
        return None
    status = str(data.get("status") or "").lower()
    if status == "success" and p.status in ("sent", "queued"):
        p.status, p.completed_at = "success", timezone.now()
        p.save(update_fields=["status", "completed_at"])
    elif status == "failed" and p.status not in ("failed", "rejected"):
        fail(p, str(data.get("description") or data.get("errorMessage") or "failed on the network"))
    return p


def approve(p, actor=None):
    if p.status != "held":
        return p
    p.status = "queued"
    p.save(update_fields=["status"])
    record("system", f"Approved {p.amount_text} to {mask_phone(p.phone)}", actor=actor)
    return dispatch(p)


def reject(p, actor=None):
    if p.status != "held":
        return p
    p.status, p.completed_at = "rejected", timezone.now()
    p.save(update_fields=["status", "completed_at"])
    _return_points(p, "not approved")
    record("system", f"Rejected {p.amount_text} to {mask_phone(p.phone)}", actor=actor)
    return p


def gift(phone, kind, amount, *, note="", actor=None):
    """Amina sends airtime or data herself - a thank-you, or sorry for a rough stay."""
    from apps.accounts.services import get_or_create_user

    user, _ = get_or_create_user(phone, channel="sms")
    p = send_payout(user, kind, amount, "manual", note=note, actor=actor, budget=False)
    if p is not None and p.status not in ("failed", "rejected"):
        why = f" - {note}" if note else ""
        messaging.send(
            user.phone,
            messaging.render("rewards_gift", _lang(user), amount=p.amount_text, why=why),
            kind="rewards_gift",
        )
    return p


# ---------- guests: redeem and refer ----------


def redeem(user, kind, lang=None, defer=False):
    """Swap points for airtime or data. Returns (payout or None, the message for the guest) - in the guest's SMS
    language, or `lang` (the website answers in English). `defer` (USSD) sends the top-up after the screen has gone
    back, since a USSD hop can't wait on the network, and texts the outcome."""
    prog, lang = program(), lang or _lang(user)
    if not prog.enabled:
        return None, messaging.render("rewards_off", lang)
    if not is_kenyan(user.phone):
        return None, messaging.render("rewards_not_kenyan", lang)
    if not can_send(kind):
        return None, messaging.render("rewards_data_off", lang)
    amount = prog.redeem_airtime if kind == "airtime" else prog.redeem_data_mb
    with transaction.atomic():
        Member.objects.select_for_update().filter(pk=member(user).pk).first()  # one redemption at a time per guest
        bal = balance(user)
        if bal < prog.redeem_points or not amount:
            return None, messaging.render(
                "rewards_not_enough", lang, balance=bal, need=max(prog.redeem_points - bal, 0)
            )
        p = Payout.objects.create(
            user=user,
            phone=user.phone,
            kind=kind,
            amount=amount,
            reason="redeem",
            note=f"{prog.redeem_points} points",
            idempotency_key=f"redeem-{user.pk}-{uuid.uuid4().hex[:16]}",
        )
        PointsEntry.objects.create(user=user, points=-prog.redeem_points, reason="redeem", payout=p, note=p.amount_text)
    if _over_budget(p, prog):
        p.status = "held"
        p.save(update_fields=["status"])
        _budget_alert()
        key = "rewards_redeem_held"
    elif defer:
        from apps.comms import deferred

        deferred.after_response(_dispatch_and_tell, p.pk, lang)
        key = "rewards_redeem_sending"
    else:
        dispatch(p)
        key = "rewards_redeem_failed" if p.status == "failed" else "rewards_redeemed"
    return p, messaging.render(key, lang, amount=p.amount_text, phone=p.phone, balance=balance(user))


def _dispatch_and_tell(payout_id, lang):
    p = Payout.objects.select_related("user").get(pk=payout_id)
    dispatch(p)
    key = "rewards_redeem_failed" if p.status == "failed" else "rewards_redeemed"
    messaging.send(
        p.phone,
        messaging.render(key, lang, amount=p.amount_text, phone=p.phone, balance=balance(p.user)),
        kind="rewards_redeem",
    )


def has_stayed(user):
    return user.bookings.filter(status="completed").exclude(channel__in=OTA).exists()


def apply_referral(user, code, lang=None):
    """A new guest enters a friend's invite code. Returns (ok, message)."""
    prog, lang = program(), lang or _lang(user)
    code = re.sub(r"[^A-Z0-9]", "", (code or "").upper())
    owner = Member.objects.filter(code=code).select_related("user").first() if code else None
    me = member(user)
    why = None
    if owner is None:
        why = "unknown"
    elif owner.user_id == user.pk:
        why = "own"
    elif me.referred_by_id:
        why = "used"
    elif has_stayed(user):
        why = "stayed"
    if why:
        return False, messaging.render("rewards_referral_bad", lang, reason=REASONS.get(lang, REASONS["en"])[why])
    me.referred_by, me.referred_at, me.referral_status = owner.user, timezone.now(), "pending"
    me.save(update_fields=["referred_by", "referred_at", "referral_status"])
    record(
        "guest",
        f"{user.display_name} joined with {owner.user.display_name}'s invite code {owner.code}",
        phone=user.phone,
    )
    return True, messaging.render(
        "rewards_referral_ok",
        lang,
        code=owner.code,
        referrer=first_name(owner.user.name) or "your friend",
        amount=prog.referee_airtime,
    )


def _qualify_referral(b, prog):
    """A referred guest's first completed stay pays airtime to both of them, once."""
    m = Member.objects.filter(user=b.guest, referral_status="pending", referred_by__isnull=False).first()
    if m is None:
        return 0
    with transaction.atomic():
        m = Member.objects.select_for_update().get(
            pk=m.pk
        )  # no join: FOR UPDATE can't lock an outer join's nullable side
        if m.referral_status != "pending":
            return 0
        m.referral_status, m.referral_booking = "rewarded", b
        m.save(update_fields=["referral_status", "referral_booking"])
    friend = m.referred_by
    mine = send_payout(b.guest, "airtime", prog.referee_airtime, "referee", booking=b, key=f"referee-{b.guest.pk}")
    theirs = send_payout(
        friend, "airtime", prog.referral_airtime, "referral", booking=b, key=f"referral-{friend.pk}-{b.guest.pk}"
    )
    if mine is not None and mine.status not in ("failed", "rejected"):
        messaging.send(
            b.guest.phone,
            messaging.render("rewards_referee_paid", _lang(b.guest), amount=prog.referee_airtime),
            kind="rewards_referral",
            booking=b,
        )
    if theirs is not None and theirs.status not in ("failed", "rejected"):
        messaging.send(
            friend.phone,
            messaging.render(
                "rewards_referrer_paid",
                _lang(friend),
                friend=first_name(b.guest.name) or "your friend",
                amount=prog.referral_airtime,
            ),
            kind="rewards_referral",
        )
    return 1


# ---------- the scheduler job ----------


def run(now=None):
    """Points for stays that just ended and for feedback; airtime once a referred guest's first stay is over."""
    from apps.bookings.models import Booking
    from apps.reviews.models import Review

    prog = program()
    if not prog.enabled:
        return 0
    now = now or timezone.now()
    since = max(now - LOOKBACK, prog.started_at)  # no back-pay for stays from before the programme began
    done = 0
    stays = (
        Booking.objects.filter(status="completed", checked_out_at__gte=since)
        .exclude(channel__in=OTA)
        .select_related("guest", "unit")
    )
    for b in stays:
        if not _is_guest(b.guest):
            continue
        entry = award(
            b.guest, stay_points(b, prog), "stay", booking=b, note=f"{b.ref} {b.unit.name}", key=f"rewards:stay:{b.ref}"
        )
        if entry is not None:
            done += 1
            messaging.send(
                b.guest.phone,
                messaging.render(
                    "rewards_points",
                    _lang(b.guest),
                    points=entry.points,
                    balance=balance(b.guest),
                    redeem=prog.redeem_points,
                    airtime=prog.redeem_airtime,
                    data=prog.redeem_data_mb,
                ),
                kind="rewards_points",
                booking=b,
            )
        done += _qualify_referral(b, prog)
    for r in Review.objects.filter(created_at__gte=since).select_related("booking", "guest"):
        if r.booking.channel in OTA or not _is_guest(r.guest):
            continue
        if award(
            r.guest,
            prog.review_points,
            "review",
            booking=r.booking,
            note=r.booking.ref,
            key=f"rewards:review:{r.booking.ref}",
        ):
            done += 1
    return done


# ---------- what guests see ----------


def summary_text(user):
    prog, lang = program(), _lang(user)
    if not prog.enabled:
        return messaging.render("rewards_off", lang)
    m, bal = member(user), balance(user)
    redeem_line = " " + (  # render() strips its result: the space joining it to the sentence goes here
        messaging.render(
            "rewards_can_redeem", lang, airtime=prog.redeem_airtime, data=prog.redeem_data_mb, points=prog.redeem_points
        )
        if bal >= prog.redeem_points
        else messaging.render("rewards_progress", lang, need=prog.redeem_points - bal)
    )
    return messaging.render(
        "rewards_summary",
        lang,
        balance=bal,
        redeem_line=redeem_line,
        code=m.code,
        referrer=prog.referral_airtime,
        referee=prog.referee_airtime,
    )


def refer_text(user, lang=None):
    prog = program()
    return messaging.render(
        "rewards_refer",
        lang or _lang(user),
        code=member(user).code,
        number=settings.AT_SMS_NUMBER or SiteSettings.load().host_contact,
        amount=prog.referee_airtime,
    )


def history(user, limit=20):
    rows = [
        {
            "kind": "points",
            "text": e.get_reason_display() + (f" - {e.note}" if e.note else ""),
            "points": e.points,
            "amount_text": None,
            "status": None,
            "created_at": e.created_at,
        }
        for e in PointsEntry.objects.filter(user=user)[:limit]
    ] + [
        {
            "kind": "payout",
            "text": p.get_reason_display(),
            "points": None,
            "amount_text": p.amount_text,
            "status": p.get_status_display(),
            "created_at": p.created_at,
        }
        for p in Payout.objects.filter(user=user)[:limit]
    ]
    return sorted(rows, key=lambda r: r["created_at"], reverse=True)[:limit]


def guest_dict(user):
    prog, m, bal = program(), member(user), balance(user)
    kenyan = is_kenyan(user.phone)
    why_not = "" if kenyan else "Airtime and data rewards need a Kenyan (+254) number."
    if kenyan and bal < prog.redeem_points:
        why_not = f"{prog.redeem_points - bal} more points to your first reward."
    return {
        "enabled": prog.enabled,
        "points": bal,
        "code": m.code,
        "share_text": refer_text(user, "en"),
        "referred_by": (first_name(m.referred_by.name) or "a friend") if m.referred_by_id else None,
        "referral_status": m.referral_status or None,
        "can_enter_code": not m.referred_by_id and not has_stayed(user),
        "kenyan": kenyan,
        "redeem": {
            "points": prog.redeem_points,
            "airtime": prog.redeem_airtime,
            "data_mb": prog.redeem_data_mb,
            "can_airtime": prog.enabled and kenyan and bal >= prog.redeem_points and prog.redeem_airtime > 0,
            "can_data": prog.enabled
            and kenyan
            and bal >= prog.redeem_points
            and prog.redeem_data_mb > 0
            and can_send("data"),
            "why_not": why_not,
        },
        "rules": {
            "points_per_100": prog.points_per_100,
            "review_points": prog.review_points,
            "referral_airtime": prog.referral_airtime,
            "referee_airtime": prog.referee_airtime,
        },
        "history": history(user),
    }


def stats():
    from apps.accounts.models import User

    return {
        "members": Member.objects.count(),
        "points_outstanding": PointsEntry.objects.aggregate(s=Sum("points"))["s"] or 0,
        "airtime_month": month_spent("airtime"),
        "airtime_budget": program().monthly_airtime_budget,
        "data_month_mb": month_spent("data"),
        "referrals_completed": Member.objects.filter(referral_status="rewarded").count(),
        "referrals_pending": Member.objects.filter(referral_status="pending").count(),
        "payouts_held": Payout.objects.filter(status="held").count(),
        "guests": User.objects.filter(role="guest").count(),
    }
