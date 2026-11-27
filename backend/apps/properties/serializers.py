from django.db.models import Avg, Count
from rest_framework import serializers

from apps.core.models import SiteSettings
from apps.reviews.models import Review

from .models import Amenity, Area, CalendarBlock, ICalFeed, PriceRule, Unit, UnitPhoto
from .services import from_price


def review_stats():
    rows = Review.objects.filter(is_public=True).values("unit").annotate(avg=Avg("rating"), n=Count("id"))
    return {r["unit"]: {"rating": round(r["avg"], 2), "count": r["n"]} for r in rows}


def _favourite(stat):
    return bool(stat and stat["rating"] >= 4.8 and stat["count"] >= 5)


def listing_card(unit, *, quote=None, stats=None, wished=False):
    stat = (stats or {}).get(unit.pk)
    photos = [p.src for p in unit.photos.all()][:6]
    card = {
        "id": unit.pk,
        "slug": unit.slug,
        "name": unit.name,
        "headline": unit.headline,
        "summary": unit.summary,
        "property_type": unit.property_type,
        "area": {"name": unit.area.name, "slug": unit.area.slug},
        "bedrooms": unit.bedrooms,
        "beds": unit.beds,
        "bathrooms": float(unit.bathrooms),
        "max_guests": unit.max_guests,
        "photos": photos,
        "tags": unit.tags,
        "is_featured": unit.is_featured,
        "rating": stat["rating"] if stat else None,
        "reviews_count": stat["count"] if stat else 0,
        "guest_favourite": _favourite(stat),
        "location": unit.approximate_location(),
        "wishlisted": wished,
        "breakfast_available": unit.breakfast_available,
        "free_cancellation": unit.cancellation_policy in ("flexible", "moderate"),
        "price": {"from_nightly": from_price(unit), "base_price": unit.base_price},
    }
    if quote:
        card["price"].update(total=quote["total"], nights=quote["nights"], avg_nightly=quote["avg_nightly_all_in"])
    return card


POLICY_TEXT = {
    "flexible": "Free cancellation until 24 hours before check-in.",
    "moderate": "Free cancellation until 5 days before check-in, then 50% back.",
    "firm": "Full refund until 30 days before check-in, 50% until 7 days before.",
    "strict": "50% refund until 7 days before check-in.",
}


def listing_detail(unit, *, stats=None, wished=False):
    from apps.bookings.models import Addon
    from apps.reviews.services import unit_stats

    s = SiteSettings.load()
    rs = unit_stats(unit)
    addons = [
        addon_dict(a)
        for a in Addon.objects.filter(active=True).prefetch_related("units")
        if (not a.units.exists() or a.units.filter(pk=unit.pk).exists())
        and (a.category != "breakfast" or unit.breakfast_available)
    ]
    data = listing_card(unit, stats=stats, wished=wished)
    data.update(
        description=unit.description,
        the_space=unit.the_space,
        guest_access=unit.guest_access,
        neighbourhood=unit.neighbourhood,
        sleeping=unit.sleeping,
        size_sqm=unit.size_sqm,
        photos=[{"src": p.src, "caption": p.caption, "room": p.room} for p in unit.photos.all()],
        amenities=[
            {"code": a.code, "name": a.name, "icon": a.icon, "category": a.category} for a in unit.amenities.all()
        ],
        highlights=unit.highlights,
        house_rules=unit.house_rules,
        pets_allowed=unit.pets_allowed,
        smoking_allowed=unit.smoking_allowed,
        events_allowed=unit.events_allowed,
        quiet_hours=unit.quiet_hours,
        safety_features=unit.safety_features,
        checkin_time=unit.effective_checkin(),
        checkout_time=unit.effective_checkout(),
        access_method=unit.guest_access_label,
        self_checkin=unit.access_method in ("simulated", "igloohome", "ttlock", "nuki", "lockbox"),
        min_nights=unit.min_nights,
        max_nights=unit.max_nights,
        cleaning_fee=unit.cleaning_fee,
        weekend_price=unit.weekend_price,
        weekly_discount=unit.weekly_discount,
        monthly_discount=unit.monthly_discount,
        cancellation={
            "policy": unit.cancellation_policy,
            "label": unit.get_cancellation_policy_display(),
            "text": POLICY_TEXT[unit.cancellation_policy],
        },
        reviews_summary=rs,
        rating=rs["rating"],
        reviews_count=rs["count"],
        guest_favourite=rs["guest_favourite"],
        area_info={
            "name": unit.area.name,
            "summary": unit.area.summary,
            "description": unit.area.description,
            "getting_there": unit.area.getting_there,
            "photo_url": unit.area.photo_url,
        },
        host={
            "name": s.host_name,
            "since": 2019,
            "response_time": "within an hour",
            "languages": ["English", "Kiswahili"],
            "superhost": True,
            "verified": True,
        },
        addons=addons,
        tra_licence=unit.tra_licence_number or s.tra_licence_number,
        levy_percent=float(s.tourism_levy_percent),
        deposit_percent=s.deposit_percent,
    )
    return data


