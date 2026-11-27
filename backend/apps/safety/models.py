from django.conf import settings
from django.db import models


class Alert(models.Model):
    """Anything Amina must act on now: SOS, urgent faults, low reviews, calendar conflicts, fraud signals."""

    KINDS = [
        ("sos", "Guest SOS"),
        ("urgent_issue", "Urgent issue"),
        ("low_review", "Low review"),
        ("conflict", "Calendar conflict"),
        ("security", "Security / fraud"),
        ("payment", "Payment problem"),
        ("compliance", "Compliance"),
        ("sms", "SMS delivery"),
    ]
    SEVERITY = [("critical", "Critical"), ("high", "High"), ("medium", "Medium"), ("low", "Low")]
    STATUS = [("open", "Open"), ("acknowledged", "Acknowledged"), ("resolved", "Resolved")]

    kind = models.CharField(max_length=14, choices=KINDS)
    severity = models.CharField(max_length=8, choices=SEVERITY, default="high")
    status = models.CharField(max_length=12, choices=STATUS, default="open", db_index=True)
    source = models.CharField(max_length=12, blank=True, help_text="sms, voice, web, ussd, system")
    phone = models.CharField(max_length=20, blank=True)
    guest = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="alerts"
    )
    booking = models.ForeignKey(
        "bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL, related_name="alerts"
    )
    summary = models.CharField(max_length=300)
    details = models.TextField(blank=True)
    call_status = models.CharField(max_length=30, blank=True)
    calls_made = models.PositiveSmallIntegerField(default=0)
    last_call_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    resolution_note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.kind}: {self.summary}"
