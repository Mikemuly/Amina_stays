import csv

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.api import IsHost
from apps.core.utils import parse_date, today

from . import services
from .models import Alert


def alert_dict(a):
    return {
        "id": a.pk,
        "kind": a.kind,
        "kind_label": a.get_kind_display(),
        "severity": a.severity,
        "status": a.status,
        "source": a.source,
        "phone": a.phone,
        "summary": a.summary,
        "details": a.details,
        "call_status": a.call_status,
        "calls_made": a.calls_made,
        "booking": a.booking.ref if a.booking_id else None,
        "created_at": a.created_at,
        "acknowledged_at": a.acknowledged_at,
        "resolved_at": a.resolved_at,
        "resolution_note": a.resolution_note,
        "resolved_by": a.resolved_by.display_name if a.resolved_by_id else None,
    }


@api_view(["GET"])
@permission_classes([IsHost])
def alerts(request):
    qs = Alert.objects.select_related("booking", "resolved_by")
    status = request.query_params.get("status", "active")
    if status == "active":
        qs = qs.exclude(status="resolved")
    elif status != "all":
        qs = qs.filter(status=status)
    return Response([alert_dict(a) for a in qs[:200]])


@api_view(["POST"])
@permission_classes([IsHost])
def alert_action(request, pk, action):
    a = get_object_or_404(Alert, pk=pk)
    if action == "ack":
        services.acknowledge(a, request.user)
    elif action == "resolve":
        services.resolve(a, request.user, request.data.get("note", ""))
    else:
        return Response({"error": "Unknown action - use ack or resolve."}, status=400)
    return Response(alert_dict(a))


@api_view(["GET"])
@permission_classes([IsHost])
def guest_register(request):
    """Guest register (Tourism Enterprises Regulations 2025, r.26) — every occupant, CSV for TRA / police."""
    from apps.bookings.models import BookingGuest

    start = parse_date(request.query_params.get("from")) or today().replace(day=1)
    end = parse_date(request.query_params.get("to")) or today()
    rows = (
        BookingGuest.objects.filter(
            booking__check_in__lte=end,
            booking__check_out__gte=start,
            booking__status__in=("confirmed", "checked_in", "completed"),
        )
        .select_related("booking", "booking__unit", "booking__guest")
        .order_by("booking__check_in")
    )
    data = [
        {
            "ref": o.booking.ref,
            "unit": o.booking.unit.name,
            "address": o.booking.unit.address,
            "name": o.full_name,
            "lead_guest": o.is_lead,
            "minor": o.is_minor,
            "id_type": o.id_type,
            "id_last4": o.id_last4,
            "nationality": o.nationality,
            "phone": o.booking.guest.phone if o.is_lead else "",
            "check_in": o.booking.check_in,
            "check_out": o.booking.check_out,
            "arrived_at": o.booking.checked_in_at,
            "left_at": o.booking.checked_out_at,
            "vehicle": o.booking.vehicle_plate,
        }
        for o in rows
    ]
    if request.query_params.get("export") == "csv":  # not ?format=, which DRF reserves for content negotiation
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="guest-register-{start}-{end}.csv"'
        w = csv.writer(resp)
        w.writerow(
            [
                "Ref",
                "Home",
                "Address",
                "Name",
                "Lead guest",
                "Minor",
                "ID type",
                "ID (last 4)",
                "Nationality",
                "Phone",
                "Check-in",
                "Check-out",
                "Arrived",
                "Left",
                "Vehicle",
            ]
        )
        for r in data:
            w.writerow(
                [
                    r["ref"],
                    r["unit"],
                    r["address"],
                    r["name"],
                    "yes" if r["lead_guest"] else "",
                    "yes" if r["minor"] else "",
                    r["id_type"],
                    r["id_last4"],
                    r["nationality"],
                    r["phone"],
                    r["check_in"],
                    r["check_out"],
                    r["arrived_at"] or "",
                    r["left_at"] or "",
                    r["vehicle"],
                ]
            )
        return resp
    return Response({"from": start, "to": end, "rows": data, "missing_id": sum(1 for r in data if not r["id_last4"])})