def addon_dict(a):
    return {
        "code": a.code,
        "name": a.name,
        "short": a.short,
        "description": a.description,
        "category": a.category,
        "icon": a.icon,
        "photo_url": a.photo_url,
        "price": a.price,
        "pricing": a.pricing,
        "pricing_label": a.get_pricing_display(),
        "requires_approval": a.requires_approval,
        "options": a.options,
    }


def area_dict(a):
    return {
        "name": a.name,
        "slug": a.slug,
        "summary": a.summary,
        "description": a.description,
        "photo_url": a.photo_url,
        "getting_there": a.getting_there,
        "units_count": getattr(a, "units_count", None),
        "location": {"lat": float(a.latitude), "lng": float(a.longitude)} if a.latitude is not None else None,
    }


# ---------- host-side (full detail incl. private fields) ----------


class PhotoSerializer(serializers.ModelSerializer):
    src = serializers.CharField(read_only=True)

    class Meta:
        model = UnitPhoto
        fields = ["id", "url", "image", "src", "caption", "room", "sort_order"]
        extra_kwargs = {"image": {"required": False}, "url": {"required": False}}


class HostUnitSerializer(serializers.ModelSerializer):
    area = serializers.SlugRelatedField(slug_field="slug", queryset=Area.objects.all())
    amenity_codes = serializers.SlugRelatedField(
        source="amenities", slug_field="code", many=True, queryset=Amenity.objects.all(), required=False
    )
    photos = PhotoSerializer(many=True, read_only=True)
    ical_export_url = serializers.SerializerMethodField()

    class Meta:
        model = Unit
        exclude = ["amenities", "ical_token"]
        read_only_fields = ["slug", "created_at", "updated_at"]

    def get_ical_export_url(self, obj):
        from django.conf import settings

        return f"{settings.PUBLIC_URL}/api/ical/{obj.ical_token}.ics"


class PriceRuleSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source="unit.name", read_only=True, default="All homes")

    class Meta:
        model = PriceRule
        fields = "__all__"


class BlockSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source="unit.name", read_only=True)

    class Meta:
        model = CalendarBlock
        fields = ["id", "unit", "unit_name", "start_date", "end_date", "reason", "note", "feed", "created_at"]
        read_only_fields = ["feed", "created_at"]

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end <= start:
            raise serializers.ValidationError("End date must be after the start date.")
        return attrs


class ICalFeedSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source="unit.name", read_only=True)

    class Meta:
        model = ICalFeed
        fields = [
            "id",
            "unit",
            "unit_name",
            "name",
            "url",
            "active",
            "last_synced_at",
            "last_ok",
            "last_error",
            "events_count",
        ]
        read_only_fields = ["last_synced_at", "last_ok", "last_error", "events_count"]


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ["id", "code", "name", "icon", "category", "description"]
