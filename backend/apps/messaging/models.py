from django.conf import settings
from django.db import models


class Thread(models.Model):
    """One conversation per guest phone number, whatever channel each message used."""

    STATUS = [("open", "Open"), ("resolved", "Resolved")]
    phone = models.CharField(max_length=20, unique=True)
    guest = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="threads"
    )
    status = models.CharField(max_length=8, choices=STATUS, default="open")
    needs_reply = models.BooleanField(default=False, db_index=True)
    unread = models.PositiveIntegerField(default=0)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_preview = models.CharField(max_length=160, blank=True)
    waiting_since = models.DateTimeField(null=True, blank=True, help_text="Oldest unanswered guest message")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_message_at"]

    def __str__(self):
        return self.phone


class Message(models.Model):
    DIRECTIONS = [("in", "Inbound"), ("out", "Outbound")]
    CHANNELS = [
        (c, c.upper() if len(c) <= 4 else c.capitalize())
        for c in ("sms", "web", "voice", "ussd", "whatsapp", "email", "system")
    ]
    SENDERS = [(s, s.capitalize()) for s in ("guest", "bot", "host", "staff", "system")]
    HANDLED = [(h, h.capitalize()) for h in ("pending", "auto", "relayed", "answered", "escalated", "na")]
    STATUS = [(s, s.capitalize()) for s in ("queued", "sending", "sent", "delivered", "failed", "received", "logged")]

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="messages")
    phone = models.CharField(max_length=20, db_index=True)
    booking = models.ForeignKey(
        "bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL, related_name="messages"
    )
    direction = models.CharField(max_length=3, choices=DIRECTIONS)
    channel = models.CharField(max_length=8, choices=CHANNELS, default="sms")
    sender = models.CharField(max_length=6, choices=SENDERS, default="system")
    body = models.TextField()
    kind = models.CharField(max_length=40, blank=True, help_text="Template key or detected intent")
    handled = models.CharField(max_length=10, choices=HANDLED, default="na")
    status = models.CharField(max_length=10, choices=STATUS, default="queued", db_index=True)
    is_marketing = models.BooleanField(default=False)
    provider_id = models.CharField(max_length=80, blank=True, db_index=True)
    provider_status = models.CharField(max_length=40, blank=True)
    failure_reason = models.CharField(max_length=120, blank=True)
    cost = models.CharField(max_length=20, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(
        null=True, blank=True, help_text="Queued: retry from then. Sending: the worker's lease runs out then."
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            # Africa's Talking retries a webhook it thinks we missed: one inbound row per provider message id
            models.UniqueConstraint(
                fields=["provider_id"],
                condition=models.Q(direction="in") & ~models.Q(provider_id=""),
                name="message_inbound_provider_id_unique",
            )
        ]

    def __str__(self):
        return f"{self.direction} {self.phone}: {self.body[:40]}"


class Template(models.Model):
    """Editable wording for every automated message, per language."""

    key = models.CharField(max_length=40)
    lang = models.CharField(max_length=2, default="en")
    body = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("key", "lang")]
        ordering = ["key", "lang"]

    def __str__(self):
        return f"{self.key} [{self.lang}]"


class Automation(models.Model):
    """The guest message timeline: what goes out, when, relative to the stay."""

    ANCHORS = [
        ("confirmed", "When booking is confirmed"),
        ("check_in", "Check-in date"),
        ("check_out", "Check-out date"),
    ]
    key = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)
    anchor = models.CharField(max_length=10, choices=ANCHORS)
    offset_days = models.SmallIntegerField(default=0, help_text="-1 = the day before")
    send_time = models.CharField(max_length=5, blank=True, help_text="HH:MM Kenya time; blank = immediately")
    template_key = models.CharField(max_length=40)
    channel = models.CharField(max_length=6, default="sms")
    enabled = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class FAQ(models.Model):
    """Knowledge base behind automatic answers on SMS, USSD, voice and the website."""

    CATEGORIES = [
        (c, c.replace("_", " ").capitalize())
        for c in (
            "booking",
            "pricing",
            "check_in",
            "breakfast",
            "wifi",
            "amenities",
            "transport",
            "area",
            "safety",
            "payment",
            "policies",
            "other",
        )
    ]
    category = models.CharField(max_length=12, choices=CATEGORIES, default="other")
    question = models.CharField(max_length=160)
    answer_en = models.TextField()
    answer_sw = models.TextField(blank=True)
    answer_fr = models.TextField(blank=True)
    answer_de = models.TextField(blank=True)
    keywords = models.CharField(max_length=400, help_text="Comma-separated trigger words (English and Kiswahili)")
    unit = models.ForeignKey("properties.Unit", null=True, blank=True, on_delete=models.CASCADE, related_name="faqs")
    active = models.BooleanField(default=True)
    hits = models.PositiveIntegerField(default=0)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "FAQ"

    def __str__(self):
        return self.question

    def answer(self, lang):
        return getattr(self, f"answer_{lang}", "") or self.answer_en


class Broadcast(models.Model):
    AUDIENCES = [
        ("in_house", "Guests staying now"),
        ("arriving", "Arriving in the next 7 days"),
        ("upcoming", "All upcoming guests"),
        ("past", "Past guests (opted in)"),
        ("waitlist", "Waitlist"),
        ("staff", "Staff"),
    ]
    audience = models.CharField(max_length=10, choices=AUDIENCES)
    unit = models.ForeignKey("properties.Unit", null=True, blank=True, on_delete=models.SET_NULL)
    body = models.TextField()
    is_marketing = models.BooleanField(default=False)
    recipients = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class Conversation(models.Model):
    """Per-phone SMS dialogue state (idle, collecting dates, showing options, awaiting payment…)."""

    phone = models.CharField(max_length=20, unique=True)
    state = models.CharField(max_length=20, default="idle")
    data = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
