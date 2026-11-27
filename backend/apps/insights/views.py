import csv
from datetime import timedelta

from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.bookings.serializers import reservation_row
from apps.core.api import IsHost
from apps.core.utils import today

from . import services


@api_view(["GET"])
@permission_classes([IsHost])
def today_view(request):
    from apps.core.models import Activity
    from apps.messaging.views import thread_dict
    from apps.operations.views import TaskSerializer
    from apps.safety.views import alert_dict

    d = services.host_today()
    t = today()
    week = services.kpis(t - timedelta(days=t.weekday()), t - timedelta(days=t.weekday()) + timedelta(days=7))
    month = services.kpis(t.replace(day=1), t + timedelta(days=1))
    return Response(
        {
            "date": d["date"],
            "arrivals": [reservation_row(b) for b in d["arrivals"]],
            "departures": [reservation_row(b) for b in d["departures"]],
            "in_house": [reservation_row(b) for b in d["in_house"]],
            "upcoming": [reservation_row(b) for b in d["upcoming"]],
            "holds": [reservation_row(b) for b in d["holds"]],
            "tasks": TaskSerializer(d["tasks"], many=True).data,
            "alerts": [alert_dict(a) for a in d["alerts"]],
            "threads": [thread_dict(x) for x in d["threads"]],
            "breakfasts": d["breakfasts"],
            "kpis": {"week": week, "month": month},
            "activity": [
                {
                    "id": a.pk,
                    "kind": a.kind,
                    "channel": a.channel,
                    "title": a.title,
                    "booking_ref": a.booking_ref,
                    "created_at": a.created_at,
                }
                for a in Activity.objects.all()[:25]
            ],
        }
    )


@api_view(["GET"])
@permission_classes([IsHost])
def insights(request):
    days = max(7, min(int(request.query_params.get("days") or 30), 365))
    end = today() + timedelta(days=1)
    start = end - timedelta(days=days)
    prev = services.kpis(start - timedelta(days=days), start)
    return Response(
        {
            "kpis": services.kpis(start, end),
            "previous": prev,
            "series": services.daily_series(start, end),
            "forward": services.forward_bookings(56),
            "days": days,
        }
    )


@api_view(["GET"])
@permission_classes([IsHost])
def tra_return(request):
    month = request.query_params.get("month") or (today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    try:
        year, mon = (int(x) for x in month.split("-"))
        r = services.tra_return(year, mon)
    except ValueError:
        return Response({"error": "Choose a month as YYYY-MM, e.g. 2026-10."}, status=400)
    if request.query_params.get("export") == "csv":  # not ?format=, which DRF reserves for content negotiation
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="tra-return-{month}.csv"'
        w = csv.writer(resp)
        w.writerow(["Month", r["month"]])
        for key in (
            "units",
            "occupancy",
            "room_nights_sold",
            "room_nights_available",
            "guest_nights",
            "arrivals",
            "room_revenue",
            "tourism_levy",
        ):
            w.writerow([key.replace("_", " ").capitalize(), r[key]])
        w.writerow([])
        w.writerow(["Country of origin", "Guests"])
        for country, n in r["visitors_by_country"].items():
            w.writerow([country, n])
        return resp
    return Response(r)
