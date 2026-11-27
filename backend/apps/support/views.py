from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.api import IsGuest, IsHost
from apps.core.utils import normalize_phone

from . import services
from .models import Ticket, TicketEvent

GUEST_CATEGORIES = ("complaint", "callback", "billing", "booking", "feedback", "other")


def ticket_dict(t, now=None):
    now = now or timezone.now()
    task = t.task
    return {
        "id": t.pk,
        "ref": t.ref,
        "category": t.category,
        "category_label": t.get_category_display(),
        "status": t.status,
        "status_label": t.get_status_display(),
        "priority": t.priority,
        "channel": t.channel,
        "subject": t.subject,
        "description": t.description,
        "phone": t.phone,
        "guest": {"name": t.guest.display_name, "phone": t.guest.phone} if t.guest_id else None,
        "booking": t.booking.ref if t.booking_id else None,
        "unit": t.unit.name if t.unit_id else None,
        "task": {
            "id": task.pk,
            "status": task.status,
            "assignee": task.assignee.display_name if task.assignee_id else None,
        }
        if task
        else None,
        "recording_url": t.recording_url,
        "created_at": t.created_at,
        "first_response_due": t.first_response_due,
        "first_response_at": t.first_response_at,
        "overdue": services.overdue(t, now),
        "resolved_at": t.resolved_at,
        "resolution": t.resolution,
        "rating": t.rating,
        "rating_comment": t.rating_comment,
        "escalation_level": t.escalation_level,
        "last_activity_at": t.updated_at,
    }


def detail_dict(t):
    return {
        **ticket_dict(t),
        "events": [
            {
                "id": e.pk,
                "kind": e.kind,
                "text": e.text,
                "channel": e.channel,
                "actor": e.actor.display_name if e.actor_id else None,
                "created_at": e.created_at,
            }
            for e in t.events.select_related("actor")
        ],
    }


def guest_dict(t):
    return {
        "id": t.pk,
        "ref": t.ref,
        "category": t.category,
        "category_label": t.get_category_display(),
        "status": t.status,
        "status_label": t.get_status_display(),
        "subject": t.subject,
        "description": t.description,
        "booking": t.booking.ref if t.booking_id else None,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "resolution": t.resolution,
        "rating": t.rating,
        "can_rate": t.status == "resolved" and t.rating is None and t.category != "issue",
        "events": [
            {"kind": e.kind, "text": e.text, "created_at": e.created_at}
            for e in t.events.all()
            if e.kind in TicketEvent.PUBLIC
        ],
    }


def _tickets():
    return Ticket.objects.select_related("guest", "booking", "unit", "task", "task__assignee")


# ---------- guests ----------


@api_view(["GET", "POST"])
@permission_classes([IsGuest])
def my_tickets(request):
    phone = request.user.phone
    if request.method == "GET":
        qs = _tickets().filter(phone=phone).prefetch_related("events")
        if ref := request.query_params.get("booking"):
            qs = qs.filter(booking__ref=ref.upper())
        return Response([guest_dict(t) for t in qs[:50]])
    category = request.data.get("category") or "complaint"
    if request.data.get("callback"):
        category = "callback"
    if category not in GUEST_CATEGORIES:
        return Response({"error": "Pick what your request is about."}, status=400)
    description = (request.data.get("description") or "").strip()
    if category != "callback" and len(description) < 3:
        return Response({"error": "Tell us a little about it so the right person can help."}, status=400)
    if len(description) > 1000:
        return Response({"error": "Please keep it under 1,000 characters."}, status=400)
    booking = None
    if ref := request.data.get("booking"):
        booking = request.user.bookings.filter(ref=str(ref).upper()).first()
        if booking is None:
            return Response({"error": "That booking isn't on your account."}, status=400)
    if category == "callback":
        t = services.request_callback(phone, channel="web", booking=booking, note=description)
    else:
        subject = description.split("\n", 1)[0][:140]
        t = services.open_ticket(
            phone, category=category, subject=subject, description=description, channel="web", booking=booking
        )
    t = _tickets().prefetch_related("events").get(pk=t.pk)
    return Response(guest_dict(t), status=201)


@api_view(["POST"])
@permission_classes([IsGuest])
def rate_ticket(request, pk):
    t = get_object_or_404(_tickets(), pk=pk, phone=request.user.phone)
    try:
        rating = int(request.data.get("rating"))
    except (TypeError, ValueError):
        rating = 0
    if not 1 <= rating <= 5:
        return Response({"error": "Pick 1 to 5 stars."}, status=400)
    if t.status != "resolved" or t.category == "issue":
        return Response({"error": "You can rate a request once it's resolved."}, status=400)
    services.rate(t, rating, request.data.get("comment", ""), channel="web")
    t = _tickets().prefetch_related("events").get(pk=t.pk)
    return Response(guest_dict(t))


# ---------- host console ----------


@api_view(["GET", "POST"])
@permission_classes([IsHost])
def host_tickets(request):
    if request.method == "POST":  # a complaint taken on the phone or at the gate
        phone = normalize_phone(request.data.get("phone"))
        if not phone:
            return Response({"error": "Enter the guest's phone number."}, status=400)
        category = request.data.get("category") or "complaint"
        if category not in dict(Ticket.CATEGORIES) or category == "issue":
            return Response({"error": "Pick a category."}, status=400)
        description = (request.data.get("description") or "").strip()
        subject = (request.data.get("subject") or description.split("\n", 1)[0]).strip()[:140]
        if not subject:
            return Response({"error": "Say what it's about."}, status=400)
        booking = None
        if ref := request.data.get("booking"):
            from apps.bookings.models import Booking

            booking = Booking.objects.filter(ref=str(ref).upper(), guest__phone=phone).first()
            if booking is None:
                return Response({"error": "That booking doesn't belong to this phone number."}, status=400)
        t = services.open_ticket(
            phone,
            category=category,
            subject=subject,
            description=description,
            channel="host",
            booking=booking,
            tell_host=False,
            actor=request.user,
        )
        return Response(detail_dict(_tickets().get(pk=t.pk)), status=201)
    status = request.query_params.get("status", "open")
    qs = _tickets()
    if status == "open":
        qs = qs.filter(status__in=services.OPEN)
    elif status == "resolved":
        qs = qs.filter(status__in=("resolved", "closed"))
    if category := request.query_params.get("category"):
        qs = qs.filter(category=category)
    now = timezone.now()
    return Response({"counts": services.stats(), "tickets": [ticket_dict(t, now) for t in qs[:200]]})


@api_view(["GET"])
@permission_classes([IsHost])
def host_ticket(request, pk):
    return Response(detail_dict(get_object_or_404(_tickets(), pk=pk)))


@api_view(["POST"])
@permission_classes([IsHost])
def host_ticket_action(request, pk, action):
    t = get_object_or_404(_tickets(), pk=pk)
    if action == "reply":
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response({"error": "Type a reply first."}, status=400)
        if len(text) > 600:
            return Response({"error": "Keep replies under 600 characters: they go out by SMS."}, status=400)
        services.reply(t, text, user=request.user)
    elif action == "resolve":
        services.resolve(t, note=request.data.get("note", ""), user=request.user, channel="web")
    elif action == "reopen":
        services.reopen(t, user=request.user)
    elif action == "call":
        result = services.call_guest(t, user=request.user)
        return Response({**result, "ticket": detail_dict(_tickets().get(pk=t.pk))})
    else:
        return Response({"error": "Unknown action - use reply, resolve, reopen or call."}, status=400)
    return Response(detail_dict(_tickets().get(pk=t.pk)))
