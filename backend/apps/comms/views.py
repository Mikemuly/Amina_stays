"""Africa's Talking callbacks + Demo Lab endpoints.

AT does not sign webhooks, so set AT_WEBHOOK_SECRET and register callback URLs as
https://<public-host>/at/<secret>/ussd (etc). Without a secret the plain /at/... paths work (dev).
Callbacks always answer AT quickly: processing errors are logged, never bubbled to AT.
"""

import functools
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.activity import record
from apps.core.utils import normalize_phone
from apps.messaging import services as messaging

from . import simswap, smsbot, ussd, voice

log = logging.getLogger("amina.webhooks")


def at_webhook(view):
    @csrf_exempt
    @require_POST
    @functools.wraps(view)
    def wrapper(request, secret=None, *args, **kwargs):
        expected = settings.AT_WEBHOOK_SECRET
        given = secret or request.GET.get("key", "")
        if expected and not hmac.compare_digest(given.encode(), expected.encode()):  # as bytes: non-ASCII is no 500
            log.warning("rejected AT callback with a bad secret from %s", request.META.get("REMOTE_ADDR"))
            return HttpResponseForbidden("bad secret")
        return view(request, *args, **kwargs)

    return wrapper


def _data(request):
    if request.content_type == "application/json":
        try:
            return json.loads(request.body or b"{}")
        except ValueError:
            return {}
    return request.POST.dict()


# ---------- SMS ----------


def process_incoming_sms(phone, text, provider_id="", channel="sms"):
    phone = normalize_phone(phone)
    if not phone:  # a malformed or probing callback: nothing to answer, and no blank thread in Amina's inbox
        log.warning("ignored an incoming SMS without a valid sender")
        return None
    inbound = messaging.record_inbound(phone, text, channel=channel, provider_id=provider_id)
    if inbound.duplicate:  # Africa's Talking re-delivered a webhook we already answered
        return inbound
    try:
        smsbot.handle_sms(phone, text or "", inbound=inbound)
    except Exception:
        log.exception("SMS handling failed for %s", phone)
        messaging.mark(inbound, "relayed", "error")
    record("sms", f"SMS from {phone}: {(text or '')[:80]}", channel="sms", phone=phone)
    return inbound


@at_webhook
def sms_incoming(request):
    d = _data(request)
    process_incoming_sms(d.get("from", ""), d.get("text", ""), d.get("id", ""))
    return HttpResponse("OK")


@at_webhook
def sms_delivery(request):
    d = _data(request)
    messaging.on_delivery_report(d.get("id", ""), d.get("status", ""), d.get("failureReason", ""))
    return HttpResponse("OK")


@at_webhook
def sms_optout(request):
    from apps.accounts.models import User

    d = _data(request)
    phone = normalize_phone(d.get("phoneNumber"))
    if phone:
        User.objects.filter(phone=phone).update(sms_opt_out_at=timezone.now(), marketing_opt_in=False)
        record("guest", f"{phone} opted out of promotional SMS ({d.get('senderId', '')})", phone=phone)
    return HttpResponse("OK")


# ---------- USSD ----------


def process_ussd(phone, text, session_id=""):
    phone = normalize_phone(phone) or phone
    if not text:
        record("ussd", f"USSD session from {phone}", channel="ussd", phone=phone, session=session_id)
    try:
        return ussd.handle(phone, text or "")
    except Exception:
        log.exception("USSD failed for %s", phone)
        return "END Sorry, something went wrong. Please try again."


@at_webhook
def ussd_callback(request):
    d = _data(request)
    return HttpResponse(
        process_ussd(d.get("phoneNumber", ""), d.get("text", ""), d.get("sessionId", "")),
        content_type="text/plain; charset=utf-8",
    )


@at_webhook
def ussd_events(request):
    d = _data(request)
    log.info("USSD session %s ended: %s", d.get("sessionId"), d.get("status"))
    return HttpResponse("OK")


# ---------- Voice ----------


def process_voice(data):
    try:
        if (
            data.get("isActive") == "1"
            and not data.get("dtmfDigits")
            and (data.get("direction") or "").lower() == "inbound"
        ):
            from apps.comms.models import VoiceSession

            if not VoiceSession.objects.filter(session_id=data.get("sessionId", "")).exists():
                record(
                    "voice",
                    f"Call from {data.get('callerNumber', '')}",
                    channel="voice",
                    phone=data.get("callerNumber", ""),
                )
        return voice.handle(data)
    except Exception:
        log.exception("voice callback failed")
        return voice.end(voice.T["en"]["error"])


