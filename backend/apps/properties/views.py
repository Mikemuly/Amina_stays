from datetime import timedelta

from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.core.activity import record
from apps.core.api import IsHost
from apps.core.utils import daterange, parse_date, today

from . import services
from .models import Amenity, Area, CalendarBlock, ICalFeed, PriceOverride, PriceRule, Unit, UnitPhoto, Wishlist
from .serializers import (
    AmenitySerializer,
    BlockSerializer,
    HostUnitSerializer,
    ICalFeedSerializer,
    PhotoSerializer,
    PriceRuleSerializer,
    addon_dict,
    area_dict,
    listing_card,
    listing_detail,
    review_stats,
)


def _dates(request):
    ci, co = parse_date(request.query_params.get("check_in")), parse_date(request.query_params.get("check_out"))
    if ci and co and co > ci and ci >= today():
        return ci, co
    return None, None


def _wished(request):
    if request.user.is_authenticated:
        return set(Wishlist.objects.filter(user=request.user).values_list("unit_id", flat=True))
    return set()


# ---------- public ----------


@api_view(["GET"])
def areas(request):
    qs = Area.objects.annotate(units_count=Count("units", filter=Q(units__status="active"))).order_by(
        "sort_order", "name"
    )
    return Response([area_dict(a) for a in qs])


@api_view(["GET"])
def amenities(request):
    return Response(AmenitySerializer(Amenity.objects.all(), many=True).data)


@api_view(["GET"])
def listings(request):
    p = request.query_params
    ci, co = _dates(request)
    guests = int(p.get("guests") or 0) or None
    qs = Unit.objects.filter(status="active").select_related("area").prefetch_related("photos")
    if ci:
        qs = services.available_units(ci, co, area=p.get("area"), guests=guests, qs=qs, bookable=True)
    else:
        if p.get("area"):
            qs = qs.filter(Q(area__slug=p["area"]) | Q(area__name__iexact=p["area"]))
        if guests:
            qs = qs.filter(max_guests__gte=guests)
    if p.get("tag"):
        qs = qs.filter(tags__contains=[p["tag"]])
    if p.get("type"):
        qs = qs.filter(property_type__in=p["type"].split(","))
    if p.get("free_cancellation"):
        qs = qs.filter(cancellation_policy__in=["flexible", "moderate"])
    if p.get("bedrooms"):
        qs = qs.filter(bedrooms__gte=int(p["bedrooms"]))
    for code in filter(None, (p.get("amenities") or "").split(",")):
        qs = qs.filter(amenities__code=code)
    stats, wished = review_stats(), _wished(request)
    cards = []
    for u in qs.distinct():
        q = services.quote(u, ci, co, guests=guests or 1) if ci else None
        card = listing_card(u, quote=q, stats=stats, wished=u.pk in wished)
        if p.get("guest_favourite") and not card["guest_favourite"]:
            continue
        price = card["price"].get("avg_nightly") or card["price"]["from_nightly"]
        if p.get("min_price") and price < int(p["min_price"]):
            continue
        if p.get("max_price") and price > int(p["max_price"]):
            continue
        cards.append(card)
    sort = p.get("sort")
    if sort == "price":
        cards.sort(key=lambda c: c["price"].get("total") or c["price"]["from_nightly"])
    elif sort == "rating":
        cards.sort(key=lambda c: -(c["rating"] or 0))
    else:
        cards.sort(key=lambda c: (not c["is_featured"], -(c["rating"] or 0)))
    return Response(
        {
            "results": cards,
            "count": len(cards),
            "check_in": ci,
            "check_out": co,
            "nights": (co - ci).days if ci else None,
        }
    )


@api_view(["GET"])
def listing(request, slug):
    unit = get_object_or_404(
        Unit.objects.select_related("area").prefetch_related("photos", "amenities"), slug=slug, status="active"
    )
    return Response(listing_detail(unit, stats=review_stats(), wished=unit.pk in _wished(request)))


@api_view(["GET"])
def calendar(request, slug):
    unit = get_object_or_404(Unit, slug=slug, status="active")
    start = max(parse_date(request.query_params.get("start")) or today(), today())
    end = parse_date(request.query_params.get("end")) or start + timedelta(days=120)
    end = min(end, start + timedelta(days=400))
    blocked = services.unavailable_nights(unit, start, end)
    prices = {d.isoformat(): p for d, p, _ in services.nightly_rates(unit, start, end)}
    return Response(
        {
            "start": start,
            "end": end,
            "unavailable": sorted(d.isoformat() for d in blocked),
            "prices": prices,
            "min_nights": unit.min_nights,
            "max_nights": unit.max_nights,
        }
    )


