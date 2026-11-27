from django.conf import settings
from django.db import models


class Ticket(models.Model):
    """One guest request with a reference (T12) the guest can quote on any channel: a complaint, a call-back request,
    a billing question or a problem in the home. Each has a reply-by time; a ticket nobody answers escalates to
    Amina by SMS, then by a phone call."""

    CATEGORIES = [
        ("complaint", "Complaint"),
        ("issue", "Problem in the home"),
        ("callback", "Call-back request"),
        ("billing", "Billing & payments"),
        ("booking", "Booking & changes"),
        ("feedback", "Feedback"),
        ("other", "Other"),
    ]
    STATUS = [("open", "Open"), ("in_progress", "In progress"), ("resolved", "Resolved"), ("closed", "Closed")]
    PRIORITIES = [("low", "Low"), ("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")]
    CHANNELS = [("sms", "SMS"), ("ussd", "USSD"), ("voice", "Voice"), ("web", "Website"), ("host", "Console")]

    phone = models.CharField(max_length=20, db_index=True)
    guest = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets"
    )
    booking = models.ForeignKey(
        "bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets"
    )
    unit = models.ForeignKey("properties.Unit", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    task = models.ForeignKey(
        "operations.Task", null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets"
    )
    channel = models.CharField(max_length=6, choices=CHANNELS, default="sms")
    category = models.CharField(max_length=10, choices=CATEGORIES, default="other")
    priority = models.CharField(max_length=7, choices=PRIORITIES, default="normal")
    status = models.CharField(max_length=12, choices=STATUS, default="open", db_index=True)
    subject = models.CharField(max_length=140)
    description = models.TextField(blank=True)
    recording_url = models.URLField(max_length=500, blank=True, help_text="A complaint left as a voice message")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    first_response_due = models.DateTimeField(null=True, blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.CharField(max_length=300, blank=True)
    escalation_level = models.PositiveSmallIntegerField(default=0, help_text="0 none, 1 SMS to Amina, 2 voice call")
    last_escalated_at = models.DateTimeField(null=True, blank=True)
    call_requested_at = models.DateTimeField(null=True, blank=True, help_text="Amina asked to be connected")
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    rating_comment = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.ref} {self.subject}"

    @property
    def ref(self):
        return f"T{self.pk}"


class TicketEvent(models.Model):
    """The ticket's timeline: what happened, on which channel, by whom."""

    KINDS = [
        (k, k.replace("_", " ").capitalize())
        for k in ("created", "reply", "guest", "note", "status", "call", "escalated", "rating", "task")
    ]
    PUBLIC = ("created", "reply", "status", "rating")  # what the guest sees on the website

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=10, choices=KINDS)
    text = models.TextField()
    channel = models.CharField(max_length=6, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
