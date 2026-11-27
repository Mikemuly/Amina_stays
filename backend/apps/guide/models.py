from datetime import timedelta
from urllib.parse import quote_plus

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Place(models.Model):
    """Things to see, eat and know near the homes. One entry answers USSD, SMS, voice and the website, so a guest
    with no data gets the same local knowledge as one browsing the site."""

    CATEGORIES = [
        ("sights", "Sights & history"),
        ("beaches", "Beaches & sea"),
        ("nature", "Nature & wildlife"),
        ("food", "Food & drink"),
        ("markets", "Markets & crafts"),
        ("culture", "Culture & faith"),
        ("evenings", "Evenings out"),
        ("transport", "Getting around"),
        ("essentials", "Health & essentials"),
    ]

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    category = models.CharField(max_length=12, choices=CATEGORIES, db_index=True)
    area = models.ForeignKey("properties.Area", null=True, blank=True, on_delete=models.SET_NULL, related_name="places")
    summary = models.CharField(max_length=110, help_text="One line: what guests see on USSD and SMS")
    summary_sw = models.CharField(max_length=110, blank=True, help_text="The same line in Kiswahili")
    description = models.TextField(blank=True)
    tips = models.CharField(max_length=240, blank=True, help_text="Etiquette, safety, the best time to go")
    hours = models.CharField(max_length=80, blank=True)
    price = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    photo = models.URLField(max_length=500, blank=True)
    featured = models.BooleanField(default=False, help_text="A top pick: listed first everywhere")
    active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    hits = models.PositiveIntegerField(default=0, help_text="How often guests opened it by USSD, SMS or voice")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-featured", "sort_order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:80] or "place"
            slug, n = base, 2
            while Place.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*args, **kwargs)

    def summary_in(self, lang):
        return (self.summary_sw if lang == "sw" else "") or self.summary

    @property
    def map_url(self):
        # searched by name: a slightly-off pin (used only to sort by distance) never sends a guest to the wrong place
        where = ", ".join(p for p in (self.name, self.area.name if self.area_id else "", settings.GUIDE_REGION) if p)
        return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(where)


class Event(models.Model):
    """What's on: weekly happenings (a market day, Amina's dhow cruise) and dated events (public holidays,
    festivals). A yearly event repeats on the same dates every year."""

    WEEKDAYS = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    title = models.CharField(max_length=100)
    summary = models.CharField(max_length=160, blank=True)
    place = models.ForeignKey(Place, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    area = models.ForeignKey("properties.Area", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    weekday = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=WEEKDAYS, help_text="Repeats every week on this day"
    )
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    yearly = models.BooleanField(default=False, help_text="Repeats on the same dates every year")
    time = models.CharField(max_length=40, blank=True)
    price = models.CharField(max_length=100, blank=True)
    addon_code = models.CharField(max_length=40, blank=True, help_text="Bookable as this extra from the trip page")
    link = models.URLField(blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["weekday", "starts_on", "id"]

    def __str__(self):
        return self.title

    def next_on(self, day):
        """The first date on or after `day` the event is on (today while it runs), or None once it's over."""
        if self.weekday is not None:
            return day + timedelta(days=(self.weekday - day.weekday()) % 7)
        if not self.starts_on:
            return None
        start, end = self.starts_on, max(self.ends_on or self.starts_on, self.starts_on)
        if not self.yearly:
            return max(start, day) if end >= day else None
        for year in (day.year - 1, day.year, day.year + 1):  # a run over New Year starts the year before
            try:
                s = start.replace(year=year)
                e = end.replace(year=year + (end.year - start.year))
            except ValueError:  # 29 February in a common year
                continue
            if e >= day:
                return max(s, day)
        return None