@api_view(["POST"])
def quote(request, slug):
    from apps.bookings.models import Addon

    unit = get_object_or_404(Unit, slug=slug, status="active")
    d = request.data
    ci, co = parse_date(d.get("check_in")), parse_date(d.get("check_out"))
    if not ci or not co or co <= ci:
        return Response({"error": "Choose your check-in and check-out dates."}, status=400)
    adults, children = int(d.get("adults") or 1), int(d.get("children") or 0)
    guests = adults + children
    items = []
    for a in d.get("addons") or []:
        addon = Addon.objects.filter(code=a.get("code"), active=True).first()
        if addon:
            items.append(
                {
                    "addon": addon,
                    "quantity": int(
                        a.get("quantity") or (guests if addon.pricing in ("per_guest_night", "per_guest") else 1)
                    ),
                }
            )
    q = services.quote(unit, ci, co, guests=guests, addons=items, payment_plan=d.get("payment_plan", "full"))
    # Amina's agreed price for a walk-in, priced exactly as the booking will be (host only: guests can't set prices)
    override = d.get("price_override")
    if override not in (None, "") and IsHost().has_permission(request, None):
        from apps.bookings.services import _with_agreed_price
        from apps.core.models import SiteSettings

        try:
            override = int(override)
        except (TypeError, ValueError):
            override = 0
        if override > 0:
            q = _with_agreed_price(q, override, ci, co, SiteSettings.load())
    problems = []
    if ci < today():
        problems.append("Check-in can't be in the past.")
    elif (ci - today()).days > 540:
        problems.append("We take bookings up to 18 months ahead.")
    if q["nights"] < unit.min_nights:
        problems.append(f"Minimum stay is {unit.min_nights} nights.")
    if q["nights"] > unit.max_nights:
        problems.append(f"Stays here are up to {unit.max_nights} nights.")
    if guests > unit.max_guests:
        problems.append(f"This home sleeps up to {unit.max_guests} guests.")
    available = services.is_available(unit, ci, co)
    if not available:
        problems.append("Those dates aren't available.")
    return Response({**q, "available": available and not problems, "problems": problems})


@api_view(["GET"])
def listing_reviews(request, slug):
    from apps.reviews.models import Review

    unit = get_object_or_404(Unit, slug=slug)
    rows = Review.objects.filter(unit=unit, is_public=True).select_related("guest")[:50]
    return Response(
        [
            {
                "id": r.pk,
                "rating": r.rating,
                "comment": r.comment,
                "guest": (r.guest.name or "Guest").split(" ")[0],
                "country": r.guest.nationality,
                "date": r.created_at.date(),
                "host_response": r.host_response,
                "categories": {
                    c: getattr(r, c)
                    for c in ("cleanliness", "accuracy", "check_in", "communication", "location", "value")
                    if getattr(r, c)
                },
            }
            for r in rows
        ]
    )


def _offered(addon, unit):
    """Some extras are home-specific, and breakfast needs a home that serves it."""
    if addon.units.exists() and not addon.units.filter(pk=unit.pk).exists():
        return False
    return addon.category != "breakfast" or unit.breakfast_available


@api_view(["GET"])
def addons(request):
    from apps.bookings.models import Addon

    qs = Addon.objects.filter(active=True).prefetch_related("units")
    slug = request.query_params.get("listing")
    unit = Unit.objects.filter(slug=slug).first() if slug else None
    return Response([addon_dict(a) for a in qs if not unit or _offered(a, unit)])


def ical_export(request, token):
    unit = get_object_or_404(Unit, ical_token=token)
    resp = HttpResponse(services.export_ics(unit), content_type="text/calendar; charset=utf-8")
    resp["Content-Disposition"] = f'inline; filename="{unit.slug}.ics"'
    return resp


# ---------- host ----------


class HostUnitViewSet(viewsets.ModelViewSet):
    permission_classes = [IsHost]
    serializer_class = HostUnitSerializer
    queryset = Unit.objects.select_related("area").prefetch_related("photos", "amenities").order_by("sort_order", "id")
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def perform_create(self, serializer):
        unit = serializer.save()
        record("listing", f"New listing: {unit.name}", actor=self.request.user)

    def perform_update(self, serializer):
        unit = serializer.save()
        record("listing", f"Listing updated: {unit.name}", actor=self.request.user)

    def destroy(self, request, *args, **kwargs):
        unit = self.get_object()
        if unit.bookings.exists():
            unit.status = "paused"
            unit.save(update_fields=["status"])
            return Response({"paused": True, "detail": "Homes with bookings are paused rather than deleted."})
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="photos")
    def add_photo(self, request, pk=None):
        unit = self.get_object()
        ser = PhotoSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if not ser.validated_data.get("url") and not ser.validated_data.get("image"):
            return Response({"error": "Add a photo file or an image URL."}, status=400)
        photo = ser.save(unit=unit, sort_order=unit.photos.count())
        return Response(PhotoSerializer(photo).data, status=201)

    @action(detail=True, methods=["post"], url_path="photos/order")
    def order_photos(self, request, pk=None):
        unit = self.get_object()
        for i, pid in enumerate(request.data.get("ids", [])):
            UnitPhoto.objects.filter(unit=unit, pk=pid).update(sort_order=i)
        return Response(PhotoSerializer(unit.photos.all(), many=True).data)

    @action(detail=True, methods=["delete"], url_path=r"photos/(?P<photo_id>\d+)")
    def delete_photo(self, request, pk=None, photo_id=None):
        UnitPhoto.objects.filter(unit=self.get_object(), pk=photo_id).delete()
        return Response(status=204)