@at_webhook
def voice_callback(request):
    out = process_voice(_data(request))
    return HttpResponse(out, content_type="application/xml") if out else HttpResponse("")


# ---------- Airtime, Mobile Data, Insights ----------


@at_webhook
def airtime_status(request):
    from apps.rewards.services import on_status

    d = _data(request)
    record(
        "system",
        f"Airtime {d.get('status', '')} to {d.get('phoneNumber', '')} ({d.get('value', '')})",
        phone=d.get("phoneNumber", ""),
    )
    try:
        on_status(d, "airtime")  # a reward or gift: mark it delivered, or failed (redeemed points go back)
    except Exception:
        log.exception("airtime status handling failed")
    return HttpResponse("OK")


@at_webhook
def data_status(request):
    from apps.rewards.services import on_status

    d = _data(request)
    phone = d.get("destination") or d.get("phoneNumber", "")  # AT sends the masked destination, e.g. +254705****48
    record("system", f"Mobile data {d.get('status', '')} to {phone}", phone=phone)
    try:
        on_status(d, "data")
    except Exception:
        log.exception("mobile data status handling failed")
    return HttpResponse("OK")


@at_webhook
def simswap_callback(request):
    simswap.on_callback(_data(request))
    return HttpResponse("OK")


# ---------- Demo Lab (DEMO=1 only) — drives the very same handlers AT would call ----------


def demo_only(view):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not settings.DEMO:
            return JsonResponse({"error": "Demo Lab is disabled (set DEMO=1)."}, status=404)
        return view(request, *args, **kwargs)

    return wrapper


def _phone_messages(phone, after=0):
    from apps.messaging.models import Message

    qs = Message.objects.filter(phone=phone)
    # First load shows the latest messages; later polls fetch only what's new.
    rows = qs.filter(id__gt=after).order_by("id")[:200] if after else reversed(qs.order_by("-id")[:100])
    return [
        {
            "id": m.id,
            "direction": m.direction,
            "channel": m.channel,
            "body": m.body,
            "status": m.status,
            "kind": m.kind,
            "created_at": m.created_at.isoformat(),
        }
        for m in rows
    ]


@csrf_exempt
@require_POST
@demo_only
def demo_sms(request):
    d = json.loads(request.body or b"{}")
    phone = normalize_phone(d.get("from"))
    if not phone:
        return JsonResponse({"error": "Enter a valid phone number"}, status=400)
    inbound = process_incoming_sms(phone, d.get("text", ""), provider_id=f"demo-{timezone.now().timestamp()}")
    return JsonResponse({"messages": _phone_messages(phone, inbound.id - 1)})


@demo_only
def demo_phone(request, phone):
    phone = normalize_phone(phone)
    return JsonResponse({"messages": _phone_messages(phone, int(request.GET.get("after", 0) or 0))})


@csrf_exempt
@require_POST
@demo_only
def demo_ussd(request):
    d = json.loads(request.body or b"{}")
    phone = normalize_phone(d.get("phone"))
    if not phone:
        return JsonResponse({"error": "Enter a valid phone number"}, status=400)
    return JsonResponse({"response": process_ussd(phone, d.get("text", ""), d.get("session", "demo"))})


@csrf_exempt
@require_POST
@demo_only
def demo_voice(request):
    d = json.loads(request.body or b"{}")
    phone = normalize_phone(d.get("phone"))
    payload = {
        "sessionId": d.get("session") or "demo",
        "isActive": "0" if d.get("hangup") else "1",
        "direction": d.get("direction", "Inbound"),
        "callerNumber": phone,
        "destinationNumber": d.get("destination", settings.AT_VOICE_NUMBER or "+254711000000"),
        "dtmfDigits": d.get("digits", ""),
        "recordingUrl": d.get("recordingUrl", ""),
        "dialDurationInSeconds": d.get("dialDuration", "0"),
    }
    if d.get("direction") == "Outbound":
        payload["destinationNumber"] = phone
        request_id = str(d.get("clientRequestId") or "")
        if request_id == "bridge-latest":  # Amina's phone answers the newest call-back she asked for
            from apps.support.models import Ticket

            latest = Ticket.objects.filter(call_requested_at__isnull=False).order_by("-call_requested_at").first()
            request_id = f"bridge-{latest.pk}" if latest else ""
        if request_id:
            payload["clientRequestId"] = request_id
    return JsonResponse({"xml": process_voice(payload)})
