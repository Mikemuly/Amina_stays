from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.api import IsHost

from . import services
from .models import CATEGORIES, Review


@api_view(["GET"])
@permission_classes([IsHost])
def host_reviews(request):
    rows = Review.objects.select_related("unit", "guest", "booking")[:200]
    return Response(
        {
            "summary": services.unit_stats(),
            "by_unit": [{"unit": u.name, **services.unit_stats(u)} for u in {r.unit for r in rows}],
            "reviews": [
                {
                    "id": r.pk,
                    "ref": r.booking.ref,
                    "unit": r.unit.name,
                    "guest": r.guest.display_name,
                    "nationality": r.guest.nationality,
                    "rating": r.rating,
                    "comment": r.comment,
                    "categories": {c: getattr(r, c) for c in CATEGORIES if getattr(r, c)},
                    "host_response": r.host_response,
                    "channel": r.channel,
                    "created_at": r.created_at,
                }
                for r in rows
            ],
        }
    )


@api_view(["POST"])
@permission_classes([IsHost])
def respond(request, pk):
    r = get_object_or_404(Review, pk=pk)
    text = str(request.data.get("text") or "").strip()
    if not text:
        return Response({"error": "Write a reply first."}, status=400)
    services.respond(r, text, request.user)
    return Response({"ok": True})
