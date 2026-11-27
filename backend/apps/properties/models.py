import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Area(models.Model):
    name = models.CharField(max_length=40, unique=True)
    slug = models.SlugField(max_length=40, unique=True)
    summary = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    photo_url = models.URLField(max_length=500, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    getting_there = models.TextField(blank=True, help_text="From Moi Airport, the SGR terminus, the Likoni ferry…")
    tips = models.TextField(blank=True, help_text="Food, beaches, safety — sent with the check-in message")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Amenity(models.Model):
    CATEGORIES = [
        (c, c.replace("_", " ").capitalize())
        for c in (
            "essentials",
            "coastal",
            "bedroom",
            "bathroom",
            "kitchen",
            "entertainment",
            "family",
            "workspace",
            "outdoor",
            "parking",
            "safety",
            "accessibility",
            "services",
        )
    ]
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=60)
    icon = models.CharField(max_length=40, default="check", help_text="lucide icon name")
    category = models.CharField(max_length=20, choices=CATEGORIES, default="essentials")
    description = models.CharField(max_length=160, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "amenities"

    def __str__(self):
        return self.name


class Unit(models.Model):
    TYPES = [(t, t.capitalize()) for t in ("apartment", "studio", "villa", "cottage", "penthouse", "house", "room")]
    POLICIES = [("flexible", "Flexible"), ("moderate", "Moderate"), ("firm", "Firm"), ("strict", "Strict")]
    LOCKS = [
        ("simulated", "Simulated keypad (dashboard)"),
        ("igloohome", "igloohome (offline algoPIN)"),
        ("ttlock", "TTLock"),
        ("nuki", "Nuki"),
        ("lockbox", "Key lockbox"),
        ("caretaker", "Caretaker hands over keys"),
    ]
    STATUS = [("active", "Listed"), ("paused", "Paused"), ("draft", "Draft")]
    HOUSEKEEPING = [
        ("clean", "Clean"),
        ("dirty", "Needs cleaning"),
        ("cleaning", "Cleaning"),
        ("inspect", "Needs inspection"),
    ]
    GUEST_ACCESS = {
        "simulated": "Self check-in with a keypad",
        "igloohome": "Self check-in with a smart lock",
        "ttlock": "Self check-in with a smart lock",
        "nuki": "Self check-in with a smart lock",
        "lockbox": "Self check-in with a key lockbox",
        "caretaker": "The caretaker meets you with the keys",
    }

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="units")
    property_type = models.CharField(max_length=12, choices=TYPES, default="apartment")
    summary = models.CharField(max_length=240, blank=True, help_text="One-line pitch shown on cards and in SMS")
    description = models.TextField(blank=True)
    the_space = models.TextField(blank=True)
    guest_access = models.TextField(blank=True)
    neighbourhood = models.TextField(blank=True)

    bedrooms = models.PositiveSmallIntegerField(default=1)
    beds = models.PositiveSmallIntegerField(default=1)
    bathrooms = models.DecimalField(max_digits=3, decimal_places=1, default=1)
    max_guests = models.PositiveSmallIntegerField(default=2)
    size_sqm = models.PositiveSmallIntegerField(null=True, blank=True)
    sleeping = models.JSONField(default=list, blank=True, help_text='[{"room": "Bedroom 1", "beds": "1 queen bed"}]')

    base_price = models.PositiveIntegerField(help_text="KES per night")
    weekend_price = models.PositiveIntegerField(null=True, blank=True, help_text="KES per Fri/Sat night")
    cleaning_fee = models.PositiveIntegerField(default=0)
    weekly_discount = models.PositiveSmallIntegerField(default=0, help_text="% off stays of 7+ nights")
    monthly_discount = models.PositiveSmallIntegerField(default=0, help_text="% off stays of 28+ nights")
    min_nights = models.PositiveSmallIntegerField(default=1)
    max_nights = models.PositiveSmallIntegerField(default=60)
    checkin_time = models.CharField(max_length=5, blank=True, help_text="Blank = business default")
    checkout_time = models.CharField(max_length=5, blank=True)
    cancellation_policy = models.CharField(max_length=10, choices=POLICIES, default="moderate")

    # Exact location and access details are private until a booking is confirmed (Airbnb pattern)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    address = models.CharField(max_length=200, blank=True)
    directions = models.TextField(blank=True)
    landmark = models.CharField(max_length=160, blank=True)
    map_link = models.URLField(max_length=500, blank=True)
    wifi_name = models.CharField(max_length=60, blank=True)
    wifi_password = models.CharField(max_length=60, blank=True)
    access_method = models.CharField(max_length=10, choices=LOCKS, default="simulated")
    lock_device_id = models.CharField(max_length=80, blank=True)
    parking = models.CharField(max_length=160, blank=True)

    house_rules = models.JSONField(default=list, blank=True)
    pets_allowed = models.BooleanField(default=False)
    smoking_allowed = models.BooleanField(default=False)
    events_allowed = models.BooleanField(default=False)
    quiet_hours = models.CharField(max_length=40, default="22:00–07:00")
    safety_features = models.JSONField(
        default=list, blank=True, help_text="Smoke alarm, guard, generator, camera disclosures…"
    )
    house_manual = models.TextField(blank=True, help_text="Appliances, AC, water, trash — shown to booked guests")
    local_tips = models.TextField(blank=True)

    amenities = models.ManyToManyField(Amenity, blank=True, related_name="units")
    highlights = models.JSONField(default=list, blank=True, help_text='[{"icon": "waves", "title": "…", "text": "…"}]')
    tags = models.JSONField(default=list, blank=True, help_text="Category slugs: beachfront, pool, family…")
    breakfast_available = models.BooleanField(default=True)

    status = models.CharField(max_length=8, choices=STATUS, default="active", db_index=True)
    tra_licence_number = models.CharField(
        max_length=40, blank=True, help_text="TRA licence for this address (blank = business licence)"
    )
    housekeeping = models.CharField(max_length=10, choices=HOUSEKEEPING, default="clean")
    is_featured = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)
    ical_token = models.CharField(max_length=40, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "stay"
            slug, n = base, 2
            while Unit.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        if not self.ical_token:
            self.ical_token = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)

    @property
    def headline(self):
        return f"Entire {self.get_property_type_display().lower()} in {self.area.name}"

    @property
    def cover_photo(self):
        photo = self.photos.first()
        return photo.src if photo else ""

    def effective_checkin(self):
        from apps.core.models import SiteSettings

        return self.checkin_time or SiteSettings.load().default_checkin_time

    def effective_checkout(self):
        from apps.core.models import SiteSettings

        return self.checkout_time or SiteSettings.load().default_checkout_time

    @property
    def guest_access_label(self):
        return self.GUEST_ACCESS.get(self.access_method, "Self check-in")

    def approximate_location(self):
        """Public map pin: deterministic ~300–600 m offset so the exact door stays private."""
        if self.latitude is None or self.longitude is None:
            return None
        h = hashlib.sha256(f"{self.pk}:{settings.SECRET_KEY}".encode()).digest()
        dlat = ((h[0] / 255) - 0.5) * 0.009
        dlng = ((h[1] / 255) - 0.5) * 0.009
        return {"lat": round(float(self.latitude) + dlat, 5), "lng": round(float(self.longitude) + dlng, 5)}


