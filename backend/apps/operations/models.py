from django.conf import settings
from django.db import models


class Task(models.Model):
    """Housekeeping and maintenance work orders: auto-created on checkout or from guest reports,
    assigned to staff by SMS, closed by replying DONE <id> (feature phones welcome)."""

    TYPES = [
        ("turnover", "Turnover clean"),
        ("maintenance", "Maintenance"),
        ("inspection", "Inspection"),
        ("laundry", "Laundry"),
        ("restock", "Restock"),
        ("guest_request", "Guest request"),
        ("other", "Other"),
    ]
    PRIORITIES = [("low", "Low"), ("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")]
    STATUS = [("open", "Open"), ("in_progress", "In progress"), ("done", "Done"), ("cancelled", "Cancelled")]
    CATEGORIES = [
        (c, c.replace("_", " ").capitalize())
        for c in (
            "water",
            "power",
            "wifi",
            "ac",
            "appliance",
            "plumbing",
            "cleanliness",
            "noise",
            "security",
            "pests",
            "lock",
            "other",
        )
    ]

    type = models.CharField(max_length=14, choices=TYPES, default="other")
    title = models.CharField(max_length=140)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=12, choices=CATEGORIES, blank=True)
    unit = models.ForeignKey("properties.Unit", null=True, blank=True, on_delete=models.CASCADE, related_name="tasks")
    booking = models.ForeignKey(
        "bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks"
    )
    priority = models.CharField(max_length=7, choices=PRIORITIES, default="normal")
    status = models.CharField(max_length=12, choices=STATUS, default="open", db_index=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks"
    )
    due_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=6, default="host", help_text="auto, guest, host, staff")
    checklist = models.JSONField(default=list, blank=True)
    completion_note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"#{self.pk} {self.title}"
