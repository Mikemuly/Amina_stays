"""Phone-number identity: one account across web, USSD, SMS and voice; login by one-time SMS code."""

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.core.activity import record
from apps.core.utils import normalize_phone

from .models import OTPCode, User

log = logging.getLogger("amina.auth")
OTP_TTL, RESEND_GAP, MAX_ATTEMPTS = timedelta(minutes=5), timedelta(seconds=30), 5


class AuthError(Exception):
    pass


def _hash(code):
    return hmac.new(settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()


def get_or_create_user(phone, *, name="", channel=""):
    phone = normalize_phone(phone)
    if not phone:
        raise AuthError("Please enter a valid phone number, e.g. 0712 345 678 or +44 7700 900123.")
    user, created = User.objects.get_or_create(phone=phone, defaults={"name": name[:80], "first_channel": channel})
    if not created and name and not user.name:
        user.name = name[:80]
        user.save(update_fields=["name"])
    return user, created


def request_otp(raw_phone):
    from apps.messaging import services as messaging

    phone = normalize_phone(raw_phone)
    if not phone:
        raise AuthError("Please enter a valid phone number, e.g. 0712 345 678 or +44 7700 900123.")
    now = timezone.now()
    prev = OTPCode.objects.filter(phone=phone).first()
    if prev and now - prev.sent_at < RESEND_GAP:
        raise AuthError("Please wait 30 seconds before requesting another code.")
    # SMS-pumping guard: at most 5 codes per number per hour (per-IP limits alone aren't enough)
    hour_key = f"otp-count:{phone}:{now:%Y%m%d%H}"
    sent = cache.get(hour_key, 0)
    if sent >= 5:
        raise AuthError("Too many codes requested for this number. Please try again in an hour.")
    # set() with the hour, not incr(): the shared database cache's incr() saves with its 5-minute default timeout
    cache.set(hour_key, sent + 1, 3600)
    code = f"{secrets.randbelow(900000) + 100000}"
    OTPCode.objects.update_or_create(
        phone=phone, defaults={"code_hash": _hash(code), "expires_at": now + OTP_TTL, "attempts": 0, "sent_at": now}
    )
    user = User.objects.filter(phone=phone).first()
    body = messaging.render("otp", user.lang if user else "en", code=code)
    messaging.send(phone, body, kind="otp", sync=True, secret=code)  # stored and shown with the code hidden
    if settings.AT_SANDBOX or not settings.AT_API_KEY or settings.DEMO:
        log.warning("Login code for %s: %s", phone, code)  # sandbox SMS never reach real handsets
    result = {
        "phone": phone,
        "sandbox": settings.AT_SANDBOX or not settings.AT_API_KEY,
        "simulator": settings.AT_SANDBOX and bool(settings.AT_API_KEY),  # read it in the Africa's Talking simulator
    }
    if settings.DEMO:
        result["debug_code"] = code
    return result


def verify_otp(raw_phone, code):
    phone = normalize_phone(raw_phone)
    row = OTPCode.objects.filter(phone=phone).first() if phone else None
    if not row or row.expires_at < timezone.now():
        raise AuthError("That code has expired. Please request a new one.")
    if row.attempts >= MAX_ATTEMPTS:
        raise AuthError("Too many attempts. Please request a new code.")
    if not hmac.compare_digest(row.code_hash, _hash(str(code or "").strip())):
        row.attempts += 1
        row.save(update_fields=["attempts"])
        raise AuthError("That code isn't right.")
    row.delete()
    user, _ = get_or_create_user(phone, channel="web")
    if not user.is_active:
        raise AuthError("This account is disabled.")
    record(
        "auth",
        f"Login: {user.display_name}{' (' + user.get_role_display() + ')' if user.role != 'guest' else ''}",
        phone=phone,
    )
    return user


def set_identity(user, *, id_type, id_number, nationality="", consent=True, name=""):
    from apps.bookings.models import BookingGuest

    if not consent:
        raise AuthError("We need your consent to store your ID for the guest register.")
    id_number = (id_number or "").strip()
    if len(id_number) < 5:
        raise AuthError("Please enter a valid ID or passport number.")
    if name:
        user.name = name[:80]
    user.id_type = id_type or ("national_id" if user.phone.startswith("+254") and id_number.isdigit() else "passport")
    user.set_id_number(id_number)
    user.nationality = (nationality or user.nationality or ("KE" if user.id_type == "national_id" else "")).upper()[:2]
    user.id_submitted_at = user.consent_at = timezone.now()
    user.save()
    BookingGuest.objects.filter(
        booking__guest=user, is_lead=True, booking__status__in=("held", "confirmed", "checked_in")
    ).update(
        full_name=user.name or user.phone,
        id_type=user.id_type,
        id_number_enc=user.id_number_enc,
        id_last4=user.id_last4,
        nationality=user.nationality,
    )
    record(
        "guest",
        f"ID registered for {user.display_name} ({user.get_id_type_display()} {user.id_last4})",
        phone=user.phone,
    )
    return user


def export_data(user):
    """Data subject access (Data Protection Act 2019, s.26) — everything we hold about this phone number."""
    from apps.messaging.models import Message

    return {
        "profile": {
            "phone": user.phone,
            "name": user.name,
            "email": user.email,
            "language": user.lang,
            "nationality": user.nationality,
            "id_document": f"{user.get_id_type_display()} ending {user.id_last4}" if user.id_last4 else None,
            "marketing_opt_in": user.marketing_opt_in,
            "joined": user.date_joined.isoformat(),
        },
        "bookings": [
            {
                "ref": b.ref,
                "home": b.unit.name,
                "check_in": b.check_in.isoformat(),
                "check_out": b.check_out.isoformat(),
                "status": b.status,
                "total": b.total,
                "paid": b.amount_paid,
                "channel": b.channel,
            }
            for b in user.bookings.select_related("unit")
        ],
        "messages": [
            {"at": m.created_at.isoformat(), "direction": m.direction, "channel": m.channel, "text": m.body}
            for m in Message.objects.filter(phone=user.phone).order_by("id")
        ],
        "reviews": [
            {"ref": r.booking.ref, "rating": r.rating, "comment": r.comment}
            for r in user.reviews.select_related("booking")
        ],
        "waitlist": [
            {
                "home": w.unit.name if w.unit else None,
                "area": w.area.name if w.area else None,
                "check_in": w.check_in.isoformat(),
                "check_out": w.check_out.isoformat(),
                "guests": w.guests,
                "status": w.status,
            }
            for w in user.waitlist.select_related("unit", "area")
        ],
    }


def erase(user):
    """Erasure request: wipe what we don't have to keep. Guest-register records (name + ID) of real stays are kept
    for the 5 years the tourism regulations require and erased automatically after that; register lines of
    bookings that never became a stay (cancelled, expired, unpaid) are erased now."""
    from apps.bookings.models import BookingGuest
    from apps.messaging.models import Message
    from apps.properties.models import Wishlist

    stays = ("confirmed", "checked_in", "completed")
    has_register = user.bookings.filter(status__in=stays).exists()
    user.email = ""
    user.marketing_opt_in = False
    user.sms_opt_out_at = user.sms_opt_out_at or timezone.now()
    user.host_notes = ""
    user.tags = []
    if not has_register:
        user.name = ""
        user.id_type, user.id_number_enc, user.id_last4 = "", "", ""
    user.save()
    BookingGuest.objects.filter(booking__guest=user).exclude(booking__status__in=(*stays, "held")).update(
        full_name="[erased]", id_type="", id_number_enc="", id_last4="", nationality=""
    )
    Wishlist.objects.filter(user=user).delete()
    user.waitlist.all().delete()
    Message.objects.filter(phone=user.phone).update(body="[erased at guest's request]")
    record("guest", f"Erasure request processed for {user.phone}", phone=user.phone)
    return {"erased": True, "register_kept": has_register}


def purge_expired_ids():
    """Retention: erase ID numbers once the register period has passed since the guest's last stay."""
    from apps.bookings.models import BookingGuest
    from apps.core.models import SiteSettings

    days = SiteSettings.load().id_retention_days
    cutoff = timezone.localdate() - timedelta(days=days)
    stale = BookingGuest.objects.filter(booking__check_out__lt=cutoff).exclude(id_number_enc="")
    n = stale.update(id_number_enc="", id_last4="")
    cutoff_dt = timezone.now() - timedelta(days=days)
    for u in (
        User.objects.exclude(id_number_enc="")
        .filter(id_submitted_at__lt=cutoff_dt)
        .exclude(bookings__check_out__gte=cutoff)
    ):
        u.id_number_enc, u.id_last4 = "", ""
        u.save(update_fields=["id_number_enc", "id_last4"])
        n += 1
    return n