class UnitPhoto(models.Model):
    ROOMS = [
        (r, r.capitalize())
        for r in ("exterior", "living", "bedroom", "kitchen", "bathroom", "view", "pool", "dining", "other")
    ]
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="photos")
    url = models.URLField(max_length=500, blank=True)
    image = models.FileField(upload_to="units/", blank=True)
    caption = models.CharField(max_length=120, blank=True)
    room = models.CharField(max_length=10, choices=ROOMS, default="other")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.unit} photo {self.pk}"

    @property
    def src(self):
        return self.image.url if self.image else self.url


class PriceRule(models.Model):
    """Rule-based pricing: seasons, weekdays and last-minute deals (coast seasonality matters)."""

    KINDS = [
        ("season", "Season / event"),
        ("weekday", "Day of week"),
        ("last_minute", "Last-minute"),
        ("early_bird", "Early bird"),
    ]
    ADJUST = [("percent", "Percent"), ("amount", "KES amount"), ("fixed", "Fixed nightly price")]
    unit = models.ForeignKey(
        Unit, null=True, blank=True, on_delete=models.CASCADE, related_name="price_rules", help_text="Blank = all units"
    )
    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=12, choices=KINDS, default="season")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True, help_text="Inclusive")
    weekdays = models.JSONField(default=list, blank=True, help_text="0=Mon … 6=Sun (nights)")
    days_before = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Last-minute: within N days; early bird: at least N days"
    )
    adjust_type = models.CharField(max_length=8, choices=ADJUST, default="percent")
    value = models.DecimalField(max_digits=10, decimal_places=2, help_text="+20 = 20% more; -15 = 15% off")
    priority = models.PositiveSmallIntegerField(default=10)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["priority", "id"]

    def __str__(self):
        return self.name


class PriceOverride(models.Model):
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="price_overrides")
    date = models.DateField()
    price = models.PositiveIntegerField()
    note = models.CharField(max_length=80, blank=True)

    class Meta:
        unique_together = [("unit", "date")]
        ordering = ["date"]


class ICalFeed(models.Model):
    """Imports Airbnb / Booking.com / Vrbo calendars so a night sold elsewhere can't be sold here."""

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="ical_feeds")
    name = models.CharField(max_length=40, help_text="Airbnb, Booking.com, Vrbo…")
    url = models.URLField(max_length=600)
    active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_ok = models.BooleanField(default=True)
    last_error = models.CharField(max_length=300, blank=True)
    events_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.unit} ← {self.name}"


class CalendarBlock(models.Model):
    REASONS = [
        ("owner", "Owner use"),
        ("maintenance", "Maintenance"),
        ("external", "Booked elsewhere"),
        ("other", "Other"),
    ]
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="blocks")
    start_date = models.DateField()
    end_date = models.DateField(help_text="Exclusive (the morning the unit is free again)")
    reason = models.CharField(max_length=12, choices=REASONS, default="owner")
    note = models.CharField(max_length=160, blank=True)
    feed = models.ForeignKey(ICalFeed, null=True, blank=True, on_delete=models.CASCADE, related_name="blocks")
    external_uid = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_date"]
        indexes = [models.Index(fields=["unit", "start_date", "end_date"])]

    def __str__(self):
        return f"{self.unit} blocked {self.start_date}→{self.end_date}"


class Wishlist(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "unit")]
        ordering = ["-created_at"]
