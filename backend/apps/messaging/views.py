import re

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.activity import record
from apps.core.api import IsGuest, IsHost
from apps.core.models import SiteSettings

from . import services
from .automations import ensure_defaults, preview
from .models import FAQ, Automation, Broadcast, Message, Template, Thread
from .templates_default import DEFAULTS, DESCRIPTIONS, PLACEHOLDERS


def message_dict(m):
    return {
        "id": m.pk,
        "direction": m.direction,
        "channel": m.channel,
        "sender": m.sender,
        "body": m.body,
        "kind": m.kind,
        "handled": m.handled,
        "status": m.status,
        "created_at": m.created_at,
        "delivered_at": m.delivered_at,
        "booking": m.booking.ref if m.booking_id else None,
        "sent_by": m.sent_by.display_name if m.sent_by_id else None,
        "failure_reason": m.failure_reason,
    }


# ---------- guest: chat with Amina (same thread as SMS) ----------


@api_view(["GET", "POST"])
@permission_classes([IsGuest])
def my_messages(request):
    phone = request.user.phone
    if request.method == "POST":
        body = (request.data.get("body") or "").strip()[:1000]
        if not body:
            return Response({"error": "Write a message first."}, status=400)
        from apps.comms.smsbot import GuestBot

        inbound = services.record_inbound(phone, body, channel="web")
        GuestBot(request.user, body, inbound).run()
    msgs = (
        Message.objects.filter(phone=phone)
        .exclude(kind__in=("otp",))
        .select_related("booking", "sent_by")
        .order_by("id")
    )
    if request.method == "GET":
        Thread.objects.filter(phone=phone).update(unread=0)
    return Response({"messages": [message_dict(m) for m in msgs[:300]], "host": SiteSettings.load().host_name})


# ---------- host inbox ----------


def thread_dict(t):
    from apps.bookings.services import current_booking

    b = current_booking(t.phone)
    g = t.guest
    return {
        "id": t.pk,
        "phone": t.phone,
        "status": t.status,
        "needs_reply": t.needs_reply,
        "unread": t.unread,
        "waiting_since": t.waiting_since,
        "last_message_at": t.last_message_at,
        "last_preview": t.last_preview,
        "guest": {"id": g.pk, "name": g.name, "lang": g.lang, "nationality": g.nationality, "role": g.role}
        if g
        else None,
        "booking": {
            "ref": b.ref,
            "unit": b.unit.name,
            "status": b.status,
            "check_in": b.check_in,
            "check_out": b.check_out,
        }
        if b
        else None,
    }


@api_view(["GET"])
@permission_classes([IsHost])
def inbox(request):
    f = request.query_params.get("filter", "all")
    qs = Thread.objects.select_related("guest").exclude(last_message_at__isnull=True)
    host = SiteSettings.load().host_contact
    qs = qs.exclude(phone=host)
    if f == "needs_reply":
        qs = qs.filter(needs_reply=True)
    elif f == "staff":
        qs = qs.filter(guest__role__in=("cleaner", "cook", "caretaker", "security", "driver", "manager"))
    else:
        qs = qs.filter(Q(guest__isnull=True) | Q(guest__role="guest"))
    q = request.query_params.get("q")
    if q:
        qs = qs.filter(Q(phone__icontains=q) | Q(guest__name__icontains=q) | Q(last_preview__icontains=q))
    return Response([thread_dict(t) for t in qs.order_by("-needs_reply", "-last_message_at")[:150]])


@api_view(["GET"])
@permission_classes([IsHost])
def inbox_thread(request, pk):
    t = get_object_or_404(Thread.objects.select_related("guest"), pk=pk)
    Thread.objects.filter(pk=t.pk).update(unread=0)
    return Response(_thread_payload(t))


def _thread_payload(t):
    from apps.bookings.models import Booking
    from apps.bookings.serializers import trip_card

    t.refresh_from_db()
    msgs = Message.objects.filter(thread=t).select_related("booking", "sent_by").order_by("id")
    bookings = (
        Booking.objects.filter(guest__phone=t.phone)
        .exclude(status="expired")
        .select_related("unit", "unit__area")
        .order_by("-check_in")[:10]
    )
    return {
        "thread": thread_dict(t),
        "messages": [message_dict(m) for m in msgs[:500]],
        "bookings": [trip_card(b) for b in bookings],
        "quick_replies": quick_replies(t),
    }


