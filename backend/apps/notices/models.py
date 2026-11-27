from django.conf import settings
from django.db import models
from django.utils import timezone


class Notice(models.Model):
    """A service disruption guests should hear about before they have to ask: an outage now, planned maintenance or
    an advisory. Guests staying at the affected homes get an SMS when it starts (a day ahead if it's planned) and
    again when it's over."""

    SERVICES = [
        ("power", "Power"),
        ("water", "Water"),
        ("wifi", "Wi-Fi"),
        ("ac", "Air conditioning"),
        ("gas", "Cooking gas"),
        ("pool", "Swimming pool"),
        ("lift", "Lift"),
        ("road", "Road access"),
        ("network", "Mobile network"),
        ("security", "Security"),
        ("other", "Other"),
    ]
    KINDS = [("outage", "Outage"), ("maintenance", "Planned maintenance"), ("advisory", "Advisory")]
    STATUS = [("scheduled", "Scheduled"), ("active", "Active"), ("resolved", "Resolved"), ("cancelled", "Cancelled")]

    kind = models.CharField(max_length=12, choices=KINDS, default="outage")
    service = models.CharField(max_length=10, choices=SERVICES)
    status = models.CharField(max_length=10, choices=STATUS, default="active", db_index=True)
    title = models.CharField(max_length=100)
    message = models.TextField(blank=True, help_text="What guests should know: the cause, what still works, what to do")
    units = models.ManyToManyField(
        "properties.Unit", blank=True, related_name="notices", help_text="Leave empty for every home"
    )
    starts_at = models.DateTimeField(default=timezone.now)
    expected_end = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.CharField(max_length=240, blank=True)
    data_mb = models.PositiveIntegerField(
        default=0, help_text="Mobile data sent to each guest staying while the Wi-Fi or power is down (0 = none)"
    )
    notified = models.PositiveIntegerField(default=0, help_text="Guest messages sent about it")
    overdue_nudged = models.BooleanField(default=False)
    source = models.CharField(max_length=8, default="host", help_text="host, staff, sms, ussd or demo")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-starts_at", "-id"]

    def __str__(self):
        return f"#{self.pk} {self.title}"


class Delivery(models.Model):
    """Who was told what about a notice, so nobody hears the same thing twice and 'it's fixed' reaches exactly the
    guests who heard it was broken."""

    KINDS = [
        ("heads_up", "Heads-up"),
        ("start", "Started"),
        ("update", "Update"),
        ("restored", "Over"),
        ("cancelled", "Cancelled"),
        ("data", "Data bundle"),
    ]
    notice = models.ForeignKey(Notice, on_delete=models.CASCADE, related_name="deliveries")
    phone = models.CharField(max_length=20)
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=10, choices=KINDS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "deliveries"
        constraints = [
            models.UniqueConstraint(
                fields=["notice", "phone", "kind"],
                condition=~models.Q(kind="update"),
                name="notice_delivery_once",
            )
        ]
