from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.api import IsHost

from .models import Activity, JobRun, SiteSettings
from .utils import normalize_phone


def health(request):
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
        db = "ok"
    except Exception as e:  # pragma: no cover
        db = f"error: {e}"
    return JsonResponse({"status": "ok" if db == "ok" else "degraded", "db": db, "time": timezone.now().isoformat()})


@api_view(["GET"])
def config(request):
    from apps.payments.providers import stripe_test_mode
    from apps.payments.services import paybill_config

    s = SiteSettings.load()
    return Response(
        {
            "business": {
                "name": s.business_name,
                "host_name": s.host_name,
                "tagline": s.tagline,
                "email": s.support_email,
                "tra_licence": s.tra_licence_number,
                "checkin_time": s.default_checkin_time,
                "checkout_time": s.default_checkout_time,
            },
            "channels": {
                "ussd_code": settings.AT_USSD_CODE,
                "sms_number": settings.AT_SMS_NUMBER,
                "voice_number": settings.AT_VOICE_NUMBER,
                "whatsapp": settings.AT_WHATSAPP_NUMBER,
            },
            "payments": {
                "mpesa": settings.MPESA_PROVIDER,  # "off": card only, everywhere
                "card": settings.CARD_PROVIDER,
                "simulated": settings.MPESA_PROVIDER == "simulate" or settings.CARD_PROVIDER == "simulate",
                "card_test_mode": settings.CARD_PROVIDER == "stripe" and stripe_test_mode(),
            },
            "paybill": paybill_config(),  # Lipa na M-Pesa fallback when a prompt can't get through (None = off)
            "currencies": {"USD": float(s.usd_rate), "EUR": float(s.eur_rate), "GBP": float(s.gbp_rate)},
            "deposit_percent": s.deposit_percent,
            "hold_minutes": s.hold_minutes,
            "levy_percent": float(s.tourism_levy_percent),
            "require_id": s.require_id_before_code,
            "demo": settings.DEMO,
            "sandbox": settings.AT_SANDBOX,
            "emergency": {"police_ambulance": "999 / 112", "red_cross": "1199", "e_plus": "1514"},
            **({"demo_lab": _demo_lab(s)} if settings.DEMO else {}),
        }
    )


def _demo_lab(s):
    """Phones the Demo Lab can 'hold': seeded demo users only, never real guests."""
    from apps.accounts.models import User
    from apps.bookings.models import Booking
    from apps.core.api import STAFF_ROLES

    guests = [
        {
            "phone": b.guest.phone,
            "name": b.guest.name,
            "role": "guest",
            "lang": b.guest.lang,
            "ref": b.ref,
            "note": f"{b.get_status_display()} · {b.unit.name}",
        }
        for b in Booking.objects.filter(status__in=("held", "confirmed", "checked_in"), guest__tags__contains=["seed"])
        .select_related("guest", "unit")
        .order_by("check_in")[:8]
    ]
    staff = [
        {"phone": u.phone, "name": u.name, "role": u.role, "lang": u.lang, "ref": None, "note": u.get_role_display()}
        for u in User.objects.filter(role__in=STAFF_ROLES, tags__contains=["seed"])
        .exclude(phone=s.host_contact)
        .order_by("role")
    ]
    return {"host_phone": s.host_contact, "host_name": s.host_name, "guests": guests, "staff": staff}


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteSettings
        exclude = ["id"]

    def validate_host_phone(self, value):
        return _dialable_phone(value)

    def validate_backup_phone(self, value):
        return _dialable_phone(value)


def _dialable_phone(value):
    """Alerts ring these numbers through Africa's Talking, which only dials +E.164: store them that way."""
    if not value:
        return ""
    phone = normalize_phone(value)
    if not phone:
        raise serializers.ValidationError("Enter a valid phone number, e.g. +254712345678.")
    return phone


