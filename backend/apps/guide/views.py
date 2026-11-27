from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.api import IsHost
from apps.core.utils import today
from apps.properties.models import Area, Unit

from . import services
from .models import Event, Place


def place_dict(p):
    return {
        "id": p.pk,
        "slug": p.slug,
        "name": p.name,
        "category": p.category,
        "category_label": p.get_category_display(),
        "area": {"slug": p.area.slug, "name": p.area.name} if p.area_id else None,
        "summary": p.summary,
        "description": p.description,
        "tips": p.tips,
        "hours": p.hours,
        "price": p.price,
        "phone": p.phone,
        "website": p.website,
        "latitude": p.latitude,
        "longitude": p.longitude,
        "photo": p.photo,
        "featured": p.featured,
        "map_url": p.map_url,
        **({"distance_km": p.distance_km} if hasattr(p, "distance_km") else {}),
    }


def occurrence_dict(on, e):
    return {
        "id": e.pk,
        "title": e.title,
        "summary": e.summary,
        "date": on,
        "time": e.time,
        "price": e.price,
        "addon_code": e.addon_code,
        "link": e.link,
        "place": {"slug": e.place.slug, "name": e.place.name} if e.place_id else None,
        "area": e.area.name if e.area_id else (e.place.area.name if e.place_id and e.place.area_id else None),
        "weekly": e.weekday is not None,
    }


@api_view(["GET"])
def guide(request):
    """The public local guide: places by category and area, and what's on in the next two weeks."""
    everything = list(services.active_places())
    category = request.query_params.get("category")
    area = request.query_params.get("area")
    places = [
        p
        for p in everything
        if (not category or p.category == category) and (not area or (p.area_id and p.area.slug == area))
    ]
    counts = {}
    for p in everything:
        counts[p.category] = counts.get(p.category, 0) + 1
    areas = {p.area.slug: p.area.name for p in everything if p.area_id}
    return Response(
        {
            "categories": [
                {"key": k, "label": label, "count": counts[k]} for k, label in Place.CATEGORIES if k in counts
            ],
            "areas": [{"slug": s, "name": n} for s, n in sorted(areas.items(), key=lambda x: x[1])],
            "places": [place_dict(p) for p in places],
            "events": [occurrence_dict(on, e) for on, e in services.upcoming(days=14)],
        }
    )


@api_view(["GET"])
def nearby(request, slug):
    """The closest things to do to one home, for its listing and trip pages."""
    unit = Unit.objects.filter(slug=slug).select_related("area").first()
    if unit is None:
        return Response({"error": "No such home."}, status=404)
    try:
        limit = min(max(int(request.query_params.get("limit") or 4), 1), 12)
    except ValueError:
        limit = 4
    return Response([place_dict(p) for p in services.nearby(unit, limit=limit)])


# ---------- host console ----------


class PlaceSerializer(serializers.ModelSerializer):
    area = serializers.SlugRelatedField(slug_field="slug", queryset=Area.objects.all(), allow_null=True, required=False)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    map_url = serializers.CharField(read_only=True)

    class Meta:
        model = Place
        fields = [
            "id",
            "name",
            "slug",
            "category",
            "category_label",
            "area",
            "summary",
            "summary_sw",
            "description",
            "tips",
            "hours",
            "price",
            "phone",
            "website",
            "latitude",
            "longitude",
            "photo",
            "featured",
            "active",
            "sort_order",
            "hits",
            "map_url",
            "updated_at",
        ]
        read_only_fields = ["slug", "hits", "updated_at"]

    def validate(self, data):
        lat = data.get("latitude", getattr(self.instance, "latitude", None))
        lng = data.get("longitude", getattr(self.instance, "longitude", None))
        if (lat is None) != (lng is None):
            raise serializers.ValidationError("Give both a latitude and a longitude, or neither.")
        if lat is not None and not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise serializers.ValidationError("That latitude/longitude isn't on the map.")
        return data


class EventSerializer(serializers.ModelSerializer):
    place = serializers.PrimaryKeyRelatedField(queryset=Place.objects.all(), allow_null=True, required=False)
    area = serializers.SlugRelatedField(slug_field="slug", queryset=Area.objects.all(), allow_null=True, required=False)
    next_on = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "summary",
            "place",
            "area",
            "weekday",
            "starts_on",
            "ends_on",
            "yearly",
            "time",
            "price",
            "addon_code",
            "link",
            "active",
            "next_on",
        ]

    def get_next_on(self, e):
        return e.next_on(today())

    def validate(self, data):
        weekday = data.get("weekday", getattr(self.instance, "weekday", None))
        starts = data.get("starts_on", getattr(self.instance, "starts_on", None))
        ends = data.get("ends_on", getattr(self.instance, "ends_on", None))
        if weekday is None and not starts:
            raise serializers.ValidationError("Pick a day of the week, or a start date.")
        if weekday is not None and starts:
            raise serializers.ValidationError("Choose either every week or set dates, not both.")
        if starts and ends and ends < starts:
            raise serializers.ValidationError("The end date is before the start date.")
        return data


class HostPlaceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsHost]
    serializer_class = PlaceSerializer
    queryset = Place.objects.select_related("area").order_by("category", "-featured", "sort_order", "name")


class HostEventViewSet(viewsets.ModelViewSet):
    permission_classes = [IsHost]
    serializer_class = EventSerializer
    queryset = Event.objects.select_related("place", "area").all()