def quick_replies(t):
    from apps.bookings.services import current_booking, guest_context

    b = current_booking(t.phone)
    ctx = guest_context(b) if b else {}
    replies = [
        "Karibu! I'm on it and will get back to you in a few minutes.",
        "Asante for letting me know - our caretaker is on the way.",
    ]
    if ctx.get("wifi"):
        replies.append(f"The Wi-Fi at {ctx['unit']} is {ctx['wifi']}.")
    if ctx.get("checkin_time"):
        replies.append(
            f"Check-in is from {ctx['checkin_time']} and checkout by {ctx['checkout_time']}. Early check-in depends on the previous guest - I'll confirm the day before."
        )
    replies.append("Breakfast is served 7:30-10:00. Reply BREAKFAST any time to choose or change it.")
    return replies


@api_view(["POST"])
@permission_classes([IsHost])
def inbox_reply(request, pk):
    from apps.comms.smsbot import reply_as_host

    t = get_object_or_404(Thread, pk=pk)
    text = (request.data.get("text") or "").strip()
    if not text:
        return Response({"error": "Write a reply first."}, status=400)
    channel = request.data.get("channel") or "sms"
    if channel not in ("sms", "whatsapp", "web"):
        return Response({"error": "Reply by SMS, WhatsApp or the web chat."}, status=400)
    reply_as_host(t.phone, text[:1000], user=request.user, channel=channel)
    record("message", f"Reply to {t.guest.display_name if t.guest else t.phone}", phone=t.phone, actor=request.user)
    return Response(_thread_payload(t))


@api_view(["POST"])
@permission_classes([IsHost])
def inbox_resolve(request, pk):
    t = get_object_or_404(Thread, pk=pk)
    t.needs_reply, t.waiting_since, t.status, t.unread = False, None, "resolved", 0
    t.save(update_fields=["needs_reply", "waiting_since", "status", "unread"])
    Message.objects.filter(thread=t, direction="in", handled__in=("pending", "relayed")).update(handled="answered")
    return Response(thread_dict(t))


# ---------- templates ----------


@api_view(["GET"])
@permission_classes([IsHost])
def templates(request):
    overrides = {(t.key, t.lang): t for t in Template.objects.all()}
    keys = sorted(set(DEFAULTS) | {k for k, _ in overrides})
    out = []
    for key in keys:
        langs = {}
        for lang in ("en", "sw", "it", "de", "fr"):
            o = overrides.get((key, lang))
            default = DEFAULTS.get(key, {}).get(lang, "")
            langs[lang] = {"body": o.body if o else default, "default": default, "custom": bool(o)}
        out.append({"key": key, "description": DESCRIPTIONS.get(key, ""), "langs": langs})
    return Response({"templates": out, "placeholders": PLACEHOLDERS})


@api_view(["PUT", "DELETE"])
@permission_classes([IsHost])
def template_edit(request, key, lang):
    if request.method == "DELETE":
        Template.objects.filter(key=key, lang=lang).delete()
        return Response({"reset": True})
    body = (request.data.get("body") or "").strip()
    if not body:
        return Response({"error": "The message can't be empty."}, status=400)
    if problem := services.placeholder_error(body):
        return Response({"error": problem}, status=400)
    Template.objects.update_or_create(key=key, lang=lang, defaults={"body": body[:1500]})
    record("message", f"Template '{key}' ({lang}) updated", actor=request.user)
    return Response({"key": key, "lang": lang, "body": body, "segments": services.sms_segments(services.to_gsm(body))})


# ---------- automations ----------


class AutomationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Automation
        fields = "__all__"
        read_only_fields = ["key"]

    def validate_send_time(self, value):
        # every automation is timed from this: one bad value would stop the whole message timeline
        if value and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
            raise serializers.ValidationError("Use a 24-hour time like 09:30, or leave it blank.")
        return value

    def validate(self, attrs):
        if self.instance is not None and self.instance.key == "balance_due":  # timed by the balance due date
            days = SiteSettings.load().balance_due_days
            if attrs.get("offset_days", -days) != -days or attrs.get("anchor", "check_in") != "check_in":
                raise serializers.ValidationError(
                    f"The balance is due {days} day{'s' if days != 1 else ''} before arrival - change that in "
                    "Settings and this message follows it."
                )
        return attrs


class AutomationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsHost]
    serializer_class = AutomationSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        ensure_defaults()
        return Automation.objects.all()


@api_view(["POST"])
@permission_classes([IsHost])
def automation_preview(request, pk):
    from apps.bookings.models import Booking

    auto = get_object_or_404(Automation, pk=pk)
    b = (
        Booking.objects.filter(ref=(request.data.get("ref") or "").upper()).first()
        or Booking.objects.filter(status__in=("confirmed", "checked_in")).order_by("check_in").first()
    )
    if not b:
        return Response({"text": "Make a booking first to preview with real data."})
    text = preview(auto, b)
    return Response({"text": text, "ref": b.ref, "segments": services.sms_segments(text)})


# ---------- FAQ / knowledge base ----------


class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = "__all__"
        read_only_fields = ["hits"]

    def validate(self, attrs):
        for field in ("answer_en", "answer_sw", "answer_fr", "answer_de"):
            if problem := services.placeholder_error(attrs.get(field)):
                raise serializers.ValidationError({field: problem})
        return attrs


class FAQViewSet(viewsets.ModelViewSet):
    permission_classes = [IsHost]
    serializer_class = FAQSerializer
    queryset = FAQ.objects.select_related("unit").all()


@api_view(["POST"])
@permission_classes([IsHost])
def faq_test(request):
    """Try a guest question against the knowledge base (as a guest with no booking)."""
    text = request.data.get("text", "")
    hit = services.match_faq(text, request.data.get("lang", "en"), ctx=services.faq_context(""))
    return Response(
        {"matched": bool(hit), "question": hit[0].question if hit else None, "answer": hit[1] if hit else None}
    )


@api_view(["GET"])
def public_faqs(request):
    """Help-centre FAQs: answers rendered with public facts only (booking-only answers are skipped)."""
    import string

    lang = request.query_params.get("lang", "en")
    ctx = services.faq_context("")
    out = []
    for f in FAQ.objects.filter(active=True, unit__isnull=True):
        answer = f.answer(lang)
        fields = {name for _, name, _, _ in string.Formatter().parse(answer) if name}
        if all(ctx.get(name) not in (None, "") for name in fields):
            out.append(
                {
                    "id": f.pk,
                    "category": f.category,
                    "question": f.question,
                    "answer": answer.format(**ctx) if fields else answer,
                }
            )
    return Response(out)


# ---------- broadcasts ----------


@api_view(["GET", "POST"])
@permission_classes([IsHost])
def broadcasts(request):
    from apps.properties.models import Unit

    if request.method == "GET":
        return Response(
            [
                {
                    "id": b.pk,
                    "audience": b.audience,
                    "audience_label": b.get_audience_display(),
                    "body": b.body,
                    "recipients": b.recipients,
                    "is_marketing": b.is_marketing,
                    "created_at": b.created_at,
                    "unit": b.unit.name if b.unit_id else None,
                }
                for b in Broadcast.objects.select_related("unit")[:50]
            ]
        )
    d = request.data
    audience = d.get("audience")
    if audience not in dict(Broadcast.AUDIENCES):
        return Response({"error": "Choose who the message is for."}, status=400)
    unit = Unit.objects.filter(pk=d.get("unit")).first() if d.get("unit") else None
    phones = services.audience_phones(audience, unit)
    if d.get("preview"):
        return Response({"recipients": len(phones)})
    body = (d.get("body") or "").strip()
    if not body:
        return Response({"error": "Write the message first."}, status=400)
    marketing = bool(d.get("is_marketing")) or audience == "past"
    if not services.broadcast_window_ok(marketing):
        s = SiteSettings.load()
        return Response(
            {
                "error": f"Promotional SMS can only go out between {s.promo_window_start}:00 and {s.promo_window_end}:00."
            },
            status=400,
        )
    if marketing and "stop" not in body.lower():
        body += " Reply STOP to opt out."
    sent = sum(
        1
        for p in phones
        if services.send(p, body, kind="broadcast", sender="host", user=request.user, marketing=marketing)
    )
    bc = Broadcast.objects.create(
        audience=audience, unit=unit, body=body, is_marketing=marketing, recipients=sent, created_by=request.user
    )
    record("broadcast", f"Broadcast to {sent} ({bc.get_audience_display()})", actor=request.user)
    return Response({"id": bc.pk, "recipients": sent}, status=201)