class PriceRuleViewSet(viewsets.ModelViewSet):
    permission_classes = [IsHost]
    serializer_class = PriceRuleSerializer
    queryset = PriceRule.objects.select_related("unit").all()


class BlockViewSet(viewsets.ModelViewSet):
    permission_classes = [IsHost]
    serializer_class = BlockSerializer

    def get_queryset(self):
        return CalendarBlock.objects.select_related("unit").filter(end_date__gte=today() - timedelta(days=60))

    def perform_create(self, serializer):
        b = serializer.save(created_by=self.request.user)
        record(
            "listing",
            f"Blocked {b.unit.name} {b.start_date}→{b.end_date} ({b.get_reason_display()})",
            actor=self.request.user,
        )


class ICalFeedViewSet(viewsets.ModelViewSet):
    permission_classes = [IsHost]
    serializer_class = ICalFeedSerializer
    queryset = ICalFeed.objects.select_related("unit").all()

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        return Response(services.sync_feed(self.get_object()))


class AmenityViewSet(viewsets.ModelViewSet):
    permission_classes = [IsHost]
    serializer_class = AmenitySerializer
    queryset = Amenity.objects.all()


@api_view(["GET"])
@permission_classes([IsHost])
def host_calendar(request):
    """Multi-calendar: every home × every day, with bookings, blocks and nightly prices."""
    from apps.bookings.models import Booking

    start = parse_date(request.query_params.get("start")) or today() - timedelta(days=2)
    days = max(7, min(int(request.query_params.get("days") or 21), 62))
    end = start + timedelta(days=days)
    units = Unit.objects.exclude(status="draft").select_related("area").order_by("sort_order", "id")
    bookings_qs = Booking.objects.filter(
        check_in__lt=end, check_out__gt=start, status__in=("held", "confirmed", "checked_in", "completed")
    ).select_related("guest")
    by_unit = {}
    for b in bookings_qs:
        if b.status == "held" and not b.hold_active:
            continue
        by_unit.setdefault(b.unit_id, []).append(
            {
                "ref": b.ref,
                "guest": b.guest.name or b.guest.phone,
                "check_in": b.check_in,
                "check_out": b.check_out,
                "status": b.status,
                "channel": b.channel,
                "nights": b.nights,
                "total": b.total,
                "balance_due": b.balance_due,
            }
        )
    blocks = {}
    for blk in CalendarBlock.objects.filter(start_date__lt=end, end_date__gt=start).select_related("feed"):
        blocks.setdefault(blk.unit_id, []).append(
            {
                "id": blk.pk,
                "start_date": blk.start_date,
                "end_date": blk.end_date,
                "reason": blk.reason,
                "reason_label": blk.get_reason_display(),
                "note": blk.note,
                "external": blk.feed_id is not None,
                "source": blk.feed.name if blk.feed_id else None,  # "Airbnb", "Booking.com"… for iCal blocks
            }
        )
    overrides = {}
    for o in PriceOverride.objects.filter(date__gte=start, date__lt=end):
        overrides.setdefault(o.unit_id, []).append(o.date.isoformat())
    return Response(
        {
            "start": start,
            "end": end,
            "days": [d.isoformat() for d in daterange(start, end)],
            "today": today(),
            "units": [
                {
                    "id": u.pk,
                    "name": u.name,
                    "area": u.area.name,
                    "status": u.status,
                    "housekeeping": u.housekeeping,
                    "base_price": u.base_price,
                    "cover": u.cover_photo,
                    "bookings": by_unit.get(u.pk, []),
                    "blocks": blocks.get(u.pk, []),
                    "prices": {d.isoformat(): p for d, p, _ in services.nightly_rates(u, start, end)},
                    "overrides": overrides.get(u.pk, []),
                }
                for u in units
            ],
        }
    )


@api_view(["PUT"])
@permission_classes([IsHost])
def set_prices(request):
    """Calendar price overrides: {unit, dates: [...] | start/end, price (null clears)}."""
    unit = get_object_or_404(Unit, pk=request.data.get("unit"))
    dates = [parse_date(d) for d in request.data.get("dates") or []]
    if request.data.get("start") and request.data.get("end"):
        dates = list(daterange(parse_date(request.data["start"]), parse_date(request.data["end"])))
    dates = [d for d in dates if d]
    price = request.data.get("price")
    if price in (None, ""):
        PriceOverride.objects.filter(unit=unit, date__in=dates).delete()
    else:
        for d in dates:
            PriceOverride.objects.update_or_create(
                unit=unit, date=d, defaults={"price": int(price), "note": request.data.get("note", "")[:80]}
            )
    record(
        "pricing",
        f"{unit.name}: {'cleared' if price in (None, '') else f'KES {int(price):,}'} for {len(dates)} night(s)",
        actor=request.user,
    )
    return Response({"updated": len(dates)}, status=status.HTTP_200_OK)