@api_view(["GET", "PATCH"])
@permission_classes([IsHost])
def host_settings(request):
    s = SiteSettings.load()
    if request.method == "PATCH":
        ser = SettingsSerializer(s, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        from .activity import record

        record("system", "Settings updated", actor=request.user, fields=list(request.data.keys()))
    return Response(SettingsSerializer(s).data)


def _mpesa_product(base, paybill, secret):
    return {
        "key": "payments",
        "name": f"M-Pesa ({settings.MPESA_PROVIDER})",
        "ready": settings.MPESA_PROVIDER != "simulate",
        "detail": "simulated for the demo"
        if settings.MPESA_PROVIDER == "simulate"
        else f"{settings.MPESA_PROVIDER} - run manage.py register_c2b once"
        if settings.MPESA_PROVIDER == "daraja"
        else settings.MPESA_PROVIDER,
        "callbacks": {
            "AT checkout": f"{base}/api/payments/at/callback/{settings.AT_WEBHOOK_SECRET or 'cb'}",
            "Daraja": f"{base}/api/payments/daraja/callback/{secret}",
            "Paybill validation": paybill["validation"],
            "Paybill confirmation": paybill["confirmation"],
        },
    }


def _card_product(base):
    """Card payments: Stripe Checkout once STRIPE_SECRET_KEY is set (its webhook is optional but instant)."""
    from apps.payments.providers import stripe_test_mode

    provider = settings.CARD_PROVIDER
    if provider == "stripe":
        ready = bool(settings.STRIPE_SECRET_KEY)
        detail = (
            "no STRIPE_SECRET_KEY set"
            if not ready
            else "test mode - pay with card 4242 4242 4242 4242"
            if stripe_test_mode()
            else "live"
        )
        if ready and not settings.STRIPE_WEBHOOK_SECRET:
            detail += "; no webhook yet, so payments confirm when guests return or within 2 minutes"
        callbacks = {"Stripe webhook": f"{base}/api/payments/stripe/webhook"}
    elif provider == "paystack":
        ready = bool(settings.PAYSTACK_SECRET_KEY)
        detail = "Paystack" if ready else "no PAYSTACK_SECRET_KEY set"
        callbacks = {"Paystack webhook": f"{base}/api/payments/paystack/webhook"}
    else:
        ready, detail, callbacks = False, "simulated for the demo - set STRIPE_SECRET_KEY for real payments", {}
    name = {"stripe": "Card payments - Stripe", "paystack": "Card payments - Paystack"}.get(provider, "Card payments")
    return {"key": "card", "name": name, "ready": ready, "detail": detail, "callbacks": callbacks}


@api_view(["GET"])
@permission_classes([IsHost])
def channels(request):
    """Africa's Talking integration status + the exact callback URLs to paste into the AT dashboard."""
    from apps.comms import at
    from apps.payments.c2b import c2b_urls
    from apps.payments.providers import callback_secret

    base = settings.PUBLIC_URL.rstrip("/")
    prefix = f"{base}/at/{settings.AT_WEBHOOK_SECRET}" if settings.AT_WEBHOOK_SECRET else f"{base}/at"
    paybill = c2b_urls()  # Daraja C2B (Paybill/Till), registered by manage.py register_c2b
    last = {
        k: Activity.objects.filter(kind=k).values_list("created_at", flat=True).first()
        for k in ("sms", "ussd", "voice", "payment")
    }
    return Response(
        {
            "username": settings.AT_USERNAME,
            "sandbox": settings.AT_SANDBOX,
            "configured": at.configured(),
            "balance": at.balance() if request.query_params.get("balance") else None,
            "webhook_secret": bool(settings.AT_WEBHOOK_SECRET),
            "products": [
                {
                    "key": "sms",
                    "name": "SMS (two-way) - Ask Amina",
                    "ready": at.configured(),
                    "detail": settings.AT_SMS_NUMBER or "no shortcode set",
                    "callbacks": {
                        "Incoming messages": f"{prefix}/sms/incoming",
                        "Delivery reports": f"{prefix}/sms/delivery",
                        "Opt-out": f"{prefix}/sms/optout",
                    },
                },
                {
                    "key": "ussd",
                    "name": "USSD",
                    "ready": bool(settings.AT_USSD_CODE),
                    "detail": settings.AT_USSD_CODE or "no code set",
                    "callbacks": {"Callback URL": f"{prefix}/ussd", "Events URL": f"{prefix}/ussd/events"},
                },
                {
                    "key": "voice",
                    "name": "Voice - Call Amina & call-backs",
                    "ready": bool(settings.AT_VOICE_NUMBER) and not settings.AT_SANDBOX,
                    "detail": settings.AT_VOICE_NUMBER or "needs a live voice number (no sandbox)",
                    "callbacks": {"Callback URL": f"{prefix}/voice"},
                },
                {
                    "key": "airtime",
                    "name": "Airtime - rewards & goodwill",
                    "ready": at.configured(),
                    "detail": "points redeemed, referral rewards, gifts and apologies",
                    "callbacks": {"Status": f"{prefix}/airtime/status"},
                },
                {
                    "key": "data",
                    "name": "Mobile Data - stay connected",
                    "ready": bool(settings.AT_DATA_PRODUCT),
                    "detail": settings.AT_DATA_PRODUCT or "no product set",
                    "callbacks": {"Status": f"{prefix}/data/status"},
                },
                {
                    "key": "insights",
                    "name": "Insights - SIM swap check",
                    "ready": at.configured(),
                    "detail": "before door codes are released",
                    "callbacks": {"Status": f"{prefix}/insights/simswap"},
                },
                {
                    "key": "whatsapp",
                    "name": "WhatsApp (AT Chat, preview)",
                    "ready": bool(settings.AT_WHATSAPP_NUMBER),
                    "detail": settings.AT_WHATSAPP_NUMBER or "optional",
                    "callbacks": {},
                },
                *([_mpesa_product(base, paybill, callback_secret())] if settings.MPESA_PROVIDER != "off" else []),
                _card_product(base),
            ],
            "last_seen": last,
            "jobs": [
                {"key": j.key, "last_run_at": j.last_run_at, "ok": j.last_ok, "runs": j.run_count}
                for j in JobRun.objects.order_by("key")
            ],
        }
    )


@api_view(["GET"])
@permission_classes([IsHost])
def activity(request):
    qs = Activity.objects.select_related("actor")
    if request.query_params.get("kind"):
        qs = qs.filter(kind=request.query_params["kind"])
    after = int(request.query_params.get("after") or 0)
    if after:
        qs = qs.filter(pk__gt=after)
    return Response(
        [
            {
                "id": a.pk,
                "kind": a.kind,
                "channel": a.channel,
                "title": a.title,
                "detail": a.detail,
                "booking_ref": a.booking_ref,
                "phone": a.phone,
                "actor": a.actor.display_name if a.actor_id else None,
                "created_at": a.created_at,
            }
            for a in qs[: int(request.query_params.get("limit") or 100)]
        ]
    )


@api_view(["GET", "POST"])
@permission_classes([IsHost])
def locks(request):
    """The keypad panel: what each door accepts right now (stands in for TTLock / igloohome hardware)."""
    from apps.bookings.models import AccessCode
    from apps.properties.models import Unit

    now = timezone.now()
    if request.method == "POST":
        unit = get_object_or_404(Unit, pk=request.data.get("unit"))
        code = (request.data.get("code") or "").strip()
        ok = AccessCode.objects.filter(
            booking__unit=unit,
            code=code,
            revoked_at__isnull=True,
            sent_at__isnull=False,
            valid_from__lte=now,
            valid_until__gte=now,
        ).first()
        if ok:
            ok.last_used_at = now
            ok.save(update_fields=["last_used_at"])
            from .activity import record

            record("lock", f"{unit.name}: door opened with {ok.booking.ref}'s code", booking=ok.booking)
        return Response({"unlocked": bool(ok), "ref": ok.booking.ref if ok else None})
    out = []
    for u in Unit.objects.select_related("area").order_by("sort_order", "id"):
        c = (
            AccessCode.objects.filter(booking__unit=u, revoked_at__isnull=True, booking__status="checked_in")
            .select_related("booking", "booking__guest")
            .first()
        )
        nxt = (
            AccessCode.objects.filter(booking__unit=u, revoked_at__isnull=True, booking__status="confirmed")
            .select_related("booking")
            .order_by("valid_from")
            .first()
        )
        out.append(
            {
                "unit": {
                    "id": u.pk,
                    "name": u.name,
                    "area": u.area.name,
                    "housekeeping": u.housekeeping,
                    "provider": u.get_access_method_display(),
                },
                "state": "occupied" if c else "vacant",
                "active": {
                    "code": c.code,
                    "ref": c.booking.ref,
                    "guest": c.booking.guest.display_name,
                    "valid_until": c.valid_until,
                    "last_used_at": c.last_used_at,
                }
                if c
                else None,
                "next": {"ref": nxt.booking.ref, "valid_from": nxt.valid_from} if nxt else None,
            }
        )
    return Response(out)


# ---------- Demo Lab controls (DEMO=1) ----------


def _demo_guard():
    if not settings.DEMO:
        return Response({"error": "Demo Lab is disabled (set DEMO=1)."}, status=404)
    return None


MPESA_OFF = "M-Pesa is off on this site (MPESA_PROVIDER=off): guests pay by card."


@api_view(["POST"])
def demo_pay(request, ref):
    """Settle the newest pending payment as the provider would. Body {"result": <M-Pesa ResultCode>} other than 0
    fails it instead, through the same code path as a Daraja callback carrying that code."""
    if (blocked := _demo_guard()) is not None:
        return blocked
    from apps.bookings.models import Booking
    from apps.payments import services as payments
    from apps.payments.models import Payment

    b = get_object_or_404(Booking, ref=ref.upper())
    data = request.data if hasattr(request.data, "get") else {}
    try:
        result = int(data.get("result") or 0)
    except (TypeError, ValueError):
        return Response({"error": "Give an M-Pesa result code, e.g. 1032."}, status=400)
    if result and not payments.mpesa_on():
        return Response({"error": MPESA_OFF}, status=400)
    pending = Payment.objects.filter(booking=b, status="pending").order_by("-id")
    p = (pending.filter(method="mpesa").first() if result else None) or pending.first()
    if not p:
        try:
            payments.start_payment(b)
        except Exception as e:
            return Response({"error": str(e)}, status=400)
        p = pending.first()
        if p is None:
            return Response({"error": "There's no payment to settle."}, status=400)
    if result:
        desc = "Simulated in the Demo Lab"
        payments.on_mpesa_result(p, result, desc=desc, raw={"ResultCode": result, "ResultDesc": desc})
        p.refresh_from_db()
        b.refresh_from_db()
        return Response(
            {
                "ok": True,
                "ref": b.ref,
                "status": b.status,
                "failure_code": p.failure_code or None,
                "failure_message": payments.public_failure(p)["failure_message"],
            }
        )
    payments.on_success(p, transaction_id=f"DEMO{p.pk}", provider_ref=f"DEMO{p.pk:06d}")
    b.refresh_from_db()
    return Response({"ref": b.ref, "status": b.status, "paid": b.amount_paid})


@api_view(["POST"])
def demo_c2b(request):
    """A Lipa na M-Pesa Paybill payment, as Daraja's C2B confirmation would deliver it: {ref, amount?, phone?}.
    The amount defaults to what's due now; a ref that matches no booking lands in the host's Unmatched queue."""
    if (blocked := _demo_guard()) is not None:
        return blocked
    from apps.payments import c2b
    from apps.payments.providers import PaymentError
    from apps.payments.services import mpesa_on

    if not mpesa_on():
        return Response({"error": MPESA_OFF}, status=400)
    data = request.data if hasattr(request.data, "get") else {}
    try:
        t = c2b.simulate(str(data.get("ref") or "").strip(), amount=data.get("amount"), phone=data.get("phone"))
    except PaymentError as e:
        return Response({"error": str(e)}, status=400)
    return Response(
        {
            "trans_id": t.trans_id,
            "matched": t.status == "matched",
            "ref": t.booking.ref if t.booking_id else None,
            "amount": t.amount,
        }
    )


@api_view(["POST"])
def demo_tick(request):
    if (blocked := _demo_guard()) is not None:
        return blocked
    from .scheduler import run_due

    return Response(run_due(only=request.data.get("jobs") or None))


@api_view(["POST"])
def demo_advance(request, ref):
    """Fast-forward one stay through its lifecycle on stage, without waiting for real dates."""
    if (blocked := _demo_guard()) is not None:
        return blocked
    from apps.bookings import services as bookings
    from apps.bookings.models import Booking
    from apps.reviews.services import request_review

    b = get_object_or_404(Booking.objects.select_related("unit", "guest", "unit__area"), ref=ref.upper())
    step = request.data.get("step")
    result = "ok"
    try:
        if step in ("pre_arrival", "directions", "id_request", "welcome_check", "checkout_reminder", "mid_stay"):
            # sent as it would be on its real date, so the day-before directions carry the real Wi-Fi and route
            bookings.send_guest(b, step, reveal=True, clean_price="KES 1,500")
        elif step == "code":  # the time machine may release ahead of the real arrival day
            result = bookings.release_code(b, force=bool(request.data.get("force")), allow_early=True)
        elif step == "checkout":
            bookings.check_out(b, channel="demo")
        elif step == "review":
            if b.status == "checked_in":
                bookings.check_out(b, channel="demo")
                b.refresh_from_db()
            from apps.core.models import OnceMarker

            OnceMarker.objects.filter(key=f"review-request:{b.ref}").delete()
            result = request_review(b)
        else:
            return Response({"error": "Unknown step"}, status=400)
    except bookings.BookingError as e:  # e.g. checking out a stay that hasn't started
        return Response({"error": str(e)}, status=400)
    b.refresh_from_db()
    return Response({"ref": b.ref, "status": b.status, "result": result})


@api_view(["POST"])
def demo_reset(request):
    if (blocked := _demo_guard()) is not None:
        return blocked
    from django.core.management import call_command

    call_command("seed_demo", "--reset")
    return Response({"reset": True, "at": timezone.now()})


DEMO_OUTAGE_TEXT = {
    "wifi": "Our internet provider is fixing a fault on the street. Mobile data works fine.",
    "power": "Kenya Power is working on the line. The backup generator runs the lights, fans and fridge.",
    "water": "The county supply is off. The tank has a few hours' reserve - please go easy on it.",
}


@api_view(["POST"])
def demo_outage(request, ref):
    """An outage at this stay's home as Amina would post it ({"service": "wifi"|"power"|"water"}), or
    {"restore": true} to end the one that's on."""
    if (blocked := _demo_guard()) is not None:
        return blocked
    from datetime import timedelta

    from apps.bookings.models import Booking
    from apps.notices import services as notices

    b = get_object_or_404(Booking.objects.select_related("unit"), ref=ref.upper())
    if request.data.get("restore"):
        n = notices.for_unit(b.unit).first()
        if n is None:
            return Response({"error": "There's no service alert on at this home."}, status=400)
        told = notices.resolve(n, note="The provider fixed it.")
        return Response({"notice": n.pk, "status": "resolved", "told": told})
    service = request.data.get("service") or "wifi"
    if service not in DEMO_OUTAGE_TEXT:
        return Response({"error": "Pick wifi, power or water."}, status=400)
    if any(n.service == service for n in notices.for_unit(b.unit)):
        return Response({"error": "That outage is already on at this home - press Fix it first."}, status=400)
    n = notices.create(
        kind="outage",
        service=service,
        message=DEMO_OUTAGE_TEXT[service],
        units=[b.unit],
        expected_end=timezone.now() + timedelta(hours=2),
        source="demo",
    )
    return Response({"notice": n.pk, "status": n.status, "told": n.notified, "data_mb": n.data_mb})


def demo_ical(request, slug):
    """A stand-in 'Airbnb' calendar so the iCal import can be demonstrated offline (DEMO=1)."""
    from django.http import Http404, HttpResponse

    from .management.commands.seed_demo import sample_ics

    if not settings.DEMO:
        raise Http404
    return HttpResponse(sample_ics(slug), content_type="text/calendar; charset=utf-8")
